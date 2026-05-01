from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models import PokemonInstance, MoveInfo

# English ability name → Japanese (for note text generation)
_ABILITY_EN_TO_JA: dict[str, str] = {
    "Levitate": "ふゆう", "Earth Eater": "どしょく",
    "Flash Fire": "もらいび", "Well-Baked Body": "こんがりボディ",
    "Dry Skin": "かんそうはだ", "Water Absorb": "ちょすい", "Storm Drain": "よびみず",
    "Volt Absorb": "ちくでん", "Lightning Rod": "ひらいしん", "Motor Drive": "でんきエンジン",
    "Sap Sipper": "そうしょく",
    "Queenly Majesty": "じょおうのいげん", "Armor Tail": "テイルアーマー", "Dazzling": "ビビッドボディ",
    "Soundproof": "ぼうおん", "Bulletproof": "ぼうだん", "Wind Rider": "かぜのり",
    "Wonder Guard": "ふしぎなまもり", "Damp": "しめりけ",
}


def _ability_ja(ability: str) -> str:
    return _ABILITY_EN_TO_JA.get(ability, ability)


from src.constants import (
    BITE_MOVES_JA,
    PULSE_MOVES_JA,
    PUNCHING_MOVES_JA,
    RECKLESS_MOVES_JA,
    SHEER_FORCE_MOVES_JA,
    SLICING_MOVES_JA,
    SOUND_MOVES_JA,
)

_SOLAR_MOVES_JA: frozenset[str] = frozenset({"ソーラービーム", "ソーラーブレード"})

# Mega stone → species name fragment (partial match used since forms vary)
# Only the correct species cannot have their mega stone knocked off.
_MEGA_STONE_SPECIES: dict[str, str] = {
    "フシギバナイト": "フシギバナ", "リザードナイトX": "リザードン", "リザードナイトY": "リザードン", "カメックスナイト": "カメックス", "スピアナイト": "スピアー",
    "ピジョットナイト": "ピジョット", "ライチュウナイトX": "ライチュウ", "ライチュウナイトY": "ライチュウ", "ピクシナイト": "ピクシー", "フーディナイト": "フーディン",
    "ウツボットナイト": "ウツボット", "ヤドランナイト": "ヤドラン", "ゲンガナイト": "ゲンガー", "ガルーラナイト": "ガルーラ", "スターミナイト": "スターミー",
    "カイロスナイト": "カイロス", "ギャラドスナイト": "ギャラドス", "プテラナイト": "プテラ", "カイリュナイト": "カイリュー", "ミュウツナイトX": "ミュウツー",
    "ミュウツナイトY": "ミュウツー", "メガニウムナイト": "メガニウム", "オーダイルナイト": "オーダイル", "デンリュウナイト": "デンリュウ", "ハガネールナイト": "ハガネール",
    "ハッサムナイト": "ハッサム", "ヘラクロスナイト": "ヘラクロス", "エアームドナイト": "エアームド", "ヘルガナイト": "ヘルガー", "バンギラスナイト": "バンギラス",
    "ジュカインナイト": "ジュカイン", "バシャーモナイト": "バシャーモ", "ラグラージナイト": "ラグラージ", "サーナイトナイト": "サーナイト", "ヤミラミナイト": "ヤミラミ",
    "クチートナイト": "クチート", "ボスゴドラナイト": "ボスゴドラ", "チャーレムナイト": "チャーレム", "ライボルトナイト": "ライボルト", "サメハダナイト": "サメハダー",
    "バクーダナイト": "バクーダ", "チルタリスナイト": "チルタリス", "ジュペッタナイト": "ジュペッタ", "チリーンナイト": "チリーン", "アブソルナイト": "アブソル",
    "アブソルナイトZ": "アブソル", "オニゴーリナイト": "オニゴーリ", "ボーマンダナイト": "ボーマンダ", "メタグロスナイト": "メタグロス", "ラティアスナイト": "ラティアス",
    "ラティオスナイト": "ラティオス", "ムクホークナイト": "ムクホーク", "ミミロップナイト": "ミミロップ", "ガブリアスナイト": "ガブリアス", "ガブリアスナイトZ": "ガブリアス",
    "ルカリオナイト": "ルカリオ", "ルカリオナイトZ": "ルカリオ", "ユキノオナイト": "ユキノオー", "エルレイドナイト": "エルレイド", "ユキメノコナイト": "ユキメノコ",
    "ヒードラナイト": "ヒードラン", "ダークライナイト": "ダークライ", "エンブオナイト": "エンブオー", "ドリュウズナイト": "ドリュウズ", "タブンネナイト": "タブンネ",
    "ペンドラナイト": "ペンドラー", "ズルズキナイト": "ズルズキン", "シビルドナイト": "シビルドン", "シャンデラナイト": "シャンデラ", "ゴルーグナイト": "ゴルーグ",
    "ブリガロナイト": "ブリガロン", "マフォクシナイト": "マフォクシー", "ゲッコウガナイト": "ゲッコウガ", "カエンジシナイト": "カエンジシ", "フラエッテナイト": "フラエッテ",
    "ニャオニクスナイト": "ニャオニクス", "カラマネナイト": "カラマネロ", "ガメノデスナイト": "ガメノデス", "ドラミドナイト": "ドラミドロ", "ルチャブルナイト": "ルチャブル",
    "ジガルデナイト": "ジガルデ", "ディアンシナイト": "ディアンシー", "ケケンカニナイト": "ケケンカニ", "グソクムシャナイト": "グソクムシャ", "ジジーロナイト": "ジジーロン",
    "マギアナイト": "マギアナ", "ゼラオラナイト": "ゼラオラ", "タイレーツナイト": "タイレーツ", "スコヴィラナイト": "スコヴィラン", "キラフロルナイト": "キラフロル",
    "シャリタツナイト": "シャリタツ", "セグレイブナイト": "セグレイブ",
}
_Z_CRYSTALS: frozenset[str] = frozenset()

