import math
from src.models import PokemonInstance, MoveInfo, SpeciesInfo
from src.constants import (
    TYPE_CHART, NATURES_JA, GAME_LEVEL,
    SOUND_MOVES_JA, WIND_MOVES_JA,
    DAMP_BLOCKED_MOVES_JA, BULLET_MOVES_JA,
)

_SKIN_ABILITY_TYPE: dict[str, str] = {
    "エレキスキン": "electric", "Galvanize": "electric",
    "フェアリースキン": "fairy", "Pixilate": "fairy",
    "フリーズスキン": "ice", "Refrigerate": "ice",
    "スカイスキン": "flying", "Aerilate": "flying",
    "ドラゴンスキン": "dragon", "Dragonize": "dragon",
}

# Arceus: plate item → type (さばきのつぶて)
_PLATE_TYPE: dict[str, str] = {
    "ひのたまプレート": "fire", "しずくプレート": "water", "いかずちプレート": "electric",
    "みどりのプレート": "grass", "こおりのプレート": "ice", "こぶしのプレート": "fighting",
    "もうどくプレート": "poison", "だいちのプレート": "ground", "あおぞらプレート": "flying",
    "ふしぎのプレート": "psychic", "たまむしプレート": "bug", "がんせきプレート": "rock",
    "もののけプレート": "ghost", "りゅうのプレート": "dragon", "こわもてプレート": "dark",
    "こうてつプレート": "steel", "せいれいプレート": "fairy",
}

# Silvally: memory item → type (マルチアタック)
_MEMORY_TYPE: dict[str, str] = {
    "ファイヤーメモリ": "fire", "ウォーターメモリ": "water", "エレクトロメモリ": "electric",
    "グラスメモリ": "grass", "アイスメモリ": "ice", "ファイトメモリ": "fighting",
    "ポイズンメモリ": "poison", "グラウンドメモリ": "ground", "フライングメモリ": "flying",
    "サイキックメモリ": "psychic", "バグメモリ": "bug", "ロックメモリ": "rock",
    "ゴーストメモリ": "ghost", "ドラゴンメモリ": "dragon", "ダークメモリ": "dark",
    "スチールメモリ": "steel", "フェアリーメモリ": "fairy",
}

# Weather Ball: weather → type
_WEATHER_BALL_TYPE: dict[str, str] = {
    "sun": "fire", "rain": "water", "sand": "rock", "snow": "ice", "hail": "ice",
}

_ABILITY_IMMUNITIES: dict[str, tuple[str, ...]] = {
    "ground": ("ふゆう", "Levitate", "どしょく", "Earth Eater"),
    "fire": ("もらいび", "Flash Fire", "こんがりボディ", "Well-Baked Body"),
    "water": ("かんそうはだ", "Dry Skin", "ちょすい", "Water Absorb", "よびみず", "Storm Drain"),
    "electric": ("ちくでん", "Volt Absorb", "ひらいしん", "Lightning Rod", "でんきエンジン", "Motor Drive"),
    "grass": ("そうしょく", "Sap Sipper"),
}


_RANK_TABLE: dict[int, float] = {
    -6: 2/8, -5: 2/7, -4: 2/6, -3: 2/5, -2: 2/4, -1: 2/3,
    0: 1.0, 1: 3/2, 2: 4/2, 3: 5/2, 4: 6/2, 5: 7/2, 6: 8/2,
}


