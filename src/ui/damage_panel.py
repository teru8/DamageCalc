"""Damage calculation panel – complete redesign."""
from __future__ import annotations

import copy
import dataclasses
import json
import math
from typing import Optional

from PyQt5.QtCore import QPointF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGroupBox, QScrollArea, QPushButton, QSizePolicy,
    QSpinBox, QComboBox, QCheckBox, QSplitter, QDialog,
    QSlider,
)

from src.models import PokemonInstance, MoveInfo, SpeciesInfo
from src.data import zukan_client
from src.ui.damage_panel_cards import AttackerCard as _AttackerCard
from src.ui.damage_panel_cards import DefenderCard as _DefenderCard
from src.ui.damage_panel_forms import FORM_NAME_TO_GROUP as _FORM_NAME_TO_GROUP
from src.ui.damage_panel_form_apply import apply_form as _apply_form_impl
from src.ui.damage_panel_hazards import StealthRockRow as _StealthRockRow
from src.ui.damage_panel_math import nature_mult_from_name as _nature_mult_from_name
from src.ui.damage_panel_math import rank_mult as _rank_mult
from src.ui.damage_panel_move_section import MoveSection as _MoveSection
from src.ui.damage_panel_panels import _AttackerPanel, _DefenderPanel
from src.ui.damage_panel_party import PartySlot as _PartySlot
from src.ui.damage_panel_species import species_from_name_en as _species_from_name_en
from src.ui.damage_panel_ui_helpers import row_label as _row_label
from src.ui.damage_panel_ui_helpers import sep as _sep
from src.ui.damage_panel_widgets import RadioGroup as _RadioGroup
from src.ui.damage_panel_widgets import ToggleBtn as _ToggleBtn
from src.ui.ui_utils import open_pokemon_edit_dialog


# ── Helpers ───────────────────────────────────────────────────────────────

_ICON_CACHE: dict[str, QPixmap] = {}


def _game_badge(text: str, c_top: str, c_bottom: str, width: int, height: int, font_size: int = 10) -> QPixmap:
    from src.ui.damage_panel_icons import game_badge

    return game_badge(text, c_top, c_bottom, width, height, font_size)


_REMOTE_ICON_CACHE: dict[str, QPixmap] = {}
_CATEGORY_ICON_URLS = {
    "physical": "https://play.pokemonshowdown.com/sprites/categories/Physical.png",
    "special": "https://play.pokemonshowdown.com/sprites/categories/Special.png",
    "status": "https://play.pokemonshowdown.com/sprites/categories/Status.png",
}


def _remote_icon(url: str, width: int, height: int) -> QPixmap | None:
    from src.ui.damage_panel_icons import remote_icon

    return remote_icon(url, width, height)


def _category_icon(category: str, width: int = 66, height: int = 22) -> QPixmap:
    from src.ui.damage_panel_icons import category_icon

    return category_icon(category, width, height)


def _battle_stat_icon(kind: str, width: int = 60, height: int = 22) -> QPixmap:
    from src.ui.damage_panel_icons import battle_stat_icon

    return battle_stat_icon(kind, width, height)


# ── Form change data ─────────────────────────────────────────────────────
# Form groups moved to src/ui/damage_panel_forms.py