_SPECIES_PROTECTED_ITEM: dict[str, str] = {
    "ディアルガ": "だいこんごうだま",
    "パルキア": "だいしらたま",
    "ギラティナ": "だいはっきんだま",
    "カイオーガ": "あいいろのたま",
    "グラードン": "べにいろのたま",
    "ザシアン": "くちたけん",
    "ザマゼンタ": "くちたたて",
}
_GENESECT_CASSETTES: frozenset[str] = frozenset({
    "アクアカセット", "イナズマカセット", "ブレイズカセット", "フリーズカセット",
})
_MEMORY_ITEMS: frozenset[str] = frozenset({
    "ファイヤーメモリ", "ウォーターメモリ", "エレクトロメモリ", "グラスメモリ",
    "アイスメモリ", "ファイトメモリ", "ポイズンメモリ", "グラウンドメモリ",
    "フライングメモリ", "サイキックメモリ", "バグメモリ", "ロックメモリ",
    "ゴーストメモリ", "ドラゴンメモリ", "ダークメモリ", "スチールメモリ", "フェアリーメモリ",
})
_ORICHALCUM_MASKS: frozenset[str] = frozenset({
    "いどのめん", "かまどのめん", "いしずえのめん",
})
_BOOST_ENERGY_EXCLUDED_SPECIES: frozenset[str] = frozenset({
    "ウガツホムラ", "タケルライコ", "テツノイワオ", "テツノカシラ",
})
_PARADOX_BOOST_ABILITIES: frozenset[str] = frozenset({
    "こだいかっせい", "Ancient Power", "クォークチャージ", "Quark Drive",
})


