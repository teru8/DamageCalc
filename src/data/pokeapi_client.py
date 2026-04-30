"""
PokeAPI client with SQLite caching.
Fetches species and move data on first run; subsequent runs use cache.
All network calls are done in a background thread via PokeApiLoader.
"""
import logging
import requests
import time
from typing import Any
from PyQt5.QtCore import QThread, pyqtSignal
from src.models import SpeciesInfo, MoveInfo
from src.data import database as db
from src.constants import POKEAPI_BASE

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "DamageCalc/0.1.0-alpha"


def _get(url: str, retries: int = 3) -> dict[str, Any]:
    for i in range(retries):
        try:
            r = _SESSION.get(url, timeout=10)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            if i < retries - 1:
                time.sleep(1)
            else:
                logging.warning("_fetch failed %s: %s", url, e)
    return {}


def _ja_name(names: list[dict[str, Any]]) -> str:
    for n in names:
        if n.get("language", {}).get("name") in ("ja-Hrkt", "ja"):
            return n["name"]
    return ""

_SPECIAL_FORM_NAME_MAP: dict[str, str] = {
    # ロトムのフォルム
    "rotom-heat": "ヒートロトム",
    "rotom-wash": "ウォッシュロトム",
    "rotom-frost": "フロストロトム",
    "rotom-fan": "スピンロトム",
    "rotom-mow": "カットロトム",
    # 原種で特殊な表示名を持つもの
    "deoxys-normal": "デオキシス（ノーマルフォルム）",
    "wormadam-plant": "ミノマダム（くさきのミノ）",
    "shaymin-land": "シェイミ（ランドフォルム）",
    "basculin-red-striped": "バスラオ（あかすじ）",
    "tornadus-incarnate": "トルネロス（けしんフォルム）",
    "thundurus-incarnate": "ボルトロス（けしんフォルム）",
    "landorus-incarnate": "ランドロス（けしんフォルム）",
    "keldeo-ordinary": "ケルディオ（いつものすがた）",
    "meowstic-male": "ニャオニクス（オスのすがた）",
    "pumpkaboo-average": "バケッチャ（ちゅうだましゅ）",
    "gourgeist-average": "パンプジン（ちゅうだましゅ）",
    "hoopa": "フーパ（いましめられしフーパ）",
    "oricorio-baile": "オドリドリ（めらめらスタイル）",
    "lycanroc-midday": "ルガルガン（まひるのすがた）",
    "toxtricity-amped": "ストリンダー（ハイなすがた）",
    "indeedee-male": "イエッサン（オスのすがた）",
    "urshifu-single-strike": "ウーラオス（いちげきのかた）",
    "basculegion-male": "イダイトウ（オスのすがた）",
    "enamorus-incarnate": "ラブトロス（けしんフォルム）",
    "oinkologne-male": "パフュートン（オスのすがた）",
    "ogerpon": "オーガポン（みどりのめん）",
    # 特殊フォーム
    "floette-eternal": "フラエッテ (えいえんのはな)",
    # サイズ違いのフォーム
    "pumpkaboo-small": "バケッチャ（こだましゅ）",
    "pumpkaboo-large": "バケッチャ（おおだましゅ）",
    "pumpkaboo-super": "バケッチャ（ギガだましゅ）",
    "gourgeist-small": "パンプジン（こだましゅ）",
    "gourgeist-large": "パンプジン（おおだましゅ）",
    "gourgeist-super": "パンプジン（ギガだましゅ）",
    # デオキシスのフォルム
    "deoxys-attack": "デオキシス（アタックフォルム）",
    "deoxys-defense": "デオキシス（ディフェンスフォルム）",
    "deoxys-speed": "デオキシス（スピードフォルム）",
    # ミノマダムのフォルム
    "wormadam-sandy": "ミノマダム（すなちのミノ）",
    "wormadam-trash": "ミノマダム（ゴミのミノ）",
    # シェイミのフォルム
    "shaymin-sky": "シェイミ（スカイフォルム）",
    # ギラティナのフォルム
    "giratina-origin": "ギラティナ（オリジンフォルム）",
    # バスラオのフォルム
    "basculin-blue-striped": "バスラオ（あおすじ）",
    "basculin-white-striped": "バスラオ（しろすじ）",
    # れいじゅうフォルム
    "tornadus-therian": "トルネロス（れいじゅうフォルム）",
    "thundurus-therian": "ボルトロス（れいじゅうフォルム）",
    "landorus-therian": "ランドロス（れいじゅうフォルム）",
    "enamorus-therian": "ラブトロス（れいじゅうフォルム）",
    # キュレムのフォルム
    "kyurem-black": "ブラックキュレム",
    "kyurem-white": "ホワイトキュレム",
    # ケルディオのフォルム
    "keldeo-resolute": "ケルディオ（かくごのすがた）",
    # オドリドリのフォルム
    "oricorio-pom-pom": "オドリドリ（ぱちぱちスタイル）",
    "oricorio-pau": "オドリドリ（ふらふらスタイル）",
    "oricorio-sensu": "オドリドリ（まいまいスタイル）",
    # ルガルガンのフォルム
    "lycanroc-midnight": "ルガルガン（まよなかのすがた）",
    "lycanroc-dusk": "ルガルガン（たそがれのすがた）",
    # ネクロズマのフォルム
    "necrozma-dusk": "ネクロズマ（たそがれのたてがみ）",
    "necrozma-dawn": "ネクロズマ（あかつきのつばさ）",
    "necrozma-dusk-mane": "ネクロズマ（たそがれのたてがみ）",
    "necrozma-dawn-wings": "ネクロズマ（あかつきのつばさ）",
    "necrozma-ultra": "ウルトラネクロズマ",
    # ザシアン/ザマゼンタのフォルム
    "zacian-crowned": "ザシアン（けんのおう）",
    "zamazenta-crowned": "ザマゼンタ（たてのおう）",
    # ウーラオスのフォルム
    "urshifu-rapid-strike": "ウーラオス（れんげきのかた）",
    # ストリンダーのフォルム
    "toxtricity-low-key": "ストリンダー（ローなすがた）",
    # オーガポンのフォルム
    "ogerpon-wellspring-mask": "オーガポン（いどのめん）",
    "ogerpon-hearthflame-mask": "オーガポン（かまどのめん）",
    "ogerpon-cornerstone-mask": "オーガポン（いしずえのめん）",
    # イダイトウのフォルム
    "basculegion-female": "イダイトウ（メスのすがた）",
    # パフュートンのフォルム
    "oinkologne-female": "パフュートン（メスのすがた）",
    # ニャオニクスのフォルム
    "meowstic-female": "ニャオニクス（メスのすがた）",
    # フーパのフォルム
    "hoopa-unbound": "フーパ（ときはなたれしフーパ）",
    # イエッサンのフォルム
    "indeedee-female": "イエッサン（メスのすがた）",
    # ディアルガ/パルキアのフォルム
    "dialga-origin": "ディアルガ（オリジンフォルム）",
    "palkia-origin": "パルキア（オリジンフォルム）",
    # リージョンフォーム（アローラ）
    "rattata-alola": "アローラコラッタ",
    "raticate-alola": "アローララッタ",
    "raichu-alola": "アローラライチュウ",
    "sandshrew-alola": "アローラサンド",
    "sandslash-alola": "アローラサンドパン",
    "vulpix-alola": "アローラロコン",
    "ninetales-alola": "アローラキュウコン",
    "diglett-alola": "アローラディグダ",
    "dugtrio-alola": "アローラダグトリオ",
    "meowth-alola": "アローラニャース",
    "persian-alola": "アローラペルシアン",
    "geodude-alola": "アローライシツブテ",
    "graveler-alola": "アローラゴローン",
    "golem-alola": "アローラゴローニャ",
    "grimer-alola": "アローラベトベター",
    "muk-alola": "アローラベトベトン",
    "exeggutor-alola": "アローラナッシー",
    "marowak-alola": "アローラガラガラ",
    # リージョンフォーム（ガラル）
    "meowth-galar": "ガラルニャース",
    "ponyta-galar": "ガラルポニータ",
    "rapidash-galar": "ガラルギャロップ",
    "slowpoke-galar": "ガラルヤドン",
    "slowbro-galar": "ガラルヤドラン",
    "farfetchd-galar": "ガラルカモネギ",
    "weezing-galar": "ガラルマタドガス",
    "mr-mime-galar": "ガラルバリヤード",
    "articuno-galar": "ガラルフリーザー",
    "zapdos-galar": "ガラルサンダー",
    "moltres-galar": "ガラルファイヤー",
    "slowking-galar": "ガラルヤドキング",
    "corsola-galar": "ガラルサニーゴ",
    "zigzagoon-galar": "ガラルジグザグマ",
    "linoone-galar": "ガラルマッスグマ",
    "darumaka-galar": "ガラルダルマッカ",
    "darmanitan-galar-standard": "ガラルヒヒダルマ",
    "yamask-galar": "ガラルデスマス",
    "stunfisk-galar": "ガラルマッギョ",
    # リージョンフォーム（ヒスイ）
    "growlithe-hisui": "ヒスイガーディ",
    "arcanine-hisui": "ヒスイウインディ",
    "voltorb-hisui": "ヒスイビリリダマ",
    "electrode-hisui": "ヒスイマルマイン",
    "typhlosion-hisui": "ヒスイバクフーン",
    "qwilfish-hisui": "ヒスイハリーセン",
    "sneasel-hisui": "ヒスイニューラ",
    "samurott-hisui": "ヒスイダイケンキ",
    "lilligant-hisui": "ヒシイドレディア",
    "zorua-hisui": "ヒスイゾロア",
    "zoroark-hisui": "ヒスイゾロアーク",
    "braviary-hisui": "ヒスイウォーグル",
    "sliggoo-hisui": "ヒスイヌメイル",
    "goodra-hisui": "ヒスイヌメルゴン",
    "avalugg-hisui": "ヒスイクレベース",
    "decidueye-hisui": "ヒスイジュナイパー",
    # リージョンフォーム（パルデア）
    "tauros-paldea-combat-breed": "パルデアケンタロス(格闘)",
    "tauros-paldea-blaze-breed": "パルデアケンタロス(炎)",
    "tauros-paldea-aqua-breed": "パルデアケンタロス(水)",
}