# PokeAPI english names for non-base forms
_FORM_POKEAPI_EN: dict[str, str] = {
    # gen 1-3 standard megas (in PokeAPI)
    "メガフシギバナ":           "venusaur-mega",
    "メガリザードンＸ":         "charizard-mega-x",
    "メガリザードンＹ":         "charizard-mega-y",
    "メガカメックス":           "blastoise-mega",
    "メガスピアー":             "beedrill-mega",
    "メガピジョット":           "pidgeot-mega",
    "メガピクシー":             "clefable-mega",
    "メガウツボット":           "victreebel-mega",
    "メガヤドラン":             "slowbro-mega",
    "メガゲンガー":             "gengar-mega",
    "メガスターミー":           "starmie-mega",
    "メガカイロス":             "pinsir-mega",
    "メガギャラドス":           "gyarados-mega",
    "メガプテラ":               "aerodactyl-mega",
    "メガカイリュー":           "dragonite-mega",
    "メガミュウツーＸ":         "mewtwo-mega-x",
    "メガミュウツーＹ":         "mewtwo-mega-y",
    # gen 2 megas
    "メガメガニウム":           "meganium-mega",
    "メガオーダイル":           "feraligatr-mega",
    "メガデンリュウ":           "ampharos-mega",
    "メガハガネール":           "steelix-mega",
    "メガハッサム":             "scizor-mega",
    "メガヘラクロス":           "heracross-mega",
    "メガエアームド":           "skarmory-mega",
    "メガヘルガー":             "houndoom-mega",
    "メガバンギラス":           "tyranitar-mega",
    # gen 3 megas
    "メガジュカイン":           "sceptile-mega",
    "メガバシャーモ":           "blaziken-mega",
    "メガラグラージ":           "swampert-mega",
    "メガヤミラミ":             "sableye-mega",
    "メガクチート":             "mawile-mega",
    "メガボスゴドラ":           "aggron-mega",
    "メガチャーレム":           "medicham-mega",
    "メガライボルト":           "manectric-mega",
    "メガサメハダー":           "sharpedo-mega",
    "メガバクーダ":             "camerupt-mega",
    "メガチルタリス":           "altaria-mega",
    "メガジュペッタ":           "banette-mega",
    "メガチリーン":             "chimecho-mega",
    "メガアブソル":             "absol-mega",
    "メガオニゴーリ":           "glalie-mega",
    "メガボーマンダ":           "salamence-mega",
    "メガメタグロス":           "metagross-mega",
    "メガラティアス":           "latias-mega",
    "メガラティオス":           "latios-mega",
    # gen 4 megas
    "メガルカリオ":             "lucario-mega",
    "メガガブリアス":           "garchomp-mega",
    "メガミミロップ":           "lopunny-mega",
    "メガエルレイド":           "gallade-mega",
    "メガユキメノコ":           "froslass-mega",
    "メガタブンネ":             "audino-mega",
    "メガムクホーク":           "staraptor-mega",
    # gen 4 legendary
    "メガヒードラン":           "heatran-mega",
    # gen 5 megas
    "メガエンブオー":           "emboar-mega",
    "メガドリュウズ":           "excadrill-mega",
    "メガペンドラー":           "scolipede-mega",
    "メガズルズキン":           "scrafty-mega",
    "メガシビルドン":           "eelektross-mega",
    "メガシャンデラ":           "chandelure-mega",
    "メガゴルーグ":             "golurk-mega",
    # gen 6 megas
    "メガブリガロン":           "chesnaught-mega",
    "メガマフォクシー":         "delphox-mega",
    "メガゲッコウガ":           "greninja-mega",
    "メガカエンジシ":           "pyroar-mega",
    "メガニャオニクス":         "meowstic-mega",
    "メガカラマネロ":           "malamar-mega",
    "メガガメノデス":           "barbaracle-mega",
    "メガドラミドロ":           "dragalge-mega",
    "メガルチャブル":           "hawlucha-mega",
    "メガサーナイト":           "gardevoir-mega",
    "メガユキノオー":           "abomasnow-mega",
    # gen 6 legendary/mythical
    "メガダークライ":           "darkrai-mega",
    "メガディアンシー":         "diancie-mega",
    # gen 7+ / gen9 fan-made (not in PokeAPI — handled via smogon calc)
    "メガライチュウＸ":         "raichu-mega-x",
    "メガライチュウＹ":         "raichu-mega-y",
    "メガゼラオラ":             "zeraora-mega",
    "メガタイレーツ":           "falinks-mega",
    "メガスコヴィラン":         "scovillain-mega",
    "メガキラフロル":           "glimmora-mega",
    "メガセグレイブ":           "baxcalibur-mega",
    "メガケケンカニ":           "crabominable-mega",
    "メガグソクムシャ":         "golisopod-mega",
    "メガジジーロン":           "drampa-mega",
    "メガマギアナ":             "magearna-mega",
    "メガフラエッテ":           "floette-mega",
    "ゲンシグラードン":         "groudon-primal",
    "ゲンシカイオーガ":         "kyogre-primal",
    "メガレックウザ":           "rayquaza-mega",
    "ギルガルド":                        "aegislash-shield",
    "ギルガルド (ブレードフォルム)":     "aegislash-blade",
    "チェリム (ポジフォルム)":           "cherrim-sunshine",
    "メロエッタ (ステップフォルム)":     "meloetta-pirouette",
    "ヒヒダルマ":                        "darmanitan-standard",
    "ヒヒダルマ (ダルマモード)":         "darmanitan-zen",
    "ヒヒダルマ (ガラルのすがた)":       "darmanitan-galar-standard",
    "ヒヒダルマ (ガラルのすがた・ダルマモード)": "darmanitan-galar-zen",
    "ガラルヒヒダルマ":                  "darmanitan-galar-standard",
    "ガラルヒヒダルマ (ダルマモード)":   "darmanitan-galar-zen",
    "オーガポン":                        "ogerpon",
    "オーガポン (いどのめん)":           "ogerpon-wellspring-mask",
    "オーガポン (かまどのめん)":         "ogerpon-hearthflame-mask",
    "オーガポン (いしずえのめん)":       "ogerpon-cornerstone-mask",
    "ジガルデ":                          "zygarde-50",
    "ジガルデ (１０％フォルム)":         "zygarde-10",
    "ジガルデ (パーフェクトフォルム)":   "zygarde-complete",
    "モルペコ":                          "morpeko-full-belly",
    "モルペコ (はらぺこもよう)":         "morpeko-hangry",
    "コオリッポ":                        "eiscue-ice",
    "コオリッポ (ナイスフェイス)":       "eiscue-noice",
    "メテノ":                            "minior-red-meteor",
    "メテノ (あかいろのコア)":           "minior-red",
    "ヨワシ":                            "wishiwashi-solo",
    "ヨワシ (むれたすがた)":             "wishiwashi-school",
    "イルカマン":                        "palafin-zero",
    "イルカマン (マイティフォルム)":     "palafin-hero",
    "テラパゴス":                        "terapagos-normal",
    "テラパゴス (テラスタルフォルム)":   "terapagos-terastal",
    "テラパゴス (ステラフォルム)":       "terapagos-stellar",
    "ポワルン (たいようのすがた)":       "castform-sunny",
    "ポワルン (あまみずのすがた)":       "castform-rainy",
    "ポワルン (ゆきぐものすがた)":       "castform-snowy",
    "ギラティナ(オリジンフォルム)":      "giratina-origin",
    "シェイミ(スカイフォルム)":          "shaymin-sky",
    "ヒートロトム":                      "rotom-heat",
    "ウォッシュロトム":                  "rotom-wash",
    "フロストロトム":                    "rotom-frost",
    "スピンロトム":                      "rotom-fan",
    "カットロトム":                      "rotom-mow",
    "デオキシス(アタックフォルム)":      "deoxys-attack",
    "デオキシス(ディフェンスフォルム)":  "deoxys-defense",
    "デオキシス(スピードフォルム)":      "deoxys-speed",
    "たそがれのたてがみネクロズマ":      "necrozma-dusk-mane",
    "あかつきのつばさネクロズマ":        "necrozma-dawn-wings",
    # Floette eternal flower — use PokeAPI name "floette-eternal" (ID 10061).
    # The Mega is NOT registered here; it is handled via _FORM_MISSING_MEGA_STATS in _apply_form.
    "フラエッテ (えいえんのはな)":       "floette-eternal",
    "フラエッテ(えいえんのはな)":        "floette-eternal",
    "フラエッテ(えいえん)":              "floette-eternal",
    "フラエッテ (えいえん)":             "floette-eternal",
}