# Damage panel — move type badge: resolves the actual type of a move considering
# Tera Burst, Normalize, skin abilities (Pixilate etc.), Liquid Voice,
# Judgment/Multi-Attack item types, form-dependent moves (Aura Wheel, Raging Bull,
# Revelation Dance), and Weather Ball.
def resolve_effective_move_type(
    attacker: PokemonInstance,
    move: MoveInfo,
    terastal_type: str = "",
    weather: str = "",
) -> str:
    name = move.name_ja

    # Tera Burst: uses tera type when terastallized
    if name == "テラバースト" and terastal_type and move.type_name == "normal":
        return terastal_type

    # Normalize: all moves become Normal
    if attacker.ability in ("ノーマルスキン", "Normalize"):
        return "normal"

    # Liquid Voice: sound moves become Water
    if attacker.ability in ("うるおいボイス", "Liquid Voice") and name in SOUND_MOVES_JA:
        return "water"

    # Judgment (Arceus/Multitype): type = held plate
    if name == "さばきのつぶて" and attacker.ability in ("マルチタイプ", "Multitype"):
        return _PLATE_TYPE.get(attacker.item, "normal")

    # Multi-Attack (Silvally/RKS System): type = held memory
    if name == "マルチアタック" and attacker.ability in ("ARシステム", "RKS System"):
        return _MEMORY_TYPE.get(attacker.item, "normal")

    # Aura Wheel (Morpeko): Hangry form → Dark, otherwise Electric
    if name == "オーラぐるま":
        return "dark" if "はらぺこもよう" in attacker.name_ja else "electric"

    # Raging Bull (Paldean Tauros): form determines type
    if name == "レイジングブル":
        if "(炎)" in attacker.name_ja:
            return "fire"
        if "(水)" in attacker.name_ja:
            return "water"
        return "fighting"

    # Revelation Dance (Oricorio): form determines type
    if name == "めざめるダンス":
        if "めらめら" in attacker.name_ja:
            return "fire"
        if "ぱちぱち" in attacker.name_ja:
            return "electric"
        if "ふらふら" in attacker.name_ja:
            return "psychic"
        if "まいまい" in attacker.name_ja:
            return "ghost"
        return "normal"

    # Weather Ball: type changes with weather
    if name == "ウェザーボール":
        return _WEATHER_BALL_TYPE.get(weather, "normal")

    # Skin abilities: Normal-type moves become the ability's type
    skin_type = _SKIN_ABILITY_TYPE.get(attacker.ability)
    if skin_type and move.type_name == "normal":
        return skin_type

    return move.type_name


# Damage panel — move category badge: resolves physical/special for Tera Burst and
# Photon Geyser based on which of Atk/SpA is higher after rank modifiers.
def resolve_effective_move_category(
    attacker: PokemonInstance,
    move: MoveInfo,
    atk_rank: int = 0,
    terastal_type: str = "",
) -> str:
    if move.name_ja in ("テラバースト", "フォトンゲイザー") and (terastal_type or move.name_ja == "フォトンゲイザー"):
        rank_mult = _RANK_TABLE.get(max(-6, min(6, atk_rank)), 1.0)
        return "physical" if attacker.attack * rank_mult > attacker.sp_attack * rank_mult else "special"
    return move.category


# Damage panel — type effectiveness multiplier label (×2, ×0.5, immune, etc.):
# handles ability-based nullification (Damp, Soundproof, Wonder Guard, etc.),
# Flying Press dual-type, and Freeze-Dry's water interaction.
def move_type_effectiveness(
    move: MoveInfo,
    move_type: str,
    defender_types: list[str],
    defender_ability: str = "",
    ignore_defender_ability: bool = False,
    notes: list[str] | None = None,
) -> float:
    from src.calc.modifier_notes import apply_note_rule

    ability = "" if ignore_defender_ability else defender_ability
    if ability in ("しめりけ", "Damp") and move.name_ja in DAMP_BLOCKED_MOVES_JA:
        apply_note_rule("ability_null", notes, ability=ability)
        return 0.0
    if ability in ("じょおうのいげん", "Queenly Majesty", "テイルアーマー", "Armor Tail", "ビビッドボディ", "Dazzling") and move.priority > 0:
        apply_note_rule("ability_null", notes, ability=ability)
        return 0.0
    if ability in ("ぼうおん", "Soundproof") and move.name_ja in SOUND_MOVES_JA:
        apply_note_rule("ability_null", notes, ability=ability)
        return 0.0
    if ability in ("ぼうだん", "Bulletproof") and move.name_ja in BULLET_MOVES_JA:
        apply_note_rule("ability_null", notes, ability=ability)
        return 0.0
    if ability in ("かぜのり", "Wind Rider") and move.name_ja in WIND_MOVES_JA:
        apply_note_rule("ability_null", notes, ability=ability)
        return 0.0

    ability_nulled = False

    def _single(mt: str) -> float:
        nonlocal ability_nulled
        if ability in _ABILITY_IMMUNITIES.get(mt, ()):
            ability_nulled = True
            apply_note_rule("ability_null", notes, ability=ability)
            return 0.0
        chart = TYPE_CHART.get(mt, {})
        m = 1.0
        for t in defender_types:
            if t:
                m *= chart.get(t, 1.0)
        return m

    if move.name_ja == "フライングプレス":
        mult = _single("fighting") * _single("flying")
    elif move.name_ja == "フリーズドライ" and move_type == "ice":
        chart = TYPE_CHART.get(move_type, {})
        mult = 1.0
        for t in defender_types:
            if not t:
                continue
            mult *= 2.0 if t == "water" else chart.get(t, 1.0)
    else:
        mult = _single(move_type)

    if ability == "ふしぎなまもり" and mult <= 1.0:
        apply_note_rule("ability_null", notes, ability=ability)
        return 0.0
    if mult == 0.0 and not ability_nulled:
        apply_note_rule("type_chart_null", notes)
    return mult