def _build_regional_name_ja(name_en: str, base_name_ja: str) -> str:
    """Build a Japanese regional form name like 'アローラキュウコン' from name_en and base name."""
    normalized = (name_en or "").lower()

    # Special out-of-battle forms with hardcoded Japanese names.
    if normalized in _SPECIAL_FORM_NAME_MAP:
        return _SPECIAL_FORM_NAME_MAP[normalized]

    return ""


def fetch_species(species_id: int) -> SpeciesInfo | None:
    cached = db.get_species_by_id(species_id)
    if cached and db.has_species_learnset(species_id):
        return cached

    poke = _get("{}/pokemon/{}".format(POKEAPI_BASE, species_id))
    if not poke:
        return None

    # For IDs >= 10000 (regional/alternate forms), pokemon-species uses the base species ID.
    # Resolve base species ID from the species URL in the poke data.
    is_form = species_id >= 10000
    spec = {}
    if is_form:
        species_url = poke.get("species", {}).get("url", "")
        if species_url:
            spec = _get(species_url)
    else:
        spec = _get("{}/pokemon-species/{}".format(POKEAPI_BASE, species_id))
    if not spec:
        return None

    stats = {s["stat"]["name"]: s["base_stat"] for s in poke.get("stats", [])}
    types_raw = sorted(poke.get("types", []), key=lambda x: x["slot"])
    type1 = types_raw[0]["type"]["name"] if len(types_raw) > 0 else "normal"
    type2 = types_raw[1]["type"]["name"] if len(types_raw) > 1 else ""

    # Apply special-form display names for both base species IDs and form IDs.
    # Example: deoxys-normal (species_id=386) should be "デオキシス（ノーマルフォルム）".
    base_name_ja = _ja_name(spec.get("names", []))
    name_en = poke.get("name", "")
    name_ja = _build_regional_name_ja(name_en, base_name_ja) or base_name_ja
    name_ja = db.normalize_species_name_ja(name_ja)

    if not name_ja:
        return None

    s = SpeciesInfo(
        species_id=species_id,
        name_ja=name_ja,
        name_en=name_en,
        type1=type1,
        type2=type2,
        base_hp=stats.get("hp", 0),
        base_attack=stats.get("attack", 0),
        base_defense=stats.get("defense", 0),
        base_sp_attack=stats.get("special-attack", 0),
        base_sp_defense=stats.get("special-defense", 0),
        base_speed=stats.get("speed", 0),
        weight_kg=(poke.get("weight") or 0) / 10.0,
    )
    db.upsert_species(s)
    move_ids: list[int] = []
    for move_entry in poke.get("moves", []):
        move_url = move_entry.get("move", {}).get("url", "")
        try:
            move_id = int(move_url.rstrip("/").split("/")[-1])
        except (ValueError, IndexError):
            continue
        move_ids.append(move_id)
    db.replace_species_learnset(species_id, move_ids)
    return s


