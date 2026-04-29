import math
from src.models import PokemonInstance, MoveInfo, DamageResult, SpeciesInfo
from src.constants import (
    TYPE_CHART, NATURES_JA, BEST_DEF_NATURE_FOR, GAME_LEVEL,
    PUNCHING_MOVES_JA, SLICING_MOVES_JA, PULSE_MOVES_JA,
    BITE_MOVES_JA, SOUND_MOVES_JA, RECKLESS_MOVES_JA, SHEER_FORCE_MOVES_JA,
    STEALTH_ROCK_CHART, WIND_MOVES_JA, CONTACT_MOVES_JA,
)


def get_nature_mult(nature_ja: str, stat: str) -> float:
    boost, reduce = NATURES_JA.get(nature_ja, (None, None))
    if boost == stat:
        return 1.1
    if reduce == stat:
        return 0.9
    return 1.0


def calc_stat(base: int, iv: int, ev: int, level: int = GAME_LEVEL,
              nature_mult: float = 1.0, is_hp: bool = False) -> int:
    inner = math.floor((2 * base + iv + ev // 4) * level / 100)
    if is_hp:
        return inner + level + 10
    return math.floor((inner + 5) * nature_mult)


_PSYSHOCK_LIKE_MOVES = frozenset(["サイコショック", "サイコブレイク", "しんぴのつるぎ"])
_SOLAR_MOVES = frozenset(["ソーラービーム", "ソーラーブレード"])
_ERUPTION_LIKE_MOVES = frozenset(["ふんか", "しおふき", "ドラゴンエナジー"])
_REVERSAL_LIKE_MOVES = frozenset(["きしかいせい", "じたばた"])
_LOW_KICK_LIKE_MOVES = frozenset(["けたぐり", "くさむすび"])
_HEAVY_SLAM_LIKE_MOVES = frozenset(["ヘビーボンバー", "ヒートスタンプ"])
_STORED_POWER_LIKE_MOVES = frozenset(["アシストパワー", "つけあがる"])
_OHKO_MOVES = frozenset(["ぜったいれいど", "じわれ", "つのドリル", "ハサミギロチン"])
_FIXED_LEVEL_MOVES = frozenset(["ナイトヘッド", "ちきゅうなげ"])
_FIXED_40_MOVES = frozenset(["りゅうのいかり"])
_FIXED_20_MOVES = frozenset(["ソニックブーム"])
_HALF_CURRENT_HP_MOVES = frozenset(["いかりのまえば", "しぜんのいかり", "カタストロフィ"])
_TYPE_BOOST_ITEMS = {
    "シルクのスカーフ": "normal",
    "もくたん": "fire",
    "しんぴのしずく": "water",
    "きせきのたね": "grass",
    "するどいくちばし": "flying",
    "ぎんのこな": "bug",
    "とけないこおり": "ice",
    "まがったスプーン": "psychic",
    "じしゃく": "electric",
    "やわらかいすな": "ground",
    "メタルコート": "steel",
    "くろおび": "fighting",
    "どくバリ": "poison",
    "くろいメガネ": "dark",
    "のろいのおふだ": "ghost",
    "かたいいし": "rock",
    "りゅうのキバ": "dragon",
    "ようせいのハネ": "fairy",
}
_POISON_STATUS_KEYS = frozenset(["poison", "tox", "toxic", "psn", "どく", "もうどく"])


def _raw_type_effectiveness(move_type: str, defender_types: list[str], defender_ability: str = "") -> float:
    if defender_ability in ("ふゆう", "Levitate") and move_type == "ground":
        return 0.0
    if defender_ability in ("もらいび", "Flash Fire") and move_type == "fire":
        return 0.0
    chart = TYPE_CHART.get(move_type, {})
    mult = 1.0
    for t in defender_types:
        if t:
            mult *= chart.get(t, 1.0)
    return mult


def type_effectiveness(move_type: str, defender_types: list[str],
                       defender_ability: str = "") -> float:
    mult = _raw_type_effectiveness(move_type, defender_types, defender_ability)
    if defender_ability == "ふしぎなまもり" and mult <= 1.0:
        return 0.0
    return mult


def resolve_effective_move_type(
    attacker: PokemonInstance,
    move: MoveInfo,
    terastal_type: str = "",
) -> str:
    effective_type = move.type_name
    if move.name_ja == "テラバースト" and terastal_type and move.type_name == "normal":
        effective_type = terastal_type
    if _is_normalize_ability(attacker.ability):
        return "normal"
    skin_type = _skin_ability_type(attacker.ability)
    if skin_type and effective_type == "normal":
        effective_type = skin_type
    return effective_type


def resolve_effective_move_category(
    attacker: PokemonInstance,
    move: MoveInfo,
    atk_rank: int = 0,
    terastal_type: str = "",
) -> str:
    if move.name_ja == "テラバースト" and terastal_type:
        rank_mult = _rank_multiplier(atk_rank)
        atk_val = attacker.attack * rank_mult
        spa_val = attacker.sp_attack * rank_mult
        return "physical" if atk_val > spa_val else "special"
    if move.name_ja == "フォトンゲイザー":
        rank_mult = _rank_multiplier(atk_rank)
        atk_val = attacker.attack * rank_mult
        spa_val = attacker.sp_attack * rank_mult
        return "physical" if atk_val > spa_val else "special"
    return move.category


def move_type_effectiveness(
    move: MoveInfo,
    move_type: str,
    defender_types: list[str],
    defender_ability: str = "",
    ignore_defender_ability: bool = False,
) -> float:
    ability = "" if ignore_defender_ability else defender_ability
    if ability in ("もらいび", "Flash Fire") and move_type == "fire":
        return 0.0
    if ability in ("かぜのり", "Wind Rider") and move.name_ja in WIND_MOVES_JA:
        return 0.0

    if move.name_ja == "フライングプレス":
        mult = _raw_type_effectiveness("fighting", defender_types, ability) * \
            _raw_type_effectiveness("flying", defender_types, ability)
    elif move.name_ja == "フリーズドライ" and move_type == "ice":
        chart = TYPE_CHART.get(move_type, {})
        mult = 1.0
        for t in defender_types:
            if not t:
                continue
            if t == "water":
                mult *= 2.0
            else:
                mult *= chart.get(t, 1.0)
    else:
        mult = _raw_type_effectiveness(move_type, defender_types, ability)

    if ability == "ふしぎなまもり" and mult <= 1.0:
        return 0.0
    return mult


def _is_grounded(defender_types: list[str], defender_ability: str = "") -> bool:
    if "flying" in defender_types:
        return False
    if defender_ability == "ふゆう":
        return False
    return True


def _stat_with_rank(stat: int, rank: int) -> int:
    return max(1, int(stat * _rank_multiplier(rank)))


def _current_hp(value: int, fallback_max_hp: int) -> int:
    if value > 0:
        return max(1, value)
    if fallback_max_hp > 0:
        return fallback_max_hp
    return 1


def _is_poisoned(status: str) -> bool:
    return (status or "").strip().lower() in _POISON_STATUS_KEYS


def _paradox_boosted_stat_key(attacker: PokemonInstance) -> str:
    """Protosynthesis/Quark Drive boosted stat priority: Atk > Def > SpA > SpD > Spe."""
    stats = {
        "attack": int(attacker.attack or 0),
        "defense": int(attacker.defense or 0),
        "sp_attack": int(attacker.sp_attack or 0),
        "sp_defense": int(attacker.sp_defense or 0),
        "speed": int(attacker.speed or 0),
    }
    priority = ["attack", "defense", "sp_attack", "sp_defense", "speed"]
    best = "attack"
    for key in priority[1:]:
        if stats.get(key, 0) > stats.get(best, 0):
            best = key
    return best


def _calc_reversal_power(current_hp: int, max_hp: int) -> int:
    max_hp = max(1, max_hp)
    ratio = current_hp * 48
    if ratio <= max_hp * 2:
        return 200
    if ratio <= max_hp * 5:
        return 150
    if ratio <= max_hp * 10:
        return 100
    if ratio <= max_hp * 17:
        return 80
    if ratio <= max_hp * 33:
        return 40
    return 20


def _calc_weight_power(move_name: str, attacker_weight_kg: float, defender_weight_kg: float) -> int:
    if move_name in _LOW_KICK_LIKE_MOVES:
        if defender_weight_kg >= 200:
            return 120
        if defender_weight_kg >= 100:
            return 100
        if defender_weight_kg >= 50:
            return 80
        if defender_weight_kg >= 25:
            return 60
        if defender_weight_kg >= 10:
            return 40
        if defender_weight_kg > 0:
            return 20
        return 60

    if move_name in _HEAVY_SLAM_LIKE_MOVES:
        if attacker_weight_kg <= 0 or defender_weight_kg <= 0:
            return 60
        ratio = attacker_weight_kg / max(0.1, defender_weight_kg)
        if ratio >= 5:
            return 120
        if ratio >= 4:
            return 100
        if ratio >= 3:
            return 80
        if ratio >= 2:
            return 60
        return 40
    return 0


def _calc_fixed_damage(move_name: str, attacker: PokemonInstance, defender_current_hp: int) -> int | None:
    if move_name in _OHKO_MOVES:
        return max(1, defender_current_hp)
    if move_name in _FIXED_LEVEL_MOVES:
        return max(1, attacker.level or GAME_LEVEL)
    if move_name in _FIXED_40_MOVES:
        return 40
    if move_name in _FIXED_20_MOVES:
        return 20
    if move_name in _HALF_CURRENT_HP_MOVES:
        return max(1, defender_current_hp // 2)
    if move_name == "いのちがけ":
        cur_hp = _current_hp(attacker.current_hp, attacker.max_hp or attacker.hp)
        return max(1, cur_hp)
    return None


def _calc_dynamic_power(
    attacker: PokemonInstance,
    move: MoveInfo,
    power_override: int,
    atk_rank: int,
    def_rank: int,
    defender_speed: int,
    defender_weight_kg: float,
    attacker_moves_after_target: bool | None,
    attacker_positive_ranks_sum: int | None,
    defender_positive_ranks_sum: int | None,
) -> int:
    if power_override > 0:
        return power_override

    move_name = move.name_ja
    base_power = move.power
    atk_speed = max(1, attacker.speed or 0)
    def_speed = max(1, defender_speed if defender_speed > 0 else atk_speed)

    if move_name == "ジャイロボール":
        return max(1, min(150, math.floor(25 * def_speed / atk_speed)))
    if move_name == "エレキボール":
        ratio = atk_speed / def_speed
        if ratio >= 4:
            return 150
        if ratio >= 3:
            return 120
        if ratio >= 2:
            return 80
        if ratio >= 1:
            return 60
        return 40
    if move_name in _ERUPTION_LIKE_MOVES:
        cur_hp = _current_hp(attacker.current_hp, attacker.max_hp or attacker.hp)
        max_hp = max(1, attacker.max_hp or attacker.hp or cur_hp)
        return max(1, math.floor(150 * cur_hp / max_hp))
    if move_name in _REVERSAL_LIKE_MOVES:
        cur_hp = _current_hp(attacker.current_hp, attacker.max_hp or attacker.hp)
        max_hp = max(1, attacker.max_hp or attacker.hp or cur_hp)
        return _calc_reversal_power(cur_hp, max_hp)
    if move_name in _LOW_KICK_LIKE_MOVES or move_name in _HEAVY_SLAM_LIKE_MOVES:
        return _calc_weight_power(move_name, float(attacker.weight_kg or 0), float(defender_weight_kg or 0))
    if move_name in _STORED_POWER_LIKE_MOVES:
        buffs = max(0, attacker_positive_ranks_sum if attacker_positive_ranks_sum is not None else atk_rank)
        return 20 + 20 * buffs
    if move_name == "おしおき":
        buffs = max(0, defender_positive_ranks_sum if defender_positive_ranks_sum is not None else def_rank)
        return min(200, 60 + 20 * buffs)
    if move_name == "しっぺがえし":
        if attacker_moves_after_target is None:
            attacker_moves_after_target = (attacker.speed > 0 and defender_speed > 0 and attacker.speed < defender_speed)
        return 100 if attacker_moves_after_target else (base_power or 50)

    return base_power


def _item_final_multiplier(
    item_name: str,
    move: MoveInfo,
    effective_type: str,
    effective_category: str,
    type_eff: float,
) -> tuple[float, list[str]]:
    item = (item_name or "").strip()
    mult = 1.0
    notes: list[str] = []

    if not item:
        return (mult, notes)

    if item == "いのちのたま":
        mult *= 1.3
        notes.append("いのちのたま ×1.3")
    if item in ("たつじんのおび", "Expert Belt") and type_eff > 1.0:
        mult *= 1.2
        notes.append("たつじんのおび ×1.2")
    if item == "ちからのハチマキ" and effective_category == "physical":
        mult *= 1.1
        notes.append("ちからのハチマキ ×1.1")
    if item == "ものしりメガネ" and effective_category == "special":
        mult *= 1.1
        notes.append("ものしりメガネ ×1.1")
    if item in ("パンチグローブ", "てっけんグローブ") and move.name_ja in PUNCHING_MOVES_JA:
        mult *= 1.1
        notes.append("{} ×1.1".format(item))
    if _TYPE_BOOST_ITEMS.get(item) == effective_type:
        mult *= 1.2
        notes.append("{} ×1.2".format(item))

    return (mult, notes)


def _base_damage(power: int, attack: int, defense: int, level: int = GAME_LEVEL) -> int:
    defense = defense or 1
    return math.floor(math.floor((2 * level // 5 + 2) * power * attack / defense) / 50) + 2


def _apply_chain(value: float, *multipliers: float) -> int:
    result = value
    for m in multipliers:
        result = math.floor(result * m)
    return int(result)


def _rank_multiplier(rank: int) -> float:
    table = {
        -6: 2/8, -5: 2/7, -4: 2/6, -3: 2/5, -2: 2/4, -1: 2/3,
        0: 1.0, 1: 3/2, 2: 4/2, 3: 5/2, 4: 6/2, 5: 7/2, 6: 8/2,
    }
    return table.get(max(-6, min(6, rank)), 1.0)


def _skin_ability_type(ability: str) -> str | None:
    """Return type override for skin/type-change abilities applied to normal-type moves."""
    _map = {
        "エレキスキン": "electric",
        "Galvanize": "electric",
        "フェアリースキン": "fairy",
        "Pixilate": "fairy",
        "フリーズスキン": "ice",
        "Refrigerate": "ice",
        "スカイスキン": "flying",
        "Aerilate": "flying",
        "ドラゴンスキン": "dragon",
        "Dragonize": "dragon",
    }
    return _map.get(ability)


def _is_normalize_ability(ability: str) -> bool:
    return ability in ("ノーマルスキン", "Normalize")


def calc_stealth_rock_damage(defender_hp: int, defender_types: list[str]) -> int:
    mult = 1.0
    for t in defender_types:
        mult *= STEALTH_ROCK_CHART.get(t, 1.0)
    return max(1, math.floor(defender_hp / 8 * mult))


def calc_damage_range(
    attacker: PokemonInstance,
    move: MoveInfo,
    defender_hp: int,
    defender_attack: int,
    defender_defense: int,
    defender_sp_attack: int,
    defender_sp_defense: int,
    defender_types: list[str],
    weather: str = "none",
    is_critical: bool = False,
    terrain: str = "none",
    defender_ability: str = "",
    has_reflect: bool = False,
    has_light_screen: bool = False,
    helping_hand: bool = False,
    steel_spirit: bool = False,
    charged: bool = False,
    terastal_type: str = "",
    fairy_aura: bool = False,
    dark_aura: bool = False,
    defender_has_berry: bool = False,
    power_override: int = 0,
    atk_rank: int = 0,
    def_rank: int = 0,
    parental_bond: bool = False,
    ignore_defender_ability: bool = False,
    defender_current_hp: int = 0,
    defender_disguise_intact: bool = False,
    is_double_battle: bool = False,
    defender_speed: int = 0,
    defender_weight_kg: float = 0.0,
    attacker_def_rank: int | None = None,
    defender_atk_rank: int | None = None,
    defender_def_rank: int | None = None,
    attacker_atk_rank: int | None = None,
    attacker_moves_after_target: bool | None = None,
    attacker_positive_ranks_sum: int | None = None,
    defender_positive_ranks_sum: int | None = None,
    allies_fainted: int = 0,
    rivalry_state: str = "none",
    stakeout_active: bool = False,
    flash_fire_active: bool = False,
    protosynthesis_active: bool = False,
    quark_drive_active: bool = False,
    friend_guard: bool = False,
    modifier_notes: list[str] | None = None,
) -> tuple[int, int]:
    """
    Returns (min_damage, max_damage) in HP points.
    Uses the level-50 Gen-6+ damage formula with full condition support.
    """
    def _note(text: str) -> None:
        if modifier_notes is not None and text and text not in modifier_notes:
            modifier_notes.append(text)

    if move.category == "status":
        return (0, 0)

    effective_def_ability = "" if ignore_defender_ability else defender_ability
    effective_type = resolve_effective_move_type(attacker, move, terastal_type)
    effective_category = resolve_effective_move_category(attacker, move, atk_rank, terastal_type)

    # サイコフィールド: 優先度+1以上を地面にいる相手へ撃てない
    if terrain == "psychic" and move.priority > 0 and _is_grounded(defender_types, effective_def_ability):
        _note("サイコフィールドで先制技無効")
        return (0, 0)
    if effective_def_ability in ("もらいび", "Flash Fire") and effective_type == "fire":
        _note("もらいびで無効")
        return (0, 0)
    if effective_def_ability in ("かんそうはだ", "Dry Skin") and effective_type == "water":
        _note("かんそうはだで無効")
        return (0, 0)
    if effective_def_ability in ("かぜのり", "Wind Rider") and move.name_ja in WIND_MOVES_JA:
        _note("かぜのりで無効")
        return (0, 0)

    type_eff = move_type_effectiveness(
        move,
        effective_type,
        defender_types,
        defender_ability=effective_def_ability,
    )
    if type_eff == 0:
        _note("タイプ相性で無効")
        return (0, 0)

    # ばけのかわ: first damaging hit is nullified
    if effective_def_ability == "ばけのかわ" and defender_disguise_intact:
        _note("ばけのかわで無効")
        return (0, 0)

    cur_hp = _current_hp(defender_current_hp, defender_hp)
    fixed_damage = _calc_fixed_damage(move.name_ja, attacker, cur_hp)
    if fixed_damage is not None:
        _note("{} 固定/割合ダメージ".format(move.name_ja))
        return (fixed_damage, fixed_damage)

    # ── Resolve stat sources and rank application ───────────────────────
    attack_source = "attacker_attack" if effective_category == "physical" else "attacker_sp_attack"
    defense_source = "defender_defense" if effective_category == "physical" else "defender_sp_defense"
    if move.name_ja == "ボディプレス":
        attack_source = "attacker_defense"
    elif move.name_ja == "イカサマ":
        attack_source = "defender_attack"
    if move.name_ja in _PSYSHOCK_LIKE_MOVES:
        defense_source = "defender_defense"

    attack_rank = atk_rank
    defense_rank = def_rank
    if attack_source == "attacker_defense" and attacker_def_rank is not None:
        attack_rank = attacker_def_rank
    if attack_source == "defender_attack":
        attack_rank = defender_atk_rank if defender_atk_rank is not None else def_rank
    if defense_source == "defender_defense" and defender_def_rank is not None:
        defense_rank = defender_def_rank

    # てんねん: defender ignores attacker-side stages / attacker ignores defender-side stages
    if effective_def_ability == "てんねん" and attack_source.startswith("attacker"):
        attack_rank = 0
    if attacker.ability == "てんねん":
        if defense_source.startswith("defender"):
            defense_rank = 0
        if attack_source == "defender_attack":
            attack_rank = 0

    # 急所のランク無視: 攻撃側マイナス / 防御側プラスを無視
    if is_critical:
        if attack_rank < 0:
            attack_rank = 0
        if defense_rank > 0:
            defense_rank = 0

    if attack_source == "attacker_attack":
        atk = _stat_with_rank(attacker.attack, attack_rank)
    elif attack_source == "attacker_sp_attack":
        atk = _stat_with_rank(attacker.sp_attack, attack_rank)
    elif attack_source == "attacker_defense":
        atk = _stat_with_rank(attacker.defense, attack_rank)
    else:
        atk = _stat_with_rank(defender_attack, attack_rank)

    if defense_source == "defender_defense":
        def_ = _stat_with_rank(defender_defense, defense_rank)
    else:
        def_ = _stat_with_rank(defender_sp_defense, defense_rank)

    # Weather defensive boosts
    if weather == "sand" and defense_source == "defender_sp_defense" and "rock" in defender_types:
        def_ = max(1, math.floor(def_ * 1.5))
        _note("すな: いわ特防 ×1.5")
    if weather in ("hail", "snow") and defense_source == "defender_defense" and "ice" in defender_types:
        def_ = max(1, math.floor(def_ * 1.5))
        _note("ゆき: こおり防御 ×1.5")
    if weather == "sun" and defense_source == "defender_sp_defense" and effective_def_ability in ("フラワーギフト", "Flower Gift"):
        def_ = max(1, math.floor(def_ * 1.5))
        _note("相手フラワーギフト ×1.5")

    # ── Effective power (dynamic/base then ability/field mods) ──────────
    effective_power = _calc_dynamic_power(
        attacker=attacker,
        move=move,
        power_override=power_override,
        atk_rank=atk_rank,
        def_rank=def_rank,
        defender_speed=defender_speed,
        defender_weight_kg=defender_weight_kg,
        attacker_moves_after_target=attacker_moves_after_target,
        attacker_positive_ranks_sum=attacker_positive_ranks_sum,
        defender_positive_ranks_sum=defender_positive_ranks_sum,
    )
    if effective_power <= 0:
        return (0, 0)

    # 雨/砂/雪下のソーラー系半減
    if move.name_ja in _SOLAR_MOVES and weather in ("rain", "sand", "hail", "snow"):
        effective_power = max(1, math.floor(effective_power * 0.5))
        _note("{} 天候半減 ×0.5".format(move.name_ja))

    # Ability-based power boosts (Gen9 @smogon/calc ordering)
    # ×1.5 group
    if attacker.ability == "テクニシャン" and 0 < effective_power <= 60:
        effective_power = math.floor(effective_power * 1.5)
        _note("テクニシャン ×1.5")
    if attacker.ability in ("どくぼうそう", "Toxic Boost") and _is_poisoned(attacker.status) and effective_category == "physical":
        effective_power = math.floor(effective_power * 1.5)
        _note("どくぼうそう ×1.5")
    if attacker.ability in ("メガランチャー", "Mega Launcher") and move.name_ja in PULSE_MOVES_JA:
        effective_power = math.floor(effective_power * 1.5)
        _note("メガランチャー ×1.5")
    if attacker.ability in ("がんじょうあご", "Strong Jaw") and move.name_ja in BITE_MOVES_JA:
        effective_power = math.floor(effective_power * 1.5)
        _note("がんじょうあご ×1.5")
    if attacker.ability in ("りゅうのあぎと", "Dragon's Maw") and effective_type == "dragon":
        effective_power = math.floor(effective_power * 1.5)
        _note("りゅうのあぎと ×1.5")
    if attacker.ability in ("いわはこび", "Rocky Payload") and effective_type == "rock":
        effective_power = math.floor(effective_power * 1.5)
        _note("いわはこび ×1.5")
    if attacker.ability in ("はがねのせいしん", "Steely Spirit") and effective_type == "steel":
        effective_power = math.floor(effective_power * 1.5)
        _note("はがねのせいしん ×1.5")
    if attacker.ability in ("はがねつかい", "Steelworker") and effective_type == "steel":
        effective_power = math.floor(effective_power * 1.5)
        _note("はがねつかい ×1.5")
    if attacker.ability in ("きれあじ", "Sharpness") and move.name_ja in SLICING_MOVES_JA:
        effective_power = math.floor(effective_power * 1.5)
        _note("きれあじ ×1.5")

    # ×1.3 group
    if attacker.ability in ("ちからずく", "Sheer Force") and move.name_ja in SHEER_FORCE_MOVES_JA:
        effective_power = math.floor(effective_power * 1.3)
        _note("ちからずく ×1.3")
    analytic_active = False
    if attacker.ability in ("アナライズ", "Analytic"):
        if attacker_moves_after_target is None:
            analytic_active = attacker.speed > 0 and defender_speed > 0 and attacker.speed < defender_speed
        else:
            analytic_active = attacker_moves_after_target
    if analytic_active:
        effective_power = math.floor(effective_power * 1.3)
        _note("アナライズ ×1.3")
    if attacker.ability in ("かたいツメ", "かたいつめ", "Tough Claws") and (move.makes_contact or move.name_ja in CONTACT_MOVES_JA):
        effective_power = math.floor(effective_power * 1.3)
        _note("かたいツメ ×1.3")
    if attacker.ability in ("トランジスタ", "Transistor") and effective_type == "electric":
        effective_power = math.floor(effective_power * 1.3)
        _note("トランジスタ ×1.3")
    if attacker.ability in ("パンクロック", "Punk Rock") and move.name_ja in SOUND_MOVES_JA:
        effective_power = math.floor(effective_power * 1.3)
        _note("パンクロック ×1.3")

    # ×1.2 group
    skin_type = _skin_ability_type(attacker.ability)
    if skin_type and move.type_name == "normal" and effective_type == skin_type:
        effective_power = math.floor(effective_power * 1.2)
        _note("{} ×1.2".format(attacker.ability))
    if _is_normalize_ability(attacker.ability) and effective_type == "normal":
        effective_power = math.floor(effective_power * 1.2)
        _note("ノーマルスキン ×1.2")
    if attacker.ability in ("すてみ", "Reckless") and move.name_ja in RECKLESS_MOVES_JA:
        effective_power = math.floor(effective_power * 1.2)
        _note("すてみ ×1.2")
    if attacker.ability in ("てつのこぶし", "Iron Fist") and move.name_ja in PUNCHING_MOVES_JA:
        effective_power = math.floor(effective_power * 1.2)
        _note("てつのこぶし ×1.2")
    if attacker.ability in ("すいほう", "Water Bubble") and effective_type == "water":
        effective_power = math.floor(effective_power * 2.0)
        _note("すいほう ×2.0")

    if attacker.ability in ("とうそうしん", "Rivalry"):
        if rivalry_state == "same":
            effective_power = math.floor(effective_power * 1.25)
            _note("とうそうしん（同性） ×1.25")
        elif rivalry_state == "opposite":
            effective_power = math.floor(effective_power * 0.75)
            _note("とうそうしん（異性） ×0.75")

    if attacker.ability in ("そうだいしょう", "Supreme Overlord"):
        fainted = max(0, min(5, int(allies_fainted or 0)))
        if fainted > 0:
            so_mult = 1.0 + 0.1 * fainted
            effective_power = math.floor(effective_power * so_mult)
            _note("そうだいしょう {}体 ×{:.1f}".format(fainted, so_mult))
    if attacker.ability in ("はりこみ", "Stakeout") and stakeout_active:
        effective_power = math.floor(effective_power * 2.0)
        _note("はりこみ ×2.0")
    if attacker.ability in ("もらいび", "Flash Fire") and flash_fire_active and effective_type == "fire":
        effective_power = math.floor(effective_power * 1.5)
        _note("もらいび発動 ×1.5")

    # Grassy terrain halves Earthquake/Bulldoze/Dig
    if terrain == "grassy" and move.name_ja in ("じしん", "じならし", "あなをほる"):
        effective_power = math.floor(effective_power * 0.5)
        _note("グラスフィールドで威力半減 ×0.5")

    # ── Attacker stat modifier (ability/status) ────────────────────────
    atk_stat_mult = 1.0
    uses_attacker_physical_attack = (
        effective_category == "physical" and attack_source == "attacker_attack"
    )
    uses_attacker_special_attack = (
        effective_category == "special" and attack_source == "attacker_sp_attack"
    )

    # ちからもち / ヨガパワー (attack × 2 for physical attack stat)
    if uses_attacker_physical_attack and attacker.ability in ("ちからもち", "ヨガパワー", "Huge Power", "Pure Power"):
        atk_stat_mult *= 2.0

    burn_mult = 1.0
    if uses_attacker_physical_attack and attacker.status == "burn":
        burn_mult = 0.5

    # こんじょう: ×1.5 physical when status; also negates burn halving
    if uses_attacker_physical_attack and attacker.ability in ("こんじょう", "Guts") and attacker.status != "":
        atk_stat_mult *= 1.5
        burn_mult = 1.0

    if uses_attacker_physical_attack and attacker.ability in ("ごりむちゅう", "Gorilla Tactics"):
        atk_stat_mult *= 1.5
        _note("ごりむちゅう ×1.5")

    attacker_cur_hp = _current_hp(attacker.current_hp, attacker.max_hp or attacker.hp)
    attacker_max_hp = max(1, attacker.max_hp or attacker.hp or attacker_cur_hp)
    if attacker_cur_hp * 3 <= attacker_max_hp:
        if attacker.ability in ("しんりょく", "Overgrow") and effective_type == "grass":
            atk_stat_mult *= 1.5
            _note("しんりょく ×1.5")
        elif attacker.ability in ("もうか", "Blaze") and effective_type == "fire":
            atk_stat_mult *= 1.5
            _note("もうか ×1.5")
        elif attacker.ability in ("げきりゅう", "Torrent") and effective_type == "water":
            atk_stat_mult *= 1.5
            _note("げきりゅう ×1.5")
        elif attacker.ability in ("むしのしらせ", "Swarm") and effective_type == "bug":
            atk_stat_mult *= 1.5
            _note("むしのしらせ ×1.5")

    if uses_attacker_physical_attack and attacker.ability in ("フラワーギフト", "Flower Gift") and weather == "sun":
        atk_stat_mult *= 1.5
        _note("フラワーギフト ×1.5")

    if uses_attacker_physical_attack and attacker.ability in ("ひひいろのこどう", "Orichalcum Pulse") and weather == "sun":
        if attacker.item not in ("ばんのうがさ", "Utility Umbrella"):
            atk_stat_mult *= (5461 / 4096)
            _note("ひひいろのこどう ×1.33")

    if uses_attacker_special_attack and attacker.ability in ("ハドロンエンジン", "Hadron Engine") and terrain == "electric":
        atk_stat_mult *= (5461 / 4096)
        _note("ハドロンエンジン ×1.33")

    paradox_active = False
    if attacker.ability in ("こだいかっせい", "Protosynthesis"):
        paradox_active = (
            protosynthesis_active or
            weather == "sun" or
            attacker.item in ("ブーストエナジー", "Booster Energy")
        )
    elif attacker.ability in ("クォークチャージ", "Quark Drive"):
        paradox_active = (
            quark_drive_active or
            terrain == "electric" or
            attacker.item in ("ブーストエナジー", "Booster Energy")
        )
    if paradox_active:
        boosted = _paradox_boosted_stat_key(attacker)
        if boosted == "attack" and attack_source == "attacker_attack":
            atk_stat_mult *= 1.3
            _note("{} ×1.3".format(attacker.ability))
        elif boosted == "sp_attack" and attack_source == "attacker_sp_attack":
            atk_stat_mult *= 1.3
            _note("{} ×1.3".format(attacker.ability))
        elif boosted == "defense" and attack_source == "attacker_defense":
            atk_stat_mult *= 1.3
            _note("{} ×1.3".format(attacker.ability))

    # ねつぼうそう (Flare Boost): SpAtk ×1.5 when burned
    if uses_attacker_special_attack and attacker.ability == "ねつぼうそう" and attacker.status == "burn":
        atk_stat_mult *= 1.5

    # はりきり: ×1.5 physical, but accuracy −20% (ignore accuracy here)
    if uses_attacker_physical_attack and attacker.ability == "はりきり":
        atk_stat_mult *= 1.5

    atk = max(1, math.floor(atk * atk_stat_mult))
    if burn_mult < 1.0:
        _note("やけど ×0.5")

    # すなのちから: ×1.3 rock/ground/steel in sand
    sand_force_mult = 1.0
    if attacker.ability == "すなのちから" and weather == "sand":
        if effective_type in ("rock", "ground", "steel"):
            sand_force_mult = 1.3
            _note("すなのちから ×1.3")

    # ブレインフォース: ×1.25 if super-effective
    brain_force_mult = 1.0
    if attacker.ability == "ブレインフォース" and type_eff > 1.0:
        brain_force_mult = 1.25
        _note("ブレインフォース ×1.25")

    # ── Weather modifier ───────────────────────────────────────────────
    weather_mult = 1.0
    if weather == "sun":
        if effective_type == "fire":
            weather_mult = 1.5
            _note("はれ: ほのお ×1.5")
        elif effective_type == "water":
            weather_mult = 0.5
            _note("はれ: みず ×0.5")
    elif weather == "rain":
        if effective_type == "water":
            weather_mult = 1.5
            _note("あめ: みず ×1.5")
        elif effective_type == "fire":
            weather_mult = 0.5
            _note("あめ: ほのお ×0.5")

    # ── Terrain modifier ──────────────────────────────────────────────
    terrain_mult = 1.0
    if terrain == "electric" and effective_type == "electric":
        terrain_mult = 1.3
        _note("エレキフィールド ×1.3")
    elif terrain == "grassy" and effective_type == "grass":
        terrain_mult = 1.3
        _note("グラスフィールド ×1.3")
    elif terrain == "psychic" and effective_type == "psychic":
        terrain_mult = 1.3
        _note("サイコフィールド ×1.3")
    elif terrain == "misty" and effective_type == "dragon":
        terrain_mult = 0.5
        _note("ミストフィールド ×0.5")

    # ── STAB (テラスタル対応) ─────────────────────────────────────────
    atk_types = attacker.types or []
    has_original_stab = effective_type in atk_types
    has_tera_stab = bool(terastal_type and effective_type == terastal_type)
    if attacker.ability == "てきおうりょく":
        if has_original_stab and has_tera_stab:
            stab = 2.25
        elif has_original_stab or has_tera_stab:
            stab = 2.0
        else:
            stab = 1.0
    else:
        if has_original_stab and has_tera_stab:
            stab = 2.0
        elif has_original_stab or has_tera_stab:
            stab = 1.5
        else:
            stab = 1.0

    # ── フェアリーオーラ / ダークオーラ ──────────────────────────────
    aura_mult = 1.0
    if fairy_aura and effective_type == "fairy":
        aura_mult = 4 / 3
        _note("フェアリーオーラ ×1.33")
    if dark_aura and effective_type == "dark":
        aura_mult = 4 / 3
        _note("ダークオーラ ×1.33")

    # ── Critical ──────────────────────────────────────────────────────
    crit_mult = 1.5 if is_critical else 1.0

    # ── Helping hand ──────────────────────────────────────────────────
    helping_hand_mult = 1.5 if helping_hand else 1.0

    # ── Steel Spirit (steel ×1.5) ─────────────────────────────────────
    steel_spirit_mult = 1.5 if (steel_spirit and effective_type == "steel") else 1.0

    # ── Charged (electric ×2) ─────────────────────────────────────────
    charge_mult = 2.0 if (charged and effective_type == "electric") else 1.0

    # ── Screen modifier ───────────────────────────────────────────────
    screen_mult = 1.0
    screen_reduction = 2 / 3 if is_double_battle else 0.5
    if has_reflect and effective_category == "physical" and not is_critical:
        screen_mult = screen_reduction
        _note("リフレクター ×{:.2f}".format(screen_reduction))
    elif has_light_screen and effective_category == "special" and not is_critical:
        screen_mult = screen_reduction
        _note("ひかりのかべ ×{:.2f}".format(screen_reduction))

    item_atk_note = ""
    attacker_item = (attacker.item or "").strip()
    if uses_attacker_physical_attack and attacker_item in ("こだわりハチマキ", "Choice Band"):
        atk = max(1, math.floor(atk * 1.5))
        item_atk_note = "こだわりハチマキ ×1.5"
    elif uses_attacker_special_attack and attacker_item in ("こだわりメガネ", "Choice Specs"):
        atk = max(1, math.floor(atk * 1.5))
        item_atk_note = "こだわりメガネ ×1.5"
    if item_atk_note:
        _note(item_atk_note)

    item_final_mult, item_notes = _item_final_multiplier(
        attacker_item, move, effective_type, effective_category, type_eff
    )
    for n in item_notes:
        _note(n)

    # ── Compute base damage ───────────────────────────────────────────
    base = _base_damage(effective_power, atk, def_)

    # Random factor must be applied inside the modifier chain (85..100%),
    # not as a final post-scale from max damage, otherwise low roll can be +1 high.
    def _roll_damage(rand_mult: float) -> int:
        return _apply_chain(
            base,
            crit_mult,
            weather_mult,
            terrain_mult,
            rand_mult,
            stab,
            type_eff,
            burn_mult,
            sand_force_mult,
            brain_force_mult,
            screen_mult,
            helping_hand_mult,
            steel_spirit_mult,
            charge_mult,
            aura_mult,
            item_final_mult,
        )

    max_base = _roll_damage(1.0)
    min_base = _roll_damage(0.85)

    # ── Defender ability post-calculation ─────────────────────────────
    # ハードロック / フィルター / プリズムアーマー: ×0.75 for super-effective
    if effective_def_ability in ("ハードロック", "フィルター", "プリズムアーマー") and type_eff > 1.0:
        max_base = math.floor(max_base * 0.75)
        min_base = math.floor(min_base * 0.75)
        _note("{} ×0.75".format(effective_def_ability))

    if friend_guard:
        max_base = math.floor(max_base * 0.75)
        min_base = math.floor(min_base * 0.75)
        _note("フレンドガード ×0.75")

    # マルチスケイル / ファントムガード: ×0.5 at full HP
    cur_hp = defender_current_hp if defender_current_hp > 0 else defender_hp
    at_full_hp = defender_hp > 0 and cur_hp >= defender_hp
    if effective_def_ability in ("マルチスケイル", "ファントムガード") and at_full_hp:
        max_base = math.floor(max_base * 0.5)
        min_base = math.floor(min_base * 0.5)
        _note("{} ×0.5".format(effective_def_ability))

    # もふもふ: contact moves ×2, fire ×0.5
    if effective_def_ability in ("もふもふ", "ふわふわ"):
        if move.makes_contact or move.name_ja in CONTACT_MOVES_JA:
            max_base = max_base * 2
            min_base = min_base * 2
            _note("{} 接触補正 ×2".format(effective_def_ability))
        if effective_type == "fire":
            max_base = math.floor(max_base * 0.5)
            min_base = math.floor(min_base * 0.5)
            _note("{} ほのお半減 ×0.5".format(effective_def_ability))

    # あついしぼう: fire / ice damage halved
    if effective_def_ability == "あついしぼう" and effective_type in ("fire", "ice"):
        max_base = math.floor(max_base * 0.5)
        min_base = math.floor(min_base * 0.5)
        _note("あついしぼう ×0.5")
    if effective_def_ability in ("きよめのしお", "Purifying Salt") and effective_type == "ghost":
        max_base = math.floor(max_base * 0.5)
        min_base = math.floor(min_base * 0.5)
        _note("きよめのしお ×0.5")
    if effective_def_ability in ("すいほう", "Water Bubble") and effective_type == "fire":
        max_base = math.floor(max_base * 0.5)
        min_base = math.floor(min_base * 0.5)
        _note("すいほう ほのお半減 ×0.5")
    if effective_def_ability in ("かんそうはだ", "Dry Skin") and effective_type == "fire":
        max_base = math.floor(max_base * 1.25)
        min_base = math.floor(min_base * 1.25)
        _note("かんそうはだ ほのお被弾 ×1.25")

    # 半減きのみ: when HP is above 50%, a resist berry halves damage
    if defender_has_berry and type_eff >= 1.0:
        max_base = math.floor(max_base * 0.5)
        min_base = math.floor(min_base * 0.5)
        _note("半減きのみ ×0.5")

    if parental_bond:
        max_base = max_base + math.floor(max_base * 0.25)
        min_base = min_base + math.floor(min_base * 0.25)

    return (min_base, max_base)


def get_damage_modifier_notes(
    attacker: PokemonInstance,
    move: MoveInfo,
    defender_hp: int,
    defender_attack: int,
    defender_defense: int,
    defender_sp_attack: int,
    defender_sp_defense: int,
    defender_types: list[str],
    **kwargs,
) -> list[str]:
    notes: list[str] = []
    calc_damage_range(
        attacker,
        move,
        defender_hp,
        defender_attack,
        defender_defense,
        defender_sp_attack,
        defender_sp_defense,
        defender_types,
        modifier_notes=notes,
        **kwargs,
    )
    return notes


def fill_stats_from_species(pokemon: PokemonInstance, species: SpeciesInfo) -> None:
    n = pokemon.nature
    if pokemon.weight_kg <= 0:
        pokemon.weight_kg = species.weight_kg
    pokemon.hp = calc_stat(
        species.base_hp, pokemon.iv_hp, pokemon.ev_hp, is_hp=True)
    pokemon.attack = calc_stat(
        species.base_attack, pokemon.iv_attack, pokemon.ev_attack,
        nature_mult=get_nature_mult(n, "attack"))
    pokemon.defense = calc_stat(
        species.base_defense, pokemon.iv_defense, pokemon.ev_defense,
        nature_mult=get_nature_mult(n, "defense"))
    pokemon.sp_attack = calc_stat(
        species.base_sp_attack, pokemon.iv_sp_attack, pokemon.ev_sp_attack,
        nature_mult=get_nature_mult(n, "sp_attack"))
    pokemon.sp_defense = calc_stat(
        species.base_sp_defense, pokemon.iv_sp_defense, pokemon.ev_sp_defense,
        nature_mult=get_nature_mult(n, "sp_defense"))
    pokemon.speed = calc_stat(
        species.base_speed, pokemon.iv_speed, pokemon.ev_speed,
        nature_mult=get_nature_mult(n, "speed"))
    if pokemon.max_hp == 0:
        pokemon.max_hp = pokemon.hp