# Damage panel — nature multiplier used when building stat values for display and
# for passing to calc_stat; also used in the Pokémon edit dialog.
def get_nature_mult(nature_ja: str, stat: str) -> float:
    boost, reduce = NATURES_JA.get(nature_ja, (None, None))
    if boost == stat:
        return 1.1
    if reduce == stat:
        return 0.9
    return 1.0

# Damage panel / edit dialog — actual stat value shown in each stat field,
# computed from base stat, IV, EV, level, and nature multiplier.
def calc_stat(base: int, iv: int, ev: int, level: int = GAME_LEVEL,
              nature_mult: float = 1.0, is_hp: bool = False) -> int:
    inner = math.floor((2 * base + iv + ev // 4) * level / 100)
    if is_hp:
        return inner + level + 10
    return math.floor((inner + 5) * nature_mult)

# Damage panel — modifier annotation list shown below the damage range.
def get_damage_modifier_notes(
    attacker: PokemonInstance,
    move: MoveInfo,
    defender: PokemonInstance,
    **kwargs,
) -> list[str]:
    from src.calc.modifier_notes import collect_notes

    notes: list[str] = []
    terastal_type: str = kwargs.get("terastal_type", "")
    weather: str = kwargs.get("weather", "none")

    effective_type = resolve_effective_move_type(attacker, move, terastal_type, weather)
    effective_category = resolve_effective_move_category(
        attacker, move, kwargs.get("atk_rank", 0), terastal_type
    )
    type_eff = move_type_effectiveness(
        move, effective_type, defender.types,
        defender_ability=defender.ability,
        ignore_defender_ability=bool(kwargs.get("ignore_defender_ability", False)),
        notes=notes,
    )

    collect_notes(
        notes, attacker, move, defender,
        effective_type=effective_type,
        effective_category=effective_category,
        type_eff=type_eff,
        skin_type=_SKIN_ABILITY_TYPE.get(attacker.ability, ""),
        attacker_item=(attacker.item or "").strip(),
        weather=weather,
        terrain=kwargs.get("terrain", ""),
        gravity=bool(kwargs.get("gravity", False)),
        is_grounded=bool(kwargs.get("is_grounded", True)),
        defender_is_grounded=bool(kwargs.get("defender_is_grounded", True)),
        attacker_moved_first=bool(kwargs.get("attacker_moved_first", False)),
        defender_moved_first=bool(kwargs.get("defender_moved_first", False)),
        attacker_status=(attacker.status or "") if hasattr(attacker, "status") else "",
        flash_fire_active=bool(kwargs.get("flash_fire_active", False)),
        stakeout_active=bool(kwargs.get("stakeout_active", False)),
        analytic_active=bool(kwargs.get("attacker_moves_after_target", False)),
        rivalry_state=str(kwargs.get("rivalry_state", "none")),
        allies_fainted=int(kwargs.get("allies_fainted", 0)),
    )

    return notes

# Damage panel / field-effect notes — True if Pokemon is affected by ground-based fields.
# Flying-type, Levitate, Air Balloon, or Telekinesis make a Pokemon ungrounded.
def is_grounded(pokemon: PokemonInstance) -> bool:
    if "flying" in (pokemon.types or []):
        return False
    if pokemon.ability in ("ふゆう", "Levitate"):
        return False
    if (pokemon.item or "") == "ふうせん":
        return False
    return True


# Edit dialog / main window — populates all six stats on a PokemonInstance from
# a SpeciesInfo record so the UI reflects the selected species immediately.
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