def _is_knock_off_protected(defender_name_ja: str, defender_item: str, defender_ability: str) -> bool:
    """Returns True if defender's item cannot be knocked off (no ×1.5 bonus)."""
    if not defender_item:
        return True
    # Mega stone: protected only when held by the corresponding species
    required_species = _MEGA_STONE_SPECIES.get(defender_item, "")
    if required_species and required_species in defender_name_ja:
        return True
    if defender_item in _Z_CRYSTALS:
        return True
    expected = _SPECIES_PROTECTED_ITEM.get(defender_name_ja, "")
    if expected and expected == defender_item:
        return True
    if defender_item in _GENESECT_CASSETTES and "ゲノセクト" in defender_name_ja:
        return True
    if defender_item in _MEMORY_ITEMS and defender_ability in ("ARシステム", "RKS System"):
        return True
    if defender_item in _ORICHALCUM_MASKS and "オーガポン" in defender_name_ja:
        return True
    if (
        defender_item == "ブーストエナジー"
        and defender_ability in _PARADOX_BOOST_ABILITIES
        and defender_name_ja not in _BOOST_ENERGY_EXCLUDED_SPECIES
    ):
        return True
    if "プレート" in defender_item and defender_ability in ("マルチタイプ", "Multitype"):
        return True
    return False

# タイプ強化アイテム（×1.2）item → type ― ITEMS_JA 収録分のみ
_TYPE_BOOST_ITEMS: dict[str, str] = {
    "シルクのスカーフ": "normal", "もくたん": "fire", "しんぴのしずく": "water",
    "きせきのタネ": "grass", "するどいくちばし": "flying", "ぎんのこな": "bug",
    "とけないこおり": "ice", "まがったスプーン": "psychic", "じしゃく": "electric",
    "やわらかいすな": "ground", "メタルコート": "steel", "くろおび": "fighting",
    "どくバリ": "poison", "くろいメガネ": "dark", "のろいのおふだ": "ghost",
    "かたいいし": "rock", "りゅうのキバ": "dragon", "ようせいのハネ": "fairy",
}

# 半減きのみ（×0.5、こうかばつぐん被弾時）item → type ― ITEMS_JA 収録分のみ
_RESIST_BERRIES: dict[str, str] = {
    "オッカのみ": "fire", "イトケのみ": "water", "ソクノのみ": "electric",
    "リンドのみ": "grass", "ヤチェのみ": "ice", "ヨプのみ": "fighting",
    "ビアーのみ": "poison", "シュカのみ": "ground", "バコウのみ": "flying",
    "ウタンのみ": "psychic", "タンガのみ": "bug", "ヨロギのみ": "rock",
    "カシブのみ": "ghost", "ハバンのみ": "dragon", "ナモのみ": "dark",
    "リリバのみ": "steel", "ホズのみ": "normal", "ロゼルのみ": "fairy",
}


def add_unique_note(notes: list[str] | None, text: str) -> None:
    if notes is None:
        return
    if text and text not in notes:
        notes.append(text)