def fetch_species_by_name_ja(name_ja: str) -> SpeciesInfo | None:
    cached = db.get_species_by_name_ja(name_ja)
    if cached:
        return cached
    # Cannot look up by Japanese name without scanning all species
    return None


def fetch_move(name_en_or_id: str | int) -> MoveInfo | None:
    if isinstance(name_en_or_id, int):
        cached = db.get_move_by_id(name_en_or_id)
        if cached:
            return cached
    data = _get(f"{POKEAPI_BASE}/move/{name_en_or_id}")
    if not data:
        return None

    names = data.get("names", [])
    name_ja = _ja_name(names)
    name_en = data.get("name", "")
    move_type = data.get("type", {}).get("name", "normal")
    damage_class = data.get("damage_class", {}).get("name", "physical")
    power = data.get("power") or 0
    accuracy = data.get("accuracy") or 100
    pp = data.get("pp") or 10
    priority = data.get("priority") or 0

    category_map = {
        "physical": "physical",
        "special": "special",
        "status": "status",
    }

    m = MoveInfo(
        name_ja=name_ja,
        name_en=name_en,
        type_name=move_type,
        category=category_map.get(damage_class, "physical"),
        power=power,
        accuracy=accuracy,
        pp=pp,
        priority=priority,
    )
    db.upsert_move(m, data["id"])
    return m


def fetch_move_by_name_ja(name_ja: str) -> MoveInfo | None:
    cached = db.get_move_by_name_ja(name_ja)
    if cached:
        return cached
    return None


# Regional/alternate form Pokemon IDs in PokeAPI (10000+ range).
# These are competitive-relevant forms that need separate species entries.
_REGIONAL_FORM_IDS = list(range(10000, 10278))

# Forms that should be hidden from UI (edit dialog, filter dialog, search results)
# These are still fetched from PokeAPI, but not shown to users
_HIDDEN_FORM_IDS: set[int] = set()
_HIDDEN_FORM_NAMES: set[str] = set()