# Ability (Japanese) overrides for forms that change ability
_FORM_ABILITY_JA: dict[str, str] = {
    # gen 1 megas
    "メガフシギバナ":   "あついしぼう",
    "メガリザードンＸ": "かたいツメ",
    "メガリザードンＹ": "ひでり",
    "メガカメックス":   "メガランチャー",
    "メガスピアー":     "てきおうりょく",
    "メガピジョット":   "ノーガード",
    "メガピクシー":     "マジックミラー",
    "メガウツボット":   "とびだすなかみ",
    "メガフーディン":   "トレース",
    "メガゲンガー":     "かげふみ",
    "メガスターミー":   "ちからもち",
    "メガカイロス":     "スカイスキン",
    "メガヤドラン":     "シェルアーマー",
    "メガガルーラ":     "おやこあい",
    "メガギャラドス":   "かたやぶり",
    "メガプテラ":       "かたいツメ",
    "メガカイリュー":   "マルチスケイル",
    "メガミュウツーＸ": "ふくつのこころ",
    "メガミュウツーＹ": "ふみん",
    # gen 2 megas
    "メガメガニウム":   "メガソーラー",
    "メガオーダイル":   "ドラゴンスキン",
    "メガデンリュウ":   "かたやぶり",
    "メガハガネール":   "すなのちから",
    "メガハッサム":     "テクニシャン",
    "メガヘラクロス":   "スキルリンク",
    "メガエアームド":   "すじがねいり",
    "メガヘルガー":     "サンパワー",
    "メガバンギラス":   "すなおこし",
    # gen 3 megas
    "メガジュカイン":   "ひらいしん",
    "メガバシャーモ":   "かそく",
    "メガラグラージ":   "すいすい",
    "メガサーナイト":   "フェアリースキン",
    "メガヤミラミ":     "マジックミラー",
    "メガクチート":     "ちからもち",
    "メガボスゴドラ":   "フィルター",
    "メガチャーレム":   "ヨガパワー",
    "メガライボルト":   "いかく",
    "メガサメハダー":   "がんじょうあご",
    "メガバクーダ":     "ちからずく",
    "メガチルタリス":   "フェアリースキン",
    "メガジュペッタ":   "いたずらごころ",
    "メガチリーン":     "ふゆう",
    "メガアブソル":     "マジックミラー",
    "メガオニゴーリ":   "フリーズスキン",
    "メガボーマンダ":   "スカイスキン",
    "メガメタグロス":   "かたいツメ",
    "メガラティアス":   "ふゆう",
    "メガラティオス":   "ふゆう",
    # gen 4 megas
    "メガルカリオ":     "てきおうりょく",
    "メガガブリアス":   "すなのちから",
    "メガミミロップ":   "きもったま",
    "メガユキノオー":   "ゆきふらし",
    "メガエルレイド":   "せいしんりょく",
    "メガユキメノコ":   "ゆきふらし",
    "メガムクホーク":   "いかく",
    "メガヒードラン":   "もらいび",
    "メガダークライ":   "ナイトメア",
    # gen 5 megas
    "メガエンブオー":   "かたやぶり",
    "メガドリュウズ":   "かんつうドリル",
    "メガタブンネ":     "いやしのこころ",
    "メガペンドラー":   "どくのトゲ",
    "メガズルズキン":   "だっぴ",
    "メガシビルドン":   "ふゆう",
    "メガシャンデラ":   "すりぬけ",
    "メガゴルーグ":     "ふかしのこぶし",
    # gen 6 megas
    "メガブリガロン":   "ぼうだん",
    "メガマフォクシー": "ふゆう",
    "メガゲッコウガ":   "へんげんじざい",
    "メガカエンジシ":   "じしんかじょう",
    "メガフラエッテ":   "フェアリーオーラ",
    "メガニャオニクス":  "トレース",
    "メガカラマネロ":   "あまのじゃく",
    "メガガメノデス":   "かたいツメ",
    "メガドラミドロ":   "どくのトゲ",
    "メガルチャブル":   "ノーガード",
    "メガディアンシー": "マジックミラー",
    # gen 7+ 
    "メガライチュウＸ": "サーフテール",
    "メガライチュウＹ": "サーフテール",
    "メガケケンカニ":   "てつのこぶし",
    "メガグソクムシャ": "にげごし",
    "メガジジーロン":   "ぎゃくじょう",
    "メガマギアナ":     "ソウルハート",
    "メガゼラオラ":     "ちくでん",
    "メガタイレーツ":   "カブトアーマー",
    "メガスコヴィラン": "とびだすハバネロ",
    "メガキラフロル":   "てきおうりょく",
    "メガシャリタツ":   "よびみず",
    "メガセグレイブ":   "ねつこうかん",
    # primals
    "ゲンシグラードン": "おわりのだいち",
    "ゲンシカイオーガ": "はじまりのうみ",
    "メガレックウザ":   "エアロック",
    "メガジガルデ": "スワームチェンジ",
    # battle-only form changes with ability change
    "ヒヒダルマ (ダルマモード)":              "ダルマモード",
    "ヒヒダルマ (ガラルのすがた・ダルマモード)": "ダルマモード",
    "テラパゴス":                             "テラスチェンジ",
    "テラパゴス (テラスタルフォルム)":        "テラスシェル",
    "テラパゴス (ステラフォルム)":            "ゼロフォーミング",
    "オーガポン":                             "みどりのめん",
    "オーガポン (いどのめん)":               "いどのめん",
    "オーガポン (かまどのめん)":             "かまどのめん",
    "オーガポン (いしずえのめん)":           "いしずえのめん",
}

# Stats for Mega forms absent from PokeAPI (gen9 fan-made / unreleased).
# Key: Smogon species name.  Value: (name_en, type1, type2, hp, atk, def, spa, spd, spe, weight_kg)
_FORM_MISSING_MEGA_STATS: dict[str, tuple] = {
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
    "Drampa-Mega":            ("drampa-mega",             "normal",  "dragon",   78,  85,  110, 160, 116, 36,  185.0),
    "Eelektross-Mega":        ("eelektross-mega",         "electric","",         85,  145, 80,  135, 90,  80,  160.0),
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
    "Starmie-Mega":           ("starmie-mega",            "water",   "psychic",  60,  140, 105, 130, 105, 120, 80.0),
    "Tatsugiri-Curly-Mega":   ("tatsugiri-curly-mega",    "dragon",  "water",    68,  65,  90,  135, 125, 92,  8.0),
    "Tatsugiri-Droopy-Mega":  ("tatsugiri-droopy-mega",   "dragon",  "water",    68,  65,  90,  135, 125, 92,  8.0),
    "Tatsugiri-Stretchy-Mega":("tatsugiri-stretchy-mega", "dragon",  "water",    68,  65,  90,  135, 125, 92,  8.0),
    "Victreebel-Mega":        ("victreebel-mega",         "grass",   "poison",   80,  125, 85,  135, 95,  70,  125.5),
    "Zeraora-Mega":           ("zeraora-mega",            "electric","",         88,  157, 75,  147, 80,  153, 44.5),
    "Zygarde-Mega":           ("zygarde-mega",            "dragon",  "ground",   216, 70,  91,  216, 85,  100, 610.0),
}


def _normalize_form_name(name_ja: str) -> str:
    from src.ui.damage_panel_forms import normalize_form_name

    return normalize_form_name(name_ja, _FORM_NAME_TO_GROUP)


def _form_group(name_ja: str) -> list[str]:
    from src.ui.damage_panel_forms import form_group

    return form_group(name_ja, _FORM_NAME_TO_GROUP)


def _next_form_name(name_ja: str) -> Optional[str]:
    from src.ui.damage_panel_forms import next_form_name

    return next_form_name(name_ja, _FORM_NAME_TO_GROUP)