def apply_note_rule(
    rule: str,
    notes: list[str] | None,
    *,
    is_poisoned: bool = False,
    is_contact_move: bool = False,
    is_grounded: bool = False,
    **ctx,
) -> bool:
    text = ""
    ok = False

    # ── ×1.5（アイテム）──────────────────────────────────────────────────
    if rule == "choice_band":
        ok = bool(ctx.get("attacker_item") in ("こだわりハチマキ",) and ctx.get("uses_attacker_physical_attack"))
        text = "こだわりハチマキ ×1.5"
    elif rule == "choice_specs":
        ok = bool(ctx.get("attacker_item") in ("こだわりメガネ",) and ctx.get("uses_attacker_special_attack"))
        text = "こだわりメガネ ×1.5"

    # ── ×1.3（アイテム）──────────────────────────────────────────────────
    elif rule == "life_orb":
        ok = bool(ctx.get("attacker_item") == "いのちのたま")
        text = "いのちのたま ×1.3"

    # ── ×1.2（アイテム・SE時）────────────────────────────────────────────
    elif rule == "expert_belt":
        ok = bool(ctx.get("attacker_item") == "たつじんのおび" and ctx.get("type_eff", 1.0) > 1.0)
        text = "たつじんのおび ×1.2"
    elif rule == "type_boost_item":
        item = ctx.get("attacker_item", "")
        ok = bool(item and _TYPE_BOOST_ITEMS.get(item) == ctx.get("effective_type"))
        text = f"{item} ×1.2"

    # ── ×1.1（アイテム）──────────────────────────────────────────────────
    elif rule == "wise_glasses":
        ok = bool(ctx.get("attacker_item") == "ものしりメガネ" and ctx.get("effective_category") == "special")
        text = "ものしりメガネ ×1.1"
    elif rule == "muscle_band":
        ok = bool(ctx.get("attacker_item") == "ちからのハチマキ" and ctx.get("effective_category") == "physical")
        text = "ちからのハチマキ ×1.1"

    # ── ×0.5（きのみ）────────────────────────────────────────────────────
    elif rule == "resist_berry":
        item = ctx.get("defender_item", "")
        berry_type = _RESIST_BERRIES.get(item, "")
        ok = bool(berry_type and berry_type == ctx.get("effective_type") and ctx.get("type_eff", 1.0) >= 2.0)
        text = f"{item} ×0.5"

    # ── ×2.0（とくせい）──────────────────────────────────────────────────
    elif rule == "water_bubble_atk":
        ok = bool(ctx["attacker"].ability in ("すいほう", "Water Bubble") and ctx["effective_type"] == "water")
        text = "すいほう ×2.0"
    elif rule == "stakeout":
        ok = bool(ctx["attacker"].ability in ("はりこみ", "Stakeout") and ctx["stakeout_active"])
        text = "はりこみ ×2.0"

    # ── ×1.5 ──────────────────────────────────────────────────────────────
    elif rule == "technician":
        ok = bool(ctx["attacker"].ability == "テクニシャン" and 0 < ctx["power"] <= 60)
        text = "テクニシャン ×1.5"
    elif rule == "toxic_boost":
        ok = bool(
            ctx["attacker"].ability in ("どくぼうそう", "Toxic Boost")
            and is_poisoned
            and ctx["effective_category"] == "physical"
        )
        text = "どくぼうそう ×1.5"
    elif rule == "mega_launcher":
        ok = bool(ctx["attacker"].ability in ("メガランチャー", "Mega Launcher") and ctx["move"].name_ja in PULSE_MOVES_JA)
        text = "メガランチャー ×1.5"
    elif rule == "strong_jaw":
        ok = bool(ctx["attacker"].ability in ("がんじょうあご", "Strong Jaw") and ctx["move"].name_ja in BITE_MOVES_JA)
        text = "がんじょうあご ×1.5"
    elif rule == "dragons_maw":
        ok = bool(ctx["attacker"].ability in ("りゅうのあぎと", "Dragon's Maw") and ctx["effective_type"] == "dragon")
        text = "りゅうのあぎと ×1.5"
    elif rule == "rocky_payload":
        ok = bool(ctx["attacker"].ability in ("いわはこび", "Rocky Payload") and ctx["effective_type"] == "rock")
        text = "いわはこび ×1.5"
    elif rule == "steely_spirit":
        ok = bool(ctx["attacker"].ability in ("はがねのせいしん", "Steely Spirit") and ctx["effective_type"] == "steel")
        text = "はがねのせいしん ×1.5"
    elif rule == "steelworker":
        ok = bool(ctx["attacker"].ability in ("はがねつかい", "Steelworker") and ctx["effective_type"] == "steel")
        text = "はがねつかい ×1.5"
    elif rule == "sharpness":
        ok = bool(ctx["attacker"].ability in ("きれあじ", "Sharpness") and ctx["move"].name_ja in SLICING_MOVES_JA)
        text = "きれあじ ×1.5"
    elif rule == "flash_fire_atk":
        ok = bool(
            ctx["attacker"].ability in ("もらいび", "Flash Fire")
            and ctx["flash_fire_active"]
            and ctx["effective_type"] == "fire"
        )
        text = "もらいび ×1.5"

    # ── ×1.3 ──────────────────────────────────────────────────────────────
    elif rule == "sheer_force":
        ok = bool(ctx["attacker"].ability in ("ちからずく", "Sheer Force") and ctx["move"].name_ja in SHEER_FORCE_MOVES_JA)
        text = "ちからずく ×1.3"
    elif rule == "analytic":
        ok = bool(ctx["analytic_active"])
        text = "アナライズ ×1.3"
    elif rule == "tough_claws":
        ok = bool(
            ctx["attacker"].ability in ("かたいツメ", "かたいつめ", "Tough Claws")
            and is_contact_move
        )
        text = "かたいツメ ×1.3"
    elif rule == "transistor":
        ok = bool(ctx["attacker"].ability in ("トランジスタ", "Transistor") and ctx["effective_type"] == "electric")
        text = "トランジスタ ×1.3"
    elif rule == "punk_rock":
        ok = bool(ctx["attacker"].ability in ("パンクロック", "Punk Rock") and ctx["move"].name_ja in SOUND_MOVES_JA)
        text = "パンクロック ×1.3"

    # ── ×1.25 / variable ──────────────────────────────────────────────────
    elif rule == "rivalry_same":
        ok = bool(ctx["attacker"].ability in ("とうそうしん", "Rivalry") and ctx["rivalry_state"] == "same")
        text = "とうそうしん（同性） ×1.25"
    elif rule == "supreme_overlord":
        fainted = max(0, min(5, int(ctx["allies_fainted"] or 0)))
        ok = bool(ctx["attacker"].ability in ("そうだいしょう", "Supreme Overlord") and fainted > 0)
        text = "そうだいしょう {}体 ×{:.1f}".format(fainted, 1.0 + 0.1 * fainted)

    # ── ×1.2 ──────────────────────────────────────────────────────────────
    elif rule == "skin_boost":
        ok = bool(ctx["skin_type"] and ctx["move"].type_name == "normal" and ctx["effective_type"] == ctx["skin_type"])
        text = "{} ×1.2".format(ctx["attacker"].ability)
    elif rule == "normalize":
        ok = bool(ctx["normalize_active"] and ctx["effective_type"] == "normal")
        text = "ノーマルスキン ×1.2"
    elif rule == "reckless":
        ok = bool(ctx["attacker"].ability in ("すてみ", "Reckless") and ctx["move"].name_ja in RECKLESS_MOVES_JA)
        text = "すてみ ×1.2"
    elif rule == "iron_fist":
        ok = bool(ctx["attacker"].ability in ("てつのこぶし", "Iron Fist") and ctx["move"].name_ja in PUNCHING_MOVES_JA)
        text = "てつのこぶし ×1.2"

    # ── ×0.75 ─────────────────────────────────────────────────────────────
    elif rule == "rivalry_opposite":
        ok = bool(ctx["attacker"].ability in ("とうそうしん", "Rivalry") and ctx["rivalry_state"] == "opposite")
        text = "とうそうしん（異性） ×0.75"

    # ── ×0.5 ──────────────────────────────────────────────────────────────
    elif rule == "grassy_halve_eq":
        ok = bool(ctx["terrain"] == "grassy" and ctx["move"].name_ja in ("じしん", "じならし", ))
        text = "グラスフィールドで半減 ×0.5"
    elif rule == "misty_halve_dragon":
        ok = bool(ctx["terrain"] == "misty" and ctx["effective_type"] == "dragon" and is_grounded)
        text = "ミストフィールドで半減 ×0.5"

    # ── ×1.5 / ×0.5（天気）──────────────────────────────────────────────
    elif rule == "weather_fire_boost":
        ok = bool(ctx.get("weather") == "sun" and ctx.get("effective_type") == "fire")
        text = "晴れ（炎） ×1.5"
    elif rule == "weather_fire_reduce":
        ok = bool(ctx.get("weather") == "rain" and ctx.get("effective_type") == "fire")
        text = "雨（炎） ×0.5"
    elif rule == "weather_water_boost":
        ok = bool(ctx.get("weather") == "rain" and ctx.get("effective_type") == "water")
        text = "雨（水） ×1.5"
    elif rule == "weather_water_reduce":
        ok = bool(ctx.get("weather") == "sun" and ctx.get("effective_type") == "water")
        text = "晴れ（水） ×0.5"
    elif rule == "weather_snow_ice_def":
        ok = bool(
            ctx.get("weather") == "snow"
            and ctx.get("effective_category") == "physical"
            and "ice" in (ctx.get("defender_types") or [])
        )
        text = "雪（氷タイプ）防御 ×1.5"
    elif rule == "weather_sand_rock_spdef":
        ok = bool(
            ctx.get("weather") == "sand"
            and ctx.get("effective_category") == "special"
            and "rock" in (ctx.get("defender_types") or [])
        )
        text = "砂嵐（岩タイプ）特防 ×1.5"
    elif rule == "solar_reduce":
        ok = bool(
            ctx.get("move") is not None
            and ctx["move"].name_ja in _SOLAR_MOVES_JA
            and ctx.get("weather") in ("rain", "snow", "sand", "hail")
        )
        text = "ソーラー系 ×0.5"

    # ── ×1.3（フィールド）────────────────────────────────────────────────
    elif rule == "electric_terrain_boost":
        ok = bool(ctx.get("terrain") == "electric" and ctx.get("effective_type") == "electric" and is_grounded)
        text = "エレキフィールド ×1.3"
    elif rule == "grassy_terrain_boost":
        ok = bool(ctx.get("terrain") == "grassy" and ctx.get("effective_type") == "grass" and is_grounded)
        text = "グラスフィールド ×1.3"
    elif rule == "psychic_terrain_boost":
        ok = bool(ctx.get("terrain") == "psychic" and ctx.get("effective_type") == "psychic" and is_grounded)
        text = "サイコフィールド ×1.3"

    # ── ×1.5（フィールド技）──────────────────────────────────────────────
    elif rule == "psychic_blade":
        ok = bool(ctx.get("terrain") == "electric" and ctx.get("move") is not None and ctx["move"].name_ja == "サイコブレイド")
        text = "エレキフィールド ×1.5"
    elif rule == "rising_volt_target":
        ok = bool(
            ctx.get("terrain") == "electric"
            and ctx.get("move") is not None
            and ctx["move"].name_ja == "ライジングボルト"
            and ctx.get("defender_is_grounded", True)
        )
        text = "エレキフィールド(相手接地) ×1.5"
    elif rule == "wide_force":
        ok = bool(ctx.get("terrain") == "psychic" and ctx.get("move") is not None and ctx["move"].name_ja == "ワイドフォース" and is_grounded)
        text = "サイコフィールド ×1.5"
    elif rule == "mist_burst":
        ok = bool(ctx.get("terrain") == "misty" and ctx.get("move") is not None and ctx["move"].name_ja == "ミストバースト" and is_grounded)
        text = "ミストフィールド ×1.5"

    # ── ×1.5（じゅうりょく）──────────────────────────────────────────────
    elif rule == "g_force":
        ok = bool(ctx.get("gravity") and ctx.get("move") is not None and ctx["move"].name_ja == "Gのちから")
        text = "じゅうりょく ×1.5"

    # ── ×2.0（わざ固有）──────────────────────────────────────────────────
    elif rule == "jaw_volt_boost":
        ok = bool(
            ctx.get("move") is not None
            and ctx["move"].name_ja in ("エラがみ", "でんげきくちばし")
            and ctx.get("attacker_moved_first", False)
        )
        text = "{} 先攻 ×2.0".format(ctx["move"].name_ja if ctx.get("move") else "")
    elif rule == "sucker_punch":
        ok = bool(
            ctx.get("move") is not None
            and ctx["move"].name_ja == "しっぺがえし"
            and ctx.get("defender_moved_first", False)
        )
        text = "しっぺがえし 後攻 ×2.0"
    elif rule == "facade":
        ok = bool(
            ctx.get("move") is not None
            and ctx["move"].name_ja == "からげんき"
            and bool(ctx.get("attacker_status", ""))
        )
        text = "状態異常 ×2.0"
    elif rule == "acrobatics":
        ok = bool(
            ctx.get("move") is not None
            and ctx["move"].name_ja == "アクロバット"
            and not ctx.get("attacker_item", "")
        )
        text = "持ち物なし(自分) ×2.0"

    # ── ×1.5（はたきおとす）──────────────────────────────────────────────
    elif rule == "knock_off":
        _d_name = ctx.get("defender_name_ja", "")
        _d_item = ctx.get("defender_item", "")
        _d_ability = ctx.get("defender_ability", "")
        ok = bool(
            ctx.get("move") is not None
            and ctx["move"].name_ja == "はたきおとす"
            and _d_item
            and not _is_knock_off_protected(_d_name, _d_item, _d_ability)
        )
        text = "持ち物あり(相手) ×1.5"

    # ── 無効（×0）────────────────────────────────────────────────────────
    elif rule == "iron_roller_null":
        ok = bool(
            ctx.get("move") is not None
            and ctx["move"].name_ja == "アイアンローラー"
            and not ctx.get("terrain", "")
        )
        text = "フィールドなし 無効"
    elif rule == "ability_null":
        # Called after condition is already confirmed; ability name passed via ctx.
        ok = True
        text = f"{_ability_ja(ctx['ability'])}によって無効"
    elif rule == "type_chart_null":
        ok = True
        text = "タイプ相性によって無効"
    elif rule == "psychic_terrain_priority_block":
        ok = bool(ctx["terrain"] == "psychic" and ctx["move"].priority > 0 and is_grounded)
        text = "サイコフィールドによって無効"
    if ok:
        add_unique_note(notes, text)
    return ok