# Pokemon where only base form should be shown (hide all alternate forms)
_BASE_ONLY_SPECIES: set[int] = {
    845,  # Cramorant (ウッウ)
    1008,  # Miraidon (ミライドン)
    1007,  # Koraidon (コライドン)
    778,  # Mimikyu (ミミッキュ)
    890,  # Eternatus (ムゲンダイナ)
    893,  # Zarude (ザルード)
    868,  # Alcremie (マホイップ)
    25,  # Pikachu (ピカチュウ)
    133,  # Eevee (イーブイ)
    585,  # Deerling (シキジカ)
    586,  # Sawsbuck (メブキジカ)
    676,  # Furfrou (トリミアン)
}

# Specific forms to hide by PokeAPI name
_SPECIFIC_HIDDEN_FORMS: set[str] = {
    "greninja-ash",  # サトシゲッコウガ
    # Gimmighoul
    "gimmighoul-roaming",  # コレクレー（とほフォルム）
    # Mega evolutions
    "venusaur-mega",  # メガフシギバナ
    "charizard-mega-x",  # メガリザードンX
    "charizard-mega-y",  # メガリザードンY
    "blastoise-mega",  # メガカメックス
    "alakazam-mega",  # メガフーディン
    "gengar-mega",  # メガゲンガー
    "kangaskhan-mega",  # メガガルーラ
    "pinsir-mega",  # メガカイロス
    "gyarados-mega",  # メガギャラドス
    "aerodactyl-mega",  # メガプテラ
    "mewtwo-mega-x",  # メガミュウツーX
    "mewtwo-mega-y",  # メガミュウツーY
    "ampharos-mega",  # メガデンリュウ
    "scizor-mega",  # メガハッサム
    "heracross-mega",  # メガヘラクロス
    "houndoom-mega",  # メガヘルガー
    "tyranitar-mega",  # メガバンギラス
    "blaziken-mega",  # メガバシャーモ
    "gardevoir-mega",  # メガサーナイト
    "mawile-mega",  # メガクチート
    "aggron-mega",  # メガボスゴドラ
    "medicham-mega",  # メガチャーレム
    "manectric-mega",  # メガライボルト
    "banette-mega",  # メガジュペッタ
    "absol-mega",  # メガアブソル
    "garchomp-mega",  # メガガブリアス
    "lucario-mega",  # メガルカリオ
    "abomasnow-mega",  # メガユキノオー
    "latias-mega",  # メガラティアス
    "latios-mega",  # メガラティオス
    "swampert-mega",  # メガラグラージ
    "sceptile-mega",  # メガジュカイン
    "sableye-mega",  # メガヤミラミ
    "altaria-mega",  # メガチルタリス
    "gallade-mega",  # メガエルレイド
    "audino-mega",  # メガタブンネ
    "sharpedo-mega",  # メガサメハダー
    "slowbro-mega",  # メガヤドラン
    "steelix-mega",  # メガハガネール
    "pidgeot-mega",  # メガピジョット
    "glalie-mega",  # メガオニゴーリ
    "diancie-mega",  # メガディアンシー
    "metagross-mega",  # メガメタグロス
    "camerupt-mega",  # メガバクーダ
    "lopunny-mega",  # メガミミロップ
    "salamence-mega",  # メガボーマンダ
    "beedrill-mega",  # メガスピアー
    # Primal forms
    "kyogre-primal",  # カイオーガ（ゲンシカイキ）
    "groudon-primal",  # グラードン（ゲンシカイキ）
    "rayquaza-mega",  # レックウザ（ゲンシカイキ）
    # Pikachu caps
    "pikachu-rock-star",  # ピカチュウ
    "pikachu-belle",  # ピカチュウ
    "pikachu-pop-star",  # ピカチュウ
    "pikachu-phd",  # ピカチュウ
    "pikachu-libre",  # ピカチュウ
    "pikachu-cosplay",  # ピカチュウ
    "pikachu-original-cap",  # オリジナルキャップ
    "pikachu-hoenn-cap",  # ホウエンキャップ
    "pikachu-sinnoh-cap",  # シンオウキャップ
    "pikachu-unova-cap",  # イッシュキャップ
    "pikachu-kalos-cap",  # カロスキャップ
    "pikachu-alola-cap",  # アローラピカチュウ
    "pikachu-starter",  # ピカチュウ
    "pikachu-world-cap",  # ワールドキャップ
    "pikachu-partner-cap",  # ピカチュウ
    # Eevee
    "eevee-starter",  # イーブイ
    # Greninja
    "greninja-battle-bond",  # ゲッコウガ（きずなへんげ）
    # Totem forms
    "raticate-totem-alola",  # アローララッタ（ぬし）
    "gumshoos-totem",  # デカグース（ぬし）
    "vikavolt-totem",  # クワガノン（ぬし）
    "lurantis-totem",  # ラランテス（ぬし）
    "salazzle-totem",  # エンニュート（ぬし）
    "mimikyu-totem-disguised",  # ミミッキュ（ぬし）
    "mimikyu-totem-busted",  # ミミッキュ（ぬし２）
    "kommo-o-totem",  # ジャラランガ（ぬし）
    "marowak-totem",  # ガラガラ（ぬし）
    "ribombee-totem",  # アブリボン（ぬし）
    "araquanid-totem",  # オニシズクモ（ぬし）
    "togedemaru-totem",  # トゲデマル（ぬし）
    # Minior forms
    "minior-orange-meteor",  # りゅうせいのすがた（だいだいいろのコア）
    "minior-yellow-meteor",  # りゅうせいのすがた（きいろのコア）
    "minior-green-meteor",  # りゅうせいのすがた（みどりいろのコア）
    "minior-blue-meteor",  # りゅうせいのすがた（みずいろのコア）
    "minior-indigo-meteor",  # りゅうせいのすがた（あおいろのコア）
    "minior-violet-meteor",  # りゅうせいのすがた（むらさきのコア）
    "minior-orange",  # コアのすがた（だいだいいろのコア）
    "minior-yellow",  # コアのすがた（きいろのコア）
    "minior-green",  # コアのすがた（みどりいろのコア）
    "minior-blue",  # コアのすがた（みずいろのコア）
    "minior-indigo",  # コアのすがた（あおいろのコア）
    "minior-violet",  # コアのすがた（むらさきのコア）
    # Mimikyu
    "mimikyu-busted",  # ミミッキュ（ばれたすがた）
    # Magearna
    "magearna-original",  # マギアナ
    # Rockruff
    "rockruff-own-tempo",  # イワンコ（マイペース）
    # Zygarde
    "zygarde-10",  # ジガルデ（10%フォルム）
    # Cramorant
    "cramorant-gulping",  # ウッウ（うのみのすがた）
    "cramorant-gorging",  # ウッウ（まるのみのすがた）
    # Zarude
    "zarude-dada",  # ザルード（とうちゃん）
    # Gigantamax forms
    "venusaur-gmax",  # キョダイマックスのすがた
    "charizard-gmax",  # キョダイマックスのすがた
    "blastoise-gmax",  # キョダイマックスのすがた
    "butterfree-gmax",  # キョダイマックスのすがた
    "pikachu-gmax",  # キョダイマックスのすがた
    "meowth-gmax",  # キョダイマックスのすがた
    "machamp-gmax",  # キョダイマックスのすがた
    "gengar-gmax",  # キョダイマックスのすがた
    "kingler-gmax",  # キョダイマックスのすがた
    "lapras-gmax",  # キョダイマックスのすがた
    "eevee-gmax",  # キョダイマックスのすがた
    "snorlax-gmax",  # キョダイマックスのすがた
    "garbodor-gmax",  # キョダイマックスのすがた
    "melmetal-gmax",  # キョダイマックスのすがた
    "rillaboom-gmax",  # キョダイマックスのすがた
    "cinderace-gmax",  # キョダイマックスのすがた
    "inteleon-gmax",  # キョダイマックスのすがた
    "corviknight-gmax",  # キョダイマックスのすがた
    "orbeetle-gmax",  # キョダイマックスのすがた
    "drednaw-gmax",  # キョダイマックスのすがた
    "coalossal-gmax",  # キョダイマックスのすがた
    "flapple-gmax",  # キョダイマックスのすがた
    "appletun-gmax",  # キョダイマックスのすがた
    "sandaconda-gmax",  # キョダイマックスのすがた
    "toxtricity-amped-gmax",  # ハイなすがた・キョダイマックスのすがた
    "centiskorch-gmax",  # キョダイマックスのすがた
    "hatterene-gmax",  # キョダイマックスのすがた
    "grimmsnarl-gmax",  # キョダイマックスのすがた
    "alcremie-gmax",  # キョダイマックスのすがた
    "copperajah-gmax",  # キョダイマックスのすがた
    "duraludon-gmax",  # キョダイマックスのすがた
    "urshifu-single-strike-gmax",  # いちげきのかた・キョダイマックスのすがた
    "urshifu-rapid-strike-gmax",  # れんげきのかた・キョダイマックスのすがた
    "toxtricity-low-key-gmax",  # ローなすがた・キョダイマックスのすがた
    "eternatus-eternamax",  # ムゲンダイナ（ムゲンダイマックス）
    # Dudunsparce
    "dudunsparce-three-segment",  # ノココッチ（みつふしフォルム）
    # Maushold
    "maushold-family-of-three",  # イッカネズミ（３びきかぞく）
    # Tatsugiri
    "tatsugiri-droopy",  # シャリタツ（たれたすがた）
    "tatsugiri-stretchy",  # シャリタツ（のびたすがた）
    # Squawkabilly
    "squawkabilly-blue-plumage",  # イキリンコ（ブルーフェザー）
    "squawkabilly-yellow-plumage",  # イキリンコ（イエローフェザー）
    "squawkabilly-white-plumage",  # イキリンコ（ホワイトフェザー）
    # Koraidon/Miraidon forms
    "koraidon-limited-build",  # せいげんけいたい
    "koraidon-sprinting-build",  # しっそうけいたい
    "koraidon-swimming-build",  # ゆうえいけいたい
    "koraidon-gliding-build",  # かっくうけいたい
    "miraidon-low-power-mode",  # リミテッドモード
    "miraidon-drive-mode",  # ドライブモード
    "miraidon-aquatic-mode",  # フロートモード
    "miraidon-glide-mode",  # グライドモード
    # Battle-only forms (show only base form in picker/filter)
    "castform-sunny",  # ポワルン（たいようのすがた）
    "castform-rainy",  # ポワルン（あまみずのすがた）
    "castform-snowy",  # ポワルン（ゆきぐものすがた）
    "darmanitan-zen",  # ヒヒダルマ（ダルマモード）
    "meloetta-pirouette",  # メロエッタ（ステップフォルム）
    "aegislash-blade",  # ギルガルド（ブレードフォルム）
    "zygarde-10-power-construct",  # ジガルデ（10%フォルム）
    "zygarde-50-power-construct",  # ジガルデ（50%フォルム）
    "zygarde-complete",  # ジガルデ（パーフェクトフォルム）
    "wishiwashi-school",  # ヨワシ（むれたすがた）
    "minior-red",  # メテノ（コアのすがた）
    "darmanitan-galar-zen",  # ガラルヒヒダルマ（ダルマモード）
    "eiscue-noice",  # コオリッポ（ナイスフェイス）
    "morpeko-hangry",  # モルペコ（はらぺこもよう）
    "palafin-hero",  # イルカマン（マイティフォルム）
    "terapagos-terastal",  # テラパゴス（テラスタルフォルム）
    "terapagos-stellar",  # テラパゴス（ステラフォルム）
}

