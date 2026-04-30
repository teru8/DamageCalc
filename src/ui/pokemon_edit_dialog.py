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
    QScrollArea,
    QFrame,
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
_TERASTAL_TYPE_EN_TO_JA: dict[str, str] = {
    **TYPE_EN_TO_JA,
    "stellar": "ステラ",
}
_POKEMON_RESULT_LIMIT = 120
_POKEMON_BAND_RESULT_LIMIT = 50
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
_POKEAPI_SESSION.headers["User-Agent"] = "DamageCalc/0.1.0-alpha"
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

def _is_picker_excluded_battle_form(name_ja: str) -> bool:
    normalized = (name_ja or "").strip()
    normalized = normalized.replace("（", "(").replace("）", ")")
    return _is_in_battle_form_name(normalized)


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
        if _is_picker_excluded_battle_form(species.name_ja):
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
        if _is_picker_excluded_battle_form(usage_name):
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


from src.ui.pokemon_edit_dialog_dialogs import NatureSelectDialog, PokemonSelectDialog, MyBoxSelectDialog, MoveSelectDialog



from src.ui.pokemon_edit_dialog_main import PokemonEditDialog