def _apply_form(p: "PokemonInstance", form_name: str, original_ability: str = "") -> "PokemonInstance":
    return _apply_form_impl(
        pokemon=p,
        form_name=form_name,
        original_ability=original_ability,
        form_name_to_group=_FORM_NAME_TO_GROUP,
        form_pokeapi_en=_FORM_POKEAPI_EN,
        form_missing_mega_stats=_FORM_MISSING_MEGA_STATS,
        form_ability_ja=_FORM_ABILITY_JA,
    )


# ── Resist berry: Japanese name → type ───────────────────────────────────
_RESIST_BERRIES: dict[str, str] = {
    "オッカのみ": "fire",
    "イトケのみ": "water",
    "ソクノのみ": "electric",
    "リンドのみ": "grass",
    "ヤチェのみ": "ice",
    "ヨプのみ": "fighting",
    "ビアーのみ": "poison",
    "シュカのみ": "ground",
    "バコウのみ": "flying",
    "ウタンのみ": "psychic",
    "タンガのみ": "bug",
    "ヨロギのみ": "rock",
    "カシブのみ": "ghost",
    "ハバンのみ": "dragon",
    "ナモのみ": "dark",
    "リリバのみ": "steel",
    "ホズのみ": "normal",
    "ロゼルのみ": "fairy",
}

# ── Simple toggle button ──────────────────────────────────────────────────

# ── Ability / Item quick-pick helpers ────────────────────────────────────

def _pick_ability(pokemon: "PokemonInstance", parent: QWidget) -> "str | None":
    from src.ui.damage_panel_pickers import pick_ability

    return pick_ability(pokemon, parent)


def _pick_item(pokemon: "PokemonInstance", parent: QWidget) -> "str | None":
    from src.ui.damage_panel_pickers import pick_item

    return pick_item(pokemon, parent)


def _show_pick_dialog(
    title: str,
    items: list,
    separator_after: "int | None",
    current: str,
    parent: QWidget,
) -> "str | None":
    from src.ui.damage_panel_pickers import show_pick_dialog

    return show_pick_dialog(title, items, separator_after, current, parent)


# ── Main DamagePanel ──────────────────────────────────────────────────────