def collect_notes(
    notes: list[str],
    attacker: PokemonInstance,
    move: MoveInfo,
    defender: PokemonInstance,
    *,
    effective_type: str,
    effective_category: str,
    type_eff: float,
    skin_type: str = "",
    attacker_item: str = "",
    weather: str = "none",
    terrain: str = "",
    gravity: bool = False,
    is_grounded: bool = True,
    defender_is_grounded: bool = True,
    attacker_moved_first: bool = False,
    defender_moved_first: bool = False,
    attacker_status: str = "",
    flash_fire_active: bool = False,
    stakeout_active: bool = False,
    analytic_active: bool = False,
    rivalry_state: str = "none",
    allies_fainted: int = 0,
) -> None:
    _r = apply_note_rule

    # アイテム（攻撃側）
    _r("choice_band", notes, attacker_item=attacker_item, uses_attacker_physical_attack=(effective_category == "physical"))
    _r("choice_specs", notes, attacker_item=attacker_item, uses_attacker_special_attack=(effective_category == "special"))
    _r("life_orb", notes, attacker_item=attacker_item)
    _r("expert_belt", notes, attacker_item=attacker_item, type_eff=type_eff)
    _r("type_boost_item", notes, attacker_item=attacker_item, effective_type=effective_type)
    _r("wise_glasses", notes, attacker_item=attacker_item, effective_category=effective_category)
    _r("muscle_band", notes, attacker_item=attacker_item, effective_category=effective_category)

    # きのみ（防御側）
    _r("resist_berry", notes, defender_item=(defender.item or ""), effective_type=effective_type, type_eff=type_eff)

    # 特性（攻撃側）
    _r("water_bubble_atk", notes, attacker=attacker, effective_type=effective_type)
    _r("stakeout", notes, attacker=attacker, stakeout_active=stakeout_active)
    _r("technician", notes, attacker=attacker, power=move.power, effective_category=effective_category)
    _r("mega_launcher", notes, attacker=attacker, move=move)
    _r("strong_jaw", notes, attacker=attacker, move=move)
    _r("dragons_maw", notes, attacker=attacker, effective_type=effective_type)
    _r("rocky_payload", notes, attacker=attacker, effective_type=effective_type)
    _r("steely_spirit", notes, attacker=attacker, effective_type=effective_type)
    _r("steelworker", notes, attacker=attacker, effective_type=effective_type)
    _r("sharpness", notes, attacker=attacker, move=move)
    _r("flash_fire_atk", notes, attacker=attacker, flash_fire_active=flash_fire_active, effective_type=effective_type)
    _r("sheer_force", notes, attacker=attacker, move=move)
    _r("analytic", notes, analytic_active=analytic_active)
    _r("tough_claws", notes, attacker=attacker, is_contact_move=move.makes_contact)
    _r("transistor", notes, attacker=attacker, effective_type=effective_type)
    _r("punk_rock", notes, attacker=attacker, move=move)
    _r("rivalry_same", notes, attacker=attacker, rivalry_state=rivalry_state)
    _r("rivalry_opposite", notes, attacker=attacker, rivalry_state=rivalry_state)
    _r("supreme_overlord", notes, attacker=attacker, allies_fainted=allies_fainted)
    _r("skin_boost", notes, attacker=attacker, move=move, effective_type=effective_type, skin_type=skin_type)
    _r("normalize", notes, attacker=attacker, effective_type=effective_type,
       normalize_active=(attacker.ability in ("ノーマルスキン", "Normalize")))
    _r("reckless", notes, attacker=attacker, move=move)
    _r("iron_fist", notes, attacker=attacker, move=move)

    # 天気
    _r("weather_fire_boost", notes, weather=weather, effective_type=effective_type)
    _r("weather_fire_reduce", notes, weather=weather, effective_type=effective_type)
    _r("weather_water_boost", notes, weather=weather, effective_type=effective_type)
    _r("weather_water_reduce", notes, weather=weather, effective_type=effective_type)
    _r("weather_snow_ice_def", notes, weather=weather, effective_category=effective_category, defender_types=defender.types)
    _r("weather_sand_rock_spdef", notes, weather=weather, effective_category=effective_category, defender_types=defender.types)
    _r("solar_reduce", notes, weather=weather, move=move)

    # フィールド
    _r("electric_terrain_boost", notes, terrain=terrain, effective_type=effective_type, is_grounded=is_grounded)
    _r("grassy_terrain_boost", notes, terrain=terrain, effective_type=effective_type, is_grounded=is_grounded)
    _r("psychic_terrain_boost", notes, terrain=terrain, effective_type=effective_type, is_grounded=is_grounded)
    _r("psychic_blade", notes, terrain=terrain, move=move)
    _r("rising_volt_target", notes, terrain=terrain, move=move, defender_is_grounded=defender_is_grounded)
    _r("wide_force", notes, terrain=terrain, move=move, is_grounded=is_grounded)
    _r("mist_burst", notes, terrain=terrain, move=move, is_grounded=is_grounded)
    _r("grassy_halve_eq", notes, terrain=terrain, move=move)
    _r("misty_halve_dragon", notes, terrain=terrain, effective_type=effective_type, is_grounded=is_grounded)
    _r("iron_roller_null", notes, terrain=terrain, move=move)

    # じゅうりょく
    _r("g_force", notes, gravity=gravity, move=move)

    # わざ固有
    _r("jaw_volt_boost", notes, move=move, attacker_moved_first=attacker_moved_first)
    _r("sucker_punch", notes, move=move, defender_moved_first=defender_moved_first)
    _r("facade", notes, move=move, attacker_status=attacker_status)
    _r("acrobatics", notes, move=move, attacker_item=attacker_item)
    _r("knock_off", notes, move=move,
       defender_name_ja=defender.name_ja,
       defender_item=(defender.item or ""),
       defender_ability=(defender.ability or ""))
