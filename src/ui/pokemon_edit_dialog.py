from __future__ import annotations

from dataclasses import dataclass
import requests
import re

from PyQt5.QtCore import QEvent, QSize, QSortFilterProxyModel, QStringListModel, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from src.constants import ABILITIES_JA, ITEMS_JA, NATURES_JA, POKEAPI_BASE, TYPE_COLORS, TYPE_EN_TO_JA
from src.data import database as db
from src.data.item_catalog import get_item_names
from src.data import zukan_client
from src.data import pokeapi_client
from src.models import MoveInfo, PokemonInstance, SpeciesInfo

_STAT_LABELS = {
    "hp": "HP",
    "attack": "こうげき",
    "defense": "ぼうぎょ",
    "sp_attack": "とくこう",
    "sp_defense": "とくぼう",
    "speed": "すばやさ",
}

_CATEGORY_LABELS = {
    "all": "すべて",
    "physical": "物理",
    "special": "特殊",
    "status": "変化",
}

_NATURE_MATRIX_ORDER = ["attack", "sp_attack", "defense", "sp_defense", "speed"]
_TYPE_SYMBOLS = {
    "normal": "普",
    "fire": "炎",
    "water": "水",
    "electric": "電",
    "grass": "草",
    "ice": "氷",
    "fighting": "闘",
    "poison": "毒",
    "ground": "地",
    "flying": "飛",
    "psychic": "超",
    "bug": "虫",
    "rock": "岩",
    "ghost": "霊",
    "dragon": "竜",
    "dark": "悪",
    "steel": "鋼",
    "fairy": "妖",
}
_TYPE_EN_TO_ZUKAN_ID = {
    "normal": 1,
    "fire": 2,
    "water": 3,
    "grass": 4,
    "electric": 5,
    "ice": 6,
    "fighting": 7,
    "poison": 8,
    "ground": 9,
    "flying": 10,
    "psychic": 11,
    "bug": 12,
    "rock": 13,
    "ghost": 14,
    "dragon": 15,
    "dark": 16,
    "steel": 17,
    "fairy": 18,
}
_TYPE_ID_TO_EN = {value: key for key, value in _TYPE_EN_TO_ZUKAN_ID.items()}
_POKEMON_RESULT_LIMIT = 120
_TYPE_ICON_CACHE: dict[tuple[str, int], QIcon] = {}
_TYPE_PNG_ICON_CACHE: dict[str, QIcon] = {}
_POKEMON_PIXMAP_CACHE: dict[tuple[str, int, int], QPixmap] = {}
_PLACEHOLDER_ICON_CACHE: dict[int, QIcon] = {}


def _pane_format_item_text(entry: PokemonPickerEntry) -> str:
    type_text = " / ".join(TYPE_EN_TO_JA.get(t, t) for t in entry.type_names)
    usage_text = "使用率{}位".format(entry.usage_rank) if entry.usage_rank else "ローカル種族"
    name = entry.display_name or entry.species_lookup_name or "?"
    dex = (entry.dex_no or "").strip()
    if dex == "0000" or not dex:
        return "{}\n{}   {}".format(name, type_text, usage_text)
    return "{}\nNo.{}   {}   {}".format(name, dex, type_text, usage_text)


def _normalize_kana(text: str) -> str:
    """カタカナをひらがなに変換してカナ区別なし比較を可能にする。"""
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ン" else c for c in text)


@dataclass(frozen=True)
class PokemonPickerEntry:
    display_name: str
    species_lookup_name: str
    name_en: str
    usage_rank: int | None
    dex_no: str
    image_url: str
    type_names: tuple[str, ...]
    is_mega: bool = False


@dataclass(frozen=True)
class FormOption:
    key: str
    label: str
    display_name: str
    species_lookup_name: str
    base_dex_no: str
    dex_no: str
    usage_name: str
    type_names: tuple[str, ...]
    is_base: bool


@dataclass(frozen=True)
class _PokeApiVarietyStats:
    name_en: str
    type_names: tuple[str, ...]
    base_hp: int
    base_attack: int
    base_defense: int
    base_sp_attack: int
    base_sp_defense: int
    base_speed: int
    weight_kg: float


_POKEAPI_SESSION = requests.Session()
_POKEAPI_SESSION.headers["User-Agent"] = "PokemonDamageCalc/1.0"
_POKEAPI_VARIETY_CACHE: dict[int, list[_PokeApiVarietyStats]] = {}
_FORM_SPECIES_CACHE: dict[str, SpeciesInfo | None] = {}
_POKEAPI_ABILITY_JA_CACHE: dict[str, str] = {}
_POKEAPI_POKEMON_ABILITY_CACHE: dict[str, list[str]] = {}