class DamagePanel(QWidget):
    attacker_changed = pyqtSignal(object)   # emitted when attacker pokemon changes
    defender_changed = pyqtSignal(object)   # emitted when defender pokemon changes
    registry_maybe_changed = pyqtSignal()
    bridge_payload_logged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._atk: Optional[PokemonInstance] = None
        self._def_custom: Optional[PokemonInstance] = None   # registered / edited defender
        self._def_species_name: str = ""
        self._my_party: list[Optional[PokemonInstance]] = []
        self._opp_party: list[Optional[PokemonInstance]] = []
        self._party_source = "my"
        self._atk_party_side: Optional[str] = None
        self._atk_party_idx: Optional[int] = None
        self._def_party_side: Optional[str] = None
        self._def_party_idx: Optional[int] = None
        self._show_bulk_rows = True
        self._move_cache: dict[str, MoveInfo] = {}
        self._display_to_move_slot = [0, 1, 2, 3]
        self._atk_form_cache: dict[str, str] = {}
        self._def_form_cache: dict[str, str] = {}
        self.setStyleSheet(
            "QPushButton{font-size:14px;}"
            "QLabel{font-size:14px;}"
            "QCheckBox{font-size:14px;}"
            "QComboBox{font-size:14px;}"
            "QSpinBox{font-size:14px;}"
        )
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        from src.ui.damage_panel_ui_builders import _build_ui as _impl
        return _impl(self)

    @property
    def side_panel(self) -> QWidget:
        """Attacker/defender controls + battle settings widget (hosted in cam panel)."""
        return self._side_panel

    def _build_side_panel(self) -> None:
        from src.ui.damage_panel_ui_builders import _build_side_panel as _impl
        return _impl(self)

    def _build_content(self) -> None:
        from src.ui.damage_panel_ui_builders import _build_content as _impl
        return _impl(self)

    def set_my_pokemon(self, pokemon: PokemonInstance) -> None:
        self._atk = copy.deepcopy(pokemon)
        self._party_source = "my"
        self._atk_party_side = None
        self._atk_party_idx = None
        self._refresh_bulk_rows_visibility()
        self._atk_panel.set_pokemon(self._atk)
        self._refresh_party_selector_labels()
        self._refresh_party_slots()
        self.recalculate()

    def set_opp_party_action_widget(self, widget: QWidget | None) -> None:
        if not hasattr(self, "_opp_party_action_layout"):
            return
        layout = self._opp_party_action_layout
        while layout.count():
            item = layout.takeAt(0)
            child = item.widget()
            if child is not None:
                child.setParent(None)
        if widget is not None:
            layout.addWidget(widget, 0, Qt.AlignVCenter)

    def _on_party_slot_context_menu(self, side: str, idx: int, global_pos) -> None:
        from src.ui.damage_panel_signal_handlers import _on_party_slot_context_menu as _impl
        return _impl(self, side, idx, global_pos)

    def _edit_party_slot(self, side: str, idx: int) -> None:
        from src.ui.damage_panel_signal_handlers import _edit_party_slot as _impl
        return _impl(self, side, idx)

    def _save_party_slot_to_db(self, side: str, idx: int) -> None:
        from src.ui.damage_panel_signal_handlers import _save_party_slot_to_db as _impl
        return _impl(self, side, idx)

    def _add_party_slot(self, side: str, idx: int) -> None:
        from src.ui.damage_panel_signal_handlers import _add_party_slot as _impl
        return _impl(self, side, idx)

    def set_my_party(self, party: list[Optional[PokemonInstance]]) -> None:
        self._my_party = [copy.deepcopy(p) if p else None for p in party]
        self._refresh_party_slots()

    def set_opponent_options(
        self,
        party: list[Optional[PokemonInstance]],
        active: Optional[PokemonInstance] = None,
    ) -> None:
        if not any(p for p in party):
            return
        self._opp_party = [(copy.deepcopy(p) if p else None) for p in (list(party) + [None] * 6)[:6]]
        defender = active or next((p for p in self._opp_party if p), None)
        if not defender:
            return
        self._def_custom = copy.deepcopy(defender)
        self._def_species_name = defender.name_ja or ""
        self._def_party_side = "opp"
        self._def_party_idx = next(
            (i for i, p in enumerate(self._opp_party) if p and p.name_ja == defender.name_ja),
            None,
        )
        self._def_panel.set_pokemon(self._def_custom)
        self.defender_changed.emit(self._def_custom)
        self._refresh_party_slots()
        self._refresh_defender_card()
        self.recalculate()

    def set_opponent_pokemon(self, pokemon: PokemonInstance) -> None:
        if self._opp_party:
            self._opp_party[0] = copy.deepcopy(pokemon)
        else:
            self._opp_party = [copy.deepcopy(pokemon)]
        self._def_custom = copy.deepcopy(pokemon)
        self._def_species_name = pokemon.name_ja or ""
        self._def_party_side = "opp"
        self._def_party_idx = 0
        self._def_panel.set_pokemon(self._def_custom)
        self.defender_changed.emit(self._def_custom)
        self._refresh_party_slots()
        self._refresh_defender_card()
        self.recalculate()

    def get_my_party_snapshot(self) -> list[Optional[PokemonInstance]]:
        return [copy.deepcopy(p) if p else None for p in self._my_party]

    def get_opp_party_snapshot(self) -> list[Optional[PokemonInstance]]:
        return [copy.deepcopy(p) if p else None for p in self._opp_party]

    def set_weather(self, weather: str) -> None:
        _map = {"sun": "はれ", "rain": "あめ", "sand": "すな", "hail": "ゆき"}
        self._weather_grp.set_value(_map.get(weather, "none"))
        self.recalculate()

    def set_terrain(self, terrain: str) -> None:
        _map = {"electric": "エレキ", "grassy": "グラス",
                "misty": "ミスト", "psychic": "サイコ"}
        self._terrain_grp.set_value(_map.get(terrain, "none"))
        self.recalculate()

    def set_terastal_controls_visible(self, visible: bool) -> None:
        if hasattr(self, "_atk_panel"):
            self._atk_panel.set_tera_visible(visible)
        if hasattr(self, "_def_panel"):
            self._def_panel.set_tera_visible(visible)
        if hasattr(self, "_move_sections"):
            self.recalculate()

    def attacker_side(self) -> str:
        return "opp" if self._party_source == "opp" else "my"

    def defender_side(self) -> str:
        return "my" if self._party_source == "opp" else "opp"

    def _sync_attacker_ability_support_buttons(self) -> None:
        if not hasattr(self, "_attacker_ability_cond_btns"):
            return
        ability = (self._atk.ability if self._atk else "").strip()
        show_map = {
            "しんりょく": ability in ("しんりょく", "Overgrow"),
            "もうか": ability in ("もうか", "Blaze"),
            "げきりゅう": ability in ("げきりゅう", "Torrent"),
            "むしのしらせ": ability in ("むしのしらせ", "Swarm"),
            "どくぼうそう": ability in ("どくぼうそう", "Toxic Boost"),
        }
        for key, btn in self._attacker_ability_cond_btns.items():
            show = show_map.get(key, False)
            if not show and btn.isChecked():
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)
                btn._refresh()
            btn.setVisible(show)

        trigger_show_map = {
            "はりこみ": ability in ("はりこみ", "Stakeout"),
            "もらいび": ability in ("もらいび", "Flash Fire"),
            "こだいかっせい": ability in ("こだいかっせい", "Protosynthesis"),
            "クォークチャージ": ability in ("クォークチャージ", "Quark Drive"),
            "アナライズ": ability in ("アナライズ", "Analytic"),
            "ねつぼうそう": ability in ("ねつぼうそう", "Flare Boost"),
            "こんじょう": ability in ("こんじょう", "Guts"),
        }
        if hasattr(self, "_attacker_trigger_cond_btns"):
            for key, btn in self._attacker_trigger_cond_btns.items():
                show = trigger_show_map.get(key, False)
                if not show and btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
                    btn._refresh()
                btn.setVisible(show)

        full_hp_guard_show_map = {
            "マルチスケイル": ability in ("マルチスケイル", "Multiscale"),
            "ファントムガード": ability in ("ファントムガード", "Shadow Shield"),
            "テラスシェル": ability in ("テラスシェル", "Tera Shell"),
        }
        if hasattr(self, "_attacker_full_hp_guard_btns"):
            for key, btn in self._attacker_full_hp_guard_btns.items():
                show = full_hp_guard_show_map.get(key, False)
                was_visible = btn.isVisible()
                btn.setVisible(show)
                if show and not was_visible:
                    btn.blockSignals(True)
                    btn.setChecked(True)
                    btn.blockSignals(False)
                    btn._refresh()

        show_supreme = ability in ("そうだいしょう", "Supreme Overlord")
        self._supreme_combo.setVisible(show_supreme)
        if not show_supreme:
            self._supreme_combo.blockSignals(True)
            self._supreme_combo.setCurrentIndex(0)
            self._supreme_combo.blockSignals(False)

        show_rivalry = ability in ("とうそうしん", "Rivalry")
        self._rivalry_combo.setVisible(show_rivalry)
        if not show_rivalry:
            self._rivalry_combo.blockSignals(True)
            self._rivalry_combo.setCurrentIndex(0)
            self._rivalry_combo.blockSignals(False)

    def _refresh_supreme_combo(self) -> None:
        self.recalculate()
        if self._supreme_combo.currentIndex() > 0:
            self._supreme_combo.setStyleSheet(
                "QComboBox{background:#f9e2af;color:#3a3218;border:1px solid #a87d3a;"
                "border-radius:4px;padding:4px 8px;font-size:14px;font-weight:bold;}"
                "QComboBox::drop-down{border:none;}"
                "QComboBox::down-arrow{image:none;width:0;height:0;}"
                "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
            )
        else:
            self._supreme_combo.setStyleSheet(
                "QComboBox{background:#3a3218;color:#f9e2af;border:1px solid #a87d3a;"
                "border-radius:4px;padding:4px 8px;font-size:14px;}"
                "QComboBox::drop-down{border:none;}"
                "QComboBox::down-arrow{image:none;width:0;height:0;}"
                "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
            )

    def _refresh_rivalry_combo(self) -> None:
        self.recalculate()
        if self._rivalry_combo.currentIndex() > 0:
            self._rivalry_combo.setStyleSheet(
                "QComboBox{background:#f9e2af;color:#3a3218;border:1px solid #a87d3a;"
                "border-radius:4px;padding:4px 8px;font-size:14px;font-weight:bold;}"
                "QComboBox::drop-down{border:none;}"
                "QComboBox::down-arrow{image:none;width:0;height:0;}"
                "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
            )
        else:
            self._rivalry_combo.setStyleSheet(
                "QComboBox{background:#3a3218;color:#f9e2af;border:1px solid #a87d3a;"
                "border-radius:4px;padding:4px 8px;font-size:14px;}"
                "QComboBox::drop-down{border:none;}"
                "QComboBox::down-arrow{image:none;width:0;height:0;}"
                "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
            )

    def _refresh_opp_rivalry_combo(self) -> None:
        self.recalculate()
        if self._opp_rivalry_combo.currentIndex() > 0:
            self._opp_rivalry_combo.setStyleSheet(
                "QComboBox{background:#f9e2af;color:#3a3218;border:1px solid #a87d3a;"
                "border-radius:4px;padding:4px 8px;font-size:14px;font-weight:bold;}"
                "QComboBox::drop-down{border:none;}"
                "QComboBox::down-arrow{image:none;width:0;height:0;}"
                "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
            )
        else:
            self._opp_rivalry_combo.setStyleSheet(
                "QComboBox{background:#3a3218;color:#f9e2af;border:1px solid #a87d3a;"
                "border-radius:4px;padding:4px 8px;font-size:14px;}"
                "QComboBox::drop-down{border:none;}"
                "QComboBox::down-arrow{image:none;width:0;height:0;}"
                "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
            )

    def _refresh_opp_supreme_combo(self) -> None:
        self.recalculate()
        if self._opp_supreme_combo.currentIndex() > 0:
            self._opp_supreme_combo.setStyleSheet(
                "QComboBox{background:#f9e2af;color:#3a3218;border:1px solid #a87d3a;"
                "border-radius:4px;padding:4px 8px;font-size:14px;font-weight:bold;}"
                "QComboBox::drop-down{border:none;}"
                "QComboBox::down-arrow{image:none;width:0;height:0;}"
                "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
            )
        else:
            self._opp_supreme_combo.setStyleSheet(
                "QComboBox{background:#3a3218;color:#f9e2af;border:1px solid #a87d3a;"
                "border-radius:4px;padding:4px 8px;font-size:14px;}"
                "QComboBox::drop-down{border:none;}"
                "QComboBox::down-arrow{image:none;width:0;height:0;}"
                "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
            )

    def _sync_defender_ability_support_buttons(self) -> None:
        if not hasattr(self, "_defender_ability_cond_btns"):
            return
        ability = (self._def_custom.ability if self._def_custom else "").strip()
        show_map = {
            "しんりょく": ability in ("しんりょく", "Overgrow"),
            "もうか": ability in ("もうか", "Blaze"),
            "げきりゅう": ability in ("げきりゅう", "Torrent"),
            "むしのしらせ": ability in ("むしのしらせ", "Swarm"),
            "どくぼうそう": ability in ("どくぼうそう", "Toxic Boost"),
        }
        for key, btn in self._defender_ability_cond_btns.items():
            show = show_map.get(key, False)
            if not show and btn.isChecked():
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)
                btn._refresh()
            btn.setVisible(show)
        trigger_show_map = {
            "はりこみ": ability in ("はりこみ", "Stakeout"),
            "もらいび": ability in ("もらいび", "Flash Fire"),
            "こだいかっせい": ability in ("こだいかっせい", "Protosynthesis"),
            "クォークチャージ": ability in ("クォークチャージ", "Quark Drive"),
            "アナライズ": ability in ("アナライズ", "Analytic"),
            "ねつぼうそう": ability in ("ねつぼうそう", "Flare Boost"),
            "こんじょう": ability in ("こんじょう", "Guts"),
        }
        if hasattr(self, "_defender_trigger_cond_btns"):
            for key, btn in self._defender_trigger_cond_btns.items():
                show = trigger_show_map.get(key, False)
                if not show and btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
                    btn._refresh()
                btn.setVisible(show)

        full_hp_guard_show_map = {
            "マルチスケイル": ability in ("マルチスケイル", "Multiscale"),
            "ファントムガード": ability in ("ファントムガード", "Shadow Shield"),
            "テラスシェル": ability in ("テラスシェル", "Tera Shell"),
        }
        if hasattr(self, "_defender_full_hp_guard_btns"):
            for key, btn in self._defender_full_hp_guard_btns.items():
                show = full_hp_guard_show_map.get(key, False)
                was_visible = btn.isVisible()
                btn.setVisible(show)
                if show and not was_visible:
                    btn.blockSignals(True)
                    btn.setChecked(True)
                    btn.blockSignals(False)
                    btn._refresh()

        if hasattr(self, "_opp_supreme_combo"):
            show_opp_supreme = ability in ("そうだいしょう", "Supreme Overlord")
            self._opp_supreme_combo.setVisible(show_opp_supreme)
            if not show_opp_supreme:
                self._opp_supreme_combo.blockSignals(True)
                self._opp_supreme_combo.setCurrentIndex(0)
                self._opp_supreme_combo.blockSignals(False)

    # ── Recalculation ─────────────────────────────────────────────────

    def recalculate(self) -> None:
        from src.ui.damage_panel_calc_logic import recalculate as _impl
        return _impl(self)

    def _show_opp_moves_only(self) -> None:
        """自分未設定・相手のみ設定時に相手のわざ名だけ右側に表示する。"""
        from src.data.database import get_move_by_name_ja

        if not self._def_custom:
            for sec in self._opp_move_sections:
                sec.setup_move(None)
            return

        opp_moves = self._def_custom.moves or []

        for slot, opp_sec in enumerate(self._opp_move_sections):
            opp_move_name = opp_moves[slot] if slot < len(opp_moves) else ""
            if opp_move_name:
                opp_move_info = self._move_cache.get(opp_move_name) or get_move_by_name_ja(opp_move_name)
                if opp_move_info:
                    self._move_cache[opp_move_name] = opp_move_info
                opp_sec.setup_move(opp_move_info)
            else:
                opp_sec.setup_move(None)

    def _resolve_species_info(
        self,
        pokemon: Optional[PokemonInstance],
        fallback_name_ja: str = "",
    ) -> Optional[SpeciesInfo]:
        from src.data.database import get_species_by_id, get_species_by_name_ja

        species = None

        name_ja = ""
        if pokemon and pokemon.name_ja:
            name_ja = pokemon.name_ja
        elif fallback_name_ja:
            name_ja = fallback_name_ja

        if name_ja:
            species = get_species_by_name_ja(name_ja)

        if species is None and pokemon and pokemon.species_id:
            species = get_species_by_id(pokemon.species_id)

        if pokemon and pokemon.name_en:
            if species is None or (species.name_en and species.name_en != pokemon.name_en):
                form_species = _species_from_name_en(pokemon.name_en, pokemon.species_id, pokemon.name_ja)
                if form_species is not None:
                    species = form_species

            if species is None:
                normalized = pokemon.name_en.lower()
                en_candidates: list[str] = []
                if normalized.startswith("mega-"):
                    en_candidates.append(normalized[5:])
                if "-mega-" in normalized:
                    en_candidates.append(normalized.split("-mega-")[0])
                if normalized.endswith("-mega"):
                    en_candidates.append(normalized[:-5])
                for cand in en_candidates:
                    if not cand:
                        continue
                    form_species = _species_from_name_en(cand, pokemon.species_id, pokemon.name_ja)
                    if form_species is not None:
                        species = form_species
                        break

        if species is None and name_ja.startswith("メガ"):
            from src.calc.smogon_bridge import smogon_mega_species as _smogon_mega
            base_name = name_ja[2:]
            base_species = get_species_by_name_ja(base_name)
            if base_species is None and base_name.endswith(("X", "Y", "Ｘ", "Ｙ")):
                base_species = get_species_by_name_ja(base_name[:-1])
            # Try _FORM_MISSING_MEGA_STATS first for accurate mega stats
            if base_species:
                smogon_name = _smogon_mega(base_species.name_en or "", name_ja)
                fb = _FORM_MISSING_MEGA_STATS.get(smogon_name)
                if fb:
                    fb_en, fb_t1, fb_t2, fb_hp, fb_atk, fb_def, fb_spa, fb_spd, fb_spe, fb_wt = fb
                    species = SpeciesInfo(
                        species_id=base_species.species_id,
                        name_ja=name_ja, name_en=fb_en,
                        type1=fb_t1, type2=fb_t2,
                        base_hp=fb_hp, base_attack=fb_atk, base_defense=fb_def,
                        base_sp_attack=fb_spa, base_sp_defense=fb_spd, base_speed=fb_spe,
                        weight_kg=fb_wt,
                    )
                else:
                    species = base_species

        # Fallback: resolve usage-scraper shorthand forms that may differ from DB name_ja.
        # e.g. "フラエッテ(えいえん)" → "フラエッテ (えいえんのはな)" (if fetched) or "フラエッテ"
        if species is None and name_ja:
            _FLOETTE_ALIASES = ("フラエッテ(えいえん)", "フラエッテ (えいえん)",
                                "フラエッテ(えいえんのはな)", "フラエッテ (えいえんのはな)")
            if name_ja in _FLOETTE_ALIASES:
                species = get_species_by_name_ja("フラエッテ (えいえんのはな)")
                if species is None:
                    species = get_species_by_name_ja("フラエッテ")

        # Last resort: strip parenthetical form suffix and try base name
        if species is None and name_ja:
            import re as _re
            base = _re.sub(r"\s*[（(].*?[)）]", "", name_ja).strip()
            if base and base != name_ja:
                species = get_species_by_name_ja(base)

        return species

    def _calc_moves(self) -> None:
        from src.ui.damage_panel_calc_logic import _calc_moves as _impl
        return _impl(self)

    def _refresh_defender_card(self, atk_view: Optional[PokemonInstance] = None) -> None:
        self._atk_card.set_pokemon(atk_view if atk_view is not None else self._atk)
        self._def_card.set_pokemon(self._def_custom)

    def _persist_party_member_edits(self) -> None:
        if self._atk:
            self._atk.ev_hp = self._atk_panel.ev_hp_pts() * 8
            self._atk.ev_attack = self._atk_panel.ev_attack_pts() * 8
            self._atk.ev_defense = self._atk_panel.ev_defense_pts() * 8
            self._atk.ev_sp_attack = self._atk_panel.ev_sp_attack_pts() * 8
            self._atk.ev_sp_defense = self._atk_panel.ev_sp_defense_pts() * 8
            self._atk.ev_speed = self._atk_panel.ev_speed_pts() * 8
            self._atk.nature = self._atk_panel.panel_nature()

        if self._def_custom:
            self._def_custom.ev_hp = self._def_panel.ev_hp_pts() * 8
            self._def_custom.ev_attack = self._def_panel.ev_attack_pts() * 8
            self._def_custom.ev_defense = self._def_panel.ev_defense_pts() * 8
            self._def_custom.ev_sp_attack = self._def_panel.ev_sp_attack_pts() * 8
            self._def_custom.ev_sp_defense = self._def_panel.ev_sp_defense_pts() * 8
            self._def_custom.ev_speed = self._def_panel.ev_speed_pts() * 8
            self._def_custom.nature = self._def_panel.panel_nature()

        if self._atk and self._atk_party_side in ("my", "opp") and self._atk_party_idx is not None:
            party = self._my_party if self._atk_party_side == "my" else self._opp_party
            if 0 <= self._atk_party_idx < len(party):
                party[self._atk_party_idx] = copy.deepcopy(self._atk)
        if self._def_custom and self._def_party_side in ("my", "opp") and self._def_party_idx is not None:
            party = self._my_party if self._def_party_side == "my" else self._opp_party
            if 0 <= self._def_party_idx < len(party):
                party[self._def_party_idx] = copy.deepcopy(self._def_custom)

    def _on_atk_panel_changed(self) -> None:
        from src.ui.damage_panel_signal_handlers import _on_atk_panel_changed as _impl
        return _impl(self)

    def _on_def_panel_changed(self) -> None:
        from src.ui.damage_panel_signal_handlers import _on_def_panel_changed as _impl
        return _impl(self)

    def _effective_def_types(self) -> list[str]:
        tera = self._def_panel.terastal_type() if hasattr(self, "_def_panel") else ""
        if tera:
            return [tera]
        if self._def_custom:
            return self._def_custom.types or ["normal"]
        return ["normal"]

    def _active_party(self) -> list[Optional[PokemonInstance]]:
        return self._opp_party if self._party_source == "opp" else self._my_party

    def _refresh_party_selector_labels(self) -> None:
        if not hasattr(self, "_my_party_row_label"):
            return
        self._my_party_row_label.setText("自分PT")
        self._opp_party_row_label.setText("相手PT")

    def _refresh_party_slots(self) -> None:
        if not hasattr(self, "_my_party_slots"):
            return
        my_is_attacker = (self._party_source == "my")
        # カノニカル（基本フォーム）名で比較することでメガ時もハイライトがずれない
        atk_canon = (_FORM_NAME_TO_GROUP.get(self._atk.name_ja) or [self._atk.name_ja])[0] if self._atk else ""
        def_canon = (_FORM_NAME_TO_GROUP.get(self._def_custom.name_ja) or [self._def_custom.name_ja])[0] if self._def_custom else ""
        atk_current = self._atk.name_ja if self._atk else ""
        def_current = self._def_custom.name_ja if self._def_custom else ""
        atk_idx_known = self._atk_party_side is not None and self._atk_party_idx is not None
        def_idx_known = self._def_party_side is not None and self._def_party_idx is not None
        for i, slot in enumerate(self._my_party_slots):
            if i < len(self._my_party) and self._my_party[i]:
                name = self._my_party[i].name_ja
                name_canon = (_FORM_NAME_TO_GROUP.get(name) or [name])[0]
                if atk_idx_known:
                    is_atk = my_is_attacker and self._atk_party_side == "my" and self._atk_party_idx == i
                else:
                    is_atk = my_is_attacker and name_canon == atk_canon
                if def_idx_known:
                    is_def = not my_is_attacker and self._def_party_side == "my" and self._def_party_idx == i
                else:
                    is_def = not my_is_attacker and name_canon == def_canon
                sprite = (atk_current if is_atk else def_current if is_def else "") or name
                slot.set_name(name, attack_active=is_atk, defense_active=is_def, sprite_name=sprite)
            else:
                slot.set_name("")
        for i, slot in enumerate(self._opp_party_slots):
            if i < len(self._opp_party) and self._opp_party[i]:
                name = self._opp_party[i].name_ja
                name_canon = (_FORM_NAME_TO_GROUP.get(name) or [name])[0]
                if atk_idx_known:
                    is_atk = not my_is_attacker and self._atk_party_side == "opp" and self._atk_party_idx == i
                else:
                    is_atk = not my_is_attacker and name_canon == atk_canon
                if def_idx_known:
                    is_def = my_is_attacker and self._def_party_side == "opp" and self._def_party_idx == i
                else:
                    is_def = my_is_attacker and name_canon == def_canon
                sprite = (atk_current if is_atk else def_current if is_def else "") or name
                slot.set_name(name, attack_active=is_atk, defense_active=is_def, sprite_name=sprite)
            else:
                slot.set_name("")

    # ── Event handlers ────────────────────────────────────────────────

    def _edit_attacker(self) -> None:
        from src.ui.damage_panel_signal_handlers import _edit_attacker as _impl
        return _impl(self)

    def _new_attacker(self) -> None:
        from src.ui.damage_panel_signal_handlers import _new_attacker as _impl
        return _impl(self)

    def _clear_attacker(self) -> None:
        from src.ui.damage_panel_signal_handlers import _clear_attacker as _impl
        return _impl(self)

    def _change_attacker(self) -> None:
        from src.ui.damage_panel_signal_handlers import _change_attacker as _impl
        return _impl(self)

    def _edit_defender(self) -> None:
        from src.ui.damage_panel_signal_handlers import _edit_defender as _impl
        return _impl(self)

    def _new_defender(self) -> None:
        from src.ui.damage_panel_signal_handlers import _new_defender as _impl
        return _impl(self)

    def _clear_defender(self) -> None:
        from src.ui.damage_panel_signal_handlers import _clear_defender as _impl
        return _impl(self)

    def _change_defender(self) -> None:
        from src.ui.damage_panel_signal_handlers import _change_defender as _impl
        return _impl(self)

    def _box_select_into_slot(self, side: str, idx: int) -> None:
        from src.ui.damage_panel_signal_handlers import _box_select_into_slot as _impl
        return _impl(self, side, idx)

    def _change_move(self, slot: int) -> None:
        from src.ui.damage_panel_signal_handlers import _change_move as _impl
        return _impl(self, slot)

    def _change_opp_move(self, slot: int) -> None:
        from src.ui.damage_panel_signal_handlers import _change_opp_move as _impl
        return _impl(self, slot)

    def _swap_atk_def(self) -> None:
        from src.ui.damage_panel_signal_handlers import _swap_atk_def as _impl
        return _impl(self)

    def _reset_conditions(self) -> None:
        from src.ui.damage_panel_signal_handlers import _reset_conditions as _impl
        return _impl(self)

    def _set_attacker_from_party(self, pokemon: PokemonInstance, source: str) -> None:
        from src.ui.damage_panel_signal_handlers import _set_attacker_from_party as _impl
        return _impl(self, pokemon, source)

    def _set_defender_from_party(self, pokemon: PokemonInstance) -> None:
        from src.ui.damage_panel_signal_handlers import _set_defender_from_party as _impl
        return _impl(self, pokemon)

    def _change_atk_ability(self) -> None:
        from src.ui.damage_panel_signal_handlers import _change_atk_ability as _impl
        return _impl(self)

    def _change_atk_item(self) -> None:
        from src.ui.damage_panel_signal_handlers import _change_atk_item as _impl
        return _impl(self)

    def _change_def_ability(self) -> None:
        from src.ui.damage_panel_signal_handlers import _change_def_ability as _impl
        return _impl(self)

    def _change_def_item(self) -> None:
        from src.ui.damage_panel_signal_handlers import _change_def_item as _impl
        return _impl(self)

    def _on_form_change_atk(self) -> None:
        from src.ui.damage_panel_signal_handlers import _on_form_change_atk as _impl
        return _impl(self)

    def _on_form_change_def(self) -> None:
        from src.ui.damage_panel_signal_handlers import _on_form_change_def as _impl
        return _impl(self)

    def _on_my_party_slot_clicked(self, idx: int) -> None:
        from src.ui.damage_panel_signal_handlers import _on_my_party_slot_clicked as _impl
        return _impl(self, idx)

    def _on_opp_party_slot_clicked(self, idx: int) -> None:
        from src.ui.damage_panel_signal_handlers import _on_opp_party_slot_clicked as _impl
        return _impl(self, idx)

    def _set_battle_format(self, mode: str) -> None:
        from src.ui.damage_panel_signal_handlers import _set_battle_format as _impl
        return _impl(self, mode)

    def _toggle_details(self, checked: bool) -> None:
        from src.ui.damage_panel_signal_handlers import _toggle_details as _impl
        return _impl(self, checked)

    def _apply_bulk_rows_default(self) -> None:
        from src.ui.damage_panel_signal_handlers import _apply_bulk_rows_default as _impl
        return _impl(self)

    def _set_bulk_rows_visible(self, visible: bool, refresh: bool = True) -> None:
        from src.ui.damage_panel_signal_handlers import _set_bulk_rows_visible as _impl
        return _impl(self, visible, refresh)

    def _on_bulk_toggle_clicked(self, checked: bool) -> None:
        from src.ui.damage_panel_signal_handlers import _on_bulk_toggle_clicked as _impl
        return _impl(self, checked)

    def _refresh_bulk_rows_visibility(self) -> None:
        pass

    def _weather_key(self) -> str:
        return {"はれ": "sun", "あめ": "rain", "すな": "sand", "ゆき": "hail"}.get(
            self._weather_grp.value(), "none")

    def _terrain_key(self) -> str:
        return {"エレキ": "electric", "グラス": "grassy",
                "ミスト": "misty", "サイコ": "psychic"}.get(
            self._terrain_grp.value(), "none")