# Minior: only show red core and its meteor form, hide other colors
_MINIOR_HIDDEN_COLORS = {"orange", "yellow", "green", "blue", "indigo", "violet"}


def is_form_hidden(species_id: int, name_en: str) -> bool:
    """Check if a form should be hidden from UI."""
    # Check if it's a specific hidden form
    if name_en.lower() in _SPECIFIC_HIDDEN_FORMS:
        return True
    
    # Check if it's a Minior form with hidden color
    if species_id == 774:  # Minior
        if name_en.lower().startswith("minior-"):
            for color in _MINIOR_HIDDEN_COLORS:
                if f"-{color}-" in name_en.lower() or name_en.lower().endswith(f"-{color}"):
                    return True
    
    # Check if it's a form of a base-only species
    # For base-only species, we need to know the base species ID
    # We'll create a mapping of form names to base species IDs
    _FORM_TO_BASE_SPECIES: dict[str, int] = {
        # Wugtrio forms
        "wugtrio": 876,
        # Miraidon forms
        "miraidon-low-power-mode": 1008,
        "miraidon-drive-mode": 1008,
        "miraidon-aquatic-mode": 1008,
        "miraidon-glide-mode": 1008,
        # Koraidon forms
        "koraidon-limited-build": 1007,
        "koraidon-sprinting-build": 1007,
        "koraidon-swimming-build": 1007,
        "koraidon-gliding-build": 1007,
        # Mimikyu forms
        "mimikyu-busted": 778,
        # Eternatus forms
        "eternatus-eternamax": 890,
        # Zarude forms
        "zarude-dada": 893,
        # Alcremie forms (many forms, all hidden except base)
        # Pikachu forms (many forms, all hidden except base)
        # Eevee forms (all evolutions are separate species, not forms)
        # Deerling forms (season forms)
        "deerling-spring": 585,
        "deerling-summer": 585,
        "deerling-autumn": 585,
        "deerling-winter": 585,
        # Sawsbuck forms (season forms)
        "sawsbuck-spring": 586,
        "sawsbuck-summer": 586,
        "sawsbuck-autumn": 586,
        "sawsbuck-winter": 586,
        # Furfrou forms (trim forms)
        "furfrou-heart": 676,
        "furfrou-star": 676,
        "furfrou-diamond": 676,
        "furfrou-deputante": 676,
        "furfrou-dandy": 676,
        "furfrou-la-reine": 676,
        "furfrou-kabuki": 676,
        "furfrou-pharaoh": 676,
        "furfrou-matron": 676,
    }
    
    base_species_id = _FORM_TO_BASE_SPECIES.get(name_en.lower())
    if base_species_id in _BASE_ONLY_SPECIES:
        return True
    
    return False


