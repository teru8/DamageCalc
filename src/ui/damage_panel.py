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
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scrollable main content (cards + moves + party slots)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll.setLayoutDirection(Qt.RightToLeft)
        content = QWidget()
        content.setLayoutDirection(Qt.LeftToRight)
        scroll.setWidget(content)
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(6, 6, 6, 6)
        self._content_layout.setSpacing(6)
        root.addWidget(scroll, 1)

        self._build_side_panel()
        self._build_content()

    @property
    def side_panel(self) -> QWidget:
        """Attacker/defender controls + battle settings widget (hosted in cam panel)."""
        return self._side_panel

    def _build_side_panel(self) -> None:
        """Build attacker/defender detail controls + battle conditions as a standalone widget."""
        sp_scroll = QScrollArea()
        sp_scroll.setWidgetResizable(True)
        sp_scroll.setFrameShape(QFrame.NoFrame)
        sp_content = QWidget()
        sp_scroll.setWidget(sp_content)
        self._side_panel = sp_scroll

        sp = QVBoxLayout(sp_content)
        sp.setContentsMargins(6, 6, 6, 6)
        sp.setSpacing(6)

        # Attacker + Defender side by side
        panels_row = QHBoxLayout()
        panels_row.setSpacing(6)

        self._atk_panel = _AttackerPanel()
        self._atk_panel.changed.connect(self._on_atk_panel_changed)
        self._atk_panel.edit_requested.connect(self._edit_attacker)
        self._atk_panel.change_requested.connect(self._change_attacker)
        self._atk_panel.new_requested.connect(self._new_attacker)
        self._atk_panel.clear_requested.connect(self._clear_attacker)
        panels_row.addWidget(self._atk_panel, 1, Qt.AlignTop)

        self._def_panel = _DefenderPanel()
        self._def_panel.changed.connect(self._on_def_panel_changed)
        self._def_panel.edit_requested.connect(self._edit_defender)
        self._def_panel.change_requested.connect(self._change_defender)
        self._def_panel.new_requested.connect(self._new_defender)
        self._def_panel.clear_requested.connect(self._clear_defender)
        panels_row.addWidget(self._def_panel, 1, Qt.AlignTop)

        self._atk_panel.ev_section_toggled.connect(self._def_panel.sync_ev_section)
        self._def_panel.ev_section_toggled.connect(self._atk_panel.sync_ev_section)

        sp.addLayout(panels_row)
        self.set_terastal_controls_visible(False)

        # Detail toggle button (for backwards compatibility but hidden)
        self._detail_toggle_btn = QPushButton("詳細設定を表示")
        self._detail_toggle_btn.setCheckable(True)
        self._detail_toggle_btn.setChecked(True)
        self._detail_toggle_btn.toggled.connect(self._toggle_details)
        self._detail_toggle_btn.setText("詳細設定を隠す")
        self._detail_toggle_btn.setVisible(False)  # Hidden, always show details

        self._detail_container = QWidget()
        self._detail_container.setVisible(True)
        dl = QVBoxLayout(self._detail_container)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(6)
        sp.addWidget(self._detail_container)

        dl.addWidget(_sep())

        self._set_battle_format("single")

        wf_row = QHBoxLayout()
        wf_row.setContentsMargins(0, 0, 0, 0)
        wf_row.setSpacing(8)

        _weather_col = QVBoxLayout()
        _weather_col.setContentsMargins(0, 0, 0, 0)
        _weather_col.setSpacing(2)
        _weather_col.addWidget(_row_label("天気"))
        self._weather_grp = _RadioGroup(["はれ", "あめ", "すな", "ゆき"])
        self._weather_grp.set_button_metrics(font_size=14, height=28, min_width=48, pad_h=4, pad_v=2)
        self._weather_grp.changed.connect(self.recalculate)
        _weather_col.addWidget(self._weather_grp)
        wf_row.addLayout(_weather_col)
        wf_row.setAlignment(_weather_col, Qt.AlignTop)

        _terrain_col = QVBoxLayout()
        _terrain_col.setContentsMargins(0, 0, 0, 0)
        _terrain_col.setSpacing(2)
        _terrain_col.addWidget(_row_label("フィールド"))
        self._terrain_grp = _RadioGroup(["エレキ", "グラス", "ミスト", "サイコ"])
        self._terrain_grp.set_button_metrics(font_size=14, height=28, min_width=48, pad_h=4, pad_v=2)
        self._terrain_grp.changed.connect(self.recalculate)
        _terrain_col.addWidget(self._terrain_grp)
        wf_row.addLayout(_terrain_col, 4)
        wf_row.setAlignment(_terrain_col, Qt.AlignTop)

        _gravity_col = QVBoxLayout()
        _gravity_col.setContentsMargins(0, 0, 0, 0)
        _gravity_col.setSpacing(2)
        _gravity_lbl = _row_label("じゅうりょく")
        _gravity_lbl.setStyleSheet("color: transparent; font-size:14px; font-weight:bold;")
        _gravity_col.addWidget(_gravity_lbl)
        self._gravity_btn = _ToggleBtn("じゅうりょく")
        self._gravity_btn.set_metrics(font_size=14, pad_h=4, pad_v=2)
        self._gravity_btn.setFixedHeight(28)
        self._gravity_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._gravity_btn.toggled.connect(lambda _: self.recalculate())
        _gravity_col.addWidget(self._gravity_btn)
        wf_row.addLayout(_gravity_col, 1)
        wf_row.setAlignment(_gravity_col, Qt.AlignTop)

        dl.addLayout(wf_row)

        dl.addWidget(_sep())

        # 自分側・相手側補助を左右2カラムで並べる
        both_sides_row = QHBoxLayout()
        both_sides_row.setContentsMargins(0, 0, 0, 0)
        both_sides_row.setSpacing(8)

        # ── 自分側補助 (左カラム) ────────────────────────────────
        self_side_col = QVBoxLayout()
        self_side_col.setContentsMargins(0, 0, 0, 0)
        self_side_col.setSpacing(4)
        self_side_col.addWidget(_row_label("自分側補助"))

        # 自分側 攻撃補助
        self_side_col.addWidget(_row_label("  攻撃側:"))
        atk_cond_ability = QHBoxLayout()  # 条件付きボタン行
        atk_cond_ability.setContentsMargins(0, 0, 0, 0)
        atk_cond_ability.setSpacing(4)
        atk_cond4 = QHBoxLayout()         # そうだいしょう/とうそうしんコンボ行
        atk_cond4.setContentsMargins(0, 0, 0, 0)
        atk_cond4.setSpacing(6)
        atk_cond1a = QHBoxLayout()        # 常時ボタン1行目: やけど・急所・じゅうでん
        atk_cond1a.setContentsMargins(0, 0, 0, 0)
        atk_cond1a.setSpacing(4)
        atk_cond1b = QHBoxLayout()        # 常時ボタン2行目: フェアリーオーラ・ダークオーラ
        atk_cond1b.setContentsMargins(0, 0, 0, 0)
        atk_cond1b.setSpacing(4)
        atk_cond1c = QHBoxLayout()        # 常時ボタン3行目: てだすけ・はがねのせいしん
        atk_cond1c.setContentsMargins(0, 0, 0, 0)
        atk_cond1c.setSpacing(4)
        self._burn_btn = _ToggleBtn("やけど")
        self._crit_btn = _ToggleBtn("きゅうしょ")
        self._fairy_aura_btn = _ToggleBtn("フェアリーオーラ")
        self._dark_aura_btn = _ToggleBtn("ダークオーラ")
        self._charge_btn = _ToggleBtn("じゅうでん")
        self._helping_btn = _ToggleBtn("てだすけ")
        self._steel_spirit_btn = _ToggleBtn("はがねのせいしん\n（未対応）")
        self._overgrow_btn = _ToggleBtn("しんりょく", cond_style=True)
        self._blaze_btn = _ToggleBtn("もうか", cond_style=True)
        self._torrent_btn = _ToggleBtn("げきりゅう", cond_style=True)
        self._swarm_btn = _ToggleBtn("むしのしらせ", cond_style=True)
        self._toxic_boost_btn = _ToggleBtn("どくぼうそう", cond_style=True)
        self._stakeout_btn = _ToggleBtn("はりこみ", cond_style=True)
        self._flash_fire_boost_btn = _ToggleBtn("もらいび", cond_style=True)
        self._protosynthesis_btn = _ToggleBtn("こだいかっせい", cond_style=True)
        self._quark_drive_btn = _ToggleBtn("クォークチャージ", cond_style=True)
        self._analytic_btn = _ToggleBtn("アナライズ", cond_style=True)
        self._flare_boost_btn = _ToggleBtn("ねつぼうそう", cond_style=True)
        self._guts_btn = _ToggleBtn("こんじょう", cond_style=True)
        self._attacker_ability_cond_btns: dict[str, _ToggleBtn] = {
            "しんりょく": self._overgrow_btn,
            "もうか": self._blaze_btn,
            "げきりゅう": self._torrent_btn,
            "むしのしらせ": self._swarm_btn,
            "どくぼうそう": self._toxic_boost_btn,
        }
        self._attacker_trigger_cond_btns: dict[str, _ToggleBtn] = {
            "はりこみ": self._stakeout_btn,
            "もらいび": self._flash_fire_boost_btn,
            "こだいかっせい": self._protosynthesis_btn,
            "クォークチャージ": self._quark_drive_btn,
            "アナライズ": self._analytic_btn,
            "ねつぼうそう": self._flare_boost_btn,
            "こんじょう": self._guts_btn,
        }
        for btn in (self._burn_btn, self._crit_btn, self._fairy_aura_btn,
                    self._dark_aura_btn, self._charge_btn, self._helping_btn,
                    self._steel_spirit_btn):
            btn.setFixedHeight(40)
            btn.setMinimumWidth(70)
            btn.toggled.connect(lambda _: self.recalculate())
        for btn in self._attacker_ability_cond_btns.values():
            btn.setFixedHeight(28)
            btn.setMinimumWidth(70)
            btn.toggled.connect(lambda _: self.recalculate())
            btn.setVisible(False)
            atk_cond_ability.addWidget(btn)
        for btn in self._attacker_trigger_cond_btns.values():
            btn.setFixedHeight(28)
            btn.setMinimumWidth(70)
            btn.toggled.connect(lambda _: self.recalculate())
            btn.setVisible(False)
            atk_cond_ability.addWidget(btn)
        for btn in (self._burn_btn, self._crit_btn, self._charge_btn):
            atk_cond1a.addWidget(btn)
        for btn in (self._fairy_aura_btn, self._dark_aura_btn):
            atk_cond1b.addWidget(btn)
        for btn in (self._helping_btn, self._steel_spirit_btn):
            atk_cond1c.addWidget(btn)

        self._supreme_combo = QComboBox()
        self._supreme_combo.setFixedHeight(24)
        self._supreme_combo.addItem("そうだいしょう", 0)
        for i in range(1, 6):
            self._supreme_combo.addItem("{}体ひんし".format(i), i)
        self._supreme_combo.setStyleSheet(
            "QComboBox{background:#3a3218;color:#f9e2af;border:1px solid #a87d3a;"
            "border-radius:4px;padding:4px 8px;font-size:14px;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox::down-arrow{image:none;width:0;height:0;}"
            "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
        )
        self._supreme_combo.currentIndexChanged.connect(self._refresh_supreme_combo)
        self._supreme_combo.setVisible(False)

        self._rivalry_combo = QComboBox()
        self._rivalry_combo.setFixedHeight(24)
        self._rivalry_combo.addItem("とうそうしん", "none")
        self._rivalry_combo.addItem("同性", "same")
        self._rivalry_combo.addItem("異性", "opposite")
        self._rivalry_combo.setStyleSheet(
            "QComboBox{background:#3a3218;color:#f9e2af;border:1px solid #a87d3a;"
            "border-radius:4px;padding:4px 8px;font-size:14px;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox::down-arrow{image:none;width:0;height:0;}"
            "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
        )
        self._rivalry_combo.currentIndexChanged.connect(self._refresh_rivalry_combo)
        self._rivalry_combo.setVisible(False)
        atk_cond4.addWidget(self._supreme_combo)
        atk_cond4.addWidget(self._rivalry_combo)
        atk_cond_ability.addStretch()
        atk_cond4.addStretch()
        atk_cond1a.addStretch()
        atk_cond1b.addStretch()
        atk_cond1c.addStretch()
        self_side_col.addLayout(atk_cond_ability)
        self_side_col.addLayout(atk_cond4)
        self_side_col.addLayout(atk_cond1a)
        self_side_col.addLayout(atk_cond1b)
        self_side_col.addLayout(atk_cond1c)

        # 自分側 防御補助 (相手→自分 計算に使用)
        self_side_col.addSpacing(8)
        self_side_col.addWidget(_row_label("  防御側:"))
        self_def_cond = QHBoxLayout()
        self_def_cond.setContentsMargins(0, 0, 0, 4)
        self_def_cond.setSpacing(4)
        self._self_reflect_btn = _ToggleBtn("リフレクター")
        self._self_lightscreen_btn = _ToggleBtn("ひかりのかべ")
        self._self_friend_guard_btn = _ToggleBtn("フレンドガード")
        self._self_tailwind_btn = _ToggleBtn("おいかぜ")
        self_def_cond2 = QHBoxLayout()
        self_def_cond2.setContentsMargins(0, 0, 0, 4)
        self_def_cond2.setSpacing(4)
        for btn in (self._self_reflect_btn, self._self_lightscreen_btn, self._self_tailwind_btn, self._self_friend_guard_btn):
            btn.setFixedHeight(40)
            btn.setMinimumWidth(70)
            btn.toggled.connect(lambda _: self.recalculate())
        for btn in (self._self_reflect_btn, self._self_lightscreen_btn, self._self_tailwind_btn):
            self_def_cond.addWidget(btn)
        self_def_cond2.addWidget(self._self_friend_guard_btn)
        self_def_cond.addStretch()
        self_def_cond2.addStretch()
        self_side_col.addLayout(self_def_cond)
        self_side_col.addLayout(self_def_cond2)
        self_side_col.addStretch()

        # ── 相手側補助 (右カラム) ────────────────────────────────
        opp_side_col = QVBoxLayout()
        opp_side_col.setContentsMargins(0, 0, 0, 0)
        opp_side_col.setSpacing(4)
        opp_side_col.addWidget(_row_label("相手側補助"))

        # 相手側 攻撃補助 (相手→自分 計算に使用)
        opp_side_col.addWidget(_row_label("  攻撃側:"))
        opp_atk_cond_ability = QHBoxLayout()  # 条件付きボタン行
        opp_atk_cond_ability.setContentsMargins(0, 0, 0, 0)
        opp_atk_cond_ability.setSpacing(4)
        opp_atk_cond4 = QHBoxLayout()           # そうだいしょうコンボ行
        opp_atk_cond4.setContentsMargins(0, 0, 0, 0)
        opp_atk_cond4.setSpacing(6)
        opp_atk_cond1a = QHBoxLayout()          # 常時ボタン1行目: やけど・急所・じゅうでん
        opp_atk_cond1a.setContentsMargins(0, 0, 0, 0)
        opp_atk_cond1a.setSpacing(4)
        opp_atk_cond1b = QHBoxLayout()          # 常時ボタン2行目: フェアリーオーラ・ダークオーラ
        opp_atk_cond1b.setContentsMargins(0, 0, 0, 0)
        opp_atk_cond1b.setSpacing(4)
        opp_atk_cond1c = QHBoxLayout()          # 常時ボタン3行目: てだすけ・はがねのせいしん
        opp_atk_cond1c.setContentsMargins(0, 0, 0, 0)
        opp_atk_cond1c.setSpacing(4)
        self._opp_burn_btn = _ToggleBtn("やけど")
        self._opp_crit_btn = _ToggleBtn("きゅうしょ")
        self._opp_fairy_aura_btn = _ToggleBtn("フェアリーオーラ")
        self._opp_dark_aura_btn = _ToggleBtn("ダークオーラ")
        self._opp_charge_btn = _ToggleBtn("じゅうでん")
        self._opp_helping_btn = _ToggleBtn("てだすけ")
        self._opp_steel_spirit_btn = _ToggleBtn("はがねのせいしん\n（未対応）")
        for btn in (self._opp_burn_btn, self._opp_crit_btn, self._opp_fairy_aura_btn,
                    self._opp_dark_aura_btn, self._opp_charge_btn, self._opp_helping_btn,
                    self._opp_steel_spirit_btn):
            btn.setFixedHeight(40)
            btn.setMinimumWidth(70)
            btn.toggled.connect(lambda _: self.recalculate())
        for btn in (self._opp_burn_btn, self._opp_crit_btn, self._opp_charge_btn):
            opp_atk_cond1a.addWidget(btn)
        for btn in (self._opp_fairy_aura_btn, self._opp_dark_aura_btn):
            opp_atk_cond1b.addWidget(btn)
        for btn in (self._opp_helping_btn, self._opp_steel_spirit_btn):
            opp_atk_cond1c.addWidget(btn)
        self._opp_overgrow_btn = _ToggleBtn("しんりょく", cond_style=True)
        self._opp_blaze_btn = _ToggleBtn("もうか", cond_style=True)
        self._opp_torrent_btn = _ToggleBtn("げきりゅう", cond_style=True)
        self._opp_swarm_btn = _ToggleBtn("むしのしらせ", cond_style=True)
        self._opp_toxic_boost_btn = _ToggleBtn("どくぼうそう", cond_style=True)
        self._opp_stakeout_btn = _ToggleBtn("はりこみ", cond_style=True)
        self._opp_flash_fire_btn = _ToggleBtn("もらいび", cond_style=True)
        self._opp_protosynthesis_btn = _ToggleBtn("こだいかっせい", cond_style=True)
        self._opp_quark_drive_btn = _ToggleBtn("クォークチャージ", cond_style=True)
        self._opp_analytic_btn = _ToggleBtn("アナライズ", cond_style=True)
        self._opp_flare_boost_btn = _ToggleBtn("ねつぼうそう", cond_style=True)
        self._opp_guts_btn = _ToggleBtn("こんじょう", cond_style=True)
        self._defender_ability_cond_btns: dict[str, _ToggleBtn] = {
            "しんりょく": self._opp_overgrow_btn,
            "もうか": self._opp_blaze_btn,
            "げきりゅう": self._opp_torrent_btn,
            "むしのしらせ": self._opp_swarm_btn,
            "どくぼうそう": self._opp_toxic_boost_btn,
        }
        self._defender_trigger_cond_btns: dict[str, _ToggleBtn] = {
            "はりこみ": self._opp_stakeout_btn,
            "もらいび": self._opp_flash_fire_btn,
            "こだいかっせい": self._opp_protosynthesis_btn,
            "クォークチャージ": self._opp_quark_drive_btn,
            "アナライズ": self._opp_analytic_btn,
            "ねつぼうそう": self._opp_flare_boost_btn,
            "こんじょう": self._opp_guts_btn,
        }
        for btn in self._defender_ability_cond_btns.values():
            btn.setFixedHeight(28)
            btn.setMinimumWidth(70)
            btn.toggled.connect(lambda _: self.recalculate())
            btn.setVisible(False)
            opp_atk_cond_ability.addWidget(btn)
        for btn in self._defender_trigger_cond_btns.values():
            btn.setFixedHeight(28)
            btn.setMinimumWidth(70)
            btn.toggled.connect(lambda _: self.recalculate())
            btn.setVisible(False)
            opp_atk_cond_ability.addWidget(btn)

        self._opp_supreme_combo = QComboBox()
        self._opp_supreme_combo.setFixedHeight(24)
        self._opp_supreme_combo.addItem("そうだいしょう", 0)
        for i in range(1, 6):
            self._opp_supreme_combo.addItem("{}体ひんし".format(i), i)
        self._opp_supreme_combo.setStyleSheet(
            "QComboBox{background:#3a3218;color:#f9e2af;border:1px solid #a87d3a;"
            "border-radius:4px;padding:4px 8px;font-size:14px;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox::down-arrow{image:none;width:0;height:0;}"
            "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
        )
        self._opp_supreme_combo.currentIndexChanged.connect(self._refresh_opp_supreme_combo)
        self._opp_supreme_combo.setVisible(False)

        self._opp_rivalry_combo = QComboBox()
        self._opp_rivalry_combo.setFixedHeight(24)
        self._opp_rivalry_combo.addItem("とうそうしん", "none")
        self._opp_rivalry_combo.addItem("同性", "same")
        self._opp_rivalry_combo.addItem("異性", "opposite")
        self._opp_rivalry_combo.setStyleSheet(
            "QComboBox{background:#3a3218;color:#f9e2af;border:1px solid #a87d3a;"
            "border-radius:4px;padding:4px 8px;font-size:14px;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox::down-arrow{image:none;width:0;height:0;}"
            "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
        )
        self._opp_rivalry_combo.currentIndexChanged.connect(self._refresh_opp_rivalry_combo)
        self._opp_rivalry_combo.setVisible(False)
        opp_atk_cond4.addWidget(self._opp_supreme_combo)
        opp_atk_cond4.addWidget(self._opp_rivalry_combo)
        opp_atk_cond_ability.addStretch()
        opp_atk_cond4.addStretch()
        opp_atk_cond1a.addStretch()
        opp_atk_cond1b.addStretch()
        opp_atk_cond1c.addStretch()
        opp_side_col.addLayout(opp_atk_cond_ability)
        opp_side_col.addLayout(opp_atk_cond4)
        opp_side_col.addLayout(opp_atk_cond1a)
        opp_side_col.addLayout(opp_atk_cond1b)
        opp_side_col.addLayout(opp_atk_cond1c)

        # 相手側 防御補助 (自分→相手 計算に使用)
        opp_side_col.addSpacing(8)
        opp_side_col.addWidget(_row_label("  防御側:"))
        def_cond = QHBoxLayout()
        def_cond.setContentsMargins(0, 0, 0, 4)
        def_cond.setSpacing(4)
        self._reflect_btn = _ToggleBtn("リフレクター")
        self._lightscreen_btn = _ToggleBtn("ひかりのかべ")
        self._friend_guard_btn = _ToggleBtn("フレンドガード")
        self._tailwind_btn = _ToggleBtn("おいかぜ")
        def_cond2 = QHBoxLayout()
        def_cond2.setContentsMargins(0, 0, 0, 4)
        def_cond2.setSpacing(4)
        for btn in (self._reflect_btn, self._lightscreen_btn, self._tailwind_btn, self._friend_guard_btn):
            btn.setFixedHeight(40)
            btn.setMinimumWidth(70)
            btn.toggled.connect(lambda _: self.recalculate())
        for btn in (self._reflect_btn, self._lightscreen_btn, self._tailwind_btn):
            def_cond.addWidget(btn)
        def_cond2.addWidget(self._friend_guard_btn)
        def_cond.addStretch()
        def_cond2.addStretch()
        opp_side_col.addLayout(def_cond)
        opp_side_col.addLayout(def_cond2)
        opp_side_col.addStretch()

        both_sides_row.addLayout(self_side_col, 1)
        both_sides_row.addLayout(opp_side_col, 1)
        dl.addLayout(both_sides_row)

        # てだすけは初期状態(シングル)では非表示
        self._helping_btn.setVisible(False)
        self._opp_helping_btn.setVisible(False)
        self._steel_spirit_btn.setVisible(False)
        self._opp_steel_spirit_btn.setVisible(False)
        self._self_friend_guard_btn.setVisible(False)
        self._friend_guard_btn.setVisible(False)
        self._self_tailwind_btn.setVisible(False)
        self._tailwind_btn.setVisible(False)

        sp.addStretch()
        sp.addWidget(_sep())

        # Reset button at bottom – 50% width, left-aligned
        _reset_btn = QPushButton("リセット")
        _reset_btn.setFixedHeight(36)
        _reset_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _reset_btn.setStyleSheet(
            "QPushButton{font-size:14px;font-weight:bold;background:#313244;"
            "color:#cdd6f4;border:1px solid #45475a;border-radius:4px;}"
            "QPushButton:hover{background:#45475a;}"
        )
        _reset_btn.clicked.connect(self._reset_conditions)
        _reset_row = QHBoxLayout()
        _reset_row.setContentsMargins(0, 4, 0, 0)
        _reset_row.addWidget(_reset_btn, 1)
        _reset_row.addStretch(1)
        sp.addLayout(_reset_row)

    def _build_content(self) -> None:
        cl = self._content_layout

        # ── Party selection rows (top) ────────────────────────────────
        self._my_party_row_label = _row_label("")
        cl.addWidget(self._my_party_row_label)
        my_party_row = QHBoxLayout()
        my_party_row.setContentsMargins(0, 0, 0, 0)
        my_party_row.setSpacing(4)
        self._my_party_slots: list[_PartySlot] = []
        for i in range(6):
            slot = _PartySlot(i)
            slot.clicked_signal.connect(self._on_my_party_slot_clicked)
            slot.context_menu_requested.connect(lambda idx, pos: self._on_party_slot_context_menu("my", idx, pos))
            my_party_row.addWidget(slot)
            self._my_party_slots.append(slot)
        my_party_row.addStretch()
        cl.addLayout(my_party_row)

        self._opp_party_row_label = _row_label("")
        cl.addWidget(self._opp_party_row_label)
        opp_party_row = QHBoxLayout()
        opp_party_row.setContentsMargins(0, 0, 0, 0)
        opp_party_row.setSpacing(4)
        self._opp_party_slots: list[_PartySlot] = []
        for i in range(6):
            slot = _PartySlot(i)
            slot.clicked_signal.connect(self._on_opp_party_slot_clicked)
            slot.context_menu_requested.connect(lambda idx, pos: self._on_party_slot_context_menu("opp", idx, pos))
            opp_party_row.addWidget(slot)
            self._opp_party_slots.append(slot)
        self._opp_party_action_host = QWidget()
        self._opp_party_action_layout = QVBoxLayout(self._opp_party_action_host)
        self._opp_party_action_layout.setContentsMargins(0, 0, 0, 0)
        self._opp_party_action_layout.setSpacing(0)
        opp_party_row.addWidget(self._opp_party_action_host, 0, Qt.AlignVCenter)
        opp_party_row.addStretch()
        cl.addLayout(opp_party_row)

        cl.addWidget(_sep())

        # ── Attacker / Defender cards in one horizontal row ───────────
        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(4)

        self._atk_card = _AttackerCard()
        self._atk_card.ability_change_requested.connect(self._change_atk_ability)
        self._atk_card.item_change_requested.connect(self._change_atk_item)
        cards_row.addWidget(self._atk_card, 1)

        self._def_card = _DefenderCard()
        self._def_card.ability_change_requested.connect(self._change_def_ability)
        self._def_card.item_change_requested.connect(self._change_def_item)
        self._def_card.form_change_requested.connect(self._on_form_change_def)
        cards_row.addWidget(self._def_card, 1)

        self._atk_card.form_change_requested.connect(self._on_form_change_atk)

        cl.addLayout(cards_row)

        cl.addWidget(_sep())

        # Move sections: left (自分→相手) + right (相手→自分) pairs
        self._move_sections: list[_MoveSection] = []
        self._opp_move_sections: list[_MoveSection] = []
        for i in range(4):
            pair = QWidget()
            pair_layout = QHBoxLayout(pair)
            pair_layout.setContentsMargins(0, 0, 0, 0)
            pair_layout.setSpacing(0)

            sec = _MoveSection(i, right_side=False)
            sec.move_change_requested.connect(self._change_move)
            sec._pow_combo.currentIndexChanged.connect(self.recalculate)
            sec._hit_spin.valueChanged.connect(self.recalculate)
            sec.set_bulk_rows_visible(self._show_bulk_rows)
            self._move_sections.append(sec)
            pair_layout.addWidget(sec, 1)

            vsep = QFrame()
            vsep.setFrameShape(QFrame.VLine)
            vsep.setStyleSheet("QFrame{border:none;border-left:1px solid #45475a;}")
            pair_layout.addWidget(vsep)

            opp_sec = _MoveSection(i, right_side=True)
            opp_sec.move_change_requested.connect(self._change_opp_move)
            opp_sec._pow_combo.currentIndexChanged.connect(self.recalculate)
            opp_sec._hit_spin.valueChanged.connect(self.recalculate)
            opp_sec.set_bulk_rows_visible(self._show_bulk_rows)
            self._opp_move_sections.append(opp_sec)
            pair_layout.addWidget(opp_sec, 1)

            cl.addWidget(pair)
            if i < 3:
                cl.addWidget(_sep())

        cl.addWidget(_sep())
        cl.addStretch()
        self._refresh_party_selector_labels()

    # ── Public API ────────────────────────────────────────────────────

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
        from PyQt5.QtWidgets import QMenu, QAction

        party = self._my_party if side == "my" else self._opp_party

        menu = QMenu(self)

        if idx < len(party) and party[idx] is not None:
            act_change = QAction("変更", menu)
            act_change.triggered.connect(lambda: self._edit_party_slot(side, idx))
            menu.addAction(act_change)

            act_save = QAction("保存", menu)
            act_save.triggered.connect(lambda: self._save_party_slot_to_db(side, idx))
            menu.addAction(act_save)
        else:
            act_add = QAction("新規登録", menu)
            act_add.triggered.connect(lambda: self._add_party_slot(side, idx))
            menu.addAction(act_add)

        menu.exec_(global_pos)

    def _edit_party_slot(self, side: str, idx: int) -> None:
        party = self._my_party if side == "my" else self._opp_party
        if idx >= len(party) or party[idx] is None:
            return

        dlg = open_pokemon_edit_dialog(None, self, save_to_db=False)
        if not dlg.exec_():
            if dlg.box_select_requested():
                QTimer.singleShot(0, lambda: self._box_select_into_slot(side, idx))
            return

        updated = dlg.get_pokemon()
        if not updated:
            return

        party[idx] = copy.deepcopy(updated)

        # 編集したスロットを選択状態にし、atk/def も更新する（_persist_party_member_edits の上書きを防ぐため先に設定）
        if self._party_source == side:
            self._atk_party_side = side
            self._atk_party_idx = idx
            self._atk = copy.deepcopy(updated)
            self._atk_panel.set_pokemon(self._atk)
            self.attacker_changed.emit(self._atk)
        else:
            self._def_party_side = side
            self._def_party_idx = idx
            self._def_custom = copy.deepcopy(updated)
            self._def_species_name = self._def_custom.name_ja
            self._def_panel.set_pokemon(self._def_custom)
            self.defender_changed.emit(self._def_custom)

        self.registry_maybe_changed.emit()
        self._refresh_party_slots()
        self._refresh_defender_card()
        self.recalculate()

    def _save_party_slot_to_db(self, side: str, idx: int) -> None:
        from src.data import database as db

        party = self._my_party if side == "my" else self._opp_party
        if idx >= len(party) or party[idx] is None:
            return

        pokemon = party[idx]
        pokemon.db_id = db.save_pokemon(pokemon)
        self.registry_maybe_changed.emit()

    def _add_party_slot(self, side: str, idx: int) -> None:
        dlg = open_pokemon_edit_dialog(None, self, save_to_db=False)
        if not dlg.exec_():
            if dlg.box_select_requested():
                QTimer.singleShot(0, lambda: self._box_select_into_slot(side, idx))
            return
        new_pokemon = dlg.get_pokemon()
        if not new_pokemon:
            return

        party = self._my_party if side == "my" else self._opp_party
        while len(party) <= idx:
            party.append(None)
        party[idx] = copy.deepcopy(new_pokemon)
        if side == "my":
            self._on_my_party_slot_clicked(idx)
        else:
            self._on_opp_party_slot_clicked(idx)

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

        if hasattr(self, "_opp_supreme_combo"):
            show_opp_supreme = ability in ("そうだいしょう", "Supreme Overlord")
            self._opp_supreme_combo.setVisible(show_opp_supreme)
            if not show_opp_supreme:
                self._opp_supreme_combo.blockSignals(True)
                self._opp_supreme_combo.setCurrentIndex(0)
                self._opp_supreme_combo.blockSignals(False)

    # ── Recalculation ─────────────────────────────────────────────────

    def recalculate(self) -> None:
        if not hasattr(self, "_move_sections"):
            return
        self._sync_attacker_ability_support_buttons()
        self._sync_defender_ability_support_buttons()
        if self._atk is None:
            for sec in self._move_sections:
                sec.setup_move(None)
            self._refresh_defender_card()
            self._show_opp_moves_only()
            return
        self._refresh_defender_card()
        self._calc_moves()

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
        from src.calc.damage_calc import (
            calc_stat, get_nature_mult,
            get_damage_modifier_notes, move_type_effectiveness,
            resolve_effective_move_category, resolve_effective_move_type,
        )
        from src.calc.smogon_bridge import (
            SmogonBridge, pokemon_to_attacker_dict, defender_scenario_dict, attacker_scenario_dict,
            pokemon_to_defender_dict,
            move_to_dict as smogon_move_to_dict,
            field_to_dict as smogon_field_to_dict,
            ABILITY_JA_TO_EN, ITEM_JA_TO_EN, NATURE_JA_TO_EN, TYPE_TO_SMOGON,
            smogon_mega_species,
            _ability_name_to_en,
        )
        from src.data.item_catalog import get_item_name_en
        from src.data.database import get_move_by_name_ja
        from src.constants import BEST_DEF_NATURE_FOR

        atk = copy.copy(self._atk)

        # Apply attacker EV overrides for all stats
        ev_pts_h_atk = self._atk_panel.ev_hp_pts()
        ev_pts_a = self._atk_panel.ev_attack_pts()
        ev_pts_b_atk = self._atk_panel.ev_defense_pts()
        ev_pts_c = self._atk_panel.ev_sp_attack_pts()
        ev_pts_d_atk = self._atk_panel.ev_sp_defense_pts()
        ev_pts_s_atk = self._atk_panel.ev_speed_pts()
        atk_nature = self._atk_panel.panel_nature()
        atk_ac_rank = self._atk_panel.ac_rank()
        atk_bd_rank = self._atk_panel.bd_rank()
        rank = atk_ac_rank
        tera = self._atk_panel.terastal_type()

        # Re-calc all stats from species if available
        species = self._resolve_species_info(atk, atk.name_ja)
        if species:
            hp_iv = atk.iv_hp if atk.iv_hp > 0 else 31
            atk.hp = calc_stat(species.base_hp, hp_iv, ev_pts_h_atk * 8, is_hp=True)
            atk.max_hp = atk.hp
            atk.attack = calc_stat(species.base_attack, 31, ev_pts_a * 8,
                                   nature_mult=_nature_mult_from_name(atk_nature, "attack"))
            atk.defense = calc_stat(species.base_defense, 31, ev_pts_b_atk * 8,
                                    nature_mult=_nature_mult_from_name(atk_nature, "defense"))
            atk.sp_attack = calc_stat(species.base_sp_attack, 31, ev_pts_c * 8,
                                      nature_mult=_nature_mult_from_name(atk_nature, "sp_attack"))
            atk.sp_defense = calc_stat(species.base_sp_defense, 31, ev_pts_d_atk * 8,
                                       nature_mult=_nature_mult_from_name(atk_nature, "sp_defense"))
            atk.speed = calc_stat(species.base_speed, 31, ev_pts_s_atk * 8,
                                  nature_mult=_nature_mult_from_name(atk_nature, "speed"))
            if atk.weight_kg <= 0:
                atk.weight_kg = species.weight_kg
            if atk.hp <= 0 and atk.max_hp > 0:
                atk.hp = atk.max_hp
        self._atk_panel.update_stat_display(atk)

        if self._burn_btn.isChecked():
            atk.status = "burn"
        if self._toxic_boost_btn.isVisible() and self._toxic_boost_btn.isChecked():
            atk.status = "poison"

        pinch_trigger = any(
            btn.isVisible() and btn.isChecked() for btn in (
                self._overgrow_btn, self._blaze_btn, self._torrent_btn, self._swarm_btn
            )
        )
        if pinch_trigger:
            hp_max = atk.max_hp if atk.max_hp > 0 else atk.hp
            if hp_max > 0:
                atk.max_hp = hp_max
                pinch_hp = max(1, hp_max // 3)
                if atk.current_hp > 0:
                    atk.current_hp = min(atk.current_hp, pinch_hp)
                else:
                    atk.current_hp = pinch_hp

        # テラスタルタイプ設定
        atk.terastal_type = tera

        # Defender scenarios
        def_types_override: list[str] = []
        def_tera = self._def_panel.terastal_type() if hasattr(self, "_def_panel") else ""
        if def_tera:
            def_types_override = [def_tera]

        weather = self._weather_key()
        terrain = self._terrain_key()
        if weather == "none" and atk.ability in ("ひひいろのこどう", "Orichalcum Pulse"):
            weather = "sun"
        if terrain == "none" and atk.ability in ("ハドロンエンジン", "Hadron Engine"):
            terrain = "electric"
        is_crit = self._crit_btn.isChecked()
        helping = self._helping_btn.isChecked()
        steel_spirit = self._steel_spirit_btn.isChecked()
        charged = self._charge_btn.isChecked()
        opp_helping = self._opp_helping_btn.isChecked()
        opp_steel_spirit = self._opp_steel_spirit_btn.isChecked()
        opp_charged = self._opp_charge_btn.isChecked()
        reflect = self._reflect_btn.isChecked()
        lightscreen = self._lightscreen_btn.isChecked()
        fairy_aura = self._fairy_aura_btn.isChecked() or self._opp_fairy_aura_btn.isChecked()
        dark_aura = self._dark_aura_btn.isChecked() or self._opp_dark_aura_btn.isChecked()
        self_reflect = self._self_reflect_btn.isChecked()
        self_lightscreen = self._self_lightscreen_btn.isChecked()
        friend_guard = self._friend_guard_btn.isChecked()
        self_friend_guard = self._self_friend_guard_btn.isChecked()
        tailwind = self._tailwind_btn.isChecked()
        self_tailwind = self._self_tailwind_btn.isChecked()
        gravity = self._gravity_btn.isChecked()
        def_ac_rank = self._def_panel.ac_rank() if hasattr(self, "_def_panel") else 0
        def_bd_rank = self._def_panel.bd_rank() if hasattr(self, "_def_panel") else 0
        def_rank = def_bd_rank
        hp_percent = self._def_panel.current_hp_percent() if hasattr(self, "_def_panel") else 100
        def_use_sp = self._def_panel.use_sp_defense() if hasattr(self, "_def_panel") else False
        def_ev_pts_h = self._def_panel.ev_hp_pts() if hasattr(self, "_def_panel") else 0
        def_ev_pts_a = self._def_panel.ev_attack_pts() if hasattr(self, "_def_panel") else 0
        def_ev_pts_b = self._def_panel.ev_defense_pts() if hasattr(self, "_def_panel") else 0
        def_ev_pts_c = self._def_panel.ev_sp_attack_pts() if hasattr(self, "_def_panel") else 0
        def_ev_pts_d = self._def_panel.ev_sp_defense_pts() if hasattr(self, "_def_panel") else 0
        def_ev_pts_s = self._def_panel.ev_speed_pts() if hasattr(self, "_def_panel") else 0
        def_nature = self._def_panel.panel_nature() if hasattr(self, "_def_panel") else "まじめ"
        is_double = getattr(self, "_battle_format", "single") == "double"
        parental_bond = bool(atk.ability == "おやこあい")
        stakeout_active = self._stakeout_btn.isVisible() and self._stakeout_btn.isChecked()
        flash_fire_active = self._flash_fire_boost_btn.isVisible() and self._flash_fire_boost_btn.isChecked()
        protosynthesis_active = self._protosynthesis_btn.isVisible() and self._protosynthesis_btn.isChecked()
        quark_drive_active = self._quark_drive_btn.isVisible() and self._quark_drive_btn.isChecked()
        analytic_active = self._analytic_btn.isVisible() and self._analytic_btn.isChecked()
        flare_boost_active = self._flare_boost_btn.isVisible() and self._flare_boost_btn.isChecked()
        guts_active = self._guts_btn.isVisible() and self._guts_btn.isChecked()
        if flare_boost_active:
            atk.status = "burn"
        if guts_active and not atk.status:
            atk.status = "par"
        ability_on = (
            (atk.ability in ("はりこみ", "Stakeout") and stakeout_active) or
            (atk.ability in ("もらいび", "Flash Fire") and flash_fire_active) or
            (atk.ability in ("アナライズ", "Analytic") and analytic_active)
        )
        allies_fainted = int(self._supreme_combo.currentData() or 0) if self._supreme_combo.isVisible() else 0
        rivalry_state = str(self._rivalry_combo.currentData() or "none") if self._rivalry_combo.isVisible() else "none"
        attacker_gender = ""
        defender_gender = ""
        if rivalry_state == "same":
            attacker_gender = "M"
            defender_gender = "M"
        elif rivalry_state == "opposite":
            attacker_gender = "M"
            defender_gender = "F"
        elif self._rivalry_combo.isVisible():
            attacker_gender = "N"
            defender_gender = "N"

        shared = dict(
            weather=weather, terrain=terrain, is_critical=is_crit,
            has_reflect=reflect, has_light_screen=lightscreen,
            helping_hand=helping, steel_spirit=steel_spirit, charged=charged,
            fairy_aura=fairy_aura, dark_aura=dark_aura,
            terastal_type=tera,
            atk_rank=atk_ac_rank,
            def_rank=atk_bd_rank,
            attacker_def_rank=atk_bd_rank,
            defender_atk_rank=def_ac_rank,
            is_double_battle=is_double,
            allies_fainted=allies_fainted,
            rivalry_state=rivalry_state,
            stakeout_active=stakeout_active,
            flash_fire_active=flash_fire_active,
            protosynthesis_active=protosynthesis_active,
            quark_drive_active=quark_drive_active,
            attacker_moves_after_target=True if analytic_active else None,
            friend_guard=friend_guard,
        )

        # ── smogon bridge: build attacker dict and field dict once ────────
        _bridge = SmogonBridge.get()
        _atk_d = pokemon_to_attacker_dict(
            atk,
            ev_override={"hp": ev_pts_h_atk * 8, "atk": ev_pts_a * 8, "def": ev_pts_b_atk * 8,
                         "spa": ev_pts_c * 8, "spd": ev_pts_d_atk * 8, "spe": ev_pts_s_atk * 8},
            atk_rank=atk_ac_rank,
            terastal_type=tera,
            allies_fainted=allies_fainted,
            gender=attacker_gender,
            ability_on=ability_on,
            apply_both=True,
        )
        _atk_d["nature"] = NATURE_JA_TO_EN.get(atk_nature, "Hardy")
        _atk_boosts = _atk_d.setdefault("boosts", {})
        if atk_bd_rank != 0:
            _atk_boosts["def"] = atk_bd_rank
            _atk_boosts["spd"] = atk_bd_rank
        if (atk.ability in ("こだいかっせい", "Protosynthesis") and protosynthesis_active and weather != "sun") or (
            atk.ability in ("クォークチャージ", "Quark Drive") and quark_drive_active and terrain != "electric"
        ):
            # Force QP active without replacing held item: explicit boostedStat triggers isQPActive().
            stat_pairs = [
                ("atk", int(atk.attack or 0)),
                ("def", int(atk.defense or 0)),
                ("spa", int(atk.sp_attack or 0)),
                ("spd", int(atk.sp_defense or 0)),
                ("spe", int(atk.speed or 0)),
            ]
            best = "atk"
            best_val = stat_pairs[0][1]
            for key, value in stat_pairs[1:]:
                if value > best_val:
                    best = key
                    best_val = value
            _atk_d["boostedStat"] = best
        if parental_bond and ABILITY_JA_TO_EN.get(atk.ability, "") != "Parental Bond":
            _atk_d["ability"] = "Parental Bond"
        _field_d = smogon_field_to_dict(
            weather,
            terrain,
            reflect,
            lightscreen,
            helping,
            fairy_aura,
            dark_aura,
            friend_guard=friend_guard,
            tailwind=tailwind,
            gravity=gravity,
        )
        _field_d_rev = smogon_field_to_dict(
            weather,
            terrain,
            self_reflect,
            self_lightscreen,
            opp_helping,
            fairy_aura,
            dark_aura,
            friend_guard=self_friend_guard,
            tailwind=self_tailwind,
            gravity=gravity,
        )

        slot_to_move: dict[int, tuple[str, Optional[MoveInfo]]] = {}
        for slot in range(4):
            move_name = atk.moves[slot] if slot < len(atk.moves) else ""
            move_info: Optional[MoveInfo] = None
            if move_name:
                move_info = self._move_cache.get(move_name) or get_move_by_name_ja(move_name)
                if move_info:
                    self._move_cache[move_name] = move_info
            slot_to_move[slot] = (move_name, move_info)

        self._display_to_move_slot = [0, 1, 2, 3]
        self._refresh_defender_card(atk)

        for disp_slot, sec in enumerate(self._move_sections):
            src_slot = self._display_to_move_slot[disp_slot] if disp_slot < len(self._display_to_move_slot) else disp_slot
            move_name, move = slot_to_move.get(src_slot, ("", None))
            effective_move: Optional[MoveInfo] = None
            if not move_name or not move:
                sec.setup_move(None)
            else:
                # Apply type override to the move
                effective_move = move
                pre_resolve_type = effective_move.type_name
                resolved_type = resolve_effective_move_type(atk, effective_move, tera)
                resolved_power = effective_move.power
                weather_ball_active_type = ""
                if effective_move.name_ja == "ウェザーボール":
                    weather_ball_active_type = {
                        "sun": "fire",
                        "rain": "water",
                        "sand": "rock",
                        "hail": "ice",
                    }.get(weather, "")
                    if weather_ball_active_type:
                        resolved_type = weather_ball_active_type
                        resolved_power = 100
                if effective_move.name_ja == "オーラぐるま" and "はらぺこもよう" in atk.name_ja:
                    resolved_type = "dark"
                resolved_category = resolve_effective_move_category(
                    atk, effective_move, atk_rank=rank, terastal_type=tera,
                )
                if (resolved_type != effective_move.type_name
                        or resolved_category != effective_move.category
                        or resolved_power != effective_move.power):
                    effective_move = dataclasses.replace(
                        effective_move, type_name=resolved_type,
                        category=resolved_category, power=resolved_power,
                    )
                sec.setup_move(effective_move)

            if effective_move is None:
                continue

            if effective_move.category == "status":
                sec.set_modifier_notes([])
                sec.update_results(None, (0, 0, 1), (0, 0, 1), show_bulk_rows=self._show_bulk_rows)
                continue

            pow_override = sec.power_override()
            move_shared = dict(**shared, power_override=pow_override)

            is_phys = effective_move.category == "physical" or effective_move.name_ja in (
                "サイコショック", "サイコブレイク", "しんぴのつるぎ"
            )
            best_nat = BEST_DEF_NATURE_FOR["defense" if is_phys else "sp_defense"]
            opp_species = self._resolve_species_info(self._def_custom, self._def_species_name)

            def _build_def(hp_ev: int, bd_ev: int, nat: str) -> PokemonInstance:
                d = copy.copy(self._def_custom) if self._def_custom else PokemonInstance()
                d.ability = (self._def_custom.ability if self._def_custom else "")
                if opp_species:
                    d.hp = calc_stat(opp_species.base_hp, 31, hp_ev, is_hp=True)
                    if d.attack <= 0:
                        d.attack = calc_stat(
                            opp_species.base_attack, 31, 0,
                            nature_mult=get_nature_mult("まじめ", "attack")
                        )
                    if d.sp_attack <= 0:
                        d.sp_attack = calc_stat(
                            opp_species.base_sp_attack, 31, 0,
                            nature_mult=get_nature_mult("まじめ", "sp_attack")
                        )
                    d.defense = calc_stat(opp_species.base_defense, 31,
                                         bd_ev if is_phys else 0,
                                         nature_mult=get_nature_mult(nat, "defense"))
                    d.sp_defense = calc_stat(opp_species.base_sp_defense, 31,
                                             bd_ev if not is_phys else 0,
                                             nature_mult=get_nature_mult(nat, "sp_defense"))
                    if d.speed <= 0:
                        d.speed = calc_stat(
                            opp_species.base_speed, 31, 0,
                            nature_mult=get_nature_mult("まじめ", "speed")
                        )
                    d.max_hp = d.hp
                    if d.weight_kg <= 0:
                        d.weight_kg = opp_species.weight_kg
                d.types = def_types_override or (d.types or ["normal"])
                return d

            hbd0 = _build_def(0, 0, "まじめ")
            hbd252 = _build_def(252, 252, best_nat)

            # ── smogon bridge: build move dict ────────────────────────────
            hits = sec.hit_count()
            bridge_forced_type = ""
            bridge_bp_multiplier = 1.0
            if (
                atk.ability in ("ドラゴンスキン", "Dragonize")
                and pre_resolve_type == "normal"
                and resolved_type == "dragon"
            ):
                bridge_forced_type = "dragon"
                bridge_bp_multiplier = 1.2
            if weather_ball_active_type:
                # Smogon が Weather Ball をノーマルタイプ固定で計算するため、
                # 天気あり時は type/basePower を直接 override した汎用技として渡す。
                _smogon_type = TYPE_TO_SMOGON.get(weather_ball_active_type, "Normal")
                _wb_overrides: dict = {
                    "basePower": 100,
                    "type": _smogon_type,
                    "category": "Special",
                }
                _mv_d = {"name": "Tackle", "isCrit": is_crit, "overrides": _wb_overrides}
            else:
                _mv_d = smogon_move_to_dict(
                    effective_move,
                    is_crit=is_crit,
                    hits=hits if hits > 1 else 0,
                    bp_override=pow_override,
                    charged=charged,
                    forced_type=bridge_forced_type,
                    bp_multiplier=bridge_bp_multiplier,
                )
            _atk_d_for_move = _atk_d
            if effective_move.name_ja == "からげんき" and pow_override > 0:
                # 「状態異常時 140」を手動指定した場合は、からげんき固有の状態異常依存計算を重ねない。
                # ここでは威力を固定し、やけどのA半減差分も出ないように status を無効化する。
                _atk_d_for_move = dict(_atk_d)
                _atk_d_for_move["status"] = ""

            # ── defender meta for smogon dicts ───────────────────────────
            _raw_species_en = (opp_species.name_en if opp_species
                               else (self._def_custom.name_en if self._def_custom else ""))
            _def_name_ja = (self._def_custom.name_ja if self._def_custom else "") or ""
            species_en = smogon_mega_species(_raw_species_en, _def_name_ja)
            def_ability_ja = self._def_custom.ability if self._def_custom else ""
            def_terastal_active = bool(def_tera)
            def_ability_en = _ability_name_to_en(def_ability_ja, _def_name_ja, def_terastal_active)
            def_item_en = ITEM_JA_TO_EN.get(
                self._def_custom.item if self._def_custom else "", ""
            )
            if not def_item_en:
                def_item_en = get_item_name_en(self._def_custom.item if self._def_custom else "")
            best_nat_en = NATURE_JA_TO_EN.get(best_nat, "Hardy")

            _def0_d = defender_scenario_dict(
                species_en, ev_hp=0, ev_def=0, ev_spd=0,
                nature_en="Hardy",
                ability_en=def_ability_en, item_en=def_item_en,
                terastal_type=def_tera, def_rank=def_bd_rank, is_physical=is_phys,
                gender=defender_gender,
                apply_both=True,
            )
            _def252_d = defender_scenario_dict(
                species_en, ev_hp=252,
                ev_def=252 if is_phys else 0,
                ev_spd=0 if is_phys else 252,
                nature_en=best_nat_en,
                ability_en=def_ability_en, item_en=def_item_en,
                terastal_type=def_tera, def_rank=def_bd_rank, is_physical=is_phys,
                gender=defender_gender,
                apply_both=True,
            )

            # ── type effectiveness (for berry check + display) ────────────
            disp_types = def_types_override or (
                (self._def_custom.types or ["normal"]) if self._def_custom else ["normal"]
            )
            disp_ability = self._def_custom.ability if self._def_custom else ""
            type_eff = move_type_effectiveness(
                effective_move, effective_move.type_name, disp_types, disp_ability
            )
            sec.set_effectiveness(type_eff)

            # ── bridge call helper ────────────────────────────────────────
            def _call_bridge(def_d: dict, hp: int) -> tuple[int, int, int, bool]:
                if hp <= 0:
                    return (0, 0, 1, False)
                cur_hp = max(1, math.floor(hp * hp_percent / 100.0))
                disguise = bool(
                    def_d.get("ability") == "Disguise" and
                    hasattr(self, "_def_panel") and
                    self._def_panel.disguise_intact() and
                    cur_hp >= hp
                )
                if disguise:
                    return (0, 0, hp, False)
                d_copy = dict(def_d)
                if cur_hp < hp:
                    d_copy["curHP"] = cur_hp
                try:
                    self.bridge_payload_logged.emit(
                        "[SmogonReq] {}".format(
                            json.dumps(
                                {
                                    "dir": "atk->def",
                                    "attacker": _atk_d_for_move,
                                    "defender": d_copy,
                                    "move": _mv_d,
                                    "field": _field_d,
                                },
                                ensure_ascii=False,
                            )
                        )
                    )
                except Exception:
                    pass
                mn, mx, is_error = _bridge.calc(_atk_d_for_move, d_copy, _mv_d, _field_d)
                return (mn, mx, hp or 1, is_error)

            # ── modifier notes (Python calc still used for notes) ─────────
            def _modifier_notes_for(d: PokemonInstance) -> list[str]:
                if d.hp <= 0:
                    return []
                cur_hp = max(1, math.floor(d.hp * hp_percent / 100.0))
                disguise = bool(
                    d.ability == "ばけのかわ" and
                    hasattr(self, "_def_panel") and
                    self._def_panel.disguise_intact() and
                    cur_hp >= d.hp
                )
                notes = get_damage_modifier_notes(
                    atk, effective_move,
                    d.hp, d.attack, d.defense, d.sp_attack, d.sp_defense,
                    d.types,
                    defender_ability=d.ability,
                    defender_current_hp=cur_hp,
                    defender_disguise_intact=disguise,
                    defender_speed=d.speed,
                    defender_weight_kg=d.weight_kg,
                    **move_shared,
                )
                skin_type = {
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
                }.get(atk.ability, "")
                if atk.ability in ("ノーマルスキン", "Normalize") and effective_move.type_name == "normal":
                    note = "ノーマルスキン ×1.2"
                    if note not in notes:
                        notes.append(note)
                elif (
                    skin_type
                    and move.type_name == "normal"
                    and effective_move.type_name == skin_type
                ):
                    note = "{} ×1.2".format(atk.ability)
                    if note not in notes:
                        notes.append(note)
                berry_type = _RESIST_BERRIES.get(d.item or "")
                if berry_type and berry_type == effective_move.type_name and type_eff >= 2.0:
                    note = "{} ×0.5".format(d.item)
                    if note not in notes:
                        notes.append(note)
                return notes

            # ── custom defender ───────────────────────────────────────────
            custom_result: Optional[tuple[int, int, int, bool]] = None
            mod_target = hbd0
            if self._def_custom and self._def_custom.hp > 0:
                cd = copy.copy(self._def_custom)
                if opp_species:
                    cd.attack = calc_stat(
                        opp_species.base_attack, 31, def_ev_pts_a * 8,
                        nature_mult=_nature_mult_from_name(def_nature, "attack")
                    )
                    cd.defense = calc_stat(
                        opp_species.base_defense, 31, def_ev_pts_b * 8,
                        nature_mult=_nature_mult_from_name(def_nature, "defense")
                    )
                    cd.sp_attack = calc_stat(
                        opp_species.base_sp_attack, 31, def_ev_pts_c * 8,
                        nature_mult=_nature_mult_from_name(def_nature, "sp_attack")
                    )
                    cd.sp_defense = calc_stat(
                        opp_species.base_sp_defense, 31, def_ev_pts_d * 8,
                        nature_mult=_nature_mult_from_name(def_nature, "sp_defense")
                    )
                    cd.hp = calc_stat(
                        opp_species.base_hp, 31, def_ev_pts_h * 8, is_hp=True
                    )
                    cd.max_hp = cd.hp
                    cd.speed = calc_stat(
                        opp_species.base_speed, 31, def_ev_pts_s * 8,
                        nature_mult=_nature_mult_from_name(def_nature, "speed")
                    )
                    if cd.weight_kg <= 0:
                        cd.weight_kg = opp_species.weight_kg
                cd.types = def_types_override or (cd.types or ["normal"])
                self._def_panel.update_stat_display(cd)

                # Build smogon dict for custom defender with panel EV/nature override
                _custom_nat = NATURE_JA_TO_EN.get(def_nature, "Hardy")
                _custom_d = pokemon_to_defender_dict(cd, def_bd_rank, is_phys, gender=defender_gender, apply_both=True)
                _custom_d["nature"] = _custom_nat
                _custom_d["evs"]["hp"] = def_ev_pts_h * 8
                _custom_d["evs"]["atk"] = def_ev_pts_a * 8
                _custom_d["evs"]["def"] = def_ev_pts_b * 8
                _custom_d["evs"]["spa"] = def_ev_pts_c * 8
                _custom_d["evs"]["spd"] = def_ev_pts_d * 8
                _custom_d["evs"]["spe"] = def_ev_pts_s * 8
                # Always align tera payload with panel toggle state.
                # When the tera checkbox is OFF, force empty teraType.
                _custom_d["teraType"] = TYPE_TO_SMOGON.get(def_tera, "") if def_tera else ""

                custom_result = _call_bridge(_custom_d, cd.hp)
                mod_target = cd

            sec.set_modifier_notes(_modifier_notes_for(mod_target))

            sec.update_results(
                custom_result,
                _call_bridge(_def0_d, hbd0.hp),
                _call_bridge(_def252_d, hbd252.hp),
                show_bulk_rows=self._show_bulk_rows,
            )

        # ── 相手→自分 計算（右側わざは左側わざと独立）────────────────────────────────────────────
        opp_moves = self._def_custom.moves if self._def_custom else []
        for slot, opp_sec in enumerate(self._opp_move_sections):
            opp_custom_result: Optional[tuple[int, int, int, bool]] = None
            opp_ac0_result: Optional[tuple[int, int, int, bool]] = None
            opp_ac32_result: Optional[tuple[int, int, int, bool]] = None
            opp_move_info: Optional[MoveInfo] = None

            opp_move_name = opp_moves[slot] if slot < len(opp_moves) else ""
            if opp_move_name:
                opp_move_info = self._move_cache.get(opp_move_name) or get_move_by_name_ja(opp_move_name)
                if opp_move_info:
                    self._move_cache[opp_move_name] = opp_move_info

            if self._def_custom and atk.hp > 0 and opp_move_info and opp_move_info.category != "status":
                _opp_species = self._resolve_species_info(self._def_custom, self._def_species_name)
                _opp_atk_en = ABILITY_JA_TO_EN.get(self._def_custom.ability or "", "") or "No Ability"
                _opp_item_en = ITEM_JA_TO_EN.get(self._def_custom.item or "", "")
                if not _opp_item_en:
                    _opp_item_en = get_item_name_en(self._def_custom.item or "")
                _opp_species_en = ""
                if _opp_species:
                    _opp_species_en = _opp_species.name_en or ""
                _opp_species_en = smogon_mega_species(
                    _opp_species_en or (self._def_custom.name_en or ""),
                    self._def_custom.name_ja or "",
                )
                _is_opp_phys = opp_move_info.category == "physical" or opp_move_info.name_ja in (
                    "サイコショック", "サイコブレイク", "しんぴのつるぎ"
                )
                _opp_best_nat_en = "Adamant" if _is_opp_phys else "Modest"

                # Build self (atk) as defender dict for reverse calc
                _self_def_d = pokemon_to_defender_dict(atk, atk_bd_rank, _is_opp_phys, apply_both=True)

                # Build move dict for opponent's move
                _opp_is_crit = self._opp_crit_btn.isChecked()
                _opp_burn = self._opp_burn_btn.isChecked()
                _opp_pow_override = opp_sec.power_override()
                _opp_hits = opp_sec.hit_count()

                # スキン系特性によるタイプ変換（相手側）
                _opp_skin_map = {
                    "エレキスキン": "electric", "Galvanize": "electric",
                    "フェアリースキン": "fairy",  "Pixilate": "fairy",
                    "フリーズスキン": "ice",     "Refrigerate": "ice",
                    "スカイスキン": "flying",    "Aerilate": "flying",
                    "ドラゴンスキン": "dragon",  "Dragonize": "dragon",
                    "ノーマルスキン": "normal",  "Normalize": "normal",
                }
                _opp_ability_for_skin = self._def_custom.ability if self._def_custom else ""
                _opp_skin_type = _opp_skin_map.get(_opp_ability_for_skin, "")
                _opp_skin_forced_type = ""
                _opp_skin_bp_mult = 1.0
                if _opp_skin_type and opp_move_info.type_name == "normal":
                    _opp_skin_forced_type = _opp_skin_type
                    _opp_skin_bp_mult = 1.2

                _opp_aura_wheel_type = ""
                if (opp_move_info.name_ja == "オーラぐるま"
                        and self._def_custom
                        and "はらぺこもよう" in (self._def_custom.name_ja or "")):
                    _opp_aura_wheel_type = "dark"

                _mv_d_opp = smogon_move_to_dict(
                    opp_move_info, is_crit=_opp_is_crit,
                    hits=_opp_hits if _opp_hits > 1 else 0,
                    bp_override=_opp_pow_override,
                    forced_type=_opp_aura_wheel_type or _opp_skin_forced_type,
                    bp_multiplier=_opp_skin_bp_mult,
                )

                _self_types = atk.types or ["normal"]
                _self_ability = atk.ability or ""
                _opp_effective_type = _opp_aura_wheel_type or _opp_skin_forced_type or opp_move_info.type_name
                _opp_type_eff = move_type_effectiveness(
                    opp_move_info, _opp_effective_type, _self_types, _self_ability
                )

                def _call_bridge_rev(opp_atk_d: dict) -> tuple[int, int, int, bool]:
                    self_hp = atk.hp if atk.hp > 0 else 1
                    try:
                        self.bridge_payload_logged.emit(
                            "[SmogonReq] {}".format(
                                json.dumps(
                                    {
                                        "dir": "def->atk",
                                        "attacker": opp_atk_d,
                                        "defender": _self_def_d,
                                        "move": _mv_d_opp,
                                        "field": _field_d_rev,
                                    },
                                    ensure_ascii=False,
                                )
                            )
                        )
                    except Exception:
                        pass
                    mn, mx, is_error = _bridge.calc(opp_atk_d, _self_def_d, _mv_d_opp, _field_d_rev)
                    return (mn, mx, self_hp, is_error)

                # 調整: 相手の現在設定
                _opp_def_ac_rank = self._def_panel.ac_rank() if hasattr(self, "_def_panel") else 0
                _opp_ability_on = any(
                    btn.isVisible() and btn.isChecked()
                    for btn in list(
                        (self._defender_ability_cond_btns or {}).values()
                    ) + list(
                        (self._defender_trigger_cond_btns or {}).values()
                    )
                )
                _opp_allies_fainted = int(self._opp_supreme_combo.currentData() or 0) if hasattr(self, "_opp_supreme_combo") and self._opp_supreme_combo.isVisible() else 0
                _opp_stakeout_active = hasattr(self, "_opp_stakeout_btn") and self._opp_stakeout_btn.isVisible() and self._opp_stakeout_btn.isChecked()
                _opp_flash_fire_active = hasattr(self, "_opp_flash_fire_btn") and self._opp_flash_fire_btn.isVisible() and self._opp_flash_fire_btn.isChecked()
                _opp_protosynthesis_active = hasattr(self, "_opp_protosynthesis_btn") and self._opp_protosynthesis_btn.isVisible() and self._opp_protosynthesis_btn.isChecked()
                _opp_quark_drive_active = hasattr(self, "_opp_quark_drive_btn") and self._opp_quark_drive_btn.isVisible() and self._opp_quark_drive_btn.isChecked()
                _opp_analytic_active = hasattr(self, "_opp_analytic_btn") and self._opp_analytic_btn.isVisible() and self._opp_analytic_btn.isChecked()
                _opp_guts_active = hasattr(self, "_opp_guts_btn") and self._opp_guts_btn.isVisible() and self._opp_guts_btn.isChecked()

                # 相手側pinch特性（げきりゅう等）のHP調整
                _opp_atk_instance = copy.copy(self._def_custom)
                _opp_pinch_trigger = any(
                    btn.isVisible() and btn.isChecked()
                    for btn in (
                        self._opp_overgrow_btn, self._opp_blaze_btn,
                        self._opp_torrent_btn, self._opp_swarm_btn,
                    )
                )
                if _opp_pinch_trigger:
                    _opp_hp_max = _opp_atk_instance.max_hp if _opp_atk_instance.max_hp > 0 else _opp_atk_instance.hp
                    if _opp_hp_max > 0:
                        _opp_atk_instance.max_hp = _opp_hp_max
                        _opp_pinch_hp = max(1, _opp_hp_max // 3)
                        if _opp_atk_instance.current_hp > 0:
                            _opp_atk_instance.current_hp = min(_opp_atk_instance.current_hp, _opp_pinch_hp)
                        else:
                            _opp_atk_instance.current_hp = _opp_pinch_hp
                _opp_toxic_boost_active = (
                    hasattr(self, "_opp_toxic_boost_btn") and
                    self._opp_toxic_boost_btn.isVisible() and
                    self._opp_toxic_boost_btn.isChecked()
                )
                if _opp_burn:
                    _opp_atk_instance.status = "brn"
                elif _opp_guts_active:
                    _opp_atk_instance.status = "par"
                elif _opp_toxic_boost_active:
                    _opp_atk_instance.status = "psn"

                _opp_custom_atk_d = pokemon_to_attacker_dict(
                    _opp_atk_instance,
                    atk_rank=_opp_def_ac_rank,
                    terastal_type=def_tera,
                    ability_on=_opp_ability_on,
                    allies_fainted=_opp_allies_fainted,
                    apply_both=True,
                )
                if opp_charged:
                    _opp_custom_atk_d["volatileStatus"] = "charge"
                opp_custom_result = _call_bridge_rev(_opp_custom_atk_d)

                # AC 0: 攻撃/特攻 EV=0, 無補正性格
                _opp_ac0_atk_d = attacker_scenario_dict(
                    _opp_species_en or self._def_custom.name_ja or "Bulbasaur",
                    ev_hp=int(_opp_atk_instance.ev_hp or 0),
                    ev_atk=0,
                    ev_spa=0,
                    nature_en="Hardy",
                    ability_en=_opp_atk_en,
                    item_en=_opp_item_en,
                    atk_rank=_opp_def_ac_rank,
                    is_physical=_is_opp_phys,
                    terastal_type=def_tera,
                    allies_fainted=_opp_allies_fainted,
                    ability_on=_opp_ability_on,
                    gender=defender_gender,
                    apply_both=True,
                )
                _opp_ac0_atk_d["status"] = _opp_atk_instance.status or ""
                if _opp_atk_instance.current_hp > 0:
                    _opp_ac0_atk_d["curHP"] = int(_opp_atk_instance.current_hp)
                opp_ac0_result = _call_bridge_rev(_opp_ac0_atk_d)

                # AC 32: 攻撃/特攻 EV=252, 有利性格
                _opp_ac32_atk_d = attacker_scenario_dict(
                    _opp_species_en or self._def_custom.name_ja or "Bulbasaur",
                    ev_hp=int(_opp_atk_instance.ev_hp or 0),
                    ev_atk=252 if _is_opp_phys else 0,
                    ev_spa=0 if _is_opp_phys else 252,
                    nature_en=_opp_best_nat_en,
                    ability_en=_opp_atk_en,
                    item_en=_opp_item_en,
                    atk_rank=_opp_def_ac_rank,
                    is_physical=_is_opp_phys,
                    terastal_type=def_tera,
                    allies_fainted=_opp_allies_fainted,
                    ability_on=_opp_ability_on,
                    gender=defender_gender,
                    apply_both=True,
                )
                _opp_ac32_atk_d["status"] = _opp_atk_instance.status or ""
                if _opp_atk_instance.current_hp > 0:
                    _opp_ac32_atk_d["curHP"] = int(_opp_atk_instance.current_hp)
                opp_ac32_result = _call_bridge_rev(_opp_ac32_atk_d)

            opp_sec.setup_move(opp_move_info)
            if opp_move_info is not None:
                _atk_types = atk.types or ["normal"]
                _atk_ability = atk.ability or ""
                _opp_disp_skin_map = {
                    "エレキスキン": "electric", "Galvanize": "electric",
                    "フェアリースキン": "fairy",  "Pixilate": "fairy",
                    "フリーズスキン": "ice",     "Refrigerate": "ice",
                    "スカイスキン": "flying",    "Aerilate": "flying",
                    "ドラゴンスキン": "dragon",  "Dragonize": "dragon",
                    "ノーマルスキン": "normal",  "Normalize": "normal",
                }
                _opp_disp_ability = self._def_custom.ability if self._def_custom else ""
                _opp_disp_eff_type = (
                    _opp_disp_skin_map.get(_opp_disp_ability, "") or opp_move_info.type_name
                    if opp_move_info.type_name == "normal"
                    else opp_move_info.type_name
                )
                _opp_eff = move_type_effectiveness(opp_move_info, _opp_disp_eff_type, _atk_types, _atk_ability)
                opp_sec.set_effectiveness(_opp_eff)
                if opp_move_info.category != "status" and self._def_custom and atk.hp > 0:
                    _opp_move_shared = dict(
                        weather=weather, terrain=terrain,
                        is_critical=self._opp_crit_btn.isChecked(),
                        has_reflect=self_reflect, has_light_screen=self_lightscreen,
                        helping_hand=opp_helping, steel_spirit=opp_steel_spirit, charged=opp_charged,
                        fairy_aura=fairy_aura, dark_aura=dark_aura,
                        terastal_type=def_tera,
                        atk_rank=self._def_panel.ac_rank() if hasattr(self, "_def_panel") else 0,
                        def_rank=def_bd_rank,
                        defender_def_rank=def_bd_rank,
                        defender_atk_rank=atk_ac_rank,
                        is_double_battle=is_double,
                        defender_speed=atk.speed,
                        defender_weight_kg=atk.weight_kg,
                        allies_fainted=_opp_allies_fainted,
                        stakeout_active=_opp_stakeout_active,
                        flash_fire_active=_opp_flash_fire_active,
                        protosynthesis_active=_opp_protosynthesis_active,
                        quark_drive_active=_opp_quark_drive_active,
                        attacker_moves_after_target=True if _opp_analytic_active else None,
                        friend_guard=self_friend_guard,
                    )
                    _opp_notes = get_damage_modifier_notes(
                        _opp_atk_instance, opp_move_info,
                        atk.hp, atk.attack, atk.defense,
                        atk.sp_attack, atk.sp_defense,
                        atk.types,
                        defender_ability=atk.ability,
                        defender_current_hp=max(1, math.floor(atk.hp * hp_percent / 100.0)),
                        **_opp_move_shared,
                    )
                    _opp_berry_type = _RESIST_BERRIES.get(atk.item or "")
                    if _opp_berry_type and _opp_berry_type == _opp_disp_eff_type and _opp_eff >= 2.0:
                        _note_str = "{} ×0.5".format(atk.item)
                        if _note_str not in _opp_notes:
                            _opp_notes.append(_note_str)
                    opp_sec.set_modifier_notes(_opp_notes)
                else:
                    opp_sec.set_modifier_notes([])
            else:
                opp_sec.set_modifier_notes([])
            opp_sec.update_results(
                opp_custom_result,
                opp_ac0_result,
                opp_ac32_result,
                show_bulk_rows=self._show_bulk_rows,
            )

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
        self._persist_party_member_edits()
        self._refresh_party_slots()
        self.recalculate()

    def _on_def_panel_changed(self) -> None:
        self._persist_party_member_edits()
        self._refresh_party_slots()
        self.recalculate()

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
        dlg = open_pokemon_edit_dialog(self._atk, self, save_to_db=False)
        if dlg.exec_():
            updated = dlg.get_pokemon()
            if updated:
                self._atk = copy.deepcopy(updated)
                if self._atk_party_side is not None and self._atk_party_idx is not None:
                    party = self._my_party if self._atk_party_side == "my" else self._opp_party
                    if 0 <= self._atk_party_idx < len(party):
                        party[self._atk_party_idx] = copy.deepcopy(updated)
                self._atk_panel.set_pokemon(self._atk)
                self.registry_maybe_changed.emit()
                self._refresh_party_slots()
                self.attacker_changed.emit(self._atk)
                self.recalculate()
        elif dlg.box_select_requested():
            QTimer.singleShot(0, self._change_attacker)

    def _new_attacker(self) -> None:
        dlg = open_pokemon_edit_dialog(None, self, save_to_db=False)
        if dlg.exec_():
            updated = dlg.get_pokemon()
            if updated:
                self._atk = copy.deepcopy(updated)
                self._atk_party_side = None
                self._atk_party_idx = None
                self._atk_panel.set_pokemon(self._atk)
                self.registry_maybe_changed.emit()
                self._refresh_party_slots()
                self.attacker_changed.emit(self._atk)
                self.recalculate()

    def _clear_attacker(self) -> None:
        self._atk = None
        self._atk_party_side = None
        self._atk_party_idx = None
        self._atk_panel.set_pokemon(None)
        self._refresh_party_slots()
        self.attacker_changed.emit(None)
        self.recalculate()

    def _change_attacker(self) -> None:
        from src.ui.pokemon_edit_dialog import MyBoxSelectDialog
        dlg = MyBoxSelectDialog("攻撃側PT", self)
        if not dlg.exec_():
            return
        p = dlg.selected_pokemon()
        if p:
            self._atk = copy.deepcopy(p)
            self._atk_party_side = None
            self._atk_party_idx = None
            self._atk_panel.set_pokemon(self._atk)
            self._refresh_party_slots()
            self.attacker_changed.emit(self._atk)
            self.recalculate()

    def _edit_defender(self) -> None:
        dlg = open_pokemon_edit_dialog(self._def_custom, self, save_to_db=False)
        if dlg.exec_():
            updated = dlg.get_pokemon()
            if updated:
                self._def_custom = copy.deepcopy(updated)
                self._def_species_name = updated.name_ja or ""
                if self._def_party_side is not None and self._def_party_idx is not None:
                    party = self._my_party if self._def_party_side == "my" else self._opp_party
                    while len(party) <= self._def_party_idx:
                        party.append(None)
                    party[self._def_party_idx] = copy.deepcopy(self._def_custom)
                else:
                    if self._opp_party:
                        self._opp_party[0] = copy.deepcopy(self._def_custom)
                    else:
                        self._opp_party = [copy.deepcopy(self._def_custom)]
                    self._def_party_side = "opp"
                    self._def_party_idx = 0
                self._def_panel.set_pokemon(self._def_custom)
                self.registry_maybe_changed.emit()
                self._refresh_party_slots()
                self.defender_changed.emit(self._def_custom)
                self.recalculate()
        elif dlg.box_select_requested():
            QTimer.singleShot(0, self._change_defender)

    def _new_defender(self) -> None:
        dlg = open_pokemon_edit_dialog(None, self, save_to_db=False)
        if dlg.exec_():
            updated = dlg.get_pokemon()
            if updated:
                self._def_custom = copy.deepcopy(updated)
                self._def_species_name = updated.name_ja or ""
                if self._opp_party:
                    self._opp_party[0] = copy.deepcopy(self._def_custom)
                else:
                    self._opp_party = [copy.deepcopy(self._def_custom)]
                self._def_party_side = "opp"
                self._def_party_idx = 0
                self._def_panel.set_pokemon(self._def_custom)
                self.registry_maybe_changed.emit()
                self._refresh_party_slots()
                self.defender_changed.emit(self._def_custom)
                self.recalculate()

    def _clear_defender(self) -> None:
        self._def_custom = None
        self._def_species_name = ""
        self._def_party_side = None
        self._def_party_idx = None
        self._def_panel.set_pokemon(None)
        self._refresh_party_slots()
        self.defender_changed.emit(None)
        self.recalculate()

    def _change_defender(self) -> None:
        from src.ui.pokemon_edit_dialog import MyBoxSelectDialog
        dlg = MyBoxSelectDialog("防御側PT", self)
        if not dlg.exec_():
            return
        p = dlg.selected_pokemon()
        if p:
            self._def_custom = copy.deepcopy(p)
            self._def_species_name = self._def_custom.name_ja or ""
            if self._opp_party:
                self._opp_party[0] = copy.deepcopy(self._def_custom)
            else:
                self._opp_party = [copy.deepcopy(self._def_custom)]
            self._def_party_side = "opp"
            self._def_party_idx = 0
            self._def_panel.set_pokemon(self._def_custom)
            self._refresh_party_slots()
            self.defender_changed.emit(self._def_custom)
            self.recalculate()

    def _box_select_into_slot(self, side: str, idx: int) -> None:
        from src.ui.pokemon_edit_dialog import MyBoxSelectDialog
        dlg = MyBoxSelectDialog("自分PT{}番".format(idx + 1), self.window())
        if not dlg.exec_():
            return
        p = dlg.selected_pokemon()
        if not p:
            return
        party = self._my_party if side == "my" else self._opp_party
        while len(party) <= idx:
            party.append(None)
        party[idx] = copy.deepcopy(p)

        # スロットをクリックしたのと同じ選択状態にする
        if side == "my":
            self._on_my_party_slot_clicked(idx)
        else:
            self._on_opp_party_slot_clicked(idx)

    def _change_move(self, slot: int) -> None:
        if self._atk is None:
            return
        from src.ui.pokemon_edit_dialog import MoveSelectDialog
        from src.data.database import get_species_by_id, get_species_by_name_ja
        species = get_species_by_id(self._atk.species_id) if self._atk.species_id else None
        if species is None and self._atk.name_ja:
            species = get_species_by_name_ja(self._atk.name_ja)
        current_moves = (self._atk.moves + ["", "", "", ""])[:4]
        original_move = current_moves[slot]
        current_moves[slot] = ""
        dlg = MoveSelectDialog(
            species.species_id if species else None,
            self._atk.name_ja or "",
            original_move,
            self,
            usage_name=self._atk.usage_name or self._atk.name_ja or "",
            current_moves=current_moves,
        )
        if dlg.exec_():
            self._atk.moves = dlg.selected_moves()
            self._persist_party_member_edits()
            self.attacker_changed.emit(self._atk)
            self.recalculate()

    def _change_opp_move(self, slot: int) -> None:
        if self._def_custom is None:
            return
        from src.ui.pokemon_edit_dialog import MoveSelectDialog
        from src.data.database import get_species_by_id, get_species_by_name_ja
        species = get_species_by_id(self._def_custom.species_id) if self._def_custom.species_id else None
        if species is None and self._def_custom.name_ja:
            species = get_species_by_name_ja(self._def_custom.name_ja)
        current_moves = (self._def_custom.moves + ["", "", "", ""])[:4]
        original_move = current_moves[slot]
        current_moves[slot] = ""
        dlg = MoveSelectDialog(
            species.species_id if species else None,
            self._def_custom.name_ja or "",
            original_move,
            self,
            usage_name=self._def_custom.usage_name or self._def_custom.name_ja or "",
            current_moves=current_moves,
        )
        if dlg.exec_():
            self._def_custom.moves = dlg.selected_moves()
            self._persist_party_member_edits()
            self.defender_changed.emit(self._def_custom)
            self.recalculate()

    def _swap_atk_def(self) -> None:
        if self._def_custom is None:
            return
        old_atk = self._atk
        self._atk = copy.deepcopy(self._def_custom)
        self._def_custom = copy.deepcopy(old_atk) if old_atk else None
        self._def_species_name = self._def_custom.name_ja if self._def_custom else ""
        self._party_source = "opp" if self._party_source == "my" else "my"
        self._refresh_bulk_rows_visibility()
        self._atk_panel.set_pokemon(self._atk)
        self._def_panel.set_pokemon(self._def_custom)
        self._refresh_party_selector_labels()
        self._refresh_party_slots()
        self.attacker_changed.emit(self._atk)
        if self._def_custom:
            self.defender_changed.emit(self._def_custom)
        self.recalculate()

    def _reset_conditions(self) -> None:
        self._weather_grp.set_value("none")
        self._terrain_grp.set_value("none")
        for btn in (self._burn_btn, self._crit_btn, self._fairy_aura_btn,
                    self._dark_aura_btn, self._charge_btn, self._helping_btn, self._steel_spirit_btn,
                    self._overgrow_btn, self._blaze_btn, self._torrent_btn,
                    self._swarm_btn, self._toxic_boost_btn,
                    self._stakeout_btn, self._flash_fire_boost_btn,
                    self._protosynthesis_btn, self._quark_drive_btn,
                    self._analytic_btn, self._flare_boost_btn,
                    self._guts_btn,
                    self._self_reflect_btn, self._self_lightscreen_btn, self._self_friend_guard_btn,
                    self._self_tailwind_btn,
                    self._reflect_btn, self._lightscreen_btn, self._friend_guard_btn, self._tailwind_btn,
                    self._opp_burn_btn, self._opp_crit_btn,
                    self._opp_fairy_aura_btn, self._opp_dark_aura_btn,
                    self._opp_charge_btn, self._opp_helping_btn, self._opp_steel_spirit_btn,
                    self._opp_overgrow_btn, self._opp_blaze_btn, self._opp_torrent_btn,
                    self._opp_swarm_btn, self._opp_toxic_boost_btn,
                    self._opp_stakeout_btn, self._opp_flash_fire_btn,
                    self._opp_protosynthesis_btn, self._opp_quark_drive_btn,
                    self._opp_analytic_btn, self._opp_flare_boost_btn, self._opp_guts_btn,
                    self._gravity_btn):
            btn.setChecked(False)
        if hasattr(self, "_supreme_combo"):
            self._supreme_combo.setCurrentIndex(0)
        if hasattr(self, "_opp_supreme_combo"):
            self._opp_supreme_combo.setCurrentIndex(0)
        if hasattr(self, "_rivalry_combo"):
            self._rivalry_combo.setCurrentIndex(0)
        self._atk_panel.reset_to_base()
        self._def_panel.reset_to_base()
        self.recalculate()

    def _set_attacker_from_party(self, pokemon: PokemonInstance, source: str) -> None:
        self._atk = copy.deepcopy(pokemon)
        self._party_source = source
        self._refresh_bulk_rows_visibility()
        self._atk_panel.set_pokemon(self._atk)
        self._refresh_party_selector_labels()
        self.attacker_changed.emit(self._atk)

    def _set_defender_from_party(self, pokemon: PokemonInstance) -> None:
        self._def_custom = copy.deepcopy(pokemon)
        self._def_species_name = self._def_custom.name_ja if self._def_custom else ""
        self._def_panel.set_pokemon(self._def_custom)
        self.defender_changed.emit(self._def_custom)

    def _change_atk_ability(self) -> None:
        if not self._atk:
            return
        new_val = _pick_ability(self._atk, self)
        if new_val is not None:
            self._atk.ability = new_val
            self._persist_party_member_edits()
            self._atk_panel.set_pokemon(self._atk)
            self._atk_card.set_pokemon(self._atk)
            self._refresh_party_slots()
            self.attacker_changed.emit(self._atk)
            self.recalculate()

    def _change_atk_item(self) -> None:
        if not self._atk:
            return
        new_val = _pick_item(self._atk, self)
        if new_val is not None:
            self._atk.item = new_val
            self._persist_party_member_edits()
            self._atk_panel.set_pokemon(self._atk)
            self._atk_card.set_pokemon(self._atk)
            self._refresh_party_slots()
            self.attacker_changed.emit(self._atk)
            self.recalculate()

    def _change_def_ability(self) -> None:
        if not self._def_custom:
            return
        new_val = _pick_ability(self._def_custom, self)
        if new_val is not None:
            self._def_custom.ability = new_val
            self._persist_party_member_edits()
            self._def_panel.set_pokemon(self._def_custom)
            self._refresh_defender_card()
            self._refresh_party_slots()
            self.defender_changed.emit(self._def_custom)
            self.recalculate()

    def _change_def_item(self) -> None:
        if not self._def_custom:
            return
        new_val = _pick_item(self._def_custom, self)
        if new_val is not None:
            self._def_custom.item = new_val
            self._persist_party_member_edits()
            self._def_panel.set_pokemon(self._def_custom)
            self._refresh_defender_card()
            self._refresh_party_slots()
            self.defender_changed.emit(self._def_custom)
            self.recalculate()

    def _on_form_change_atk(self) -> None:
        if not self._atk:
            return
        key = _normalize_form_name(self._atk.name_ja)
        group = _FORM_NAME_TO_GROUP.get(key)
        if not group or len(group) < 2:
            return
        canon = group[0]
        cur_idx = group.index(key) if key in group else 0
        next_name = group[(cur_idx + 1) % len(group)]
        if next_name == canon:
            # ベースフォームに戻す際、キャッシュに保存しておいた元の特性を復元
            cached = self._atk_form_cache.pop(canon, None)
            original_ability = cached[1] if isinstance(cached, tuple) else ""
            if not original_ability:
                # PTから直接メガフォームで選んだ場合などキャッシュが空の場合、DBから取得
                from src.data.database import get_abilities_by_usage
                abilities = get_abilities_by_usage(canon)
                original_ability = abilities[0] if abilities else ""
            new_p = _apply_form(self._atk, next_name, original_ability=original_ability)
        else:
            # メガ/別フォームへ移行する際、元の特性を保存
            existing = self._atk_form_cache.get(canon)
            original_ability = existing[1] if isinstance(existing, tuple) else self._atk.ability
            self._atk_form_cache[canon] = (next_name, original_ability)
            new_p = _apply_form(self._atk, next_name)
        self._atk = new_p
        self._persist_party_member_edits()
        self._atk_panel.set_pokemon(self._atk)
        self.attacker_changed.emit(self._atk)
        self._refresh_defender_card()
        self._refresh_party_slots()
        self.recalculate()

    def _on_form_change_def(self) -> None:
        if not self._def_custom:
            return
        key = _normalize_form_name(self._def_custom.name_ja)
        group = _FORM_NAME_TO_GROUP.get(key)
        if not group or len(group) < 2:
            return
        canon = group[0]
        cur_idx = group.index(key) if key in group else 0
        next_name = group[(cur_idx + 1) % len(group)]
        if next_name == canon:
            cached = self._def_form_cache.pop(canon, None)
            original_ability = cached[1] if isinstance(cached, tuple) else ""
            if not original_ability:
                from src.data.database import get_abilities_by_usage
                abilities = get_abilities_by_usage(canon)
                original_ability = abilities[0] if abilities else ""
            new_p = _apply_form(self._def_custom, next_name, original_ability=original_ability)
        else:
            existing = self._def_form_cache.get(canon)
            original_ability = existing[1] if isinstance(existing, tuple) else self._def_custom.ability
            self._def_form_cache[canon] = (next_name, original_ability)
            new_p = _apply_form(self._def_custom, next_name)
        self._def_custom = new_p
        self._def_species_name = new_p.name_ja
        self._persist_party_member_edits()
        self._def_panel.set_pokemon(self._def_custom)
        self.defender_changed.emit(self._def_custom)
        self._refresh_defender_card()
        self._refresh_party_slots()
        self.recalculate()

    def _on_my_party_slot_clicked(self, idx: int) -> None:
        if idx >= len(self._my_party) or self._my_party[idx] is None:
            self._add_party_slot("my", idx)
            return
        p = self._my_party[idx]
        if self._party_source == "my":
            self._atk_party_side = "my"
            self._atk_party_idx = idx
            self._set_attacker_from_party(p, source="my")
            canon = (_FORM_NAME_TO_GROUP.get(p.name_ja) or [p.name_ja])[0]
            cached = self._atk_form_cache.get(canon)
            if cached:
                form_name = cached[0] if isinstance(cached, tuple) else cached
                self._atk = _apply_form(self._atk, form_name)
                self._atk_panel.set_pokemon(self._atk)
                self.attacker_changed.emit(self._atk)
        else:
            self._def_party_side = "my"
            self._def_party_idx = idx
            self._set_defender_from_party(p)
            canon = (_FORM_NAME_TO_GROUP.get(p.name_ja) or [p.name_ja])[0]
            cached = self._def_form_cache.get(canon)
            if cached:
                form_name = cached[0] if isinstance(cached, tuple) else cached
                self._def_custom = _apply_form(self._def_custom, form_name)
                self._def_species_name = self._def_custom.name_ja
                self._def_panel.set_pokemon(self._def_custom)
                self.defender_changed.emit(self._def_custom)
        self._refresh_party_slots()
        self.recalculate()

    def _on_opp_party_slot_clicked(self, idx: int) -> None:
        if idx >= len(self._opp_party) or self._opp_party[idx] is None:
            self._add_party_slot("opp", idx)
            return
        p = self._opp_party[idx]
        if self._party_source == "opp":
            self._atk_party_side = "opp"
            self._atk_party_idx = idx
            self._set_attacker_from_party(p, source="opp")
            canon = (_FORM_NAME_TO_GROUP.get(p.name_ja) or [p.name_ja])[0]
            cached = self._atk_form_cache.get(canon)
            if cached:
                form_name = cached[0] if isinstance(cached, tuple) else cached
                self._atk = _apply_form(self._atk, form_name)
                self._atk_panel.set_pokemon(self._atk)
                self.attacker_changed.emit(self._atk)
        else:
            self._def_party_side = "opp"
            self._def_party_idx = idx
            self._set_defender_from_party(p)
            canon = (_FORM_NAME_TO_GROUP.get(p.name_ja) or [p.name_ja])[0]
            cached = self._def_form_cache.get(canon)
            if cached:
                form_name = cached[0] if isinstance(cached, tuple) else cached
                self._def_custom = _apply_form(self._def_custom, form_name)
                self._def_species_name = self._def_custom.name_ja
                self._def_panel.set_pokemon(self._def_custom)
                self.defender_changed.emit(self._def_custom)
        self._refresh_party_slots()
        self.recalculate()

    # ── Key mapping helpers ───────────────────────────────────────────

    def _set_battle_format(self, mode: str) -> None:
        self._battle_format = mode
        is_double = mode == "double"
        if hasattr(self, "_helping_btn"):
            self._helping_btn.setVisible(is_double)
            self._opp_helping_btn.setVisible(is_double)
            self._steel_spirit_btn.setVisible(is_double)
            self._opp_steel_spirit_btn.setVisible(is_double)
            self._self_friend_guard_btn.setVisible(is_double)
            self._friend_guard_btn.setVisible(is_double)
            self._self_tailwind_btn.setVisible(is_double)
            self._tailwind_btn.setVisible(is_double)
        self.recalculate()

    def _toggle_details(self, checked: bool) -> None:
        self._detail_container.setVisible(checked)
        self._detail_toggle_btn.setText("詳細設定を隠す" if checked else "詳細設定を表示")
        if checked:
            self.recalculate()

    def _apply_bulk_rows_default(self) -> None:
        self._set_bulk_rows_visible(True, refresh=False)

    def _set_bulk_rows_visible(self, visible: bool, refresh: bool = True) -> None:
        self._show_bulk_rows = bool(visible)
        if hasattr(self, "_move_sections"):
            for sec in self._move_sections:
                sec.set_bulk_rows_visible(self._show_bulk_rows)
        if hasattr(self, "_opp_move_sections"):
            for sec in self._opp_move_sections:
                sec.set_bulk_rows_visible(self._show_bulk_rows)
        if refresh:
            self._refresh_defender_card()

    def _on_bulk_toggle_clicked(self, checked: bool) -> None:
        self._set_bulk_rows_visible(bool(checked), refresh=True)

    def _refresh_bulk_rows_visibility(self) -> None:
        pass

    def _weather_key(self) -> str:
        return {"はれ": "sun", "あめ": "rain", "すな": "sand", "ゆき": "hail"}.get(
            self._weather_grp.value(), "none")

    def _terrain_key(self) -> str:
        return {"エレキ": "electric", "グラス": "grassy",
                "ミスト": "misty", "サイコ": "psychic"}.get(
            self._terrain_grp.value(), "none")