# Stats for Mega forms that exist in Smogon calc but NOT in PokeAPI
# Key: Smogon species name (as returned by smogon_mega_species()).
# Value: (name_en, type1, type2, hp, atk, def, spa, spd, spe, weight_kg)
_MEGA_POKEAPI_MISSING: dict[str, tuple] = {
    # gen9 ZA megas
    "Absol-Mega-Z":           ("absol-mega-z",           "dark",    "ghost",    65,  154, 60,  75,  60,  151, 49.0),
    "Barbaracle-Mega":        ("barbaracle-mega",         "rock",    "fighting", 72,  140, 130, 64,  106, 88,  100.0),
    "Baxcalibur-Mega":        ("baxcalibur-mega",         "dragon",  "ice",      115, 175, 117, 105, 101, 87,  315.0),
    "Chandelure-Mega":        ("chandelure-mega",         "ghost",   "fire",     60,  75,  110, 175, 110, 90,  69.6),
    "Chesnaught-Mega":        ("chesnaught-mega",         "grass",   "fighting", 88,  137, 172, 74,  115, 44,  90.0),
    "Chimecho-Mega":          ("chimecho-mega",           "psychic", "steel",    75,  50,  110, 135, 120, 65,  8.0),
    "Clefable-Mega":          ("clefable-mega",           "fairy",   "flying",   95,  80,  93,  135, 110, 70,  42.3),
    "Crabominable-Mega":      ("crabominable-mega",       "fighting","ice",      97,  157, 122, 62,  107, 33,  252.8),
    "Darkrai-Mega":           ("darkrai-mega",            "dark",    "",         70,  120, 130, 165, 130, 85,  240.0),
    "Delphox-Mega":           ("delphox-mega",            "fire",    "psychic",  75,  69,  72,  159, 125, 134, 39.0),
    "Dragalge-Mega":          ("dragalge-mega",           "poison",  "dragon",   65,  85,  105, 132, 163, 44,  100.3),
    "Dragonite-Mega":         ("dragonite-mega",          "dragon",  "flying",   91,  124, 115, 145, 125, 100, 290.0),
    "Drampa-Mega":            ("drampa-mega",             "normal",  "dragon",   78,  85,  110, 160, 116, 36,  240.5),
    "Eelektross-Mega":        ("eelektross-mega",         "electric","",         85,  145, 80,  135, 90,  80,  180.0),
    "Emboar-Mega":            ("emboar-mega",             "fire",    "fighting", 110, 148, 75,  110, 110, 75,  180.3),
    "Excadrill-Mega":         ("excadrill-mega",          "ground",  "steel",    110, 165, 100, 65,  65,  103, 60.0),
    "Falinks-Mega":           ("falinks-mega",            "fighting","",         65,  135, 135, 70,  65,  100, 99.0),
    "Feraligatr-Mega":        ("feraligatr-mega",         "water",   "dragon",   85,  160, 125, 89,  93,  78,  108.8),
    "Floette-Mega":           ("floette-mega",            "fairy",   "",         74,  85,  87,  155, 148, 102, 100.8),
    "Froslass-Mega":          ("froslass-mega",           "ice",     "ghost",    70,  80,  70,  140, 100, 120, 29.6),
    "Garchomp-Mega-Z":        ("garchomp-mega-z",         "dragon",  "",         108, 130, 85,  141, 85,  151, 99.0),
    "Glimmora-Mega":          ("glimmora-mega",           "rock",    "poison",   83,  90,  105, 150, 96,  101, 77.0),
    "Golisopod-Mega":         ("golisopod-mega",          "bug",     "steel",    75,  150, 175, 70,  120, 40,  148.0),
    "Golurk-Mega":            ("golurk-mega",             "ground",  "ghost",    89,  159, 105, 70,  105, 55,  330.0),
    "Greninja-Mega":          ("greninja-mega",           "water",   "dark",     72,  125, 77,  133, 81,  142, 40.0),
    "Hawlucha-Mega":          ("hawlucha-mega",           "fighting","flying",   78,  137, 100, 74,  93,  118, 25.0),
    "Heatran-Mega":           ("heatran-mega",            "fire",    "steel",    91,  120, 106, 175, 141, 67,  570.0),
    "Lucario-Mega-Z":         ("lucario-mega-z",          "fighting","steel",    70,  100, 70,  164, 70,  151, 49.4),
    "Magearna-Mega":          ("magearna-mega",           "steel",   "fairy",    80,  125, 115, 170, 115, 95,  248.1),
    "Magearna-Original-Mega": ("magearna-original-mega",  "steel",   "fairy",    80,  125, 115, 170, 115, 95,  248.1),
    "Malamar-Mega":           ("malamar-mega",            "dark",    "psychic",  86,  102, 88,  98,  120, 88,  69.8),
    "Meganium-Mega":          ("meganium-mega",           "grass",   "fairy",    80,  92,  115, 143, 115, 80,  201.0),
    "Meowstic-F-Mega":        ("meowstic-f-mega",         "psychic", "",         74,  48,  76,  143, 101, 124, 10.1),
    "Meowstic-M-Mega":        ("meowstic-m-mega",         "psychic", "",         74,  48,  76,  143, 101, 124, 10.1),
    "Pyroar-Mega":            ("pyroar-mega",             "fire",    "normal",   86,  88,  92,  129, 86,  126, 93.3),
    "Raichu-Mega-X":          ("raichu-mega-x",           "electric","",         60,  135, 95,  90,  95,  110, 38.0),
    "Raichu-Mega-Y":          ("raichu-mega-y",           "electric","",         60,  100, 55,  160, 80,  130, 26.0),
    "Scolipede-Mega":         ("scolipede-mega",          "bug",     "poison",   60,  140, 149, 75,  99,  62,  230.5),
    "Scovillain-Mega":        ("scovillain-mega",         "grass",   "fire",     65,  138, 85,  138, 85,  75,  22.0),
    "Scrafty-Mega":           ("scrafty-mega",            "dark",    "fighting", 65,  130, 135, 55,  135, 68,  31.0),
    "Skarmory-Mega":          ("skarmory-mega",           "steel",   "flying",   65,  140, 110, 40,  100, 110, 40.4),
    "Staraptor-Mega":         ("staraptor-mega",          "fighting","flying",   85,  140, 100, 60,  90,  110, 50.0),
    "Starmie-Mega":           ("starmie-mega",            "water",   "psychic",  60,  100, 105, 130, 105, 120, 80.0),
    "Tatsugiri-Curly-Mega":   ("tatsugiri-curly-mega",    "dragon",  "water",    68,  65,  90,  135, 125, 92,  8.0),
    "Tatsugiri-Droopy-Mega":  ("tatsugiri-droopy-mega",   "dragon",  "water",    68,  65,  90,  135, 125, 92,  8.0),
    "Tatsugiri-Stretchy-Mega":("tatsugiri-stretchy-mega", "dragon",  "water",    68,  65,  90,  135, 125, 92,  8.0),
    "Victreebel-Mega":        ("victreebel-mega",         "grass",   "poison",   80,  125, 85,  135, 95,  70,  125.5),
    "Zeraora-Mega":           ("zeraora-mega",            "electric","",         88,  157, 75,  147, 80,  153, 44.5),
    "Zygarde-Mega":           ("zygarde-mega",            "dragon",  "ground",   216, 70,  91,  216, 85,  100, 610.0),
}


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        item = (item or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _build_ranked_options(ranked: list[str], fallback: list[str]) -> tuple[list[str], int | None]:
    ranked_items = _unique(ranked)
    fallback_items = [item for item in _unique(fallback) if item not in set(ranked_items)]
    items = [""] + ranked_items + fallback_items
    separator_after = None
    if ranked_items and fallback_items:
        separator_after = 1 + len(ranked_items)
    return items, separator_after


def _filter_ranked_abilities_for_form(ranked: list[str], form_abilities: list[str]) -> list[str]:
    ranked_items = _unique(ranked)
    allowed = set(_unique(form_abilities))
    if not allowed:
        return ranked_items
    return [name for name in ranked_items if name in allowed]


def _find_nature(boost_stat: str, reduce_stat: str) -> str:
    for name, (boost, reduce) in NATURES_JA.items():
        if boost == boost_stat and reduce == reduce_stat:
            return name
    return ""



def _type_png_icon(type_name: str, icon_w: int, icon_h: int) -> QIcon:
    """PNG アイコンをアス比保持でロードする（タイプ絞り込みボタン専用）。"""
    cache_key = type_name
    if cache_key in _TYPE_PNG_ICON_CACHE:
        return _TYPE_PNG_ICON_CACHE[cache_key]
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent.parent / "assets" / "templates" / "icons" / "{}.png".format(type_name)
    pm: QPixmap | None = None
    if path.exists():
        src = QPixmap(str(path))
        if not src.isNull():
            pm = src.scaled(icon_w, icon_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    if pm is None:
        pm = QPixmap(icon_w, icon_h)
        pm.fill(Qt.transparent)
    icon = QIcon(pm)
    _TYPE_PNG_ICON_CACHE[cache_key] = icon
    return icon


def _fallback_pokemon_pixmap(label: str, width: int, height: int) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#313244"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor("#585b70"))
    painter.drawRoundedRect(1, 1, width - 2, height - 2, 10, 10)
    painter.setPen(QColor("#cdd6f4"))
    font = QFont("Yu Gothic UI", 10)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, (label or "？")[:4])
    painter.end()
    return pixmap


def _placeholder_pokemon_icon(size: int) -> QIcon:
    if size in _PLACEHOLDER_ICON_CACHE:
        return _PLACEHOLDER_ICON_CACHE[size]
    icon = QIcon(_fallback_pokemon_pixmap("?", size, size))
    _PLACEHOLDER_ICON_CACHE[size] = icon
    return icon


def _pokemon_pixmap(url: str, width: int, height: int, label: str) -> QPixmap:
    cache_key = (url, width, height)
    if cache_key in _POKEMON_PIXMAP_CACHE:
        return _POKEMON_PIXMAP_CACHE[cache_key]

    payload = zukan_client.get_cached_asset_bytes(url)
    if payload:
        source = QPixmap()
        if source.loadFromData(payload):
            scaled = source.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            _POKEMON_PIXMAP_CACHE[cache_key] = scaled
            return scaled

    fallback = _fallback_pokemon_pixmap(label, width, height)
    _POKEMON_PIXMAP_CACHE[cache_key] = fallback
    return fallback


def _estimate_ev_points(species: SpeciesInfo, stat_key: str, target_stat: int, nature: str) -> int:
    from src.calc.damage_calc import calc_stat, get_nature_mult

    if stat_key == "hp":
        base_value = species.base_hp
        is_hp = True
        nature_mult = 1.0
    else:
        base_value = getattr(species, "base_{}".format(stat_key))
        is_hp = False
        nature_mult = get_nature_mult(nature, stat_key)

    best_points = 0
    best_diff = None
    for points in range(33):
        ev_value = points * 8
        value = calc_stat(
            base_value,
            31,
            ev_value,
            is_hp=is_hp,
            nature_mult=nature_mult,
        )
        diff = abs(value - target_stat)
        score = (diff, points)
        if best_diff is None or score < best_diff:
            best_diff = score
            best_points = points
    return best_points


def _dex_sort_key(dex_no: str) -> tuple[int, int]:
    value = (dex_no or "").strip()
    if not value:
        return (9999, 0)
    if "-" in value:
        head, tail = value.split("-", 1)
        try:
            return (int(head), int(tail))
        except ValueError:
            return (9999, 0)
    try:
        return (int(value), 0)
    except ValueError:
        return (9999, 0)


def _zukan_entry_types(entry: zukan_client.ZukanPokemonEntry) -> tuple[str, ...]:
    return tuple(
        type_name
        for type_name in [
            _TYPE_ID_TO_EN.get(entry.type1_id, ""),
            _TYPE_ID_TO_EN.get(entry.type2_id, ""),
        ]
        if type_name
    )


def _pick_best_zukan_entry(
    species: SpeciesInfo,
    candidates: list[zukan_client.ZukanPokemonEntry],
) -> zukan_client.ZukanPokemonEntry | None:
    if not candidates:
        return None
    species_types = tuple(type_name for type_name in [species.type1, species.type2] if type_name)

    def score(entry: zukan_client.ZukanPokemonEntry) -> tuple[int, int, tuple[int, int]]:
        candidate_types = _zukan_entry_types(entry)
        if candidate_types == species_types or set(candidate_types) == set(species_types):
            type_penalty = 0
        elif candidate_types[:1] == species_types[:1]:
            type_penalty = 2
        else:
            type_penalty = 4
        sub_penalty = 0 if not entry.sub_name else 1
        return (type_penalty, sub_penalty, _dex_sort_key(entry.dex_no))

    return min(candidates, key=score)


# Map from any display variant → canonical picker display name
_TAUROS_DISPLAY_ALIAS: dict[str, str] = {
    "パルデアケンタロス (アクア)": "パルデアケンタロス(水)",
    "パルデアケンタロス(アクア)": "パルデアケンタロス(水)",
    "パルデアケンタロス(水)": "パルデアケンタロス(水)",
    "パルデアケンタロス (コンバット)": "パルデアケンタロス(格闘)",
    "パルデアケンタロス(コンバット)": "パルデアケンタロス(格闘)",
    "パルデアケンタロス(格闘)": "パルデアケンタロス(格闘)",
    "パルデアケンタロス (ブレイズ)": "パルデアケンタロス(炎)",
    "パルデアケンタロス(ブレイズ)": "パルデアケンタロス(炎)",
    "パルデアケンタロス(炎)": "パルデアケンタロス(炎)",
}

# Map from canonical display name → zukan sub_name token for breed Tauros forms
_TAUROS_DISPLAY_TO_ZUKAN_SUB: dict[str, str] = {
    "パルデアケンタロス(格闘)": "コンバット",
    "パルデアケンタロス(炎)": "ブレイズ",
    "パルデアケンタロス(水)": "アクア",
}

# Gender suffix ♂/♀ → display parenthesis label
_GENDER_SYMBOL_TO_LABEL: dict[str, str] = {
    "♂": "(オス)",
    "♀": "(メス)",
}
_GENDER_LABEL_TO_SYMBOL: dict[str, str] = {v: k for k, v in _GENDER_SYMBOL_TO_LABEL.items()}


def _normalize_picker_display_name(name: str) -> str:
    text = (name or "").strip()
    if not text:
        return ""

    # Normalize full-width parens first so alias lookup works regardless of paren style
    text = text.replace("（", "(").replace("）", ")")

    if text in _TAUROS_DISPLAY_ALIAS:
        return _TAUROS_DISPLAY_ALIAS[text]

    # Convert ♂/♀ suffix to (オス)/(メス) for UI display
    gender_m = re.match(r"^(.+?)([♀♂])$", text)
    if gender_m:
        return "{}{}".format(gender_m.group(1).strip(), _GENDER_SYMBOL_TO_LABEL[gender_m.group(2)])

    match = re.match(r"^(.+?)\((ヒスイ|ガラル|アローラ|パルデア)\)$", text)
    if match:
        return "{}{}".format(match.group(2), match.group(1).strip())
    return text


# Pokémon that should default to a non-base form when first selected.
# Key: base name_ja, Value: form combo index (1-based, 0 = base/通常).
_DEFAULT_FORM_INDEX: dict[str, int] = {
}

_IN_BATTLE_FORM_BASE_NAMES: set[str] = {
    "ギルガルド",
    "チェリム",
    "メロエッタ",
    "ヒヒダルマ",
    "ヒヒダルマ (ガラルのすがた)",
    "ジガルデ",
    "モルペコ",
    "コオリッポ",
    "メテノ",
    "ヨワシ",
    "イルカマン",
    "ポワルン",
}

_IN_BATTLE_FORM_KEYWORDS: tuple[str, ...] = (
    "ブレードフォルム",
    "ポジフォルム",
    "ステップフォルム",
    "ダルマモード",
    "１０％フォルム",
    "10%フォルム",
    "パーフェクトフォルム",
    "はらぺこもよう",
    "ナイスフェイス",
    "むれたすがた",
    "マイティフォルム",
    "たいようのすがた",
    "あまみずのすがた",
    "ゆきぐものすがた",
    "キョダイマックス",
)


# Base species names for which Mega evolution is NOT a same-species form option.
# The Mega is instead tied to an alternate out-of-battle form (e.g. えいえんのはな).
_MEGA_EXCLUDED_FROM_BASE: set[str] = {
    "フラエッテ",
}


def _is_same_species_form_option(base_name: str, entry: zukan_client.ZukanPokemonEntry) -> bool:
    text = "{} {} {}".format(entry.name_ja or "", entry.sub_name or "", entry.dex_no or "")
    if "メガ" in text:
        # Mega is a same-species option UNLESS it belongs to an excluded base
        # whose Mega is only accessible from a specific alternate form.
        return base_name not in _MEGA_EXCLUDED_FROM_BASE
    if any(keyword in text for keyword in _IN_BATTLE_FORM_KEYWORDS):
        return True
    return base_name in _IN_BATTLE_FORM_BASE_NAMES


# Pokémon whose names naturally contain 「メガ」 but are NOT Mega evolutions.
_MEGA_IN_NAME_NOT_MEGA_FORM: frozenset[str] = frozenset({
    "メガニウム", "メガヤンマ",
})


def _is_in_battle_form_text(text: str) -> bool:
    value = (text or "").strip()
    if not value:
        return False
    if "メガ" in value and value not in _MEGA_IN_NAME_NOT_MEGA_FORM:
        return True
    return any(keyword in value for keyword in _IN_BATTLE_FORM_KEYWORDS)


def _is_in_battle_form_name(name_ja: str) -> bool:
    return _is_in_battle_form_text(name_ja)


def _is_in_battle_form_entry(entry: zukan_client.ZukanPokemonEntry) -> bool:
    name = (entry.name_ja or "").strip()
    if name in _MEGA_IN_NAME_NOT_MEGA_FORM:
        return False
    text = "{} {} {}".format(name, entry.sub_name or "", entry.dex_no or "")
    return _is_in_battle_form_text(text)


_REGION_PREFIX_TO_SUB: dict[str, str] = {
    "アローラ": "アローラのすがた",
    "ガラル": "ガラルのすがた",
    "ヒスイ": "ヒスイのすがた",
    "パルデア": "パルデアのすがた",
}

# Map usage-scraper shorthand names → canonical name used in DB / form groups.
_USAGE_NAME_CANONICAL: dict[str, str] = {
    "フラエッテ(えいえん)":  "フラエッテ (えいえんのはな)",
    "フラエッテ (えいえん)": "フラエッテ (えいえんのはな)",
    # pokechamdb uses full-width parens + katakana breed names for Paldean Tauros;
    # species_cache uses half-width parens + kanji (from PokeAPI _BREED_SUFFIX_JA).
    "パルデアケンタロス（コンバット）": "パルデアケンタロス(格闘)",
    "パルデアケンタロス（ブレイズ）":   "パルデアケンタロス(炎)",
    "パルデアケンタロス（アクア）":     "パルデアケンタロス(水)",
}

_DEFAULT_GENDER_FORM_CANONICAL: dict[str, dict[str, str]] = {
    "イダイトウ": {
        "オス": "イダイトウ（オスのすがた）",
        "メス": "イダイトウ（メスのすがた）",
    },
    "ニャオニクス": {
        "オス": "ニャオニクス（オスのすがた）",
        "メス": "ニャオニクス（メスのすがた）",
    },
    "イエッサン": {
        "オス": "イエッサン（オスのすがた）",
        "メス": "イエッサン（メスのすがた）",
    },
    "パフュートン": {
        "オス": "パフュートン（オスのすがた）",
        "メス": "パフュートン（メスのすがた）",
    },
}


def _normalize_usage_species_name(name: str) -> str:
    text = (name or "").strip()
    if not text:
        return ""

    direct = _USAGE_NAME_CANONICAL.get(text)
    if direct:
        return direct

    normalized = text.replace("（", "(").replace("）", ")")
    direct_normalized = _USAGE_NAME_CANONICAL.get(normalized)
    if direct_normalized:
        return direct_normalized

    label_match = re.match(r"^(.+?)\((オス|メス)\)$", normalized)
    if label_match:
        base_name = label_match.group(1).strip()
        gender = label_match.group(2)
        canonical = _DEFAULT_GENDER_FORM_CANONICAL.get(base_name, {}).get(gender)
        if canonical:
            return canonical

    male_default = _DEFAULT_GENDER_FORM_CANONICAL.get(normalized, {}).get("オス")
    if male_default:
        return male_default

    return normalized


def _build_canonical_to_usage_name_map() -> dict[str, str]:
    mapping: dict[str, str] = {
        "フラエッテ (えいえんのはな)": "フラエッテ(えいえん)",
        "パルデアケンタロス(格闘)": "パルデアケンタロス（コンバット）",
        "パルデアケンタロス(炎)": "パルデアケンタロス（ブレイズ）",
        "パルデアケンタロス(水)": "パルデアケンタロス（アクア）",
    }
    for base_name, forms in _DEFAULT_GENDER_FORM_CANONICAL.items():
        male_name = forms.get("オス")
        female_name = forms.get("メス")
        if male_name:
            mapping[male_name] = base_name
        if female_name:
            mapping[female_name] = "{}(メス)".format(base_name)
    return mapping

# Reverse: canonical name → usage-scraper key (for usage_rank lookup in picker).
# Explicit map avoids dict-comprehension overwrite when multiple aliases share the same canonical value.
_CANONICAL_TO_USAGE_NAME: dict[str, str] = _build_canonical_to_usage_name_map()

_ROTOM_SUB_TO_PREFIX: dict[str, str] = {
    "ヒート": "ヒートロトム",
    "ウォッシュ": "ウォッシュロトム",
    "フロスト": "フロストロトム",
    "スピン": "スピンロトム",
    "カット": "カットロトム",
}


def _resolve_picker_zukan_entry(
    display_name: str,
    zukan_by_name: dict[str, list[zukan_client.ZukanPokemonEntry]],
) -> zukan_client.ZukanPokemonEntry | None:
    name = (display_name or "").strip()
    if not name:
        return None

    direct = [entry for entry in zukan_by_name.get(name, []) if not _is_in_battle_form_entry(entry)]
    if direct:
        return sorted(direct, key=lambda row: _dex_sort_key(row.dex_no))[0]

    normalized = name.replace("（", "(").replace("）", ")")
    match = re.match(r"^(.+?)\s*\((.+?)\)$", normalized)
    if match:
        base_name, sub_name = match.group(1).strip(), match.group(2).strip()
        candidates = [entry for entry in zukan_by_name.get(base_name, []) if not _is_in_battle_form_entry(entry)]
        exact = [entry for entry in candidates if (entry.sub_name or "").strip() == sub_name]
        if exact:
            return sorted(exact, key=lambda row: _dex_sort_key(row.dex_no))[0]
        partial = [entry for entry in candidates if sub_name and sub_name in (entry.sub_name or "")]
        if partial:
            return sorted(partial, key=lambda row: _dex_sort_key(row.dex_no))[0]

    # Name styles like "イダイトウ♀" / "ニャオニクス♂"
    gender_match = re.match(r"^(.+?)([♀♂])$", name)
    if gender_match:
        base_name = gender_match.group(1).strip()
        gender_symbol = gender_match.group(2)
        candidates = [entry for entry in zukan_by_name.get(base_name, []) if not _is_in_battle_form_entry(entry)]
        if candidates:
            marker = "メス" if gender_symbol == "♀" else "オス"
            gendered = [
                entry
                for entry in candidates
                if marker in (entry.sub_name or "") or marker in (entry.name_ja or "")
            ]
            if gendered:
                return sorted(gendered, key=lambda row: _dex_sort_key(row.dex_no))[0]
            return sorted(candidates, key=lambda row: _dex_sort_key(row.dex_no))[0]

    # Prefix-style Rotom names like "ウォッシュロトム"
    if "ロトム" in name and name != "ロトム":
        rotom_forms = {
            "ヒート": "ヒート",
            "ウォッシュ": "ウォッシュ",
            "フロスト": "フロスト",
            "スピン": "スピン",
            "カット": "カット",
        }
        candidates = [entry for entry in zukan_by_name.get("ロトム", []) if not _is_in_battle_form_entry(entry)]
        for key, sub_token in rotom_forms.items():
            if key not in name:
                continue
            matched = [entry for entry in candidates if sub_token in (entry.sub_name or "")]
            if matched:
                return sorted(matched, key=lambda row: _dex_sort_key(row.dex_no))[0]

    # Paldea breed Tauros: "パルデアケンタロス(格闘)" / "(炎)" / "(水)"
    canonical_display = _TAUROS_DISPLAY_ALIAS.get(name, name)
    tauros_sub = _TAUROS_DISPLAY_TO_ZUKAN_SUB.get(canonical_display, "")
    if tauros_sub:
        candidates = [entry for entry in zukan_by_name.get("ケンタロス", []) if not _is_in_battle_form_entry(entry)]
        matched = [entry for entry in candidates if tauros_sub in (entry.sub_name or "")]
        if matched:
            return sorted(matched, key=lambda row: _dex_sort_key(row.dex_no))[0]

    # Gender-display-label style: "イダイトウ(メス)" / "イダイトウ(オス)"
    gender_label_m = re.match(r"^(.+?)(\(オス\)|\(メス\))$", name)
    if gender_label_m:
        base_name = gender_label_m.group(1).strip()
        label = gender_label_m.group(2)
        symbol = _GENDER_LABEL_TO_SYMBOL.get(label, "")
        candidates = [entry for entry in zukan_by_name.get(base_name, []) if not _is_in_battle_form_entry(entry)]
        if candidates and symbol:
            marker = "メス" if symbol == "♀" else "オス"
            gendered = [e for e in candidates if marker in (e.sub_name or "") or marker in (e.name_ja or "")]
            if gendered:
                return sorted(gendered, key=lambda row: _dex_sort_key(row.dex_no))[0]
            return sorted(candidates, key=lambda row: _dex_sort_key(row.dex_no))[0]

    for prefix, sub_name in _REGION_PREFIX_TO_SUB.items():
        if not name.startswith(prefix):
            continue
        base_name = name[len(prefix):].strip()
        if not base_name:
            continue
        candidates = [entry for entry in zukan_by_name.get(base_name, []) if not _is_in_battle_form_entry(entry)]
        regional = [entry for entry in candidates if sub_name in (entry.sub_name or "")]
        if regional:
            return sorted(regional, key=lambda row: _dex_sort_key(row.dex_no))[0]

    return None

def _build_form_label(base_name: str, entry: zukan_client.ZukanPokemonEntry) -> str:
    if entry.name_ja and entry.name_ja != base_name:
        return entry.name_ja
    if entry.sub_name:
        return entry.sub_name
    return "フォルム {}".format(entry.dex_no)


def _build_form_display_name(base_name: str, entry: zukan_client.ZukanPokemonEntry) -> str:
    if entry.name_ja and entry.name_ja != base_name:
        return entry.name_ja
    if entry.sub_name:
        return "{} ({})".format(base_name, entry.sub_name)
    return "{} ({})".format(base_name, entry.dex_no)


def _build_form_options_by_base(species_list: list[SpeciesInfo]) -> dict[str, list[FormOption]]:
    zukan_entries = zukan_client.get_pokemon_index()
    zukan_by_name: dict[str, list[zukan_client.ZukanPokemonEntry]] = {}
    zukan_by_base_no: dict[str, list[zukan_client.ZukanPokemonEntry]] = {}
    for entry in zukan_entries:
        zukan_by_name.setdefault(entry.name_ja, []).append(entry)
        base_no = entry.base_no or (entry.dex_no.split("-", 1)[0] if entry.dex_no else "")
        if base_no:
            zukan_by_base_no.setdefault(base_no, []).append(entry)

    form_options: dict[str, list[FormOption]] = {}
    for species in species_list:
        # Skip hidden forms
        if pokeapi_client.is_form_hidden(species.species_id, species.name_en):
            continue

        base_types = tuple(type_name for type_name in [species.type1, species.type2] if type_name)
        base_match = _pick_best_zukan_entry(species, zukan_by_name.get(species.name_ja, []))
        if not base_match:
            base_match = _resolve_picker_zukan_entry(species.name_ja, zukan_by_name)
        base_dex_no = base_match.dex_no if base_match and base_match.dex_no else "{:04d}".format(species.species_id)
        base_label = "通常"
        display_name = species.name_ja
        base_option = FormOption(
            key="base",
            label=base_label,
            display_name=display_name,
            species_lookup_name=species.name_ja,
            base_dex_no=base_dex_no,
            dex_no=base_dex_no,
            usage_name=species.name_ja,
            type_names=base_types,
            is_base=True,
        )

        if not base_match:
            form_options[species.name_ja] = [base_option]
            continue

        base_no = base_match.base_no or (base_match.dex_no.split("-", 1)[0] if base_match.dex_no else "")
        variants: list[FormOption] = [base_option]
        seen_keys = {"base"}
        for entry in sorted(zukan_by_base_no.get(base_no, []), key=lambda row: _dex_sort_key(row.dex_no)):
            if entry.dex_no == base_match.dex_no:
                continue
            if "-" not in entry.dex_no and not entry.sub_name and entry.name_ja == species.name_ja:
                continue
            if not _is_same_species_form_option(species.name_ja, entry):
                continue

            key = entry.dex_no or "{}:{}".format(entry.name_ja, entry.sub_index)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            variant_types = _zukan_entry_types(entry) or base_types
            variants.append(
                FormOption(
                    key=key,
                    label=_build_form_label(species.name_ja, entry),
                    display_name=_build_form_display_name(species.name_ja, entry),
                    species_lookup_name=species.name_ja,
                    base_dex_no=base_dex_no,
                    dex_no=entry.dex_no,
                    usage_name=entry.name_ja if entry.name_ja and entry.name_ja != species.name_ja else species.name_ja,
                    type_names=variant_types,
                    is_base=False,
                )
            )
        form_options[species.name_ja] = variants
    return form_options


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _pokeapi_get_json(url: str) -> dict:
    url = (url or "").strip()
    if not url:
        return {}
    try:
        response = _POKEAPI_SESSION.get(url, timeout=15)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _fetch_pokeapi_varieties(base_species_id: int) -> list[_PokeApiVarietyStats]:
    if base_species_id in _POKEAPI_VARIETY_CACHE:
        return _POKEAPI_VARIETY_CACHE[base_species_id]

    species_payload = _pokeapi_get_json("{}/pokemon-species/{}".format(POKEAPI_BASE, base_species_id))
    varieties = species_payload.get("varieties")
    result: list[_PokeApiVarietyStats] = []
    if isinstance(varieties, list):
        for entry in varieties:
            if not isinstance(entry, dict):
                continue
            pokemon_data = entry.get("pokemon")
            if not isinstance(pokemon_data, dict):
                continue
            pokemon_url = str(pokemon_data.get("url") or "").strip()
            pokemon_name = str(pokemon_data.get("name") or "").strip()
            detail = _pokeapi_get_json(pokemon_url)
            if not detail:
                continue

            type_rows = detail.get("types")
            type_names: list[str] = []
            if isinstance(type_rows, list):
                def _slot(row: dict) -> int:
                    if not isinstance(row, dict):
                        return 99
                    return _safe_int(row.get("slot"), 99)

                for type_row in sorted(type_rows, key=_slot):
                    if not isinstance(type_row, dict):
                        continue
                    type_data = type_row.get("type")
                    if not isinstance(type_data, dict):
                        continue
                    type_name = str(type_data.get("name") or "").strip()
                    if type_name:
                        type_names.append(type_name)

            stats_map: dict[str, int] = {}
            stat_rows = detail.get("stats")
            if isinstance(stat_rows, list):
                for stat_row in stat_rows:
                    if not isinstance(stat_row, dict):
                        continue
                    stat_info = stat_row.get("stat")
                    if not isinstance(stat_info, dict):
                        continue
                    stat_name = str(stat_info.get("name") or "").strip()
                    if not stat_name:
                        continue
                    stats_map[stat_name] = _safe_int(stat_row.get("base_stat"), 0)

            result.append(
                _PokeApiVarietyStats(
                    name_en=str(detail.get("name") or pokemon_name),
                    type_names=tuple(type_names),
                    base_hp=stats_map.get("hp", 0),
                    base_attack=stats_map.get("attack", 0),
                    base_defense=stats_map.get("defense", 0),
                    base_sp_attack=stats_map.get("special-attack", 0),
                    base_sp_defense=stats_map.get("special-defense", 0),
                    base_speed=stats_map.get("speed", 0),
                    weight_kg=_safe_int(detail.get("weight"), 0) / 10.0,
                )
            )

    _POKEAPI_VARIETY_CACHE[base_species_id] = result
    return result


def _pokeapi_ability_name_ja(ability_name_en: str) -> str:
    key = (ability_name_en or "").strip().lower()
    if not key:
        return ""
    if key in _POKEAPI_ABILITY_JA_CACHE:
        return _POKEAPI_ABILITY_JA_CACHE[key]

    payload = _pokeapi_get_json("{}/ability/{}".format(POKEAPI_BASE, key))
    resolved = ""
    names = payload.get("names")
    if isinstance(names, list):
        for row in names:
            if not isinstance(row, dict):
                continue
            lang = row.get("language")
            if not isinstance(lang, dict):
                continue
            lang_name = str(lang.get("name") or "").strip()
            if lang_name == "ja-Hrkt":
                resolved = str(row.get("name") or "").strip()
            if lang_name == "ja":
                resolved = str(row.get("name") or "").strip()
                break
    if not resolved:
        resolved = str(payload.get("name") or key).strip()

    _POKEAPI_ABILITY_JA_CACHE[key] = resolved
    return resolved


def _pokeapi_ability_names_for_pokemon(pokemon_name_en: str) -> list[str]:
    key = (pokemon_name_en or "").strip().lower()
    if not key:
        return []
    if key in _POKEAPI_POKEMON_ABILITY_CACHE:
        return list(_POKEAPI_POKEMON_ABILITY_CACHE[key])

    payload = _pokeapi_get_json("{}/pokemon/{}".format(POKEAPI_BASE, key))
    rows = payload.get("abilities")
    parsed: list[tuple[int, int, str]] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            ability_info = row.get("ability")
            if not isinstance(ability_info, dict):
                continue
            ability_name_en = str(ability_info.get("name") or "").strip()
            if not ability_name_en:
                continue
            slot = _safe_int(row.get("slot"), 99)
            is_hidden = 1 if bool(row.get("is_hidden")) else 0
            ability_name_ja = _pokeapi_ability_name_ja(ability_name_en)
            if not ability_name_ja:
                continue
            parsed.append((is_hidden, slot, ability_name_ja))

    parsed.sort(key=lambda x: (x[0], x[1], x[2]))
    resolved = _unique([name for _, _, name in parsed])
    _POKEAPI_POKEMON_ABILITY_CACHE[key] = resolved
    return list(resolved)


def _detail_types(detail: dict) -> tuple[str, ...]:
    if not detail:
        return ()
    return tuple(
        type_name
        for type_name in [
            _TYPE_ID_TO_EN.get(_safe_int(detail.get("type_1"), 0), ""),
            _TYPE_ID_TO_EN.get(_safe_int(detail.get("type_2"), 0), ""),
        ]
        if type_name
    )


def _stat_to_rank(base_stat: int) -> int:
    # Zukan rank is 1..10; map base stat into rough deciles only for tie-break scoring.
    if base_stat <= 0:
        return 1
    return max(1, min(10, int(round((base_stat - 1) / 25.0)) + 1))


def _resolve_form_species_from_pokeapi(base_species: SpeciesInfo, option: FormOption) -> SpeciesInfo | None:
    # Include display_name in the key so Mega and its Eternal-flower base don't collide
    # when they share the same Zukan dex_no (Mega derives from Eternal form).
    cache_key = "{}|{}|{}".format(
        base_species.species_id, option.dex_no or option.key, option.display_name or ""
    )
    if cache_key in _FORM_SPECIES_CACHE:
        return _FORM_SPECIES_CACHE[cache_key]

    detail = zukan_client.get_pokemon_detail(option.dex_no)
    target_types = option.type_names or _detail_types(detail)
    target_weight = _safe_float(detail.get("omosa"), 0.0)
    is_mega = _safe_int(detail.get("mega_flg"), 0) > 0
    is_primal = _safe_int(detail.get("genshi_flg"), 0) > 0
    is_gmax = _safe_int(detail.get("kyodai_flg"), 0) > 0
    target_ranks = (
        _safe_int(detail.get("spec_hp"), 0),
        _safe_int(detail.get("spec_kougeki"), 0),
        _safe_int(detail.get("spec_bougyo"), 0),
        _safe_int(detail.get("spec_tokukou"), 0),
        _safe_int(detail.get("spec_tokubou"), 0),
        _safe_int(detail.get("spec_subayasa"), 0),
    )

    varieties = _fetch_pokeapi_varieties(base_species.species_id)
    if not varieties:
        _FORM_SPECIES_CACHE[cache_key] = None
        return None

    def score(candidate: _PokeApiVarietyStats) -> tuple[int, int, int, float, int, str]:
        candidate_name = (candidate.name_en or "").lower()
        if is_mega:
            flag_penalty = 0 if "mega" in candidate_name else 8
        elif is_primal:
            flag_penalty = 0 if "primal" in candidate_name else 8
        elif is_gmax:
            flag_penalty = 0 if "gmax" in candidate_name else 8
        else:
            flag_penalty = 0

        candidate_types = candidate.type_names
        if target_types:
            if candidate_types == target_types:
                type_penalty = 0
            elif set(candidate_types) == set(target_types):
                type_penalty = 1
            elif set(candidate_types) & set(target_types):
                type_penalty = 3
            else:
                type_penalty = 6
        else:
            type_penalty = 0

        rank_penalty = 0
        if any(target_ranks):
            candidate_ranks = (
                _stat_to_rank(candidate.base_hp),
                _stat_to_rank(candidate.base_attack),
                _stat_to_rank(candidate.base_defense),
                _stat_to_rank(candidate.base_sp_attack),
                _stat_to_rank(candidate.base_sp_defense),
                _stat_to_rank(candidate.base_speed),
            )
            rank_penalty = sum(
                abs(cand_rank - target_rank)
                for cand_rank, target_rank in zip(candidate_ranks, target_ranks)
                if target_rank > 0
            )

        if target_weight > 0:
            if candidate.weight_kg > 0:
                weight_penalty = abs(candidate.weight_kg - target_weight)
            else:
                weight_penalty = 200.0
        else:
            weight_penalty = 0.0

        base_name_penalty = 0
        if candidate.name_en == base_species.name_en:
            base_name_penalty = 3

        return (
            flag_penalty,
            type_penalty,
            rank_penalty,
            weight_penalty,
            base_name_penalty,
            candidate.name_en,
        )

    chosen = min(varieties, key=score)
    chosen_types = target_types or chosen.type_names
    if not chosen_types:
        chosen_types = tuple(type_name for type_name in [base_species.type1, base_species.type2] if type_name)

    # When no PokeAPI variety contains "mega" but the form display name indicates a Mega
    # (including unreleased Mega evolutions absent from PokeAPI), use hardcoded stats.
    # Do NOT rely on mega_flg from Zukan as it may be unset for custom / fan-game forms.
    from src.calc.smogon_bridge import smogon_mega_species
    smogon_name = smogon_mega_species(base_species.name_en, option.display_name)
    if smogon_name in _MEGA_POKEAPI_MISSING and "mega" not in (chosen.name_en or "").lower():
        fallback = _MEGA_POKEAPI_MISSING.get(smogon_name)
        if fallback:
            fb_name_en, fb_t1, fb_t2, fb_hp, fb_atk, fb_def, fb_spa, fb_spd, fb_spe, fb_wt = fallback
            fb_types = tuple(t for t in (fb_t1, fb_t2) if t)
            resolved = SpeciesInfo(
                species_id=base_species.species_id,
                name_ja=option.display_name or base_species.name_ja,
                name_en=fb_name_en,
                type1=fb_types[0] if len(fb_types) >= 1 else base_species.type1,
                type2=fb_types[1] if len(fb_types) >= 2 else "",
                base_hp=fb_hp, base_attack=fb_atk, base_defense=fb_def,
                base_sp_attack=fb_spa, base_sp_defense=fb_spd, base_speed=fb_spe,
                weight_kg=fb_wt,
            )
            _FORM_SPECIES_CACHE[cache_key] = resolved
            return resolved

    resolved = SpeciesInfo(
        species_id=base_species.species_id,
        name_ja=option.display_name or base_species.name_ja,
        name_en=chosen.name_en or base_species.name_en,
        type1=chosen_types[0] if len(chosen_types) >= 1 else base_species.type1,
        type2=chosen_types[1] if len(chosen_types) >= 2 else "",
        base_hp=chosen.base_hp or base_species.base_hp,
        base_attack=chosen.base_attack or base_species.base_attack,
        base_defense=chosen.base_defense or base_species.base_defense,
        base_sp_attack=chosen.base_sp_attack or base_species.base_sp_attack,
        base_sp_defense=chosen.base_sp_defense or base_species.base_sp_defense,
        base_speed=chosen.base_speed or base_species.base_speed,
        weight_kg=chosen.weight_kg if chosen.weight_kg > 0 else (target_weight or base_species.weight_kg),
    )
    _FORM_SPECIES_CACHE[cache_key] = resolved
    return resolved


def _build_pokemon_picker_entries() -> list[PokemonPickerEntry]:
    usage_ranks = db.get_species_usage_rank_map()
    species_list = db.get_all_species()

    zukan_entries = zukan_client.get_pokemon_index()
    zukan_by_name: dict[str, list[zukan_client.ZukanPokemonEntry]] = {}
    for entry in zukan_entries:
        zukan_by_name.setdefault(entry.name_ja, []).append(entry)

    result: list[PokemonPickerEntry] = []
    added_names: set[str] = set()

    for species in species_list:
        # Skip species with no Japanese name or placeholder entries
        if not (species.name_ja and species.name_ja.strip()):
            continue
        # Some invalid entries use a single question mark as a placeholder
        if species.name_ja.strip() == "?":
            continue
        if _is_in_battle_form_name(species.name_ja):
            continue
        # Skip hidden forms
        if pokeapi_client.is_form_hidden(species.species_id, species.name_en):
            continue

        match = _pick_best_zukan_entry(species, zukan_by_name.get(species.name_ja, []))
        if not match:
            match = _resolve_picker_zukan_entry(species.name_ja, zukan_by_name)
        if match and _is_in_battle_form_entry(match):
            non_battle_matches = [entry for entry in zukan_by_name.get(species.name_ja, []) if not _is_in_battle_form_entry(entry)]
            if non_battle_matches:
                match = _pick_best_zukan_entry(species, non_battle_matches)
        fallback_dex = ""
        if species.species_id and 0 < species.species_id < 10000:
            fallback_dex = "{:04d}".format(species.species_id)
        display_name = _normalize_picker_display_name(species.name_ja)
        if display_name in added_names:
            continue
        result.append(
            PokemonPickerEntry(
                display_name=display_name,
                species_lookup_name=species.name_ja,
                name_en=species.name_en,
                usage_rank=usage_ranks.get(species.name_ja)
                    or usage_ranks.get(species.name_ja.replace("（", "(").replace("）", ")"))
                    or usage_ranks.get(_CANONICAL_TO_USAGE_NAME.get(species.name_ja, "")),
                dex_no=match.dex_no if match and match.dex_no else fallback_dex,
                image_url=match.image_small_url if match else "",
                type_names=tuple(type_name for type_name in [species.type1, species.type2] if type_name),
                is_mega=False,
            )
        )
        added_names.add(display_name)

    # Add entries for usage-ranked Pokemon that are not in species_cache.
    # This covers regional forms (e.g. アローラキュウコン) whose PokeAPI data
    # hasn't been fetched yet, but whose name appears in the usage ranking.
    for usage_name in usage_ranks:
        if not usage_name:
            continue
        if _is_in_battle_form_name(usage_name):
            continue
        # Normalize usage-scraper shorthand names to canonical display names.
        usage_name = _normalize_usage_species_name(usage_name)
        zukan_entry = _resolve_picker_zukan_entry(usage_name, zukan_by_name)
        type_names: tuple[str, ...] = ()
        lookup_name = usage_name
        resolved_name_en = ""
        if zukan_entry:
            type_names = _zukan_entry_types(zukan_entry)
            candidate_names = [usage_name, zukan_entry.name_ja]
            sub_name = (zukan_entry.sub_name or "").strip()
            if zukan_entry.name_ja == "ロトム":
                for token, alias_name in _ROTOM_SUB_TO_PREFIX.items():
                    if token in sub_name:
                        candidate_names.append(alias_name)
                        break
            for prefix, region_sub_name in _REGION_PREFIX_TO_SUB.items():
                if region_sub_name in sub_name:
                    candidate_names.append("{}{}".format(prefix, zukan_entry.name_ja))
                    break
            for candidate in _unique(candidate_names):
                # Do not collapse a form-specific usage name (e.g. ヒートロトム) onto
                # the plain base species (e.g. ロトム). Only accept a DB hit when the
                # candidate is the usage_name itself or a known form alias — not
                # when it is merely the zukan base-name for a different form.
                if candidate == zukan_entry.name_ja and candidate != usage_name:
                    continue
                species = db.get_species_by_name_ja(candidate)
                if species:
                    lookup_name = species.name_ja
                    resolved_name_en = species.name_en
                    if not type_names:
                        type_names = tuple(type_name for type_name in [species.type1, species.type2] if type_name)
                    break
        display_name = _normalize_picker_display_name(lookup_name if lookup_name else usage_name)
        if display_name in added_names:
            continue
        result.append(
            PokemonPickerEntry(
                display_name=display_name,
                species_lookup_name=lookup_name,
                name_en=resolved_name_en,
                usage_rank=usage_ranks[usage_name],
                dex_no=zukan_entry.dex_no if zukan_entry and zukan_entry.dex_no else "",
                image_url=zukan_entry.image_small_url if zukan_entry else "",
                type_names=type_names,
                is_mega=False,
            )
        )
        added_names.add(display_name)

    return result


def _best_text_color(background_hex: str) -> str:
    value = (background_hex or "").strip().lstrip("#")
    if len(value) != 6:
        return "#ffffff"
    try:
        red = int(value[0:2], 16)
        green = int(value[2:4], 16)
        blue = int(value[4:6], 16)
    except ValueError:
        return "#ffffff"
    luma = (0.299 * red) + (0.587 * green) + (0.114 * blue)
    return "#11111b" if luma > 160 else "#ffffff"


class _KanaInsensitiveProxyModel(QSortFilterProxyModel):
    """カタカナ/ひらがなを区別しない部分一致フィルタ。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pattern = ""

    def set_filter_pattern(self, pattern: str) -> None:
        self._pattern = _normalize_kana(pattern.lower())
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        if not self._pattern:
            return True
        item = self.sourceModel().data(self.sourceModel().index(source_row, 0, source_parent), Qt.DisplayRole) or ""
        return self._pattern in _normalize_kana(item.lower())


class ArrowComboBox(QComboBox):
    pass


class SuggestComboBox(ArrowComboBox):
    def __init__(self, items: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMaxVisibleItems(20)
        self.lineEdit().setClearButtonEnabled(True)
        self.set_items(items or [])

    def _apply_completer(self, items: list[str]) -> None:
        source_model = QStringListModel([item for item in items if item], self)
        proxy = _KanaInsensitiveProxyModel(self)
        proxy.setSourceModel(source_model)
        completer = QCompleter(proxy, self)
        completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        completer.setMaxVisibleItems(20)
        self.setCompleter(completer)
        self.lineEdit().textEdited.connect(lambda text, p=proxy, c=completer: (p.set_filter_pattern(text), c.complete() if text else None))

    def set_items(
        self,
        items: list[str],
        preserve_text: bool = True,
        separator_after: int | None = None,
    ) -> None:
        current = self.current_text_stripped()
        self.blockSignals(True)
        self.clear()
        self.addItems(items)
        if separator_after is not None and 0 < separator_after < self.count():
            self.insertSeparator(separator_after)
        self._apply_completer(items)
        self.blockSignals(False)
        if preserve_text:
            self.set_text(current)
        elif items:
            self.setCurrentIndex(0)

    def current_text_stripped(self) -> str:
        return self.currentText().strip()

    def set_text(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            self.setEditText("")
            return
        index = self.findText(text)
        if index >= 0:
            self.setCurrentIndex(index)
        else:
            self.setEditText(text)


class ChipButton(QPushButton):
    def __init__(self, text: str, checked_color: str = "#89b4fa", parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self._checked_color = checked_color
        self.toggled.connect(self._update_style)
        self._update_style(self.isChecked())

    def _update_style(self, checked: bool) -> None:
        if checked:
            self.setStyleSheet(
                "QPushButton { background-color: %s; color: #11111b; font-weight: bold; "
                "border: none; border-radius: 8px; padding: 6px 10px; }" % self._checked_color
            )
        else:
            self.setStyleSheet(
                "QPushButton { background-color: #313244; color: #cdd6f4; "
                "border: 1px solid #45475a; border-radius: 8px; padding: 6px 10px; }"
            )


class TypeIconButton(QToolButton):
    # PNG: 119×26 → アイコン 110×24、ボタン 114×30
    _PNG_ICON_W = 110
    _PNG_ICON_H = 24
    _BTN_W = 114
    _BTN_H = 30

    def __init__(self, type_name: str, show_label: bool = True, parent=None):
        super().__init__(parent)
        self.type_name = type_name
        self.setCheckable(True)
        self.setText(TYPE_EN_TO_JA.get(type_name, type_name))
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon if show_label else Qt.ToolButtonIconOnly)
        self.setIcon(_type_png_icon(type_name, self._PNG_ICON_W, self._PNG_ICON_H))
        self.setIconSize(QSize(self._PNG_ICON_W, self._PNG_ICON_H))
        self.setToolTip(TYPE_EN_TO_JA.get(type_name, type_name))
        self.setFixedSize(self._BTN_W, self._BTN_H + (24 if show_label else 0))
        self.toggled.connect(self._update_style)
        self._update_style(self.isChecked())

    def _update_style(self, checked: bool) -> None:
        border = "#f9e2af" if checked else "#45475a"
        background = "#2a2a3d" if checked else "transparent"
        self.setStyleSheet(
            "QToolButton { background-color: %s; border: 2px solid %s; border-radius: 4px; "
            "padding: 2px; color: #cdd6f4; font-size: 11px; }" % (background, border)
        )


class MoveBandRow(QWidget):
    def __init__(self, move: MoveInfo, usage_rank: int | None, parent=None):
        super().__init__(parent)
        from src.ui.damage_panel import _category_icon

        self.setStyleSheet("QWidget{background:#1b1f36;}")

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(6)

        rank_text = "" if usage_rank is None else str(usage_rank)
        self._rank_btn = QLabel(rank_text)
        self._rank_btn.setFixedSize(40, 40)
        self._rank_btn.setAlignment(Qt.AlignCenter)
        self._rank_btn.setStyleSheet(
            "QLabel{background:#1e3f14;border:1px solid #a6e3a1;border-radius:8px;"
            "color:#a6e3a1;font-size:28px;font-weight:bold;padding-bottom: 4px;}"
        )
        self._rank_btn.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(self._rank_btn)

        self._type_lbl = QLabel("")
        self._type_lbl.setFixedSize(48, 22)
        self._type_lbl.setAlignment(Qt.AlignCenter)
        from src.ui.ui_utils import type_pixmap as _type_pm
        type_pm = _type_pm(move.type_name, 48, 22)
        if type_pm:
            self._type_lbl.setPixmap(type_pm)
            self._type_lbl.setStyleSheet("QLabel{border:1px solid #45475a;border-radius:4px;}")
        else:
            type_ja = TYPE_EN_TO_JA.get(move.type_name, move.type_name)
            self._type_lbl.setText(type_ja)
            self._type_lbl.setStyleSheet(
                "QLabel{background:#45475a;border:1px solid #585b70;border-radius:4px;"
                "color:#f8f8ff;font-size:11px;font-weight:bold;}"
            )
        row.addWidget(self._type_lbl)

        self._cat_lbl = QLabel("")
        self._cat_lbl.setFixedSize(48, 22)
        self._cat_lbl.setAlignment(Qt.AlignCenter)
        self._cat_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._cat_lbl.setPixmap(_category_icon(move.category, 48, 22))
        row.addWidget(self._cat_lbl)

        name_lbl = QLabel(move.name_ja)
        name_lbl.setStyleSheet(
            "background:#181825;font-size:22px;font-weight:bold;color:#f8f8ff;")
        row.addWidget(name_lbl, 1)

        power_value = "---" if move.power == 0 else str(move.power)
        acc_value = "---" if move.power == 0 and move.accuracy == 100 else str(move.accuracy)
        pp_value = str(move.pp)

        stat_specs = (
            ("威力", "#D87C31", power_value),
            ("命中", "#4ECDC4", acc_value),
            ("PP", "#C678DD", pp_value),
        )
        for label_text, color, value in stat_specs:
            stat_wrap = QWidget()
            stat_wrap.setStyleSheet("QWidget{background:#181825;}")
            stat_layout = QHBoxLayout(stat_wrap)
            stat_layout.setContentsMargins(0, 0, 0, 0)
            stat_layout.setSpacing(4)

            btn = QPushButton(label_text)
            btn.setFixedSize(40, 22)
            btn.setStyleSheet(
                "QPushButton{background:#181825;border:1px solid %s;color:%s;"
                "font-weight:bold;border-radius:4px;font-size:15px;padding:0px;margin:0px;}" % (color, color)
            )
            btn.setAttribute(Qt.WA_TransparentForMouseEvents)
            stat_layout.addWidget(btn)

            value_lbl = QLabel(value)
            value_lbl.setFixedWidth(40)
            value_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
            value_lbl.setStyleSheet("background:#181825;font-size:24px;font-weight:bold;color:#f8f8ff;")
            stat_layout.addWidget(value_lbl)

            row.addWidget(stat_wrap)

        row.addSpacing(2)


class PokemonBandRow(QWidget):
    _RANK_W = 40
    _SPRITE_W = 64
    _TYPE_W = 48
    _TYPE_H = 22
    _DEX_W = 96

    def __init__(self, entry: PokemonPickerEntry, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QWidget{background:#1b1f36;}")

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(6)

        rank_text = "" if entry.usage_rank is None else str(entry.usage_rank)
        self._rank_lbl = QLabel(rank_text)
        self._rank_lbl.setFixedSize(self._RANK_W, self._RANK_W)
        self._rank_lbl.setAlignment(Qt.AlignCenter)
        font_size = "20px" if entry.usage_rank and entry.usage_rank >= 100 else "28px"
        self._rank_lbl.setStyleSheet(
            "QLabel{background:#1e3f14;border:1px solid #a6e3a1;border-radius:8px;"
            "color:#a6e3a1;font-size:%s;font-weight:bold;padding-bottom: 4px;}" % font_size
        )
        self._rank_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(self._rank_lbl)

        self._sprite_lbl = QLabel("")
        self._sprite_lbl.setFixedSize(self._SPRITE_W, self._SPRITE_W)
        self._sprite_lbl.setAlignment(Qt.AlignCenter)
        self._sprite_lbl.setPixmap(_placeholder_pokemon_icon(self._SPRITE_W).pixmap(self._SPRITE_W, self._SPRITE_W))
        self._sprite_lbl.setStyleSheet("background:#181825;")
        self._sprite_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(self._sprite_lbl)

        type_names = list(entry.type_names)
        self._type_lbl_1 = self._build_type_label(type_names[0] if len(type_names) >= 1 else "")
        self._type_lbl_2 = self._build_type_label(type_names[1] if len(type_names) >= 2 else "")
        row.addWidget(self._type_lbl_1)
        row.addWidget(self._type_lbl_2)
        row.addSpacing(5)

        name = entry.display_name or entry.species_lookup_name or "?"
        self._name_lbl = QLabel(name)
        self._name_lbl.setStyleSheet("background:#181825;font-size:22px;font-weight:bold;color:#f8f8ff;")
        self._name_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._name_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(self._name_lbl, 1)

        dex = (entry.dex_no or "").strip()
        dex_text = "" if dex in ("", "0000") else "No.{}".format(dex)
        self._dex_lbl = QLabel(dex_text)
        self._dex_lbl.setFixedWidth(self._DEX_W)
        self._dex_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self._dex_lbl.setStyleSheet("background:#181825;font-size:15px;color:#f8f8ff;padding-right:4px;")
        self._dex_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(self._dex_lbl)

    def _build_type_label(self, type_name: str) -> QLabel:
        label = QLabel("")
        label.setFixedSize(self._TYPE_W, self._TYPE_H)
        label.setAlignment(Qt.AlignCenter)
        from src.ui.ui_utils import type_pixmap as _type_pm

        type_pm = _type_pm(type_name, self._TYPE_W, self._TYPE_H) if type_name else None
        if type_pm:
            label.setPixmap(type_pm)
            label.setStyleSheet("QLabel{background:#181825;border:1px solid #45475a;border-radius:4px;}")
        elif type_name:
            type_ja = TYPE_EN_TO_JA.get(type_name, type_name)
            label.setText(type_ja)
            label.setStyleSheet(
                "QLabel{background:#181825;border:1px solid #585b70;border-radius:4px;"
                "color:#f8f8ff;font-size:11px;font-weight:bold;}"
            )
        else:
            label.setStyleSheet("QLabel{background:#181825;border:1px solid #1b1f36;border-radius:4px;}")
        label.setAttribute(Qt.WA_TransparentForMouseEvents)
        return label

    def set_sprite(self, pixmap: QPixmap) -> None:
        self._sprite_lbl.setPixmap(pixmap)


class NatureSelectDialog(QDialog):
    def __init__(self, current_nature: str, ranked_natures: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("性格を選択")
        self.setMinimumWidth(700)
        self._selected_nature = current_nature if current_nature in NATURES_JA else "まじめ"
        self._ranked_natures = ranked_natures or []
        self._build_ui()

    def _make_cell_button(self, label: str, nature: str) -> QPushButton:
        button = QPushButton(label)
        button.setMinimumHeight(44)
        if nature:
            button.clicked.connect(lambda: self._choose(nature))
        else:
            button.setEnabled(False)
            button.setText("—")
        return button

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        info = QLabel("横が上昇補正、縦が下降補正です。")
        info.setStyleSheet("color: #a6adc8;")
        layout.addWidget(info)

        grid = QGridLayout()
        grid.setHorizontalSpacing(2)
        grid.setVerticalSpacing(2)

        top_left = QLabel("")
        top_left.setFixedHeight(40)
        grid.addWidget(top_left, 0, 0)

        for col, stat_key in enumerate(_NATURE_MATRIX_ORDER, start=1):
            header = QLabel(_STAT_LABELS[stat_key])
            header.setAlignment(Qt.AlignCenter)
            header.setMinimumHeight(40)
            header.setStyleSheet(
                "background-color: #e86666; color: white; font-weight: bold; border: 1px solid #2b2d42;"
            )
            grid.addWidget(header, 0, col)

        for row, reduce_stat in enumerate(_NATURE_MATRIX_ORDER, start=1):
            row_header = QLabel(_STAT_LABELS[reduce_stat])
            row_header.setAlignment(Qt.AlignCenter)
            row_header.setMinimumHeight(40)
            row_header.setStyleSheet(
                "background-color: #6aa7ff; color: white; font-weight: bold; border: 1px solid #2b2d42;"
            )
            grid.addWidget(row_header, row, 0)

            for col, boost_stat in enumerate(_NATURE_MATRIX_ORDER, start=1):
                nature = "" if reduce_stat == boost_stat else _find_nature(boost_stat, reduce_stat)
                button = self._make_cell_button(nature or "—", nature)
                button.setStyleSheet(
                    "QPushButton { background-color: #f5f5f5; color: #11111b; border: 1px solid #555; }"
                    "QPushButton:disabled { background-color: #f0f0f0; color: #666; border: 1px solid #777; }"
                )
                grid.addWidget(button, row, col)

        layout.addLayout(grid)

        bottom_row = QHBoxLayout()

        neutral_box = QGroupBox("補正なし")
        neutral_layout = QVBoxLayout(neutral_box)
        neutral_button = QPushButton("がんばりや")
        neutral_button.setMinimumHeight(32)
        neutral_button.clicked.connect(lambda: self._choose("がんばりや"))
        neutral_layout.addWidget(neutral_button)
        neutral_box.setMaximumWidth(180)
        bottom_row.addWidget(neutral_box, 0)

        ranking_box = QGroupBox("使用率 上位4つ")
        ranking_layout = QGridLayout(ranking_box)
        for index in range(4):
            if index < len(self._ranked_natures):
                nature = self._ranked_natures[index]
                button = QPushButton("{}位\n{}".format(index + 1, nature))
                button.setMinimumHeight(52)
                button.clicked.connect(lambda _, value=nature: self._choose(value))
            else:
                button = QPushButton("{}位\n-".format(index + 1))
                button.setMinimumHeight(52)
                button.setEnabled(False)
            ranking_layout.addWidget(button, 0, index)
        bottom_row.addWidget(ranking_box, 1)
        layout.addLayout(bottom_row)

        cancel_button = QPushButton("閉じる")
        cancel_button.clicked.connect(self.reject)
        layout.addWidget(cancel_button)

    def _choose(self, nature: str) -> None:
        self._selected_nature = nature
        self.accept()

    def selected_nature(self) -> str:
        return self._selected_nature


class PokemonSelectDialog(QDialog):
    def __init__(self, current_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("ポケモンを選択")
        self.setMinimumSize(820, 920)
        self._selected_name = current_name.strip()
        self._entries = _build_pokemon_picker_entries()
        self._sort_mode = "usage"
        self._type_filters: set[str] = set()
        self._icon_job_id = 0
        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel("使用率順とタイプ条件でポケモンを選択できます。")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("名前や図鑑番号で検索")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._refresh_list)
        layout.addWidget(self._search_edit)

        # タイプ絞り込み（3列×6行グリッド）
        self._type_box = QGroupBox("タイプ絞り込み")
        type_layout = QVBoxLayout(self._type_box)
        type_layout.setContentsMargins(6, 6, 6, 6)

        type_grid = QGridLayout()
        type_grid.setHorizontalSpacing(4)
        type_grid.setVerticalSpacing(4)

        self._type_buttons: dict[str, TypeIconButton] = {}
        for index, type_en in enumerate(TYPE_EN_TO_JA):
            button = TypeIconButton(type_en, show_label=False)
            button.toggled.connect(lambda checked, value=type_en: self._on_type_toggled(value, checked))
            self._type_buttons[type_en] = button
            type_grid.addWidget(button, index // 6, index % 6)

        grid_wrap = QHBoxLayout()
        grid_wrap.setContentsMargins(0, 0, 0, 0)
        grid_wrap.addLayout(type_grid)
        grid_wrap.addStretch()
        type_layout.addLayout(grid_wrap)

        layout.addWidget(self._type_box)

        sort_row = QHBoxLayout()
        self._sort_buttons: dict[str, ChipButton] = {}
        for key, label in (
            ("usage", "採用順"),
            ("dex", "図鑑順"),
            ("name", "名前順"),
        ):
            button = ChipButton(label, "#74c7ec")
            button.clicked.connect(lambda _, value=key: self._set_sort_mode(value))
            sort_row.addWidget(button)
            self._sort_buttons[key] = button
        sort_row.addStretch()
        layout.addLayout(sort_row)

        self._result_label = QLabel("")
        self._result_label.setStyleSheet("color: #a6adc8; font-size: 14px;")
        layout.addWidget(self._result_label)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setIconSize(QSize(78, 78))
        self._list.setStyleSheet("QListWidget { font-size: 15px; }")
        self._list.itemDoubleClicked.connect(lambda *_: self._accept_selection())
        layout.addWidget(self._list, 1)

        button_row = QHBoxLayout()
        clear_button = QPushButton("未設定にする")
        clear_button.clicked.connect(self._clear_selection)
        button_row.addWidget(clear_button)
        button_row.addStretch()
        cancel_button = QPushButton("キャンセル")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        choose_button = QPushButton("選択")
        choose_button.clicked.connect(self._accept_selection)
        button_row.addWidget(choose_button)
        layout.addLayout(button_row)

        self._apply_button_state()

    def _apply_button_state(self) -> None:
        for type_en, button in self._type_buttons.items():
            button.blockSignals(True)
            button.setChecked(type_en in self._type_filters)
            button.blockSignals(False)
            button._update_style(button.isChecked())

        for key, button in self._sort_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == self._sort_mode)
            button.blockSignals(False)
            button._update_style(button.isChecked())

    def _clear_type_filters(self) -> None:
        self._type_filters.clear()
        self._apply_button_state()
        self._refresh_list()

    def _on_type_toggled(self, type_name: str, checked: bool) -> None:
        if checked:
            self._type_filters.add(type_name)
        else:
            self._type_filters.discard(type_name)
        self._apply_button_state()
        self._refresh_list()

    def _set_sort_mode(self, sort_mode: str) -> None:
        self._sort_mode = sort_mode
        self._apply_button_state()
        self._refresh_list()

    def _matches_keyword(self, entry: PokemonPickerEntry, keyword: str) -> bool:
        if not keyword:
            return True

        lowered = keyword.lower()
        normalized_number = lowered.replace("no.", "").replace("no", "").replace(".", "").strip()
        if normalized_number.isdigit():
            digits = normalized_number.lstrip("0") or "0"
            dex_digits = entry.dex_no.replace("-", "").lstrip("0") or "0"
            return digits in dex_digits

        return (
            lowered in entry.display_name.lower()
            or lowered in entry.name_en.lower()
            or lowered in entry.species_lookup_name.lower()
        )

    def _sort_key(self, entry: PokemonPickerEntry):
        if self._sort_mode == "name":
            return (entry.display_name,)
        if self._sort_mode == "dex":
            return (_dex_sort_key(entry.dex_no), entry.display_name)
        usage_missing = 0 if entry.usage_rank else 1
        usage_rank = entry.usage_rank or 9999
        return (usage_missing, usage_rank, _dex_sort_key(entry.dex_no), entry.display_name)

    def _format_item_text(self, entry: PokemonPickerEntry) -> str:
        type_text = " / ".join(TYPE_EN_TO_JA.get(type_name, type_name) for type_name in entry.type_names)
        usage_text = "使用率{}位".format(entry.usage_rank) if entry.usage_rank else "ローカル種族"
        name = entry.display_name or entry.species_lookup_name or "?"
        dex = (entry.dex_no or "").strip()
        if dex == "0000" or not dex:
            return "{}\n{}   {}".format(
                name,
                type_text,
                usage_text,
            )
        return "{}\nNo.{}   {}   {}".format(
            name,
            dex,
            type_text,
            usage_text,
        )

    def _refresh_list(self) -> None:
        keyword = self._search_edit.text().strip()
        self._list.clear()
        self._icon_job_id += 1
        current_job_id = self._icon_job_id

        filtered: list[PokemonPickerEntry] = []
        for entry in self._entries:
            if not self._matches_keyword(entry, keyword):
                continue
            if self._type_filters and not self._type_filters.issubset(set(entry.type_names)):
                continue
            filtered.append(entry)

        filtered.sort(key=self._sort_key)
        visible_entries = filtered[:_POKEMON_RESULT_LIMIT]
        if len(filtered) > len(visible_entries):
            self._result_label.setText(
                "{}件中 {}件を表示。タイプ切替後に画像を順次読み込みます。".format(
                    len(filtered),
                    len(visible_entries),
                )
            )
        else:
            self._result_label.setText("{}件".format(len(filtered)))

        selected_item: QListWidgetItem | None = None
        placeholder = _placeholder_pokemon_icon(78)
        for entry in visible_entries:
            item = QListWidgetItem(placeholder, self._format_item_text(entry))
            item.setData(Qt.UserRole, entry.display_name)
            item.setData(Qt.UserRole + 1, entry.image_url)
            item.setData(Qt.UserRole + 2, entry.display_name)
            item.setSizeHint(QSize(0, 94))
            self._list.addItem(item)
            if entry.display_name == self._selected_name:
                selected_item = item

        if selected_item:
            self._list.setCurrentItem(selected_item)
            self._list.scrollToItem(selected_item)
        elif self._list.count() > 0:
            self._list.setCurrentRow(0)

        QTimer.singleShot(0, lambda job_id=current_job_id: self._load_icons_step(job_id, 0))

    def _load_icons_step(self, job_id: int, start_index: int) -> None:
        if job_id != self._icon_job_id:
            return
        count = self._list.count()
        if start_index >= count:
            return

        end_index = min(start_index + 8, count)
        from src.ui.ui_utils import sprite_pixmap as _local_sprite
        for row in range(start_index, end_index):
            item = self._list.item(row)
            image_url = item.data(Qt.UserRole + 1) or ""
            label = item.data(Qt.UserRole + 2) or ""
            pm = _local_sprite(label, 78, 78)
            icon = QIcon(pm) if pm else QIcon(_pokemon_pixmap(image_url, 78, 78, label))
            item.setIcon(icon)

        QTimer.singleShot(0, lambda: self._load_icons_step(job_id, end_index))

    def _accept_selection(self) -> None:
        item = self._list.currentItem()
        if not item:
            QMessageBox.information(self, "情報", "ポケモンを選択してください")
            return
        self._selected_name = item.data(Qt.UserRole) or ""
        self.accept()

    def _clear_selection(self) -> None:
        self._selected_name = ""
        self.accept()

    def selected_name(self) -> str:
        return self._selected_name


class MyBoxSelectDialog(QDialog):
    """登録済みポケモン（自分PT）からポケモンを選ぶダイアログ。"""

    def __init__(self, title: str = "自分PT", parent=None):
        super().__init__(parent)
        self.setWindowTitle("{} を選択".format(title))
        self.setFixedWidth(720)
        self.setMinimumHeight(660)
        self._selected_pokemon: PokemonInstance | None = None
        self._all_entries: list[PokemonInstance] = db.load_all_pokemon()
        self._type_filters: set[str] = set()
        self._sort_mode = "updated"
        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        title_label = QLabel("登録済みポケモンから選択します。タイプ絞り込みで候補を絞れます。")
        title_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(title_label)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("名前・特性・持ち物で検索")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._refresh_list)
        layout.addWidget(self._search_edit)

        # タイプグループ
        self._type_box = QGroupBox("タイプ絞り込み")
        type_layout = QVBoxLayout(self._type_box)
        type_layout.setContentsMargins(6, 6, 6, 6)

        type_grid = QGridLayout()
        type_grid.setHorizontalSpacing(4)
        type_grid.setVerticalSpacing(4)

        self._type_buttons: dict[str, TypeIconButton] = {}
        for index, type_en in enumerate(TYPE_EN_TO_JA):
            button = TypeIconButton(type_en, show_label=False)
            button.toggled.connect(lambda checked, v=type_en: self._on_type_toggled(v, checked))
            self._type_buttons[type_en] = button
            type_grid.addWidget(button, index // 6, index % 6)

        grid_wrap = QHBoxLayout()
        grid_wrap.setContentsMargins(0, 0, 0, 0)
        grid_wrap.addLayout(type_grid)
        grid_wrap.addStretch()
        type_layout.addLayout(grid_wrap)
        layout.addWidget(self._type_box)

        # 並び順
        sort_label = QLabel("並び順：")
        sort_row = QHBoxLayout()
        sort_row.addWidget(sort_label)
        self._sort_buttons: dict[str, ChipButton] = {}
        for key, label in (("updated", "更新順"), ("name", "名前順"), ("type", "タイプ順")):
            btn = ChipButton(label, "#74c7ec")
            btn.clicked.connect(lambda _, v=key: self._set_sort_mode(v))
            sort_row.addWidget(btn)
            self._sort_buttons[key] = btn
        sort_row.addStretch()
        layout.addLayout(sort_row)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setStyleSheet("QListWidget { font-size: 14px; }")
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.itemDoubleClicked.connect(lambda *_: self._accept_selection())
        layout.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        new_btn = QPushButton("新規")
        new_btn.clicked.connect(self._new_pokemon)
        btn_row.addWidget(new_btn)
        clear_btn = QPushButton("クリア")
        clear_btn.clicked.connect(self._clear_selection)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        choose_btn = QPushButton("選択")
        choose_btn.clicked.connect(self._accept_selection)
        btn_row.addWidget(choose_btn)
        layout.addLayout(btn_row)

        self._apply_button_state()

    def _apply_button_state(self) -> None:
        for type_en, button in self._type_buttons.items():
            button.blockSignals(True)
            button.setChecked(type_en in self._type_filters)
            button.blockSignals(False)
            button._update_style(button.isChecked())

        for key, button in self._sort_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == self._sort_mode)
            button.blockSignals(False)
            button._update_style(button.isChecked())

    def _clear_type_filters(self) -> None:
        self._type_filters.clear()
        self._apply_button_state()
        self._refresh_list()

    def _on_type_toggled(self, type_name: str, checked: bool) -> None:
        if checked:
            self._type_filters.add(type_name)
        else:
            self._type_filters.discard(type_name)
        self._apply_button_state()
        self._refresh_list()

    def _set_sort_mode(self, mode: str) -> None:
        self._sort_mode = mode
        self._apply_button_state()
        self._refresh_list()

    def _get_type_names(self, p: PokemonInstance) -> list[str]:
        from src.data.database import get_species_by_id, get_species_by_name_ja
        species = get_species_by_id(p.species_id) if p.species_id else None
        if species is None and p.name_ja:
            species = get_species_by_name_ja(p.name_ja)
        if species:
            types = [species.type1] if species.type1 else []
            if species.type2:
                types.append(species.type2)
            return types
        return []

    def _sort_key(self, p: PokemonInstance):
        if self._sort_mode == "name":
            return (p.name_ja or "",)
        if self._sort_mode == "type":
            types = self._get_type_names(p)
            return (types[0] if types else "zzz", types[1] if len(types) > 1 else "zzz", p.name_ja or "")
        # updated: DB挿入順（idが大きいほど新しい）
        return (-(p.db_id or 0),)

    def _matches_keyword(self, p: PokemonInstance, keyword: str) -> bool:
        if not keyword:
            return True
        kw = keyword.lower()
        return (
            kw in (p.name_ja or "").lower()
            or kw in (p.ability or "").lower()
            or kw in (p.item or "").lower()
        )

    def _format_item_text(self, p: PokemonInstance) -> str:
        types = self._get_type_names(p)
        type_str = " / ".join(TYPE_EN_TO_JA.get(t, t) for t in types)
        parts = [p.name_ja or "?"]
        detail = []
        if type_str:
            detail.append("タイプ:{}".format(type_str))
        if p.nature:
            detail.append("性格:{}".format(p.nature))
        if p.ability:
            detail.append("特性:{}".format(p.ability))
        if p.item:
            detail.append("持ち物:{}".format(p.item))
        if detail:
            parts.append("  ".join(detail))
        return "\n".join(parts)

    def _refresh_list(self) -> None:
        keyword = self._search_edit.text().strip()
        self._list.clear()

        filtered: list[PokemonInstance] = []
        for p in self._all_entries:
            if not self._matches_keyword(p, keyword):
                continue
            if self._type_filters:
                types = set(self._get_type_names(p))
                if not self._type_filters.issubset(types):
                    continue
            filtered.append(p)

        filtered.sort(key=self._sort_key)

        for p in filtered:
            item = QListWidgetItem(self._format_item_text(p))
            item.setData(Qt.UserRole, p)
            self._list.addItem(item)

        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _accept_selection(self) -> None:
        item = self._list.currentItem()
        if not item:
            QMessageBox.information(self, "情報", "ポケモンを選択してください")
            return
        self._selected_pokemon = item.data(Qt.UserRole)
        self.accept()

    def _clear_selection(self) -> None:
        self._selected_pokemon = None
        self.accept()

    def _new_pokemon(self) -> None:
        self.reject()

    def selected_pokemon(self) -> PokemonInstance | None:
        return self._selected_pokemon


class _MoveSlotButton(QPushButton):
    """技スロットボタン：ダブルクリックまたは右クリック「クリア」でクリア。"""

    def __init__(self, slot_idx: int, dialog: "MoveSelectDialog") -> None:
        super().__init__()
        self._slot_idx = slot_idx
        self._dialog = dialog
        self.setMinimumHeight(40)
        self.setFocusPolicy(Qt.NoFocus)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self._dialog._clear_slot(self._slot_idx)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        action = menu.addAction("クリア")
        action.triggered.connect(lambda: self._dialog._clear_slot(self._slot_idx))
        menu.exec_(self.mapToGlobal(pos))


class MoveSelectDialog(QDialog):
    def __init__(
        self,
        species_id: int | None,
        pokemon_name: str,
        current_move: str = "",
        parent=None,
        usage_name: str | None = None,
        current_moves: list[str] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("技を選択")
        self.setMinimumSize(720, 760)
        self._species_id = species_id
        self._pokemon_name = pokemon_name
        self._usage_name = (usage_name or pokemon_name).strip()
        self._selected_move = current_move.strip()
        if current_moves is not None:
            self._slot_moves: list[str] = (list(current_moves) + ["", "", "", ""])[:4]
        else:
            self._slot_moves = [current_move.strip(), "", "", ""]
        self._learnset_ready = True
        self._all_moves = self._load_moves()
        self._search_only_moves = self._build_search_only_moves()
        self._usage_order = {
            name: index
            for index, name in enumerate(db.get_moves_by_usage(self._usage_name), start=1)
        }
        self._category_filter = "non_status"
        self._type_filter = ""
        self._sort_mode = "usage"
        self._tooltip_shown = False
        self._build_ui()
        self._list.viewport().installEventFilter(self)
        self._refresh_list()

    def _load_moves(self) -> list[MoveInfo]:
        if self._species_id:
            species_moves = db.get_moves_for_species(self._species_id)
            self._learnset_ready = bool(species_moves)

            move_map: dict[str, MoveInfo] = {}
            for move in species_moves:
                move_map[move.name_ja] = move

            # Learnset に無くても使用率に載っている技は候補として表示する。
            usage_moves = db.get_moves_by_usage(self._usage_name)
            learnset_names = {move.name_ja for move in species_moves}
            for move_name in usage_moves:
                if move_name in move_map:
                    continue
                if self._learnset_ready and learnset_names and move_name not in learnset_names:
                    continue
                move = db.get_move_by_name_ja(move_name)
                if move:
                    move_map[move_name] = move

            if self._selected_move and self._selected_move not in move_map:
                move = db.get_move_by_name_ja(self._selected_move)
                if move:
                    move_map[self._selected_move] = move

            for _slot_mv in self._slot_moves:
                if _slot_mv and _slot_mv not in move_map:
                    move = db.get_move_by_name_ja(_slot_mv)
                    if move:
                        move_map[_slot_mv] = move

            if move_map:
                return list(move_map.values())
        return db.get_all_moves()

    def _build_search_only_moves(self) -> list[MoveInfo]:
        """技一覧は learnset+使用率を基本にし、検索時のみそれ以外も表示する。"""
        all_moves = db.get_all_moves()
        base_names = {move.name_ja for move in self._all_moves}
        return [move for move in all_moves if move.name_ja not in base_names]

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        self._category_buttons: dict[str, ChipButton] = {}
        for key in ("all", "physical", "special", "status"):
            button = ChipButton(_CATEGORY_LABELS[key], "#89b4fa")
            button.toggled.connect(lambda checked, value=key: self._on_category_toggled(value, checked))
            title_row.addWidget(button)
            self._category_buttons[key] = button
        title_row.addStretch()
        title = QLabel("候補: {}".format(self._pokemon_name or "全技"))
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        title_row.addWidget(title)
        layout.addLayout(title_row)

        if not self._learnset_ready and self._species_id:
            hint = QLabel("learnset が未取得です。PokeAPI取得後は覚える技だけを表示します。")
            hint.setStyleSheet("color: #f9e2af; font-size: 13px;")
            layout.addWidget(hint)

        # タイプ絞り込み（4列グリッド）
        self._type_box = QGroupBox("タイプ絞り込み")
        type_layout = QVBoxLayout(self._type_box)
        type_layout.setContentsMargins(6, 6, 6, 6)

        type_grid = QGridLayout()
        type_grid.setHorizontalSpacing(4)
        type_grid.setVerticalSpacing(4)

        self._type_buttons: dict[str, TypeIconButton] = {}
        for index, type_en in enumerate(TYPE_EN_TO_JA):
            button = TypeIconButton(type_en, show_label=False)
            button.toggled.connect(lambda checked, value=type_en: self._on_type_toggled(value, checked))
            self._type_buttons[type_en] = button
            type_grid.addWidget(button, index // 6, index % 6)

        grid_wrap = QHBoxLayout()
        grid_wrap.setContentsMargins(0, 0, 0, 0)
        grid_wrap.addLayout(type_grid)
        grid_wrap.addStretch()
        type_layout.addLayout(grid_wrap)

        layout.addWidget(self._type_box)

        sort_row = QHBoxLayout()
        self._sort_buttons: dict[str, ChipButton] = {}
        for key, label in (
            ("usage", "採用順"),
            ("name", "名前順"),
            ("power", "威力順"),
            ("pp", "PP順"),
        ):
            button = ChipButton(label, "#74c7ec")
            button.clicked.connect(lambda _, value=key: self._set_sort_mode(value))
            sort_row.addWidget(button)
            self._sort_buttons[key] = button
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("わざ名で検索")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._refresh_list)
        sort_row.addWidget(self._search_edit)
        layout.addLayout(sort_row)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setStyleSheet(
            "QListWidget { font-size: 15px; }"
            "QListWidget::item { padding: 0px; margin: 0px; border-bottom: 1px solid #2b2f3f; }"
            "QListWidget::item:selected { background: #1b2a43; }"
        )
        self._list.itemDoubleClicked.connect(lambda *_: self._add_to_slot())
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_list_context_menu)
        layout.addWidget(self._list, 1)

        slot_row = QHBoxLayout()
        slot_row.setSpacing(4)
        self._slot_buttons: list[_MoveSlotButton] = []
        for i in range(4):
            btn = _MoveSlotButton(i, self)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            slot_row.addWidget(btn)
            self._slot_buttons.append(btn)
        layout.addLayout(slot_row)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(4)
        confirm_btn = QPushButton("反映")
        confirm_btn.setMinimumHeight(40)
        confirm_btn.setStyleSheet(
            "QPushButton { background-color: #89b4fa; color: #1e1e2e; font-weight: bold; "
            "font-size: 15px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #b4d0fa; }"
        )
        confirm_btn.clicked.connect(self._confirm_selection)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.setMinimumHeight(40)
        cancel_btn.setStyleSheet(
            "QPushButton { background-color: #45475a; color: #cdd6f4; font-weight: bold; font-size: 15px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #585b70; }"
        )
        cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(confirm_btn, 2)
        bottom_row.addWidget(cancel_btn, 2)
        layout.addLayout(bottom_row)

        self._apply_filter_button_state()
        self._update_slot_buttons()



    def _apply_filter_button_state(self) -> None:
        for key, button in self._category_buttons.items():
            button.blockSignals(True)
            checked = key == self._category_filter or (key == "all" and self._category_filter == "non_status")
            button.setChecked(checked)
            button.blockSignals(False)
            button._update_style(button.isChecked())

        for key, button in self._type_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == self._type_filter)
            button.blockSignals(False)
            button._update_style(button.isChecked())

        for key, button in self._sort_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == self._sort_mode)
            button.blockSignals(False)
            button._update_style(button.isChecked())

    def _on_category_toggled(self, category: str, checked: bool) -> None:
        if checked:
            self._category_filter = category
        else:
            self._category_filter = "all"
        self._apply_filter_button_state()
        self._refresh_list()

    def _clear_type_filter(self) -> None:
        self._type_filter = ""
        self._apply_filter_button_state()
        self._refresh_list()

    def _on_type_toggled(self, type_name: str, checked: bool) -> None:
        if checked:
            self._type_filter = type_name
        else:
            self._type_filter = ""
        self._apply_filter_button_state()
        self._refresh_list()

    def _set_sort_mode(self, sort_mode: str) -> None:
        self._sort_mode = sort_mode
        self._apply_filter_button_state()
        self._refresh_list()

    def _sort_key(self, move: MoveInfo):
        usage_rank = self._usage_order.get(move.name_ja, 9999)
        in_usage = 0 if move.name_ja in self._usage_order else 1
        if self._sort_mode == "name":
            return (move.name_ja,)
        if self._sort_mode == "power":
            return (-move.power, in_usage, usage_rank, move.name_ja)
        if self._sort_mode == "pp":
            return (-move.pp, in_usage, usage_rank, move.name_ja)
        return (in_usage, usage_rank, move.name_ja)

    def _refresh_list(self) -> None:
        keyword = self._search_edit.text().strip()
        normalized_kw = _normalize_kana(keyword.lower()) if keyword else ""
        self._list.clear()

        moves: list[MoveInfo] = []
        added_names: set[str] = set()
        for move in self._all_moves:
            if normalized_kw and normalized_kw not in _normalize_kana(move.name_ja.lower()):
                continue
            if self._category_filter == "non_status" and move.category == "status":
                continue
            if self._category_filter not in ("all", "non_status") and move.category != self._category_filter:
                continue
            if self._type_filter and move.type_name != self._type_filter:
                continue
            added_names.add(move.name_ja)
            moves.append(move)

        if keyword:
            for move in self._search_only_moves:
                if move.name_ja in added_names:
                    continue
                if normalized_kw not in _normalize_kana(move.name_ja.lower()):
                    continue
                if self._category_filter == "non_status" and move.category == "status":
                    continue
                if self._category_filter not in ("all", "non_status") and move.category != self._category_filter:
                    continue
                if self._type_filter and move.type_name != self._type_filter:
                    continue
                moves.append(move)

        moves.sort(key=self._sort_key)
        selected_item: QListWidgetItem | None = None
        for move in moves:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, move.name_ja)
            item.setSizeHint(QSize(0, 50))
            self._list.addItem(item)
            band = MoveBandRow(move, self._usage_order.get(move.name_ja), self._list)
            self._list.setItemWidget(item, band)
            if move.name_ja == self._selected_move:
                selected_item = item

        if selected_item:
            self._list.setCurrentItem(selected_item)
            self._list.scrollToItem(selected_item)
        # デフォルトでは無選択状態にするため、elseブロック（setCurrentRow(0)）を削除

    def _add_to_slot(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        move_name = item.data(Qt.UserRole) or ""
        if not move_name:
            return
        for i in range(4):
            if not self._slot_moves[i]:
                self._slot_moves[i] = move_name
                self._update_slot_buttons()
                return
        QMessageBox.warning(
            self, "わざスロットが満杯",
            "わざが4つすべて入っています。\n"
            "各わざボタンをダブルクリックするか、右クリックメニュー「クリア」で空きを作ってください。",
        )

    def _clear_slot(self, slot: int) -> None:
        self._slot_moves[slot] = ""
        self._update_slot_buttons()

    def _update_slot_buttons(self) -> None:
        for i, btn in enumerate(self._slot_buttons):
            name = self._slot_moves[i]
            if name:
                btn.setText(name)
                move = db.get_move_by_name_ja(name)
                if move:
                    bg = TYPE_COLORS.get(move.type_name, "#45475a")
                    text_color = _best_text_color(bg)
                    btn.setStyleSheet(
                        "QPushButton {{ background-color: {bg}; color: {tc}; border-radius: 4px; "
                        "font-weight: bold; padding: 4px 8px; }}"
                        "QPushButton:hover {{ border: 2px solid #f9e2af; }}".format(bg=bg, tc=text_color)
                    )
                else:
                    btn.setStyleSheet(
                        "QPushButton { background-color: #585b70; color: #ffffff; border-radius: 4px; "
                        "font-weight: bold; padding: 4px 8px; }"
                    )
            else:
                btn.setText("（空き）")
                btn.setStyleSheet(
                    "QPushButton { background-color: #313244; color: #585b70; border-radius: 4px; "
                    "border: 1px solid #585b70; padding: 4px 8px; }"
                )

    def _confirm_selection(self) -> None:
        self.accept()

    def _clear_selection(self) -> None:
        self._slot_moves = ["", "", "", ""]
        self._update_slot_buttons()

    def selected_move(self) -> str:
        return self._slot_moves[0]

    def selected_moves(self) -> list[str]:
        return list(self._slot_moves)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._list.viewport() and event.type() == QEvent.ToolTip:
            if not self._tooltip_shown:
                self._tooltip_shown = True
                QToolTip.showText(event.globalPos(), "ダブルクリックで技スロットに追加", self._list)
            return True
        return super().eventFilter(obj, event)

    def _on_list_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        action = menu.addAction("選択")
        action.triggered.connect(self._add_to_slot)
        menu.exec_(self._list.viewport().mapToGlobal(pos))


class PokemonEditDialog(QDialog):
    def __init__(self, pokemon=None, parent=None, save_to_db: bool = True):
        super().__init__(parent)
        self._save_to_db = save_to_db
        self._is_new_entry = pokemon is None
        self._lock_species_selector = (not save_to_db) and (pokemon is not None)
        self._auto_template_key = ""
        self._box_select_requested = False
        self.setWindowTitle("ポケモン登録 / 編集" if save_to_db else "ポケモン編集（ダメージ計算用）")
        self.setMinimumSize(1100, 794)
        self._pokemon = None  # type: PokemonInstance | None
        self._loading = False
        self._updating_stats = False
        self._selected_form_index: int = 0
        self._pane_sort_mode: str = "usage"
        self._pane_type_filters: set[str] = set()
        self._pane_icon_job_id: int = 0
        self._pane_tooltip_shown: bool = False
        self._current_nature = "がんばりや"
        self._selected_moves = ["", "", "", ""]
        self._species_list = db.get_all_species()
        self._form_options_by_base = _build_form_options_by_base(self._species_list)
        self._current_form_options: list[FormOption] = []
        self._picker_entries = _build_pokemon_picker_entries()
        self._picker_entry_map = {entry.display_name: entry for entry in self._picker_entries}
        canonical_names: list[str] = []
        for entry in self._picker_entries:
            if entry.display_name:
                canonical_names.append(entry.display_name)
        self._all_species_names = [
            name
            for name in _unique(canonical_names)
            if name and name not in _REGION_PREFIX_TO_SUB.values() and name not in ("オスのすがた", "メスのすがた", "ロトムのすがた")
        ]
        self._all_abilities = sorted(_unique(list(ABILITIES_JA)))
        self._all_items = sorted(_unique(list(ITEMS_JA) + get_item_names()))

        self._build_ui()
        self._pane_refresh_list()
        if pokemon:
            self._load(pokemon)
        else:
            self._set_form_options("")
            self._update_usage_options("")
        self._apply_species_selector_lock()

    def _combo_row(self, *widgets: QWidget) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for index, widget in enumerate(widgets):
            layout.addWidget(widget, 1 if index == 0 else 0)
        return container

    def _build_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # ── 左ペイン ──────────────────────────────────────────────────────
        left_pane = QWidget()
        left_pane.setFixedWidth(380)
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # 基本
        basic_box = QGroupBox("基本")
        basic_form = QFormLayout(basic_box)
        self.name_combo = SuggestComboBox([""] + self._all_species_names)
        self.name_combo.setPlaceholderText("名前を入力または選択")
        basic_form.addRow("名前:", self.name_combo)

        self.ability_combo = SuggestComboBox([""] + self._all_abilities)
        self.ability_combo.setPlaceholderText("特性を入力または選択")
        basic_form.addRow("特性:", self.ability_combo)

        self.item_combo = SuggestComboBox([""] + self._all_items)
        self.item_combo.setPlaceholderText("持ち物を入力または選択")
        basic_form.addRow("持ち物:", self.item_combo)
        left_layout.addWidget(basic_box)

        # 努力値/性格（スライダー形式）— 順番: 努力値→性格
        stat_box = QGroupBox("努力値/性格")
        stat_layout = QVBoxLayout(stat_box)
        stat_layout.setSpacing(4)

        self._ev_sliders: dict[str, QSlider] = {}
        self._stat_val_labels: dict[str, QLabel] = {}
        self._ev_toggle_buttons: dict[str, QPushButton] = {}
        for key, lbl_text in _STAT_LABELS.items():
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)

            stat_lbl = QLabel("{}(---)".format(lbl_text))
            stat_lbl.setFixedWidth(72)
            stat_lbl.setStyleSheet("font-size:13px;font-weight:bold;color:#cdd6f4;")
            self._stat_val_labels[key] = stat_lbl
            row.addWidget(stat_lbl)

            minus_btn = QPushButton("−")
            minus_btn.setFixedSize(24, 24)
            minus_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #f38ba8;color:#f38ba8;"
                "font-weight:bold;border-radius:3px;font-size:14px;padding:0;}"
                "QPushButton:hover{background:#3b3240;}"
            )
            row.addWidget(minus_btn)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 32)
            slider.setValue(0)
            slider.setFixedHeight(24)
            slider.valueChanged.connect(lambda _, stat_key=key: self._on_ev_changed(stat_key))
            self._ev_sliders[key] = slider
            minus_btn.clicked.connect(lambda _, s=slider: s.setValue(max(0, s.value() - 1)))

            plus_btn = QPushButton("+")
            plus_btn.setFixedSize(24, 24)
            plus_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #a6e3a1;color:#a6e3a1;"
                "font-weight:bold;border-radius:3px;font-size:14px;padding:0;}"
                "QPushButton:hover{background:#2f3c36;}"
            )
            plus_btn.clicked.connect(lambda _, s=slider: s.setValue(min(32, s.value() + 1)))

            val_lbl = QLabel("0")
            val_lbl.setFixedWidth(15)
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_lbl.setStyleSheet("font-size:13px;color:#a6adc8;font-weight:bold;")
            slider.valueChanged.connect(val_lbl.setNum)

            row.addWidget(slider, 1)
            row.addWidget(plus_btn)
            row.addWidget(val_lbl)

            toggle_btn = QPushButton("32振り")
            toggle_btn.setFixedSize(48, 24)
            toggle_btn.setStyleSheet(
                "QPushButton{font-size:13px;font-weight:bold;"
                "background:#313244;border:1px solid #89b4fa;color:#89b4fa;"
                "border-radius:3px;padding:0;}"
                "QPushButton:hover{background:#2a3452;}"
            )
            toggle_btn.clicked.connect(lambda _, s=slider: s.setValue(0 if s.value() == 32 else 32))
            row.addWidget(toggle_btn)

            stat_layout.addLayout(row)
            self._ev_toggle_buttons[key] = toggle_btn

        nature_row = QHBoxLayout()
        nature_row.setContentsMargins(0, 4, 0, 0)
        nature_row.setSpacing(4)
        nature_lbl = QLabel("性格")
        nature_lbl.setFixedWidth(72)
        nature_lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;")
        nature_row.addWidget(nature_lbl)

        self.nature_btn = QPushButton("がんばりや（補正なし）")
        self.nature_btn.setFixedHeight(32)
        self.nature_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.nature_btn.setStyleSheet(
            "QPushButton{font-size:15px;text-align:left;padding:0 6px;"
            "background:#313244;border:1px solid #45475a;border-radius:4px;}"
            "QPushButton:hover{border-color:#89b4fa;}"
        )
        self.nature_btn.clicked.connect(self._select_nature)
        nature_row.addWidget(self.nature_btn, 1)
        stat_layout.addLayout(nature_row)

        left_layout.addWidget(stat_box)

        # わざ
        move_box = QGroupBox("わざ")
        move_layout = QVBoxLayout(move_box)
        move_layout.setContentsMargins(8, 10, 8, 10)
        move_layout.setSpacing(8)
        self._move_buttons: list[QPushButton] = []
        for index in range(4):
            row_widget = QWidget()
            row_widget.setFixedHeight(42)
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            button = QPushButton("わざを選択")
            button.setMinimumHeight(36)
            button.setMaximumHeight(36)
            button.clicked.connect(lambda _, slot=index: self._open_move_dialog(slot))
            row.addWidget(button, 1)
            row.setAlignment(button, Qt.AlignVCenter)
            move_layout.addWidget(row_widget, 0, Qt.AlignTop)
            self._move_buttons.append(button)
        move_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        left_layout.addWidget(move_box)

        left_layout.addStretch()

        footer_layout = QVBoxLayout()
        footer_layout.setSpacing(4)
        footer_layout.setContentsMargins(0, 0, 0, 0)

        first_row = QHBoxLayout()
        first_row.setSpacing(4)

        if not self._save_to_db:
            box_button = QPushButton("ボックス")
            box_button.setMinimumHeight(40)
            box_button.setStyleSheet(
                "QPushButton { background-color: #45475a; color: #cdd6f4; font-weight: bold; font-size: 15px; border-radius: 6px; min-height: 40px; }"
                "QPushButton:hover { background-color: #585b70; }"
            )
            box_button.clicked.connect(self._on_box_select_clicked)
            first_row.addWidget(box_button, 1)

        cancel_button = QPushButton("キャンセル")
        cancel_button.setMinimumHeight(40)
        cancel_button.setStyleSheet(
            "QPushButton { background-color: #45475a; color: #cdd6f4; font-weight: bold; font-size: 15px; border-radius: 6px; min-height: 40px; }"
            "QPushButton:hover { background-color: #585b70; }"
        )
        cancel_button.clicked.connect(self.reject)
        first_row.addWidget(cancel_button, 1)

        footer_layout.addLayout(first_row, 1)

        second_row = QHBoxLayout()
        second_row.setSpacing(4)

        if not self._save_to_db:
            apply_button = QPushButton("反映")
            apply_button.setMinimumHeight(40)
            apply_button.setStyleSheet(
                "QPushButton { background-color: #89b4fa; color: #1e1e2e; font-weight: bold; font-size: 15px; border-radius: 6px; min-height: 40px; }"
                "QPushButton:hover { background-color: #b4d0fa; }"
            )
            apply_button.clicked.connect(self._save)
            second_row.addWidget(apply_button, 1)

            save_button = QPushButton("保存")
            save_button.setMinimumHeight(40)
            save_button.setStyleSheet(
                "QPushButton { background-color: #45475a; color: #cdd6f4; font-weight: bold; font-size: 15px; border-radius: 6px; min-height: 40px; }"
                "QPushButton:hover { background-color: #585b70; }"
            )
            save_button.clicked.connect(lambda _=False: self._save(save_to_db_override=True))
            second_row.addWidget(save_button, 1)
        else:
            save_button = QPushButton("保存")
            save_button.setMinimumHeight(40)
            save_button.setStyleSheet(
                "QPushButton { background-color: #89b4fa; color: #1e1e2e; font-weight: bold; font-size: 15px; border-radius: 6px; min-height: 40px; }"
                "QPushButton:hover { background-color: #b4d0fa; }"
            )
            save_button.clicked.connect(self._save)
            second_row.addWidget(save_button, 1)

        footer_layout.addLayout(second_row, 1)

        left_layout.addLayout(footer_layout)

        main_layout.addWidget(left_pane)

        # ── 右ペイン ──────────────────────────────────────────────────────
        right_pane = self._build_right_pane()
        main_layout.addWidget(right_pane, 1)

        self.name_combo.currentTextChanged.connect(self._on_name_changed)
        self.name_combo.currentTextChanged.connect(lambda _: self._pane_refresh_list())
        self.name_combo.lineEdit().textEdited.connect(self._on_name_manually_edited)
        self._pane_list.installEventFilter(self)
        self._set_nature("がんばりや", recalc=False)
        self._refresh_move_buttons()

    def _apply_species_selector_lock(self) -> None:
        self.name_combo.setEnabled(not self._lock_species_selector)

    # ── 右ペイン構築・操作 ──────────────────────────────────────────────

    def _build_right_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        type_box = QGroupBox("タイプ絞り込み")
        type_layout = QVBoxLayout(type_box)
        type_layout.setContentsMargins(6, 6, 6, 6)
        type_grid = QGridLayout()
        type_grid.setHorizontalSpacing(4)
        type_grid.setVerticalSpacing(4)

        self._pane_type_buttons: dict[str, TypeIconButton] = {}
        for index, type_en in enumerate(TYPE_EN_TO_JA):
            button = TypeIconButton(type_en, show_label=False)
            button.toggled.connect(lambda checked, value=type_en: self._pane_on_type_toggled(value, checked))
            self._pane_type_buttons[type_en] = button
            type_grid.addWidget(button, index // 6, index % 6)

        grid_wrap = QHBoxLayout()
        grid_wrap.setContentsMargins(0, 0, 0, 0)
        grid_wrap.addLayout(type_grid)
        grid_wrap.addStretch()
        type_layout.addLayout(grid_wrap)
        layout.addWidget(type_box)

        sort_row = QHBoxLayout()
        self._pane_sort_buttons: dict[str, ChipButton] = {}
        for sort_key, sort_label in (("usage", "採用順"), ("dex", "図鑑順"), ("name", "名前順")):
            btn = ChipButton(sort_label, "#74c7ec")
            btn.clicked.connect(lambda _, value=sort_key: self._pane_set_sort_mode(value))
            sort_row.addWidget(btn)
            self._pane_sort_buttons[sort_key] = btn
        self._pane_result_label = QLabel("")
        self._pane_result_label.setStyleSheet("color: #a6adc8; font-size: 14px;")
        sort_row.addWidget(self._pane_result_label)
        sort_row.addStretch()
        layout.addLayout(sort_row)

        self._pane_list = QListWidget()
        self._pane_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._pane_list.setStyleSheet(
            "QListWidget { font-size: 15px; }"
            "QListWidget::item { padding: 0px; margin: 0px; border-bottom: 1px solid #2b2f3f; }"
            "QListWidget::item:selected { background: #1b2a43; }"
        )
        self._pane_list.itemDoubleClicked.connect(lambda *_: self._on_pokemon_double_clicked())
        self._pane_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._pane_list.customContextMenuRequested.connect(self._on_pane_list_context_menu)
        layout.addWidget(self._pane_list, 1)

        self._pane_apply_button_state()
        return pane

    def _on_pane_list_context_menu(self, pos) -> None:
        item = self._pane_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        action = menu.addAction("選択")
        action.triggered.connect(self._on_pokemon_double_clicked)
        menu.exec_(self._pane_list.viewport().mapToGlobal(pos))

    def _pane_apply_button_state(self) -> None:
        for type_en, button in self._pane_type_buttons.items():
            button.blockSignals(True)
            button.setChecked(type_en in self._pane_type_filters)
            button.blockSignals(False)
            button._update_style(button.isChecked())

        for sort_key, button in self._pane_sort_buttons.items():
            button.blockSignals(True)
            button.setChecked(sort_key == self._pane_sort_mode)
            button.blockSignals(False)
            button._update_style(button.isChecked())

    def _pane_clear_type_filters(self) -> None:
        self._pane_type_filters.clear()
        self._pane_apply_button_state()
        self._pane_refresh_list()

    def _pane_on_type_toggled(self, type_en: str, checked: bool) -> None:
        if checked:
            self._pane_type_filters.add(type_en)
        else:
            self._pane_type_filters.discard(type_en)
        self._pane_apply_button_state()
        self._pane_refresh_list()

    def _pane_set_sort_mode(self, mode: str) -> None:
        self._pane_sort_mode = mode
        self._pane_apply_button_state()
        self._pane_refresh_list()

    def _pane_sort_key(self, entry: PokemonPickerEntry):
        if self._pane_sort_mode == "name":
            return (entry.display_name,)
        if self._pane_sort_mode == "dex":
            return (_dex_sort_key(entry.dex_no), entry.display_name)
        usage_missing = 0 if entry.usage_rank else 1
        return (usage_missing, entry.usage_rank or 9999, _dex_sort_key(entry.dex_no), entry.display_name)

    def _pane_refresh_list(self) -> None:
        keyword = self.name_combo.current_text_stripped()
        self._pane_list.clear()
        self._pane_icon_job_id += 1
        current_job_id = self._pane_icon_job_id

        filtered: list[PokemonPickerEntry] = []
        for entry in self._picker_entries:
            if keyword:
                lowered = _normalize_kana(keyword.lower())
                if not (
                    lowered in _normalize_kana(entry.display_name.lower())
                    or lowered in entry.name_en.lower()
                    or lowered in _normalize_kana(entry.species_lookup_name.lower())
                ):
                    continue
            if self._pane_type_filters and not self._pane_type_filters.issubset(set(entry.type_names)):
                continue
            filtered.append(entry)

        filtered.sort(key=self._pane_sort_key)
        visible = filtered[:_POKEMON_RESULT_LIMIT]
        if len(filtered) > len(visible):
            self._pane_result_label.setText(
                "{}件中 {}件を表示。タイプ切替後に画像を順次読み込みます。".format(len(filtered), len(visible))
            )
        else:
            self._pane_result_label.setText("{}件".format(len(filtered)))

        current_name = self.name_combo.current_text_stripped()
        selected_item = None
        for entry in visible:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, entry.display_name)
            item.setData(Qt.UserRole + 1, entry.image_url)
            item.setData(Qt.UserRole + 2, entry.display_name)
            item.setSizeHint(QSize(0, 72))
            self._pane_list.addItem(item)
            self._pane_list.setItemWidget(item, PokemonBandRow(entry, self._pane_list))
            if entry.display_name == current_name:
                selected_item = item

        if selected_item:
            self._pane_list.setCurrentItem(selected_item)
            self._pane_list.scrollToItem(selected_item)
        # デフォルトでは無選択状態にするため、elseブロック（setCurrentRow(0)）を削除

        QTimer.singleShot(0, lambda job_id=current_job_id: self._pane_load_icons_step(job_id, 0))

    def _pane_load_icons_step(self, job_id: int, start_index: int) -> None:
        if job_id != self._pane_icon_job_id:
            return
        count = self._pane_list.count()
        if start_index >= count:
            return
        end_index = min(start_index + 8, count)
        from src.ui.ui_utils import sprite_pixmap as _local_sprite
        for row in range(start_index, end_index):
            item = self._pane_list.item(row)
            image_url = item.data(Qt.UserRole + 1) or ""
            label = item.data(Qt.UserRole + 2) or ""
            pm = _local_sprite(label, 64, 64)
            sprite_pm = pm if pm else _pokemon_pixmap(image_url, 64, 64, label)
            widget = self._pane_list.itemWidget(item)
            if isinstance(widget, PokemonBandRow):
                widget.set_sprite(sprite_pm)
        QTimer.singleShot(0, lambda: self._pane_load_icons_step(job_id, end_index))

    def _on_pokemon_double_clicked(self) -> None:
        item = self._pane_list.currentItem()
        if not item:
            return
        display_name = item.data(Qt.UserRole) or ""
        # フィールドをクリアしてから反映（前の情報が残らないように）
        self._loading = True
        self.ability_combo.set_text("")
        self.item_combo.set_text("")
        self._set_nature("がんばりや", recalc=False)
        for slider in self._ev_sliders.values():
            slider.setValue(0)
        for key in self._ev_sliders:
            self._update_ev_toggle_label(key)
        self._selected_moves = ["", "", "", ""]
        self._refresh_move_buttons()
        self._loading = False
        # テンプレートが再ロードされるよう is_new_entry フラグをリセット
        self._auto_template_key = ""
        self._is_new_entry = True
        self.name_combo.set_text(display_name)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._pane_list and event.type() == QEvent.ToolTip:
            if not self._pane_tooltip_shown:
                self._pane_tooltip_shown = True
                QToolTip.showText(event.globalPos(), "ダブルクリックで反映", self._pane_list)
            return True
        return super().eventFilter(obj, event)

    def _on_name_manually_edited(self, _text: str) -> None:
        """ユーザーが名前欄を直接編集した時にタイプフィルタを全タイプに戻す。"""
        if self._pane_type_filters:
            self._pane_type_filters.clear()
            self._pane_apply_button_state()

    # ── 種族・フォーム解決 ──────────────────────────────────────────────

    def _resolve_species_lookup_name(self, display_name: str) -> str:
        name = (display_name or "").strip()
        if name in self._form_options_by_base:
            return name
        for base_name, options in self._form_options_by_base.items():
            if any(option.display_name == name for option in options):
                return base_name
        entry = self._picker_entry_map.get(name)
        if entry:
            return entry.species_lookup_name
        # Try normalized display name (e.g. ♀ → (メス) display) to find picker entry
        normalized_display = _normalize_picker_display_name(name)
        if normalized_display != name:
            entry2 = self._picker_entry_map.get(normalized_display)
            if entry2:
                return entry2.species_lookup_name
        return name

    def _resolve_loaded_form(self, stored_name: str) -> tuple[str, str | None]:
        name = (stored_name or "").strip()
        if not name:
            return "", None
        if name in self._form_options_by_base:
            return name, name
        for base_name, options in self._form_options_by_base.items():
            for option in options:
                if option.display_name == name:
                    return base_name, option.display_name
        # Also try the normalized display name (e.g. DB stores "イダイトウ♀",
        # but picker uses "イダイトウ(メス)" as display_name).
        normalized = _normalize_picker_display_name(name)
        if normalized != name:
            if normalized in self._form_options_by_base:
                return normalized, normalized
            for base_name, options in self._form_options_by_base.items():
                for option in options:
                    if option.display_name == normalized:
                        return base_name, option.display_name
        return name, None

    def _set_form_options(self, base_name: str, preferred_display_name: str | None = None) -> None:
        base_name = (base_name or "").strip()
        species = db.get_species_by_name_ja(base_name) if base_name else None
        if species:
            default_base = FormOption(
                key="base",
                label="通常",
                display_name=species.name_ja,
                species_lookup_name=species.name_ja,
                base_dex_no="{:04d}".format(species.species_id),
                dex_no="{:04d}".format(species.species_id),
                usage_name=species.name_ja,
                type_names=tuple(type_name for type_name in [species.type1, species.type2] if type_name),
                is_base=True,
            )
            options = self._form_options_by_base.get(species.name_ja, [default_base])
        else:
            options = []

        self._current_form_options = options

        # フォームインデックスを preferred_display_name または name_combo テキストから決定
        index = 0
        effective_display = preferred_display_name or self.name_combo.current_text_stripped()
        if effective_display and options:
            for idx, option in enumerate(options):
                if option.display_name == effective_display:
                    index = idx
                    break
            else:
                if not preferred_display_name and base_name in _DEFAULT_FORM_INDEX:
                    index = min(_DEFAULT_FORM_INDEX[base_name], len(options) - 1)
        elif not preferred_display_name and base_name in _DEFAULT_FORM_INDEX and options:
            index = min(_DEFAULT_FORM_INDEX[base_name], len(options) - 1)
        self._selected_form_index = index

    def _current_form_option(self) -> FormOption | None:
        if not self._current_form_options:
            return None
        index = self._selected_form_index
        if 0 <= index < len(self._current_form_options):
            return self._current_form_options[index]
        return self._current_form_options[0]

    def _usage_lookup_name(self, display_name: str) -> str:
        option = self._current_form_option()
        if option:
            name = option.usage_name
        else:
            name = self._resolve_species_lookup_name(display_name)
        # Normalize full-width parens to half-width (pokedb_tokyo uses half-width)
        return name.replace("（", "(").replace("）", ")")

    def _selected_species(self) -> SpeciesInfo | None:
        lookup_name = self._resolve_species_lookup_name(self.name_combo.current_text_stripped())
        return db.get_species_by_name_ja(lookup_name)

    def _effective_species_for_calc(self) -> SpeciesInfo | None:
        species = self._selected_species()
        if not species:
            return None
        option = self._current_form_option()
        if not option or option.is_base:
            return species

        resolved = _resolve_form_species_from_pokeapi(species, option)
        if resolved:
            return resolved

        base_detail = zukan_client.get_pokemon_detail(option.base_dex_no)
        form_detail = zukan_client.get_pokemon_detail(option.dex_no)
        if not base_detail or not form_detail:
            return species

        def rank(detail: dict, key: str) -> int:
            try:
                return int(detail.get(key) or 0)
            except Exception:
                return 0

        def scaled(base_value: int, base_rank: int, form_rank: int) -> int:
            if base_value <= 0 or base_rank <= 0 or form_rank <= 0:
                return base_value
            value = int(round(base_value * (form_rank / float(base_rank))))
            return max(1, min(255, value))

        base_hp_rank = rank(base_detail, "spec_hp")
        base_attack_rank = rank(base_detail, "spec_kougeki")
        base_defense_rank = rank(base_detail, "spec_bougyo")
        base_sp_attack_rank = rank(base_detail, "spec_tokukou")
        base_sp_defense_rank = rank(base_detail, "spec_tokubou")
        base_speed_rank = rank(base_detail, "spec_subayasa")

        form_hp_rank = rank(form_detail, "spec_hp")
        form_attack_rank = rank(form_detail, "spec_kougeki")
        form_defense_rank = rank(form_detail, "spec_bougyo")
        form_sp_attack_rank = rank(form_detail, "spec_tokukou")
        form_sp_defense_rank = rank(form_detail, "spec_tokubou")
        form_speed_rank = rank(form_detail, "spec_subayasa")

        return SpeciesInfo(
            species_id=species.species_id,
            name_ja=option.display_name or species.name_ja,
            name_en=species.name_en,
            type1=option.type_names[0] if len(option.type_names) >= 1 else species.type1,
            type2=option.type_names[1] if len(option.type_names) >= 2 else "",
            base_hp=scaled(species.base_hp, base_hp_rank, form_hp_rank),
            base_attack=scaled(species.base_attack, base_attack_rank, form_attack_rank),
            base_defense=scaled(species.base_defense, base_defense_rank, form_defense_rank),
            base_sp_attack=scaled(species.base_sp_attack, base_sp_attack_rank, form_sp_attack_rank),
            base_sp_defense=scaled(species.base_sp_defense, base_sp_defense_rank, form_sp_defense_rank),
            base_speed=scaled(species.base_speed, base_speed_rank, form_speed_rank),
            weight_kg=_safe_float(form_detail.get("omosa"), species.weight_kg),
        )

    def _selected_types(self) -> list[str]:
        option = self._current_form_option()
        if option and option.type_names:
            return list(option.type_names)
        species = self._effective_species_for_calc()
        if not species:
            return []
        return [type_name for type_name in [species.type1, species.type2] if type_name]

    def _set_nature(self, nature: str, recalc: bool = True) -> None:
        nature = nature if nature in NATURES_JA else "まじめ"
        self._current_nature = nature
        boost, reduce = NATURES_JA.get(nature, (None, None))
        if boost and reduce:
            text = "{}  (↑{} / ↓{})".format(
                nature,
                _STAT_LABELS.get(boost, boost),
                _STAT_LABELS.get(reduce, reduce),
            )
        else:
            text = "{}  (補正なし)".format(nature)
        self.nature_btn.setText(text)
        self._update_stat_label_colors()
        if recalc:
            self._recalculate_stats_from_species()

    def _update_stat_label_colors(self) -> None:
        boost, reduce = NATURES_JA.get(self._current_nature, (None, None))
        for stat_key, label in self._stat_val_labels.items():
            base_style = "font-size:13px;font-weight:bold;"
            if stat_key == boost:
                label.setStyleSheet(base_style + "color:#f38ba8;")
            elif stat_key == reduce:
                label.setStyleSheet(base_style + "color:#89b4fa;")
            else:
                label.setStyleSheet(base_style + "color:#cdd6f4;")

    def _form_ability_names(self) -> list[str]:
        option = self._current_form_option()
        result: list[str] = []
        if option:
            detail = zukan_client.get_pokemon_detail(option.dex_no)
            if detail:
                for key in ("tokusei_1", "tokusei_2", "tokusei_3"):
                    ability_name = zukan_client.get_ability_name_by_id(detail.get(key))
                    if ability_name and ability_name not in result:
                        result.append(ability_name)

        # Zukan details often omit hidden abilities for low-usage Pokemon/forms.
        # Supplement from PokeAPI ability list of the effective form.
        species = self._effective_species_for_calc()
        if species and species.name_en:
            for ability_name in _pokeapi_ability_names_for_pokemon(species.name_en):
                if ability_name and ability_name not in result:
                    result.append(ability_name)
        return result

    def _apply_form_ability_default(self) -> None:
        form_abilities = self._form_ability_names()
        if not form_abilities:
            return
        current = self.ability_combo.current_text_stripped()
        if current not in form_abilities:
            self.ability_combo.set_text(form_abilities[0])

    def _update_usage_options(self, pokemon_name: str) -> None:
        usage_name = self._usage_lookup_name(pokemon_name)
        form_abilities = self._form_ability_names()
        usage_abilities = db.get_abilities_by_usage(usage_name) if usage_name else []
        ranked_abilities = _filter_ranked_abilities_for_form(
            form_abilities + usage_abilities,
            form_abilities,
        )
        ability_items, ability_separator = _build_ranked_options(
            ranked_abilities,
            self._all_abilities,
        )
        item_items, item_separator = _build_ranked_options(
            db.get_items_by_usage(usage_name) if usage_name else [],
            self._all_items,
        )

        self.ability_combo.set_items(ability_items, separator_after=ability_separator)
        self.item_combo.set_items(item_items, separator_after=item_separator)

    def _apply_usage_template_defaults(self, pokemon_name: str) -> None:
        usage_name = self._usage_lookup_name(pokemon_name)
        if not usage_name:
            return

        form_abilities = self._form_ability_names()
        abilities = _filter_ranked_abilities_for_form(
            db.get_abilities_by_usage(usage_name),
            form_abilities,
        )
        if abilities:
            self.ability_combo.set_text(abilities[0])
        else:
            self._apply_form_ability_default()

        items = db.get_items_by_usage(usage_name)
        if items:
            self.item_combo.set_text(items[0])

        natures = db.get_natures_by_usage(usage_name)
        if natures:
            self._set_nature(natures[0], recalc=False)
        else:
            self._set_nature("がんばりや", recalc=False)

        spreads = db.get_effort_spreads_by_usage(usage_name)
        if spreads:
            hp_pt, attack_pt, defense_pt, sp_attack_pt, sp_defense_pt, speed_pt, _ = spreads[0]
            spread_map = {
                "hp": hp_pt,
                "attack": attack_pt,
                "defense": defense_pt,
                "sp_attack": sp_attack_pt,
                "sp_defense": sp_defense_pt,
                "speed": speed_pt,
            }
            self._updating_stats = True
            for key, slider in self._ev_sliders.items():
                slider.setValue(max(0, min(32, int(spread_map.get(key, 0)))))
            self._updating_stats = False
            for key in self._ev_sliders:
                self._update_ev_toggle_label(key)
        else:
            self._updating_stats = True
            for slider in self._ev_sliders.values():
                slider.setValue(0)
            self._updating_stats = False
            for key in self._ev_sliders:
                self._update_ev_toggle_label(key)

        species = self._selected_species()
        move_candidates = [move for move in db.get_moves_by_usage(usage_name) if move]
        if species and species.species_id:
            learnset_moves = db.get_moves_for_species(species.species_id)
            learnset_names = {move.name_ja for move in learnset_moves}
            if learnset_names:
                filtered = [move_name for move_name in move_candidates if move_name in learnset_names]
                if filtered:
                    move_candidates = filtered
        non_status_candidates: list[str] = []
        for move_name in move_candidates:
            move_info = db.get_move_by_name_ja(move_name)
            if move_info and move_info.category != "status":
                non_status_candidates.append(move_name)
        self._selected_moves = (non_status_candidates + ["", "", "", ""])[:4]
        self._refresh_move_buttons()

        self._recalculate_stats_from_species()

    def _update_ev_toggle_label(self, stat_key: str) -> None:
        ev_value = self._ev_sliders[stat_key].value()
        self._ev_toggle_buttons[stat_key].setText("0振り" if ev_value == 32 else "32振り")

    def _recalculate_stats_from_species(self) -> None:
        if self._loading or self._updating_stats:
            return
        species = self._effective_species_for_calc()
        if not species:
            for key, lbl_text in _STAT_LABELS.items():
                self._stat_val_labels[key].setText("{}(---)".format(lbl_text))
            return

        from src.calc.damage_calc import fill_stats_from_species

        temp = PokemonInstance(
            species_id=species.species_id,
            name_ja=species.name_ja,
            name_en=species.name_en,
            types=self._selected_types(),
            weight_kg=species.weight_kg,
            nature=self._current_nature,
            ev_hp=self._ev_sliders["hp"].value() * 8,
            ev_attack=self._ev_sliders["attack"].value() * 8,
            ev_defense=self._ev_sliders["defense"].value() * 8,
            ev_sp_attack=self._ev_sliders["sp_attack"].value() * 8,
            ev_sp_defense=self._ev_sliders["sp_defense"].value() * 8,
            ev_speed=self._ev_sliders["speed"].value() * 8,
        )
        fill_stats_from_species(temp, species)

        for key, lbl_text in _STAT_LABELS.items():
            self._stat_val_labels[key].setText("{}({})".format(lbl_text, getattr(temp, key)))

    def _move_button_style(self, move_name: str) -> str:
        move = db.get_move_by_name_ja(move_name)
        if not move:
            return ""
        background = TYPE_COLORS.get(move.type_name, "#45475a")
        text_color = _best_text_color(background)
        return (
            "QPushButton { background-color: %s; color: %s; border: 1px solid #585b70; "
            "border-radius: 6px; font-weight: bold; text-align: left; padding: 6px 10px; }"
            "QPushButton:hover { border-color: #f9e2af; }"
        ) % (background, text_color)

    def _refresh_move_buttons(self) -> None:
        for index, button in enumerate(self._move_buttons):
            name = self._selected_moves[index]
            button.setText(name if name else "わざを選択")
            if name:
                button.setStyleSheet(self._move_button_style(name))
            else:
                button.setStyleSheet("")

    def _on_name_changed(self, name: str) -> None:
        if self._loading:
            return
        if not name.strip():
            return
        base_name = self._resolve_species_lookup_name(name.strip())
        self._set_form_options(base_name)
        self._update_usage_options(base_name)
        self._apply_form_ability_default()
        template_key = self._usage_lookup_name(base_name)
        if self._is_new_entry and template_key and template_key != self._auto_template_key:
            self._apply_usage_template_defaults(base_name)
            self._auto_template_key = template_key
            return
        self._recalculate_stats_from_species()

    def _on_ev_changed(self, stat_key: str) -> None:
        self._update_ev_toggle_label(stat_key)
        self._recalculate_stats_from_species()

    def _select_nature(self) -> None:
        usage_name = self._usage_lookup_name(self.name_combo.current_text_stripped())
        ranked_natures = db.get_natures_by_usage(usage_name)[:4] if usage_name else []
        dialog = NatureSelectDialog(self._current_nature, ranked_natures, self)
        if dialog.exec_():
            self._set_nature(dialog.selected_nature(), recalc=not self._loading)

    def _open_move_dialog(self, slot: int) -> None:
        species = self._selected_species()
        form_option = self._current_form_option()
        display_name = form_option.display_name if form_option else self.name_combo.current_text_stripped()
        usage_name = self._usage_lookup_name(display_name)
        current_moves = list(self._selected_moves)
        original_move = current_moves[slot]
        current_moves[slot] = ""
        dialog = MoveSelectDialog(
            species.species_id if species else None,
            display_name,
            original_move,
            self,
            usage_name=usage_name,
            current_moves=current_moves,
        )
        if dialog.exec_():
            self._selected_moves = dialog.selected_moves()
            self._refresh_move_buttons()

    def _clear_move(self, slot: int) -> None:
        self._selected_moves[slot] = ""
        self._refresh_move_buttons()

    def _load(self, pokemon: PokemonInstance) -> None:
        self._loading = True
        self._is_new_entry = False
        self._pokemon = pokemon
        base_name, preferred_display = self._resolve_loaded_form(pokemon.name_ja)
        display_base = _normalize_picker_display_name(base_name) if base_name else base_name
        self.name_combo.set_text(display_base)
        self._set_form_options(base_name, preferred_display_name=preferred_display or pokemon.name_ja)
        self._update_usage_options(base_name)
        self.ability_combo.set_text(pokemon.ability)
        self.item_combo.set_text(pokemon.item)
        self._set_nature(pokemon.nature or "まじめ", recalc=False)

        for key, lbl_text in _STAT_LABELS.items():
            stat_val = getattr(pokemon, key, 0)
            ev_pt = getattr(pokemon, "ev_{}".format(key), 0) // 8
            self._stat_val_labels[key].setText("{}({})".format(lbl_text, stat_val))
            self._ev_sliders[key].setValue(ev_pt)
            self._update_ev_toggle_label(key)

        self._selected_moves = (pokemon.moves + ["", "", "", ""])[:4]
        self._refresh_move_buttons()
        self._loading = False

    def _save(self, save_to_db_override: bool = False) -> None:
        base_name = self.name_combo.current_text_stripped()
        if not base_name:
            QMessageBox.warning(self, "エラー", "名前を入力または選択してください")
            return

        lookup_name = self._resolve_species_lookup_name(base_name)
        species = db.get_species_by_name_ja(lookup_name)
        if not species:
            # Usage-only entry (regional form not yet in species_cache).
            # Build a minimal SpeciesInfo from zukan data so saving is still possible.
            zukan_matches = zukan_client.get_pokemon_index()
            zukan_by_name: dict[str, list[zukan_client.ZukanPokemonEntry]] = {}
            for entry in zukan_matches:
                zukan_by_name.setdefault(entry.name_ja, []).append(entry)
            zukan_entry = _resolve_picker_zukan_entry(lookup_name, zukan_by_name)
            if zukan_entry:
                type_names = _zukan_entry_types(zukan_entry)
                species = SpeciesInfo(
                    species_id=0,
                    name_ja=lookup_name,
                    name_en="",
                    type1=type_names[0] if len(type_names) >= 1 else "normal",
                    type2=type_names[1] if len(type_names) >= 2 else "",
                    base_hp=0, base_attack=0, base_defense=0,
                    base_sp_attack=0, base_sp_defense=0, base_speed=0,
                )
            else:
                QMessageBox.warning(
                    self,
                    "エラー",
                    "ポケモン名の候補が見つかりません。\n先に PokeAPI データを取得してください。",
                )
                return

        form_option = self._current_form_option()
        display_name = form_option.display_name if form_option else species.name_ja
        selected_types = list(form_option.type_names) if form_option and form_option.type_names else self._selected_types()
        effective_species = self._effective_species_for_calc() or species

        pokemon = self._pokemon or PokemonInstance()
        pokemon.species_id = species.species_id
        pokemon.name_ja = display_name
        pokemon.usage_name = form_option.usage_name if form_option else species.name_ja
        pokemon.name_en = effective_species.name_en or species.name_en
        pokemon.types = selected_types
        pokemon.weight_kg = effective_species.weight_kg if effective_species.weight_kg > 0 else species.weight_kg
        pokemon.ability = self.ability_combo.current_text_stripped()
        pokemon.item = self.item_combo.current_text_stripped()
        pokemon.nature = self._current_nature

        for key in self._ev_sliders:
            lbl_text = self._stat_val_labels[key].text()
            # ラベルは "HP(207)" 形式 — 括弧内の数値を取得
            try:
                stat_val = int(lbl_text.split("(")[-1].rstrip(")"))
            except (ValueError, IndexError):
                stat_val = 0
            setattr(pokemon, key, stat_val)
            setattr(pokemon, "ev_{}".format(key), self._ev_sliders[key].value() * 8)

        pokemon.max_hp = pokemon.hp
        pokemon.current_hp = pokemon.hp
        pokemon.moves = [move for move in self._selected_moves if move]

        if self._save_to_db or save_to_db_override:
            new_id = db.save_pokemon(pokemon)
            pokemon.db_id = new_id
        self._pokemon = pokemon
        self.accept()

    def _on_box_select_clicked(self) -> None:
        self._box_select_requested = True
        self.reject()

    def box_select_requested(self) -> bool:
        return self._box_select_requested

    def get_pokemon(self):
        return self._pokemon