class PokeApiLoader(QThread):
    """
    Background thread that pre-fetches common Pokemon and move data.
    Emits progress updates so the UI can show a loading bar.
    """
    progress = pyqtSignal(int, str)   # (percent, message)
    finished = pyqtSignal()

    MAX_SPECIES = 1025
    MAX_MOVE_ID = 920   # fetch move IDs 1..920
    MIN_MOVES = 500     # skip move loading if this many are already cached

    def run(self) -> None:
        self.progress.emit(0, "PokeAPIからデータ取得中...")
        with db.connection() as conn:
            species_count = conn.execute(
                "SELECT COUNT(*) FROM species_cache").fetchone()[0]
            learnset_species_count = conn.execute(
                "SELECT COUNT(DISTINCT species_id) FROM species_move_cache"
            ).fetchone()[0]
            move_count = conn.execute(
                "SELECT COUNT(*) FROM move_cache WHERE name_ja IS NOT NULL AND name_ja != ''"
            ).fetchone()[0]
            regional_count = conn.execute(
                "SELECT COUNT(*) FROM species_cache WHERE species_id >= 10000"
            ).fetchone()[0]

        needs_base = species_count < self.MAX_SPECIES or learnset_species_count < self.MAX_SPECIES
        # Check if any specific form ID is missing from cache (handles newly added IDs).
        cached_form_ids: set[int] = set()
        if regional_count > 0:
            with db.connection() as conn:
                rows = conn.execute(
                    "SELECT species_id FROM species_cache WHERE species_id >= 10000"
                ).fetchall()
            cached_form_ids = {row[0] for row in rows}
        # Also check that key forms have the correct name_ja (stale entries with wrong names
        # won't be re-fetched by ID-presence check alone).
        _EXPECTED_FORM_NAMES: dict[int, str] = {
            10008: "ヒートロトム",
            10009: "ウォッシュロトム",
            10010: "フロストロトム",
            10011: "スピンロトム",
            10012: "カットロトム",
            10027: "バケッチャ（こだましゅ）",
            10028: "バケッチャ（おおだましゅ）",
            10029: "バケッチャ（ギガだましゅ）",
            10030: "パンプジン（こだましゅ）",
            10031: "パンプジン（おおだましゅ）",
            10032: "パンプジン（ギガだましゅ）",
            10061: "フラエッテ (えいえんのはな)",
            902: "イダイトウ（オスのすがた）",
            10248: "イダイトウ（メスのすがた）",
            10250: "パルデアケンタロス(格闘)",
            10251: "パルデアケンタロス(炎)",
            10252: "パルデアケンタロス(水)",
            # Additional competitive forms
            10001: "デオキシス（アタックフォルム）",
            10002: "デオキシス（ディフェンスフォルム）",
            10003: "デオキシス（スピードフォルム）",
            10004: "ミノマダム（すなちのミノ）",
            10005: "ミノマダム（ゴミのミノ）",
            10006: "シェイミ（スカイフォルム）",
            10007: "ギラティナ（オリジンフォルム）",
            10015: "バスラオ（あおすじ）",
            10016: "バスラオ（しろすじ）",
            10019: "トルネロス（れいじゅうフォルム）",
            10020: "ボルトロス（れいじゅうフォルム）",
            10021: "ランドロス（れいじゅうフォルム）",
            10022: "ブラックキュレム",
            10023: "ホワイトキュレム",
            10024: "ケルディオ（かくごのすがた）",
            10025: "ニャオニクス（メスのすがた）",
            10026: "ブレードフォルムギルガルド",
            678: "ニャオニクス（オスのすがた）",
            10086: "フーパ（ときはなたれしフーパ）",
            10123: "オドリドリ（ぱちぱちスタイル）",
            10124: "オドリドリ（ふらふらスタイル）",
            10125: "オドリドリ（まいまいスタイル）",
            10126: "ルガルガン（まよなかのすがた）",
            10152: "ルガルガン（たそがれのすがた）",
            10184: "ストリンダー（ローなすがた）",
            10186: "イッカネズミ♀",
            10191: "ウーラオス（れんげきのかた）",
            10247: "バスラオ（しろすじ）",
            10248: "イダイトウ（メスのすがた）",
            10249: "ラブトロス（れいじゅうフォルム）",
            10254: "パフュートン（メスのすがた）",
            10272: "あかつきのつきウルサルナ",
            10273: "オーガポン（いどのめん）",
            10274: "オーガポン（かまどのめん）",
            10275: "オーガポン（いしずえのめん）",
            10276: "テラスタルテラパゴス",
            10277: "ステラテラパゴス",
            # Base species display names
            386: "デオキシス（ノーマルフォルム）",
            413: "ミノマダム（くさきのミノ）",
            492: "シェイミ（ランドフォルム）",
            550: "バスラオ（あかすじ）",
            641: "トルネロス（けしんフォルム）",
            642: "ボルトロス（けしんフォルム）",
            645: "ランドロス（けしんフォルム）",
            647: "ケルディオ（いつものすがた）",
            678: "ニャオニクス（オスのすがた）",
            710: "バケッチャ（ちゅうだましゅ）",
            711: "パンプジン（ちゅうだましゅ）",
            720: "フーパ（いましめられしフーパ）",
            741: "オドリドリ（めらめらスタイル）",
            745: "ルガルガン（まひるのすがた）",
            849: "ストリンダー（ハイなすがた）",
            876: "イエッサン（オスのすがた）",
            892: "ウーラオス（いちげきのかた）",
            902: "イダイトウ（オスのすがた）",
            905: "ラブトロス（けしんフォルム）",
            916: "パフュートン（オスのすがた）",
            1017: "オーガポン（みどりのめん）",
            # Updated form names
            10155: "ネクロズマ（たそがれのたてがみ）",
            10156: "ネクロズマ（あかつきのつばさ）",
            10157: "ウルトラネクロズマ",
            10188: "ザシアン（けんのおう）",
            10189: "ザマゼンタ（たてのおう）",
            10193: "バドレックス（はくばじょうのすがた）",
            10194: "バドレックス（こくばじょうのすがた）",
            10245: "ディアルガ（オリジンフォルム）",
            10246: "パルキア（オリジンフォルム）",
            10272: "ガチグマ（アカツキ）",
            10091: "アローラコラッタ",
            10092: "アローララッタ",
            10100: "アローラライチュウ",
            10101: "アローラサンド",
            10102: "アローラサンドパン",
            10103: "アローラロコン",
            10104: "アローラキュウコン",
            10105: "アローラディグダ",
            10106: "アローラダグトリオ",
            10107: "アローラニャース",
            10108: "アローラペルシアン",
            10109: "アローライシツブテ",
            10110: "アローラゴローン",
            10111: "アローラゴローニャ",
            10112: "アローラベトベター",
            10113: "アローラベトベトン",
            10114: "アローラナッシー",
            10115: "アローラガラガラ",
            # Regional forms (Galar)
            10161: "ガラルニャース",
            10162: "ガラルポニータ",
            10163: "ガラルギャロップ",
            10164: "ガラルヤドン",
            10165: "ガラルヤドラン",
            10166: "ガラルカモネギ",
            10167: "ガラルマタドガス",
            10168: "ガラルバリヤード",
            10169: "ガラルフリーザー",
            10170: "ガラルサンダー",
            10171: "ガラルファイヤー",
            10172: "ガラルヤドキング",
            10173: "ガラルサニーゴ",
            10174: "ガラルジグザグマ",
            10175: "ガラルマッスグマ",
            10176: "ガラルダルマッカ",
            10177: "ガラルヒヒダルマ",
            10179: "ガラルデスマス",
            10180: "ガラルマッギョ",
            # Regional forms (Hisui)
            10229: "ヒスイガーディ",
            10230: "ヒスイウインディ",
            10231: "ヒスイビリリダマ",
            10232: "ヒスイマルマイン",
            10233: "ヒスイバクフーン",
            10234: "ヒスイハリーセン",
            10235: "ヒスイニューラ",
            10236: "ヒスイダイケンキ",
            10237: "ヒスイドレディア",
            10238: "ヒスイゾロア",
            10239: "ヒスイゾロアーク",
            10240: "ヒスイウォーグル",
            10241: "ヒスイヌメイル",
            10242: "ヒスイヌメルゴン",
            10243: "ヒスイクレベース",
            10244: "ヒスイジュナイパー",
            # Regional forms (Paldea)
            10253: "パルデアウパー",
        }
        stale_ids = []
        with db.connection() as conn:
            for fid, expected_name in _EXPECTED_FORM_NAMES.items():
                row = conn.execute(
                    "SELECT name_ja FROM species_cache WHERE species_id=?", (fid,)
                ).fetchone()
                actual_name = db.normalize_species_name_ja(row[0]) if row else ""
                if not row or actual_name != db.normalize_species_name_ja(expected_name):
                    stale_ids.append(fid)
            if stale_ids:
                # Delete stale entries (both species and learnset) so fetch_species
                # won't short-circuit on the cached-ID check.
                placeholders = ",".join("?" * len(stale_ids))
                conn.execute(
                    "DELETE FROM species_cache WHERE species_id IN ({})".format(placeholders),
                    stale_ids,
                )
                conn.execute(
                    "DELETE FROM species_move_cache WHERE species_id IN ({})".format(placeholders),
                    stale_ids,
                )
                conn.commit()
        needs_regional = any(fid not in cached_form_ids for fid in _REGIONAL_FORM_IDS) or bool(stale_ids)
        needs_moves = move_count < self.MIN_MOVES

        if not needs_base and not needs_regional and not needs_moves:
            self.progress.emit(100, "データ読み込み完了")
            self.finished.emit()
            return

        # Phase 1: base species + learnset (IDs 1-1025)
        if needs_base:
            total = self.MAX_SPECIES
            for i in range(1, total + 1):
                if db.get_species_by_id(i) and db.has_species_learnset(i):
                    self.progress.emit(int(i / total * 50),
                                       "キャッシュ済み: {}/{}".format(i, total))
                    continue
                fetch_species(i)
                self.progress.emit(int(i / total * 50),
                                   "種族/learnset取得中: {}/{}".format(i, total))

        # Phase 2: regional/alternate forms (alola, galar, hisui, paldea etc.)
        if needs_regional:
            total = len(_REGIONAL_FORM_IDS)
            for idx, form_id in enumerate(_REGIONAL_FORM_IDS):
                if db.get_species_by_id(form_id):
                    self.progress.emit(50 + int(idx / total * 25),
                                       "リージョンフォームキャッシュ済み: {}".format(form_id))
                    continue
                fetch_species(form_id)
                self.progress.emit(50 + int(idx / total * 25),
                                   "リージョンフォーム取得中: {}".format(form_id))

        # Phase 3: moves (fetch_move checks cache by ID internally)
        if needs_moves:
            total = self.MAX_MOVE_ID
            for i in range(1, total + 1):
                fetch_move(i)
                self.progress.emit(75 + int(i / total * 25),
                                   "技データ取得中: {}/{}".format(i, total))

        self.progress.emit(100, "データ読み込み完了")
        self.finished.emit()
