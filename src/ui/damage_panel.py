"""Damage calculation panel – complete redesign."""
from __future__ import annotations

import copy
import dataclasses
import math
from typing import Callable, Optional

import requests
from PyQt5.QtCore import QPointF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QBrush, QFont, QPixmap, QPen, QLinearGradient, QPolygonF
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGroupBox, QScrollArea, QPushButton, QSizePolicy,
    QSpinBox, QComboBox, QCheckBox, QSplitter, QDialog,
    QSlider,
)

from src.models import PokemonInstance, MoveInfo, SpeciesInfo
from src.constants import (
    TYPE_COLORS, TYPE_EN_TO_JA, TYPE_JA_TO_EN,
    MULTI_HIT_MOVES_JA,
    POKEAPI_BASE, STEALTH_ROCK_CHART, NATURES_JA,
)
from src.data import zukan_client
from src.ui.ui_utils import open_pokemon_edit_dialog


# ── Helpers ───────────────────────────────────────────────────────────────

def _rank_mult(rank: int) -> float:
    table = {-6: 2/8, -5: 2/7, -4: 2/6, -3: 2/5, -2: 2/4, -1: 2/3,
              0: 1.0, 1: 3/2, 2: 4/2, 3: 5/2, 4: 6/2, 5: 7/2, 6: 8/2}
    return table.get(max(-6, min(6, rank)), 1.0)


def _n_hit_ko(min_dmg: int, max_dmg: int, hp: int) -> str:
    if max_dmg <= 0 or hp <= 0:
        return "効果なし"

    min_hits = max(1, math.ceil(hp / max_dmg))
    if min_dmg <= 0:
        return "乱数{}発以上".format(min_hits)

    max_hits = max(1, math.ceil(hp / min_dmg))
    if min_hits == max_hits:
        if min_dmg * min_hits >= hp:
            return "確定{}発".format(min_hits)
        return "乱数{}発".format(min_hits)

    return "乱数{}発".format(min_hits)


def _bar_color(min_pct: float, max_pct: float) -> str:
    if max_pct >= 100:
        return "#f38ba8"
    if min_pct >= 50:
        return "#fab387"
    if max_pct >= 50:
        return "#f9e2af"
    return "#a6e3a1"


def _bar_variation_color(min_pct: float, max_pct: float) -> str:
    if max_pct >= 100:
        return "#6b1a2a"
    if min_pct >= 50:
        return "#5e2d10"
    if max_pct >= 50:
        return "#5a4a0a"
    return "#1e4a1a"


def _hp_color(remaining_pct: float) -> str:
    if remaining_pct <= 20:
        return "#f38ba8"
    if remaining_pct <= 50:
        return "#f9e2af"
    return "#a6e3a1"


def _nature_mult_from_name(nature_ja: str, stat_key: str) -> float:
    boost, reduce = NATURES_JA.get(nature_ja or "", (None, None))
    if boost == stat_key:
        return 1.1
    if reduce == stat_key:
        return 0.9
    return 1.0


def _mult_label(value: float) -> str:
    if value <= 0.95:
        return "×0.9"
    if value >= 1.05:
        return "×1.1"
    return "×1.0"


def _round1(value: float) -> float:
    # Python round() は銀行丸めになるため、一般的な四捨五入に揃える。
    if value >= 0:
        return math.floor(value * 10 + 0.5) / 10
    return math.ceil(value * 10 - 0.5) / 10


_ICON_CACHE: dict[str, QPixmap] = {}


def _game_badge(text: str, c_top: str, c_bottom: str, width: int, height: int, font_size: int = 10) -> QPixmap:
    key = "{}|{}|{}|{}|{}|{}".format(text, c_top, c_bottom, width, height, font_size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    pm = QPixmap(width, height)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    grad = QLinearGradient(0, 0, 0, height)
    grad.setColorAt(0.0, QColor(c_top))
    grad.setColorAt(1.0, QColor(c_bottom))
    p.setBrush(QBrush(grad))
    p.setPen(QPen(QColor("#dce2ff"), 1))
    p.drawRoundedRect(0, 0, width - 1, height - 1, 6, 6)

    p.setPen(QColor("#ffffff"))
    f = QFont("Yu Gothic UI", font_size)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, text)
    p.end()

    _ICON_CACHE[key] = pm
    return pm


_REMOTE_ICON_CACHE: dict[str, QPixmap] = {}
_CATEGORY_ICON_URLS = {
    "physical": "https://play.pokemonshowdown.com/sprites/categories/Physical.png",
    "special": "https://play.pokemonshowdown.com/sprites/categories/Special.png",
    "status": "https://play.pokemonshowdown.com/sprites/categories/Status.png",
}


def _remote_icon(url: str, width: int, height: int) -> QPixmap | None:
    cache_key = "{}|{}|{}".format(url, width, height)
    cached = _REMOTE_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    payload = zukan_client.get_cached_asset_bytes(url)
    if not payload:
        return None
    source = QPixmap()
    if not source.loadFromData(payload):
        return None
    scaled = source.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    _REMOTE_ICON_CACHE[cache_key] = scaled
    return scaled


def _category_icon(category: str, width: int = 66, height: int = 22) -> QPixmap:
    url = _CATEGORY_ICON_URLS.get(category, "")
    if url:
        icon = _remote_icon(url, width, height)
        if icon is not None:
            return icon
    fallback = {
        "physical": ("ぶつり", "#f87f5a", "#d44936"),
        "special": ("とくしゅ", "#67a8ff", "#3b69d8"),
        "status": ("へんか", "#9da5bc", "#707993"),
    }.get(category, ("-", "#9da5bc", "#707993"))
    return _game_badge(fallback[0], fallback[1], fallback[2], width, height, 9)


def _battle_stat_icon(kind: str, width: int = 60, height: int = 22) -> QPixmap:
    key = "stat:{}:{}:{}".format(kind, width, height)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    text = "威力" if kind == "power" else "命中"
    top_color = "#f7c46a" if kind == "power" else "#8bd6a2"
    bottom_color = "#d18931" if kind == "power" else "#4f9c6f"
    icon_color = "#fff6de" if kind == "power" else "#eafff1"

    pm = QPixmap(width, height)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    grad = QLinearGradient(0, 0, 0, height)
    grad.setColorAt(0.0, QColor(top_color))
    grad.setColorAt(1.0, QColor(bottom_color))
    p.setBrush(QBrush(grad))
    p.setPen(QPen(QColor("#dce2ff"), 1))
    p.drawRoundedRect(0, 0, width - 1, height - 1, 7, 7)

    # Left-side glyph
    gx = 8
    gy = height // 2
    p.setPen(QPen(QColor(icon_color), 2))
    if kind == "power":
        points = [
            (gx, gy - 6), (gx + 3, gy - 1), (gx + 9, gy - 1),
            (gx + 4, gy + 2), (gx + 6, gy + 7), (gx, gy + 3),
            (gx - 6, gy + 7), (gx - 4, gy + 2), (gx - 9, gy - 1),
            (gx - 3, gy - 1),
        ]
        poly = QPolygonF([QPointF(float(px), float(py)) for px, py in points])
        p.setBrush(QColor(icon_color))
        p.drawPolygon(poly)
    else:
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(gx - 7, gy - 7, 14, 14)
        p.drawLine(gx - 10, gy, gx + 10, gy)
        p.drawLine(gx, gy - 10, gx, gy + 10)
        p.setBrush(QColor(icon_color))
        p.drawEllipse(gx - 2, gy - 2, 4, 4)

    p.setPen(QColor("#ffffff"))
    f = QFont("Yu Gothic UI", 9)
    f.setBold(True)
    p.setFont(f)
    p.drawText(20, 0, width - 20, height, Qt.AlignCenter, text)
    p.end()

    _ICON_CACHE[key] = pm
    return pm


def _power_option_value(data: object) -> int:
    if isinstance(data, tuple) and len(data) >= 1:
        try:
            return int(data[0])
        except Exception:
            return 0
    try:
        return int(data)
    except Exception:
        return 0


def _discrete_options(values: list[int], prefix: str = "威力") -> list[tuple[str, object]]:
    result: list[tuple[str, object]] = []
    used: set[int] = set()
    for value in values:
        v = int(value)
        if v <= 0 or v in used:
            continue
        used.add(v)
        result.append(("{} {}".format(prefix, v), v))
    return result


def _hp_percent_options(
    label_prefix: str,
    percent_to_power: Callable[[int], int],
) -> list[tuple[str, object]]:
    # 1% と 10%刻みだけ表示する要件。
    hp_steps = [100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 1]
    options: list[tuple[str, object]] = []
    for pct in hp_steps:
        power = max(1, int(percent_to_power(pct)))
        options.append(("{}{}% (威力 {})".format(label_prefix, pct, power), (power, pct)))
    return options


def _reversal_flail_power_from_hp_percent(hp_percent: int) -> int:
    # きしかいせい/じたばた: 現HP/最大HPの閾値で威力が決まる (Gen3+)
    scaled = int(hp_percent) * 48
    if scaled <= 100:
        return 200
    if scaled <= 400:
        return 150
    if scaled <= 900:
        return 100
    if scaled <= 1600:
        return 80
    if scaled <= 3200:
        return 40
    return 20


def _eruption_family_power_from_hp_percent(hp_percent: int) -> int:
    return max(1, (150 * int(hp_percent)) // 100)


def _wring_out_family_power_from_hp_percent(hp_percent: int) -> int:
    return max(1, (120 * int(hp_percent)) // 100 + 1)


def _variable_power_options(move: MoveInfo) -> list[tuple[str, object]]:
    name = move.name_ja
    base_power = move.power or 1

    if name in ("ころがる", "アイスボール"):
        normal = [30, 60, 120, 240, 480]
        rolled = [value * 2 for value in normal]
        options: list[tuple[str, int]] = []
        for idx, value in enumerate(normal, start=1):
            options.append(("{} {}回目 ({})".format(name, idx, value), value))
        for idx, value in enumerate(rolled, start=1):
            options.append(("まるくなる後 {}回目 ({})".format(idx, value), value))
        return options

    if name == "れんぞくぎり":
        return [
            ("1回目 (40)", 40),
            ("2回目 (80)", 80),
            ("3回目以降 (160)", 160),
        ]

    if name == "おはかまいり":
        return [("味方{}体ひんし ({})".format(i, 50 + 50 * i), 50 + 50 * i) for i in range(0, 6)]

    if name == "ふんどのこぶし":
        return [("被弾{}回 ({})".format(i, 50 + 50 * i), 50 + 50 * i) for i in range(0, 7)]

    if name == "エコーボイス":
        return [("連続{}回目 ({})".format(i, min(200, 40 * i)), min(200, 40 * i)) for i in range(1, 6)]

    if name in ("アシストパワー", "つけあがる"):
        return [("上昇ランク合計 {} ({})".format(i, 20 + 20 * i), 20 + 20 * i) for i in range(0, 43)]

    if name == "おしおき":
        return [("相手上昇ランク合計 {} ({})".format(i, min(200, 60 + 20 * i)), min(200, 60 + 20 * i)) for i in range(0, 8)]

    if name in ("しおふき", "ふんか", "ドラゴンエナジー"):
        return _hp_percent_options("自分HP ", _eruption_family_power_from_hp_percent)

    if name in ("じたばた", "きしかいせい"):
        return _hp_percent_options("自分HP ", _reversal_flail_power_from_hp_percent)

    if name in ("しぼりとる", "にぎりつぶす"):
        return _hp_percent_options("相手HP ", _wring_out_family_power_from_hp_percent)

    if name == "からげんき":
        return [("通常 (70)", 70), ("状態異常時 (140)", 140)]

    if name in ("たたりめ", "ベノムショック", "しおみず", "かたきうち"):
        return [("通常 ({})".format(base_power), base_power), ("条件成立 ({})".format(base_power * 2), base_power * 2)]

    if name == "ジャイロボール":
        return _discrete_options(list(range(150, 0, -1)))

    if name == "エレキボール":
        return _discrete_options([40, 60, 80, 120, 150])

    if name == "ゆきなだれ":
        return [("通常 (60)", 60), ("後攻被弾後 (120)", 120)]

    if name == "はたきおとす":
        return [("通常 (65)", 65), ("道具あり対象 (97)", 97)]

    if name == "マグニチュード":
        return _discrete_options([10, 30, 50, 70, 90, 110, 150])

    return []


# ── Form change data ─────────────────────────────────────────────────────
# Each list: [base_form, alt1, alt2, …]. Cycle on button press.
_FORM_GROUPS: list[list[str]] = [
    # ── Dual-branch megas (full-width X/Y to match Zukan display names)
    ["リザードン",   "メガリザードンＸ", "メガリザードンＹ"],
    ["ミュウツー",   "メガミュウツーＸ", "メガミュウツーＹ"],
    ["ライチュウ",   "メガライチュウＸ", "メガライチュウＹ"],
    # ── Single megas (gen 1–6, standard)
    ["フシギバナ",   "メガフシギバナ"],
    ["スピアー",     "メガスピアー"],
    ["ピジョット",   "メガピジョット"],
    ["ピクシー",     "メガピクシー"],
    ["ウツボット",   "メガウツボット"],
    ["ヤドラン",     "メガヤドラン"],
    ["ゲンガー",     "メガゲンガー"],
    ["スターミー",   "メガスターミー"],
    ["カイロス",     "メガカイロス"],
    ["ギャラドス",   "メガギャラドス"],
    ["プテラ",       "メガプテラ"],
    ["カイリュー",   "メガカイリュー"],
    ["カメックス",   "メガカメックス"],
    ["フーディン",   "メガフーディン"],
    ["ガルーラ",     "メガガルーラ"],
    ["ハッサム",     "メガハッサム"],
    ["ヘラクロス",   "メガヘラクロス"],
    ["ヘルガー",     "メガヘルガー"],
    ["デンリュウ",   "メガデンリュウ"],
    ["ハガネール",   "メガハガネール"],
    ["バンギラス",   "メガバンギラス"],
    ["ジュカイン",   "メガジュカイン"],
    ["バシャーモ",   "メガバシャーモ"],
    ["ラグラージ",   "メガラグラージ"],
    ["ヤミラミ",     "メガヤミラミ"],
    ["クチート",     "メガクチート"],
    ["ボスゴドラ",   "メガボスゴドラ"],
    ["チャーレム",   "メガチャーレム"],
    ["ライボルト",   "メガライボルト"],
    ["サメハダー",   "メガサメハダー"],
    ["バクーダ",     "メガバクーダ"],
    ["チルタリス",   "メガチルタリス"],
    ["ジュペッタ",   "メガジュペッタ"],
    ["チリーン",     "メガチリーン"],
    ["アブソル",     "メガアブソル"],
    ["オニゴーリ",   "メガオニゴーリ"],
    ["ボーマンダ",   "メガボーマンダ"],
    ["メタグロス",   "メガメタグロス"],
    ["ラティアス",   "メガラティアス"],
    ["ラティオス",   "メガラティオス"],
    ["サーナイト",   "メガサーナイト"],
    ["ユキノオー",   "メガユキノオー"],
    ["ルカリオ",     "メガルカリオ"],
    ["ガブリアス",   "メガガブリアス"],
    ["ミミロップ",   "メガミミロップ"],
    ["エアームド",   "メガエアームド"],
    ["エルレイド",   "メガエルレイド"],
    ["ユキメノコ",   "メガユキメノコ"],
    ["タブンネ",     "メガタブンネ"],
    ["ムクホーク",   "メガムクホーク"],
    # ── Single megas (gen 7+, gen9 fan-made)
    ["メガニウム",   "メガメガニウム"],
    ["オーダイル",   "メガオーダイル"],
    ["エンブオー",   "メガエンブオー"],
    ["ドリュウズ",   "メガドリュウズ"],
    ["ペンドラー",   "メガペンドラー"],
    ["ズルズキン",   "メガズルズキン"],
    ["シビルドン",   "メガシビルドン"],
    ["シャンデラ",   "メガシャンデラ"],
    ["ゴルーグ",     "メガゴルーグ"],
    ["ブリガロン",   "メガブリガロン"],
    ["マフォクシー", "メガマフォクシー"],
    ["ゲッコウガ",   "メガゲッコウガ"],
    ["カエンジシ",   "メガカエンジシ"],
    ["ニャオニクス", "メガニャオニクス"],
    ["カラマネロ",   "メガカラマネロ"],
    ["ガメノデス",   "メガガメノデス"],
    ["ドラミドロ",   "メガドラミドロ"],
    ["ルチャブル",   "メガルチャブル"],
    ["ヒードラン",   "メガヒードラン"],
    ["ダークライ",   "メガダークライ"],
    ["ゼラオラ",     "メガゼラオラ"],
    ["タイレーツ",   "メガタイレーツ"],
    ["スコヴィラン", "メガスコヴィラン"],
    ["キラフロル",   "メガキラフロル"],
    ["セグレイブ",   "メガセグレイブ"],
    ["ケケンカニ",   "メガケケンカニ"],
    ["グソクムシャ", "メガグソクムシャ"],
    ["ジジーロン",   "メガジジーロン"],
    ["マギアナ",     "メガマギアナ"],
    # ── Floette: default form is えいえんのはな; Mega requires Floettite
    ["フラエッテ (えいえんのはな)", "メガフラエッテ"],
    # ── Primals
    ["グラードン",   "ゲンシグラードン"],
    ["カイオーガ",   "ゲンシカイオーガ"],
    ["レックウザ",   "メガレックウザ"],
    # ── Battle-only form changes (display_name = DB name_ja or "DB名 (フォルム名)")
    ["ギルガルド",              "ギルガルド (ブレードフォルム)"],
    ["チェリム",                "チェリム (ポジフォルム)"],
    ["メロエッタ",              "メロエッタ (ステップフォルム)"],
    ["ヒヒダルマ",              "ヒヒダルマ (ダルマモード)"],
    ["ガラルヒヒダルマ",        "ガラルヒヒダルマ (ダルマモード)"],
    ["ジガルデ",                "ジガルデ (１０％フォルム)", "ジガルデ (パーフェクトフォルム)", "メガジガルデ"],
    ["モルペコ",                "モルペコ (はらぺこもよう)"],
    ["コオリッポ",              "コオリッポ (ナイスフェイス)"],
    ["メテノ",                  "メテノ (あかいろのコア)"],
    ["ヨワシ",                  "ヨワシ (むれたすがた)"],
    ["イルカマン",              "イルカマン (マイティフォルム)"],
    ["ポワルン",                "ポワルン (たいようのすがた)", "ポワルン (あまみずのすがた)", "ポワルン (ゆきぐものすがた)"],
    ["テラパゴス",              "テラパゴス (テラスタルフォルム)", "テラパゴス (ステラフォルム)"],
]

_FORM_NAME_TO_GROUP: dict[str, list[str]] = {
    name: group for group in _FORM_GROUPS for name in group
}
# Spacing-normalized aliases so name_ja variants with no space before "(" still resolve.
# Also cover the usage-scraper short form "フラエッテ(えいえん)" (without のはな).
_FLOETTE_ETERNAL_GROUP = _FORM_NAME_TO_GROUP.get("フラエッテ (えいえんのはな)")
if _FLOETTE_ETERNAL_GROUP is not None:
    _FORM_NAME_TO_GROUP["フラエッテ(えいえんのはな)"] = _FLOETTE_ETERNAL_GROUP
    _FORM_NAME_TO_GROUP["フラエッテ(えいえん)"] = _FLOETTE_ETERNAL_GROUP
    _FORM_NAME_TO_GROUP["フラエッテ (えいえん)"] = _FLOETTE_ETERNAL_GROUP

# Canonical display name: group内のname_ja → UIカード表示名
# DBのname_ja（= group[0]）がフォルム名を含まない場合のみ登録
_FORM_CANONICAL_NAME: dict[str, str] = {
    "ギルガルド":   "ギルガルド (シールドフォルム)",
    "チェリム":     "チェリム (ネガフォルム)",
    "メロエッタ":   "メロエッタ (ボイスフォルム)",
    "ジガルデ":     "ジガルデ (５０％フォルム)",
    "モルペコ":     "モルペコ (まんぷくもよう)",
    "コオリッポ":   "コオリッポ (アイスフェイス)",
    "メテノ":       "メテノ (りゅうせいのすがた)",
    "ヨワシ":       "ヨワシ (たんどくのすがた)",
    "イルカマン":   "イルカマン (ナイーブフォルム)",
    "ポワルン":     "ポワルン (ポワルンのすがた)",
    # Floette eternal: normalize spacing/shorthand variants for display
    "フラエッテ(えいえんのはな)": "フラエッテ (えいえんのはな)",
    "フラエッテ(えいえん)": "フラエッテ (えいえんのはな)",
    "フラエッテ (えいえん)": "フラエッテ (えいえんのはな)",
    # Paldea Tauros breed display names
    "パルデアケンタロス(格闘)": "パルデアケンタロス(格闘)",
    "パルデアケンタロス(炎)": "パルデアケンタロス(炎)",
    "パルデアケンタロス(水)": "パルデアケンタロス(水)",
}

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
    """Return the canonical form group key for name_ja, resolving spacing variants."""
    if name_ja in _FORM_NAME_TO_GROUP:
        return name_ja
    # Try adding a space before '(' so 'フラエッテ(えいえんのはな)' → 'フラエッテ (えいえんのはな)'
    import re as _re
    spaced = _re.sub(r"(?<!\s)\(", " (", name_ja)
    if spaced != name_ja and spaced in _FORM_NAME_TO_GROUP:
        return spaced
    return name_ja


def _form_group(name_ja: str) -> list[str]:
    return _FORM_NAME_TO_GROUP.get(_normalize_form_name(name_ja), [])


def _next_form_name(name_ja: str) -> Optional[str]:
    key = _normalize_form_name(name_ja)
    group = _FORM_NAME_TO_GROUP.get(key)
    if not group or len(group) < 2:
        return None
    idx = group.index(key) if key in group else 0
    return group[(idx + 1) % len(group)]


def _apply_form(p: "PokemonInstance", form_name: str, original_ability: str = "") -> "PokemonInstance":
    """Return a new PokemonInstance with form_name's stats/types/ability, same EVs/nature/moves."""
    import copy as _copy
    from src.data.database import get_species_by_name_ja
    from src.calc.damage_calc import calc_stat
    from src.calc.smogon_bridge import smogon_mega_species

    new_p = _copy.deepcopy(p)
    new_p.name_ja = form_name
    group = _FORM_NAME_TO_GROUP.get(form_name)
    new_p.usage_name = group[0] if group else (p.usage_name or p.name_ja)

    en = _FORM_POKEAPI_EN.get(form_name, "")
    if en:
        # フォルム名が _FORM_POKEAPI_EN に登録されている場合は直接PokeAPIから取得して正確なstatsを使う
        species = _species_from_name_en(en, name_ja=form_name)
        # Fallback: use hardcoded stats for megas absent from PokeAPI
        if species is None and form_name.startswith("メガ"):
            smogon_name = smogon_mega_species(en, form_name)
            fb = _FORM_MISSING_MEGA_STATS.get(smogon_name)
            if fb:
                fb_en, fb_t1, fb_t2, fb_hp, fb_atk, fb_def, fb_spa, fb_spd, fb_spe, fb_wt = fb
                species = SpeciesInfo(
                    species_id=p.species_id if hasattr(p, "species_id") else 0,
                    name_ja=form_name, name_en=fb_en,
                    type1=fb_t1, type2=fb_t2,
                    base_hp=fb_hp, base_attack=fb_atk, base_defense=fb_def,
                    base_sp_attack=fb_spa, base_sp_defense=fb_spd, base_speed=fb_spe,
                    weight_kg=fb_wt,
                )
    else:
        species = get_species_by_name_ja(form_name)
        # Fallback for Mega forms absent from DB: use hardcoded stats
        if species is None and form_name.startswith("メガ"):
            base_ja = form_name[2:]  # strip メガ prefix
            base_species = get_species_by_name_ja(base_ja)
            smogon_name = smogon_mega_species(base_species.name_en or "" if base_species else "", form_name)
            fb = _FORM_MISSING_MEGA_STATS.get(smogon_name)
            if fb:
                fb_en, fb_t1, fb_t2, fb_hp, fb_atk, fb_def, fb_spa, fb_spd, fb_spe, fb_wt = fb
                species = SpeciesInfo(
                    species_id=p.species_id if hasattr(p, "species_id") else 0,
                    name_ja=form_name, name_en=fb_en,
                    type1=fb_t1, type2=fb_t2,
                    base_hp=fb_hp, base_attack=fb_atk, base_defense=fb_def,
                    base_sp_attack=fb_spa, base_sp_defense=fb_spd, base_speed=fb_spe,
                    weight_kg=fb_wt,
                )

    if species:
        new_p.name_en = species.name_en or new_p.name_en
        new_p.types = [t for t in [species.type1, species.type2] if t]
        new_p.weight_kg = species.weight_kg
        lv = new_p.level or 50
        nat = new_p.nature or ""
        new_p.hp = calc_stat(species.base_hp, 31, new_p.ev_hp or 0, level=lv, is_hp=True)
        new_p.attack = calc_stat(species.base_attack, 31, new_p.ev_attack or 0, level=lv,
                                  nature_mult=_nature_mult_from_name(nat, "attack"))
        new_p.defense = calc_stat(species.base_defense, 31, new_p.ev_defense or 0, level=lv,
                                   nature_mult=_nature_mult_from_name(nat, "defense"))
        new_p.sp_attack = calc_stat(species.base_sp_attack, 31, new_p.ev_sp_attack or 0, level=lv,
                                     nature_mult=_nature_mult_from_name(nat, "sp_attack"))
        new_p.sp_defense = calc_stat(species.base_sp_defense, 31, new_p.ev_sp_defense or 0, level=lv,
                                      nature_mult=_nature_mult_from_name(nat, "sp_defense"))
        new_p.speed = calc_stat(species.base_speed, 31, new_p.ev_speed or 0, level=lv,
                                 nature_mult=_nature_mult_from_name(nat, "speed"))
        new_p.max_hp = new_p.hp
        new_p.current_hp = new_p.hp

    ability = _FORM_ABILITY_JA.get(form_name)
    if ability:
        new_p.ability = ability
    elif original_ability:
        new_p.ability = original_ability

    return new_p


_POKEAPI_SPECIES_CACHE_BY_NAME_EN: dict[str, SpeciesInfo | None] = {}
_POKEAPI_SESSION = requests.Session()
_POKEAPI_SESSION.headers["User-Agent"] = "PokemonDamageCalc/1.0"


def _species_from_name_en(name_en: str, species_id: int = 0, name_ja: str = "") -> SpeciesInfo | None:
    key = (name_en or "").strip().lower()
    if not key:
        return None
    if key in _POKEAPI_SPECIES_CACHE_BY_NAME_EN:
        return _POKEAPI_SPECIES_CACHE_BY_NAME_EN[key]
    try:
        response = _POKEAPI_SESSION.get("{}/pokemon/{}".format(POKEAPI_BASE, key), timeout=15)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            _POKEAPI_SPECIES_CACHE_BY_NAME_EN[key] = None
            return None
    except Exception:
        _POKEAPI_SPECIES_CACHE_BY_NAME_EN[key] = None
        return None

    type_rows = payload.get("types")
    type_names: list[str] = []
    if isinstance(type_rows, list):
        for row in sorted(type_rows, key=lambda x: int((x or {}).get("slot") or 99)):
            type_name = str(((row or {}).get("type") or {}).get("name") or "").strip()
            if type_name:
                type_names.append(type_name)

    stats_map: dict[str, int] = {}
    for row in payload.get("stats") or []:
        stat_name = str(((row or {}).get("stat") or {}).get("name") or "").strip()
        if not stat_name:
            continue
        try:
            stats_map[stat_name] = int(row.get("base_stat") or 0)
        except Exception:
            stats_map[stat_name] = 0

    resolved = SpeciesInfo(
        species_id=species_id or 0,
        name_ja=name_ja or key,
        name_en=key,
        type1=type_names[0] if len(type_names) >= 1 else "normal",
        type2=type_names[1] if len(type_names) >= 2 else "",
        base_hp=stats_map.get("hp", 0),
        base_attack=stats_map.get("attack", 0),
        base_defense=stats_map.get("defense", 0),
        base_sp_attack=stats_map.get("special-attack", 0),
        base_sp_defense=stats_map.get("special-defense", 0),
        base_speed=stats_map.get("speed", 0),
        weight_kg=float(payload.get("weight") or 0) / 10.0,
    )
    _POKEAPI_SPECIES_CACHE_BY_NAME_EN[key] = resolved
    return resolved


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

class _ToggleBtn(QPushButton):
    def __init__(
        self,
        text: str,
        parent=None,
        font_size: int = 14,
        pad_h: int = 8,
        pad_v: int = 4,
        cond_style: bool = False,
    ):
        super().__init__(text, parent)
        self._font_size = int(font_size)
        self._pad_h = int(pad_h)
        self._pad_v = int(pad_v)
        self._cond_style = cond_style
        self.setCheckable(True)
        self.toggled.connect(lambda _: self._refresh())
        self._refresh()

    def set_metrics(
        self,
        *,
        font_size: Optional[int] = None,
        pad_h: Optional[int] = None,
        pad_v: Optional[int] = None,
    ) -> None:
        if font_size is not None:
            self._font_size = int(font_size)
        if pad_h is not None:
            self._pad_h = int(pad_h)
        if pad_v is not None:
            self._pad_v = int(pad_v)
        self._refresh()

    def _refresh(self) -> None:
        if self.isChecked():
            if self._cond_style:
                self.setStyleSheet(
                    "QPushButton{{background:#f9e2af;color:#3a3218;border:1px solid #a87d3a;"
                    "border-radius:4px;padding:{}px {}px;font-weight:bold;font-size:{}px;}}".format(
                        self._pad_v, self._pad_h, self._font_size))
            else:
                self.setStyleSheet(
                    "QPushButton{{background:#89b4fa;color:#1e1e2e;border:none;"
                    "border-radius:4px;padding:{}px {}px;font-weight:bold;font-size:{}px;}}".format(
                        self._pad_v, self._pad_h, self._font_size))
        elif self._cond_style:
            self.setStyleSheet(
                "QPushButton{{background:#3a3218;color:#f9e2af;border:1px solid #a87d3a;"
                "border-radius:4px;padding:{}px {}px;font-size:{}px;}}".format(
                    self._pad_v, self._pad_h, self._font_size))
        else:
            self.setStyleSheet(
                "QPushButton{{background:#313244;color:#cdd6f4;border:1px solid #45475a;"
                "border-radius:4px;padding:{}px {}px;font-size:{}px;}}".format(
                    self._pad_v, self._pad_h, self._font_size))


class _RadioGroup(QWidget):
    """Row of mutually exclusive toggle buttons."""
    changed = pyqtSignal()

    def __init__(self, options: list[str], parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(3)
        self._btns: dict[str, _ToggleBtn] = {}
        self._value = "none"
        for lbl in options:
            btn = _ToggleBtn(lbl)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _, l=lbl: self._click(l))
            layout.addWidget(btn)
            self._btns[lbl] = btn
        layout.addStretch()

    def set_button_metrics(
        self,
        *,
        font_size: int = 14,
        height: int = 30,
        min_width: int = 62,
        pad_h: int = 8,
        pad_v: int = 3,
    ) -> None:
        for btn in self._btns.values():
            btn.set_metrics(font_size=font_size, pad_h=pad_h, pad_v=pad_v)
            btn.setFixedHeight(height)
            btn.setMinimumWidth(min_width)

    def _click(self, label: str) -> None:
        was = self._value
        for l, b in self._btns.items():
            b.blockSignals(True)
            b.setChecked(l == label and was != label)
            b.blockSignals(False)
            b._refresh()
        self._value = "none" if was == label else label
        self.changed.emit()

    def value(self) -> str:
        return self._value

    def set_value(self, val: str) -> None:
        self._value = val
        for l, b in self._btns.items():
            b.blockSignals(True)
            b.setChecked(l == val)
            b.blockSignals(False)
            b._refresh()


# ── Inline damage bar ─────────────────────────────────────────────────────

class _DmgBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(16)
        self._mn = 0.0
        self._mx = 0.0
        self._error_mode = False
        self._empty = True   # True = no data, draw blank

    def set_range(self, mn: float, mx: float) -> None:
        self._mn = max(0.0, mn)
        self._mx = min(200.0, mx)
        self._empty = False
        self.update()

    def set_empty(self) -> None:
        self._empty = True
        self._mn = self._mx = 0.0
        self.update()

    def set_error_mode(self, error: bool) -> None:
        self._error_mode = error
        self._empty = False
        self.update()

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        w, h = self.width(), self.height()
        if self._empty:
            p.fillRect(0, 0, w, h, QColor("#1e1e2e"))
            p.setPen(QColor("#45475a"))
            p.drawRect(0, 0, w - 1, h - 1)
            return
        if self._error_mode:
            p.fillRect(0, 0, w, h, QColor("#f38ba8"))
            p.setPen(QColor("#000000"))
            p.drawRect(0, 0, w - 1, h - 1)
            return
        mn = max(0.0, self._mn)
        mx = max(0.0, self._mx)
        mn_draw = min(100.0, mn)
        mx_draw = min(100.0, mx)

        # 残HPバーを先に描画（緑/黄/赤）。
        remaining_worst = max(0.0, 100.0 - mx_draw)
        hp_color = QColor(_hp_color(remaining_worst))
        p.fillRect(0, 0, w, h, hp_color)

        # 被ダメージは右側を黒系で塗る（保証分＋乱数幅）。
        if mx_draw <= 0:
            p.setPen(QColor("#000000"))
            p.drawRect(0, 0, w - 1, h - 1)
            return
        s = w / 100.0
        guaranteed_w = int(mn_draw * s)
        uncertain_w = int(max(0.0, mx_draw - mn_draw) * s)
        dmg_color = QColor("#101015")
        var_color = QColor(_bar_variation_color(mn, mx))
        var_color.setAlpha(235)

        if uncertain_w > 0:
            p.fillRect(
                max(0, w - guaranteed_w - uncertain_w),
                0,
                min(w, uncertain_w),
                h,
                QBrush(var_color),
            )
        if guaranteed_w > 0:
            p.fillRect(max(0, w - guaranteed_w), 0, min(w, guaranteed_w), h, QBrush(dmg_color))

        p.setPen(QColor("#000000"))
        p.drawRect(0, 0, w - 1, h - 1)


# ── One damage bar row (カスタム / HBD0 / HBD32) ────────────────────────

class _DmgRow(QWidget):
    def __init__(self, tag: str, color: str = "#45475a", parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(1)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        self._tag_lbl = QLabel(tag)
        self._tag_lbl.setFixedSize(52, 18)
        self._tag_lbl.setAlignment(Qt.AlignCenter)
        self._tag_lbl.setStyleSheet(
            "color:#1e1e2e;background:{};border-radius:3px;"
            "font-size:11px;font-weight:bold;".format(color)
        )
        top.addWidget(self._tag_lbl)

        self._bar = _DmgBar()
        top.addWidget(self._bar, 1)
        root.addLayout(top)

        bottom = QVBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(0)

        ko_row = QHBoxLayout()
        ko_row.setContentsMargins(0, 0, 0, 0)
        ko_row.setSpacing(6)
        spacer = QLabel("")
        spacer.setFixedWidth(52)
        ko_row.addWidget(spacer)
        self._ko_txt = QLabel("")
        self._ko_txt.setStyleSheet("font-size:14px;color:#f9e2af;font-weight:bold;")
        ko_row.addWidget(self._ko_txt)
        self._detail_txt = QLabel("---")
        self._detail_txt.setStyleSheet("font-size:14px;color:#cdd6f4;")
        ko_row.addWidget(self._detail_txt)
        ko_row.addStretch()
        bottom.addLayout(ko_row)

        root.addLayout(bottom)

    def set_damage(self, min_dmg: int, max_dmg: int, hp: int) -> None:
        self._bar.set_error_mode(False)
        if hp <= 0:
            self._detail_txt.setText("---")
            self._ko_txt.setText("")
            self._bar.set_range(0, 0)
            return
        mn_pct = _round1(min_dmg / hp * 100)
        mx_pct = _round1(max_dmg / hp * 100)
        self._bar.set_range(mn_pct, mx_pct)
        if max_dmg == 0:
            self._detail_txt.setText("0-0 (0.0~0.0%)")
            self._detail_txt.setStyleSheet("font-size:14px;color:#585b70;")
            self._ko_txt.setText("")
            return
        hits_str = _n_hit_ko(min_dmg, max_dmg, hp)
        self._detail_txt.setText("{}-{} ({:.1f}~{:.1f}%)".format(min_dmg, max_dmg, mn_pct, mx_pct))
        self._ko_txt.setText(hits_str)
        color = _bar_color(mn_pct, mx_pct)
        self._detail_txt.setStyleSheet("font-size:14px;color:{};".format(color))
        self._ko_txt.setStyleSheet("font-size:14px;color:{};font-weight:bold;".format(color))

    def set_no_damage(self, reason: str = "ダメージなし") -> None:
        self._bar.set_error_mode(False)
        if reason == "ダメージなし":
            self._detail_txt.setText("0-0 (0.0~0.0%)")
        else:
            self._detail_txt.setText(reason)
        self._detail_txt.setStyleSheet("font-size:14px;color:#585b70;")
        self._ko_txt.setText("")
        self._bar.set_range(0, 0)

    def set_error(self, reason: str = "計算エラー") -> None:
        self._bar.set_error_mode(True)
        self._detail_txt.setText(reason)
        self._detail_txt.setStyleSheet("font-size:14px;color:#f38ba8;font-weight:bold;")
        self._ko_txt.setText("")


# ── One move section ──────────────────────────────────────────────────────

class _MoveSection(QWidget):
    """Header + damage bars for a single move slot (self or opponent)."""
    move_change_requested = pyqtSignal(int)   # slot index

    # row_labels: (custom_label, bulk0_label, bulk32_label)
    _LEFT_LABELS  = ("使用率", "HBD 0", "HBD 32")
    _RIGHT_LABELS = ("使用率",   "AC 0",  "AC 32")

    def __init__(self, slot: int, right_side: bool = False, parent=None):
        super().__init__(parent)
        self._slot = slot
        self._right_side = right_side
        self._move: Optional[MoveInfo] = None
        self._last_move_name = ""
        self._details_visible = False
        self._has_extra_controls = False
        self._has_modifier_notes = False
        self._show_bulk_rows = True

        labels = self._RIGHT_LABELS if right_side else self._LEFT_LABELS

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(2)

        self._header_wrap = QFrame()
        self._header_wrap.setCursor(Qt.PointingHandCursor)
        self._header_wrap.setStyleSheet(
            "QFrame{background:transparent;border:1px solid transparent;border-radius:5px;}"
            "QFrame:hover{border-color:#45475a;}"
        )
        self._header_wrap.mousePressEvent = lambda _: self._toggle_detail_visibility()
        hdr = QHBoxLayout(self._header_wrap)
        hdr.setContentsMargins(4, 2, 4, 2)
        hdr.setSpacing(4)

        # タイプとカテゴリをグループ化
        type_cat_wrap = QWidget()
        type_cat_row = QHBoxLayout(type_cat_wrap)
        type_cat_row.setContentsMargins(0, 0, 0, 0)
        type_cat_row.setSpacing(4)
        self._type_lbl = QLabel("")
        self._type_lbl.setFixedWidth(48)
        self._type_lbl.setFixedHeight(22)
        self._type_lbl.setAlignment(Qt.AlignCenter)
        self._type_lbl.setStyleSheet(
            "border-radius:3px;color:white;font-size:11px;font-weight:bold;"
            "border:2px solid #45475a;"
        )
        self._type_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        type_cat_row.addWidget(self._type_lbl)

        self._cat_icon_lbl = QLabel("")
        self._cat_icon_lbl.setFixedSize(48, 22)
        self._cat_icon_lbl.setAlignment(Qt.AlignCenter)
        self._cat_icon_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        type_cat_row.addWidget(self._cat_icon_lbl)
        hdr.addWidget(type_cat_wrap)

        self._name_lbl = QLabel("（未設定）")
        self._name_lbl.setStyleSheet("font-weight:bold;font-size:15px;")
        self._name_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        hdr.addWidget(self._name_lbl, 1)

        self._expand_lbl = QLabel("▼")
        self._expand_lbl.setFixedWidth(14)
        self._expand_lbl.setAlignment(Qt.AlignCenter)
        self._expand_lbl.setStyleSheet("font-size:12px;color:#a6adc8;")
        self._expand_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        hdr.addWidget(self._expand_lbl)

        chg_btn = QPushButton("わざ変更")
        chg_btn.setFixedSize(60, 22)
        chg_btn.setStyleSheet(
            "QPushButton{background:#313244;border:1px solid #89b4fa;color:#89b4fa;"
            "font-weight:bold;border-radius:4px;font-size:12px;padding:0px;margin:0px;}"
            "QPushButton:hover{background:#3b3240;}"
        )
        chg_btn.clicked.connect(lambda: self.move_change_requested.emit(self._slot))
        hdr.addWidget(chg_btn, 0, Qt.AlignVCenter)
        layout.addWidget(self._header_wrap)

        # 詳細情報
        if True:
            self._stats_wrap = QWidget()
            stat_row = QHBoxLayout(self._stats_wrap)
            stat_row.setContentsMargins(5, 0, 0, 0)
            stat_row.setSpacing(6)
            self._pow_btn = QPushButton("威力")
            self._pow_btn.setFixedSize(40, 2)
            self._pow_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #D87C31;color:#D87C31;"
                "font-weight:bold;border-radius:4px;font-size:12px;padding:0px;margin:0px;}"
            )
            self._pow_btn.setAttribute(Qt.WA_TransparentForMouseEvents)
            stat_row.addWidget(self._pow_btn, 0, Qt.AlignVCenter)
            self._pow_lbl = QLabel("---")
            self._pow_lbl.setMinimumWidth(30)
            self._pow_lbl.setStyleSheet("font-size:14px;color:#cdd6f4;font-weight:bold;")
            self._pow_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            stat_row.addWidget(self._pow_lbl, 0, Qt.AlignVCenter)
            self._acc_btn = QPushButton("命中")
            self._acc_btn.setFixedSize(40, 22)
            self._acc_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #4ECDC4;color:#4ECDC4;"
                "font-weight:bold;border-radius:4px;font-size:12px;padding:0px;margin:0px;}"
            )
            self._acc_btn.setAttribute(Qt.WA_TransparentForMouseEvents)
            stat_row.addWidget(self._acc_btn, 0, Qt.AlignVCenter)
            self._acc_lbl = QLabel("---")
            self._acc_lbl.setMinimumWidth(30)
            self._acc_lbl.setStyleSheet("font-size:14px;color:#cdd6f4;font-weight:bold;")
            self._acc_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            stat_row.addWidget(self._acc_lbl, 0, Qt.AlignVCenter)
            self._eff_lbl = QLabel("")
            self._eff_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._eff_lbl.setWordWrap(True)
            self._eff_lbl.setStyleSheet("font-size:14px;color:#a6adc8;font-weight:bold;")
            stat_row.addWidget(self._eff_lbl, 1)
            layout.addWidget(self._stats_wrap, 0, Qt.AlignVCenter)

            self._extra_wrap = QWidget()
            extra = QVBoxLayout(self._extra_wrap)
            extra.setContentsMargins(58, 0, 0, 0)
            extra.setSpacing(2)
            pow_row = QHBoxLayout()
            pow_row.setContentsMargins(0, 0, 0, 0)
            pow_row.setSpacing(8)
            self._pow_opt_lbl = QLabel("威力設定:")
            self._pow_opt_lbl.setStyleSheet("font-size:13px;color:#a6adc8;")
            self._pow_opt_lbl.setFixedWidth(60)
            pow_row.addWidget(self._pow_opt_lbl)
            self._pow_combo = QComboBox()
            self._pow_combo.setFixedWidth(222)
            self._pow_combo.setFixedHeight(28)
            self._pow_combo.setVisible(False)
            pow_row.addWidget(self._pow_combo)
            pow_row.addStretch()
            extra.addLayout(pow_row)
            hit_row = QHBoxLayout()
            hit_row.setContentsMargins(0, 0, 0, 0)
            hit_row.setSpacing(8)
            self._hit_opt_lbl = QLabel("ヒット設定:")
            self._hit_opt_lbl.setStyleSheet("font-size:13px;color:#a6adc8;")
            self._hit_opt_lbl.setFixedWidth(60)
            hit_row.addWidget(self._hit_opt_lbl)
            self._hit_spin = QSpinBox()
            self._hit_spin.setRange(1, 10)
            self._hit_spin.setFixedWidth(150)
            self._hit_spin.setFixedHeight(28)
            self._hit_spin.setPrefix("ヒット ")
            self._hit_spin.setSuffix(" 回")
            self._hit_spin.setVisible(False)
            hit_row.addWidget(self._hit_spin)
            hit_row.addStretch()
            extra.addLayout(hit_row)
            self._extra_wrap.setVisible(False)
            layout.addWidget(self._extra_wrap)

            self._mod_lbl = QLabel("")
            self._mod_lbl.setWordWrap(True)
            self._mod_lbl.setStyleSheet("font-size:12px;color:#89b4fa;padding-left:58px;")
            self._mod_lbl.setVisible(False)
            layout.addWidget(self._mod_lbl)

        # ダメージ行
        self._row_custom = _DmgRow(labels[0], color="#89b4fa")
        self._row_hbd0   = _DmgRow(labels[1], color="#a6e3a1")
        self._row_hbd252 = _DmgRow(labels[2], color="#fab387")
        layout.addWidget(self._row_custom)
        layout.addWidget(self._row_hbd0)
        layout.addWidget(self._row_hbd252)

        self._status_note = QLabel("変化わざ")
        self._status_note.setStyleSheet("font-size:14px;color:#a6adc8;padding-left:64px;")
        self._status_note.setVisible(False)
        layout.addWidget(self._status_note)

        layout.addStretch()
        self._apply_detail_visibility()

    def set_bulk_rows_visible(self, visible: bool) -> None:
        self._show_bulk_rows = bool(visible)
        is_status = self._move is not None and self._move.category == "status"
        show = self._show_bulk_rows and not is_status
        self._row_hbd0.setVisible(show)
        self._row_hbd252.setVisible(show)

    def _toggle_detail_visibility(self) -> None:
        if self._move is None:
            return
        self._details_visible = not self._details_visible
        self._apply_detail_visibility()

    def _apply_detail_visibility(self) -> None:
        visible = self._details_visible and (self._move is not None)
        self._stats_wrap.setVisible(visible)
        self._extra_wrap.setVisible(visible and self._has_extra_controls)
        self._mod_lbl.setVisible(visible and self._has_modifier_notes)
        self._expand_lbl.setText("▲" if visible else "▼")

    def _set_power_options(self, options: list[tuple[str, object]], preferred_data: object) -> None:
        self._pow_combo.blockSignals(True)
        self._pow_combo.clear()
        selected_index = 0
        preferred_power = _power_option_value(preferred_data)
        exact_index = -1
        power_index = -1
        for index, (label, option_data) in enumerate(options):
            self._pow_combo.addItem(label, option_data)
            if preferred_data is not None and option_data == preferred_data and exact_index < 0:
                exact_index = index
            if preferred_power > 0 and _power_option_value(option_data) == preferred_power and power_index < 0:
                power_index = index
        if exact_index >= 0:
            selected_index = exact_index
        elif power_index >= 0:
            selected_index = power_index
        if self._pow_combo.count() > 0:
            self._pow_combo.setCurrentIndex(selected_index)
        self._pow_combo.blockSignals(False)

    def setup_move(self, move: Optional[MoveInfo]) -> None:
        prev_pow_data = self._pow_combo.currentData()
        prev_hit = self._hit_spin.value()
        prev_is_var = not self._pow_combo.isHidden()
        prev_is_multi = not self._hit_spin.isHidden()
        self._move = move
        if move is None:
            self._last_move_name = ""
            self._details_visible = False
            self._type_lbl.setText("")
            self._type_lbl.setStyleSheet("border-radius:3px;color:white;font-size:13px;font-weight:bold;border:2px solid #45475a;")
            self._name_lbl.setText("（未設定）")
            self._cat_icon_lbl.clear()
            self._pow_lbl.setText("---")
            self._acc_lbl.setText("---")
            self._eff_lbl.setText("")
            self._pow_combo.setVisible(False)
            self._pow_opt_lbl.setVisible(False)
            self._hit_spin.setVisible(False)
            self._hit_opt_lbl.setVisible(False)
            self._has_extra_controls = False
            self._has_modifier_notes = False
            self._status_note.setVisible(False)
            self._row_custom.setVisible(True)
            self._row_custom.set_no_damage("---")
            self._row_hbd0.setVisible(self._show_bulk_rows)
            self._row_hbd0.set_no_damage("---")
            self._row_hbd252.setVisible(self._show_bulk_rows)
            self._row_hbd252.set_no_damage("---")
            self._apply_detail_visibility()
            return

        from src.ui.ui_utils import type_pixmap as _type_pm
        _pm = _type_pm(move.type_name, 48, 22)
        if _pm:
            self._type_lbl.setPixmap(_pm)
            self._type_lbl.setText("")
            self._type_lbl.setStyleSheet("border-radius:3px;border:2px solid #45475a;")
        else:
            type_ja = TYPE_EN_TO_JA.get(move.type_name, move.type_name)
            color = TYPE_COLORS.get(move.type_name, "#888888")
            self._type_lbl.setPixmap(QPixmap())
            self._type_lbl.setText(type_ja)
            self._type_lbl.setStyleSheet(
                "background-color:{};border-radius:3px;color:white;"
                "font-size:11px;font-weight:bold;border:2px solid #45475a;".format(color))
        self._cat_icon_lbl.setPixmap(_category_icon(move.category, 66, 22))
        self._name_lbl.setText(move.name_ja)
        same_move = self._last_move_name == move.name_ja
        if not same_move:
            self._details_visible = False

        self._pow_lbl.setText(str(move.power) if move.power else "---")
        self._acc_lbl.setText(str(move.accuracy) if move.accuracy else "---")
        self._eff_lbl.setText("")
        self._has_modifier_notes = False
        self._status_note.setVisible(False)

        options = _variable_power_options(move)
        if options:
            default_data = options[0][1]
            next_data = prev_pow_data if (same_move and prev_is_var and prev_pow_data is not None) else default_data
            self._set_power_options(options, next_data)
            self._pow_combo.setVisible(True)
            self._pow_opt_lbl.setVisible(True)
            self._pow_lbl.setText(str(self.power_override()))
        else:
            self._pow_combo.setVisible(False)
            self._pow_opt_lbl.setVisible(False)

        if move.name_ja in MULTI_HIT_MOVES_JA:
            mn, mx, default = MULTI_HIT_MOVES_JA[move.name_ja]
            self._hit_spin.blockSignals(True)
            self._hit_spin.setRange(mn, mx)
            next_hit = prev_hit if (same_move and prev_is_multi) else default
            self._hit_spin.setValue(max(mn, min(mx, next_hit)))
            self._hit_spin.blockSignals(False)
            self._hit_spin.setVisible(True)
            self._hit_opt_lbl.setVisible(True)
        else:
            self._hit_spin.setVisible(False)
            self._hit_opt_lbl.setVisible(False)

        self._has_extra_controls = (not self._pow_combo.isHidden()) or (not self._hit_spin.isHidden())

        self._last_move_name = move.name_ja
        self._apply_detail_visibility()

    def _set_all_no_damage(self, reason: str) -> None:
        for row in (self._row_custom, self._row_hbd0, self._row_hbd252):
            row.set_no_damage(reason)

    def update_results(
        self,
        custom: tuple[int, int, int, bool] | None,
        bulk0: tuple[int, int, int, bool],
        bulk32: tuple[int, int, int, bool],
        show_bulk_rows: bool = True,
    ) -> None:
        """Each tuple is (min_dmg, max_dmg, defender_hp, is_error)."""
        self._show_bulk_rows = bool(show_bulk_rows)
        if self._move is None:
            self._set_all_no_damage("---")
            return
        if self._move.category == "status":
            self._status_note.setVisible(True)
            self._row_custom.setVisible(False)
            self._row_hbd0.setVisible(False)
            self._row_hbd252.setVisible(False)
            return
        self._status_note.setVisible(False)

        def _apply(row: _DmgRow, data: tuple[int, int, int, bool] | None, show: bool) -> None:
            if not show or data is None:
                row.setVisible(False)
                return
            row.setVisible(True)
            mn, mx, hp, is_error = data
            if is_error:
                row.set_error("計算エラー")
            else:
                row.set_damage(mn, mx, hp)

        _apply(self._row_custom, custom, custom is not None)
        _apply(self._row_hbd0, bulk0, self._show_bulk_rows)
        _apply(self._row_hbd252, bulk32, self._show_bulk_rows)

    def set_modifier_notes(self, notes: list[str]) -> None:
        if not notes:
            self._has_modifier_notes = False
            self._mod_lbl.setText("")
            self._apply_detail_visibility()
            return
        text = "補正:\n" + "\n".join(notes)
        self._mod_lbl.setText(text)
        self._has_modifier_notes = True
        self._apply_detail_visibility()

    def power_override(self) -> int:
        if self._pow_combo.isHidden():
            return 0
        return _power_option_value(self._pow_combo.currentData())

    def hit_count(self) -> int:
        return self._hit_spin.value() if not self._hit_spin.isHidden() else 1

    def set_effectiveness(self, mult: float) -> None:
        if mult <= 0:
            self._eff_lbl.setText("無効")
            self._eff_lbl.setStyleSheet("font-size:14px;color:#f38ba8;font-weight:bold;")
            return
        if mult > 1.0:
            self._eff_lbl.setText("抜群 x{:.1f}".format(mult))
            self._eff_lbl.setStyleSheet("font-size:14px;color:#f38ba8;font-weight:bold;")
            return
        if mult < 1.0:
            self._eff_lbl.setText("今ひとつ x{:.2g}".format(mult))
            self._eff_lbl.setStyleSheet("font-size:14px;color:#f9e2af;font-weight:bold;")
            return
        self._eff_lbl.setText("等倍")
        self._eff_lbl.setStyleSheet("font-size:14px;color:#a6adc8;font-weight:bold;")


# ── Attacker left panel ───────────────────────────────────────────────────

class _AttackerPanel(QWidget):
    """Left panel: attacker name, テラスタル, rank, EV slider."""
    changed = pyqtSignal()
    edit_requested = pyqtSignal()
    change_requested = pyqtSignal()
    new_requested = pyqtSignal()
    clear_requested = pyqtSignal()
    ev_section_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._base_pokemon: Optional[PokemonInstance] = None
        self._tera_visible = False
        self._actions_visible = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        ttl = QLabel("自分のポケモン")
        ttl.setStyleSheet("font-size:15px;font-weight:bold;color:#89b4fa;")
        layout.addWidget(ttl)

        self._name_lbl = QLabel("（未設定）")
        self._name_lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;background:#181825;border:1px solid #45475a;border-radius:4px;padding:4px;")
        layout.addWidget(self._name_lbl)

        self._tera_wrap = QWidget()
        tera_row = QHBoxLayout(self._tera_wrap)
        tera_row.setContentsMargins(0, 0, 0, 0)
        tera_row.setSpacing(4)
        self._tera_cb = QCheckBox("テラスタル")
        self._tera_cb.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;")
        self._tera_cb.toggled.connect(self._on_tera_changed)
        tera_row.addWidget(self._tera_cb)
        self._tera_combo = QComboBox()
        self._tera_combo.addItem("（タイプ未選択）", "")
        for en, ja in TYPE_EN_TO_JA.items():
            self._tera_combo.addItem(ja, en)
        self._tera_combo.setStyleSheet("QComboBox { font-size: 15px; min-height: 32px; max-height: 32px; padding: 0px; }")
        self._tera_combo.setFixedHeight(32)
        self._tera_combo.setEnabled(False)
        self._tera_combo.currentIndexChanged.connect(self._emit)
        tera_row.addWidget(self._tera_combo, 1)
        layout.addWidget(self._tera_wrap)
        self._tera_wrap.setVisible(False)

        # Rank modifiers: AC and BD separately
        def _make_rank_row(label_text: str, adj_cb):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(70)
            lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;")
            row.addWidget(lbl)
            d_btn = QPushButton("−")
            d_btn.setFixedSize(42, 32)
            d_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #f38ba8;color:#f38ba8;"
                "font-weight:bold;border-radius:4px;font-size:15px;padding:0px;margin:0px;"
                "min-height:32px;max-height:32px;}"
                "QPushButton:hover{background:#3b3240;}"
            )
            rank_lbl = QLabel(" 0")
            rank_lbl.setFixedSize(42, 32)
            rank_lbl.setAlignment(Qt.AlignCenter)
            rank_lbl.setStyleSheet(
                "font-weight:bold;font-size:15px;color:#cdd6f4;background:#181825;"
                "border:1px solid #45475a;border-radius:4px;padding:0px;margin:0px;"
                "min-height:32px;max-height:32px;"
            )
            u_btn = QPushButton("+")
            u_btn.setFixedSize(42, 32)
            u_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #a6e3a1;color:#a6e3a1;"
                "font-weight:bold;border-radius:4px;font-size:15px;padding:0px;margin:0px;"
                "min-height:32px;max-height:32px;}"
                "QPushButton:hover{background:#2f3c36;}"
            )
            d_btn.clicked.connect(lambda: adj_cb(-1))
            u_btn.clicked.connect(lambda: adj_cb(1))
            row.addWidget(d_btn)
            row.addWidget(rank_lbl)
            row.addWidget(u_btn)
            row.addStretch()
            return row, rank_lbl

        self._ac_rank = 0
        self._bd_rank = 0
        ac_row, self._ac_rank_lbl = _make_rank_row("ACランク:", self._adj_ac_rank)
        bd_row, self._bd_rank_lbl = _make_rank_row("BDランク:", self._adj_bd_rank)
        layout.addLayout(ac_row)
        layout.addLayout(bd_row)

        layout.addWidget(_sep())

        # EV slider collapsible section
        ev_toggle_row = QHBoxLayout()
        ev_toggle_row.setContentsMargins(0, 0, 0, 0)
        ev_toggle_row.setSpacing(4)
        self._ev_toggle_btn = QPushButton("▷ 努力値/性格")
        self._ev_toggle_btn.setCheckable(True)
        self._ev_toggle_btn.setChecked(False)
        self._ev_toggle_btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#89b4fa;"
            "font-size:15px;font-weight:bold;text-align:left;padding:0;}"
            "QPushButton:hover{color:#cdd6f4;}"
        )
        self._ev_toggle_btn.clicked.connect(lambda _: self._toggle_ev_section())
        ev_toggle_row.addWidget(self._ev_toggle_btn)
        ev_toggle_row.addStretch()
        layout.addLayout(ev_toggle_row)

        self._ev_section = QWidget()
        self._ev_section.setVisible(False)
        ev_section_layout = QVBoxLayout(self._ev_section)
        ev_section_layout.setContentsMargins(0, 2, 0, 2)
        ev_section_layout.setSpacing(3)

        # EV sliders for H, A, B, C, D, S
        for slider_attr, val_attr, lbl_attr, label_char in (
            ("_ev_slider_h", "_ev_val_lbl_h", "_stat_lbl_h", "H"),
            ("_ev_slider_a", "_ev_val_lbl_a", "_stat_lbl_a", "A"),
            ("_ev_slider_b", "_ev_val_lbl_b", "_stat_lbl_b", "B"),
            ("_ev_slider_c", "_ev_val_lbl_c", "_stat_lbl_c", "C"),
            ("_ev_slider_d", "_ev_val_lbl_d", "_stat_lbl_d", "D"),
            ("_ev_slider_s", "_ev_val_lbl_s", "_stat_lbl_s", "S"),
        ):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)
            stat_lbl = QLabel("{}(---)".format(label_char))
            stat_lbl.setFixedWidth(50)
            stat_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            stat_lbl.setStyleSheet("font-size:16px;font-weight:bold;color:#cdd6f4;")
            setattr(self, lbl_attr, stat_lbl)
            row.addWidget(stat_lbl)
            minus_btn = QPushButton("\u2212")
            minus_btn.setFixedSize(28, 28)
            minus_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #f38ba8;color:#f38ba8;"
                "font-weight:bold;border-radius:3px;font-size:16px;padding:0;}"
                "QPushButton:hover{background:#3b3240;}"
            )
            row.addWidget(minus_btn)
            row.addStretch()
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 32)
            slider.setValue(0)
            slider.setFixedHeight(28)
            slider.valueChanged.connect(self._emit)
            setattr(self, slider_attr, slider)
            minus_btn.clicked.connect(lambda _, s=slider: s.setValue(max(0, s.value() - 1)))
            plus_btn = QPushButton("+")
            plus_btn.setFixedSize(28, 28)
            plus_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #a6e3a1;color:#a6e3a1;"
                "font-weight:bold;border-radius:3px;font-size:16px;padding:0;}"
                "QPushButton:hover{background:#2f3c36;}"
            )
            plus_btn.clicked.connect(lambda _, s=slider: s.setValue(min(32, s.value() + 1)))
            val_lbl = QLabel("0")
            val_lbl.setFixedWidth(15)
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_lbl.setStyleSheet("font-size:13px;color:#a6adc8;")
            setattr(self, val_attr, val_lbl)
            row.addWidget(slider, 1)
            row.addStretch()
            row.addWidget(plus_btn)
            row.addWidget(val_lbl)
            ev_section_layout.addLayout(row)
            slider.valueChanged.connect(val_lbl.setNum)

        # Nature button (inside collapsible section)
        nat_row = QHBoxLayout()
        nat_row.setContentsMargins(0, 4, 0, 0)
        nat_row.setSpacing(4)
        nat_lbl = QLabel("性格")
        nat_lbl.setFixedWidth(50)
        nat_lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;")
        nat_row.addWidget(nat_lbl)
        self._nat_btn = QPushButton("がんばりや（補正なし）")
        self._nat_btn.setFixedHeight(32)
        self._nat_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._nat_btn.setStyleSheet(
            "QPushButton{font-size:15px;text-align:left;padding:0 6px;"
            "background:#313244;border:1px solid #45475a;border-radius:4px;}"
            "QPushButton:hover{border-color:#89b4fa;}"
        )
        self._nat_btn.clicked.connect(self._open_nature_dialog)
        nat_row.addWidget(self._nat_btn, 1)
        self._panel_nature: str = "がんばりや"
        ev_section_layout.addLayout(nat_row)

        layout.addWidget(self._ev_section)

    def _toggle_ev_section(self, from_sync: bool = False) -> None:
        visible = self._ev_toggle_btn.isChecked()
        self._ev_section.setVisible(visible)
        self._ev_toggle_btn.setText("▽ 努力値/性格" if visible else "▷ 努力値/性格")
        if not from_sync:
            self.ev_section_toggled.emit(visible)

    def sync_ev_section(self, visible: bool) -> None:
        self._ev_toggle_btn.blockSignals(True)
        self._ev_toggle_btn.setChecked(visible)
        self._ev_toggle_btn.blockSignals(False)
        self._ev_section.setVisible(visible)
        self._ev_toggle_btn.setText("▽ 努力値/性格" if visible else "▷ 努力値/性格")

    # ── Public ──────────────────────────────────────────────────────────

    def set_pokemon(self, p: Optional[PokemonInstance]) -> None:
        if p is None:
            self._base_pokemon = None
            self._name_lbl.setText("（未設定）")
            for _s in (self._ev_slider_h, self._ev_slider_a, self._ev_slider_b,
                        self._ev_slider_c, self._ev_slider_d, self._ev_slider_s):
                _s.blockSignals(True)
                _s.setValue(0)
                _s.blockSignals(False)
            self._sync_ev_val_lbls()
            self._set_panel_nature("まじめ", emit=False)
            self._ac_rank = 0
            self._bd_rank = 0
            self._ac_rank_lbl.setText(" 0")
            self._bd_rank_lbl.setText(" 0")
            self._tera_cb.blockSignals(True)
            self._tera_cb.setChecked(False)
            self._tera_cb.blockSignals(False)
            self._tera_combo.blockSignals(True)
            self._tera_combo.setCurrentIndex(0)
            self._tera_combo.blockSignals(False)
            self._tera_combo.setEnabled(False)
            for lbl_attr, ch in (
                ("_stat_lbl_h", "H"), ("_stat_lbl_a", "A"), ("_stat_lbl_b", "B"),
                ("_stat_lbl_c", "C"), ("_stat_lbl_d", "D"), ("_stat_lbl_s", "S"),
            ):
                getattr(self, lbl_attr).setText("{}(---)".format(ch))
            return
        self._base_pokemon = copy.deepcopy(p)
        self._name_lbl.setText(_FORM_CANONICAL_NAME.get(p.name_ja or "", p.name_ja or "---"))
        ev_map = [
            (self._ev_slider_h, max(0, int((p.ev_hp or 0) / 8))),
            (self._ev_slider_a, max(0, int((p.ev_attack or 0) / 8))),
            (self._ev_slider_b, max(0, int((p.ev_defense or 0) / 8))),
            (self._ev_slider_c, max(0, int((p.ev_sp_attack or 0) / 8))),
            (self._ev_slider_d, max(0, int((p.ev_sp_defense or 0) / 8))),
            (self._ev_slider_s, max(0, int((p.ev_speed or 0) / 8))),
        ]
        for _s, _v in ev_map:
            _s.blockSignals(True)
            _s.setValue(_v)
            _s.blockSignals(False)
        self._sync_ev_val_lbls()
        self._set_panel_nature(p.nature or "まじめ", emit=False)
        self._ac_rank = 0
        self._bd_rank = 0
        self._ac_rank_lbl.setText(" 0")
        self._bd_rank_lbl.setText(" 0")
        tera = p.terastal_type or ""
        enable_tera = bool(tera) and self._tera_visible
        self._tera_cb.blockSignals(True)
        self._tera_cb.setChecked(enable_tera)
        self._tera_cb.blockSignals(False)
        self._tera_combo.blockSignals(True)
        self._tera_combo.setCurrentIndex(0)
        self._tera_combo.blockSignals(False)
        self._tera_combo.setEnabled(enable_tera)
        self._update_stat_display(p)

    def update_stat_display(self, p: Optional[PokemonInstance]) -> None:
        if p:
            self._update_stat_display(p)

    def terastal_type(self) -> str:
        if not self._tera_visible:
            return ""
        if not self._tera_cb.isChecked():
            return ""
        return self._tera_combo.currentData() or ""

    def panel_nature(self) -> str:
        return self._panel_nature

    def nat_mult(self, stat_key: str = "attack") -> float:
        return _nature_mult_from_name(self._panel_nature, stat_key)

    def ac_rank(self) -> int:
        return self._ac_rank

    def bd_rank(self) -> int:
        return self._bd_rank

    def rank(self) -> int:
        return self._ac_rank

    def ev_hp_pts(self) -> int:
        return self._ev_slider_h.value()

    def ev_attack_pts(self) -> int:
        return self._ev_slider_a.value()

    def ev_defense_pts(self) -> int:
        return self._ev_slider_b.value()

    def ev_sp_attack_pts(self) -> int:
        return self._ev_slider_c.value()

    def ev_sp_defense_pts(self) -> int:
        return self._ev_slider_d.value()

    def ev_speed_pts(self) -> int:
        return self._ev_slider_s.value()

    def ev_points(self) -> int:
        """後方互換: A/C の大きい方を返す"""
        return max(self._ev_slider_a.value(), self._ev_slider_c.value())

    def use_sp_attack(self) -> bool:
        """後方互換: C >= A のとき True"""
        return self._ev_slider_c.value() >= self._ev_slider_a.value()

    def set_tera_visible(self, visible: bool) -> None:
        self._tera_visible = bool(visible)
        self._tera_wrap.setVisible(self._tera_visible)
        if not self._tera_visible:
            self._tera_cb.blockSignals(True)
            self._tera_cb.setChecked(False)
            self._tera_cb.blockSignals(False)
            self._tera_combo.blockSignals(True)
            self._tera_combo.setCurrentIndex(0)
            self._tera_combo.blockSignals(False)
            self._tera_combo.setEnabled(False)
            self._emit()

    # ── Private ─────────────────────────────────────────────────────────

    def _update_stat_display(self, p: PokemonInstance) -> None:
        self._stat_lbl_h.setText("H({})".format(p.hp or p.max_hp or "--"))
        if p.ability in ("ちからもち", "ヨガパワー", "Huge Power", "Pure Power"):
            self._stat_lbl_a.setText("A({}×2)".format(p.attack))
        else:
            self._stat_lbl_a.setText("A({})".format(p.attack))
        self._stat_lbl_b.setText("B({})".format(p.defense))
        self._stat_lbl_c.setText("C({})".format(p.sp_attack))
        self._stat_lbl_d.setText("D({})".format(p.sp_defense))
        self._stat_lbl_s.setText("S({})".format(p.speed))

    def _toggle_actions(self) -> None:
        self._actions_visible = not self._actions_visible
        self._action_row_wrap.setVisible(self._actions_visible)

    def _on_tera_changed(self, checked: bool) -> None:
        self._tera_combo.setEnabled(checked)
        self._emit()

    def reset_to_base(self) -> None:
        p = self._base_pokemon
        if p is None:
            return
        ev_map = [
            (self._ev_slider_h, max(0, int((p.ev_hp or 0) / 8))),
            (self._ev_slider_a, max(0, int((p.ev_attack or 0) / 8))),
            (self._ev_slider_b, max(0, int((p.ev_defense or 0) / 8))),
            (self._ev_slider_c, max(0, int((p.ev_sp_attack or 0) / 8))),
            (self._ev_slider_d, max(0, int((p.ev_sp_defense or 0) / 8))),
            (self._ev_slider_s, max(0, int((p.ev_speed or 0) / 8))),
        ]
        for _s, _v in ev_map:
            _s.blockSignals(True)
            _s.setValue(_v)
            _s.blockSignals(False)
        self._sync_ev_val_lbls()
        self._set_panel_nature(p.nature or "まじめ", emit=False)
        self._ac_rank = 0
        self._bd_rank = 0
        self._ac_rank_lbl.setText(" 0")
        self._bd_rank_lbl.setText(" 0")
        tera = p.terastal_type or ""
        enable_tera = bool(tera) and self._tera_visible
        self._tera_cb.blockSignals(True)
        self._tera_cb.setChecked(enable_tera)
        self._tera_cb.blockSignals(False)
        idx = self._tera_combo.findData(tera)
        if idx < 0:
            idx = 0
        self._tera_combo.blockSignals(True)
        self._tera_combo.setCurrentIndex(idx)
        self._tera_combo.blockSignals(False)
        self._tera_combo.setEnabled(enable_tera)
        self._update_stat_display(p)
        self._emit()

    def _sync_ev_val_lbls(self) -> None:
        for slider_attr, val_attr in (
            ("_ev_slider_h", "_ev_val_lbl_h"),
            ("_ev_slider_a", "_ev_val_lbl_a"),
            ("_ev_slider_b", "_ev_val_lbl_b"),
            ("_ev_slider_c", "_ev_val_lbl_c"),
            ("_ev_slider_d", "_ev_val_lbl_d"),
            ("_ev_slider_s", "_ev_val_lbl_s"),
        ):
            getattr(self, val_attr).setText(str(getattr(self, slider_attr).value()))

    def _set_panel_nature(self, nature: str, emit: bool = True) -> None:
        from src.constants import NATURES_JA
        nature = nature if nature in NATURES_JA else "まじめ"
        self._panel_nature = nature
        boost, reduce = NATURES_JA.get(nature, (None, None))
        if boost and reduce:
            from src.ui.pokemon_edit_dialog import _STAT_LABELS
            text = "{}  (↑{} / ↓{})".format(
                nature,
                _STAT_LABELS.get(boost, boost),
                _STAT_LABELS.get(reduce, reduce),
            )
        else:
            text = "{}（補正なし）".format(nature)
        self._nat_btn.setText(text)
        if emit:
            self._emit()

    def _open_nature_dialog(self) -> None:
        from src.ui.pokemon_edit_dialog import NatureSelectDialog
        from src.data import database as db
        usage_name = (self._base_pokemon.usage_name or self._base_pokemon.name_ja) if self._base_pokemon else ""
        ranked = db.get_natures_by_usage(usage_name)[:4] if usage_name else []
        dlg = NatureSelectDialog(self._panel_nature, ranked_natures=ranked, parent=self)
        if dlg.exec_():
            self._set_panel_nature(dlg.selected_nature())

    def _adj_ac_rank(self, delta: int) -> None:
        self._ac_rank = max(-6, min(6, self._ac_rank + delta))
        self._ac_rank_lbl.setText("{:+d}".format(self._ac_rank) if self._ac_rank != 0 else " 0")
        self._emit()

    def _adj_bd_rank(self, delta: int) -> None:
        self._bd_rank = max(-6, min(6, self._bd_rank + delta))
        self._bd_rank_lbl.setText("{:+d}".format(self._bd_rank) if self._bd_rank != 0 else " 0")
        self._emit()

    def _emit(self) -> None:
        self.changed.emit()


class _DefenderPanel(QWidget):
    """Left panel: defender quick edit / register select / HP% / rank."""
    changed = pyqtSignal()
    edit_requested = pyqtSignal()
    change_requested = pyqtSignal()
    new_requested = pyqtSignal()
    clear_requested = pyqtSignal()
    ev_section_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._ac_rank = 0
        self._bd_rank = 0
        self._base_pokemon: Optional[PokemonInstance] = None
        self._current_key = ""
        self._tera_visible = False
        self._actions_visible = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        ttl = QLabel("相手のポケモン")
        ttl.setStyleSheet("font-size:15px;font-weight:bold;color:#89b4fa;")
        layout.addWidget(ttl)

        self._name_lbl = QLabel("（未設定）")
        self._name_lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;background:#181825;border:1px solid #45475a;border-radius:4px;padding:4px;")
        layout.addWidget(self._name_lbl)

        self._tera_wrap = QWidget()
        tera_row = QHBoxLayout(self._tera_wrap)
        tera_row.setContentsMargins(0, 0, 0, 0)
        tera_row.setSpacing(4)
        self._tera_cb = QCheckBox("テラスタル")
        self._tera_cb.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;")
        self._tera_cb.toggled.connect(self._on_tera_changed)
        tera_row.addWidget(self._tera_cb)
        self._tera_combo = QComboBox()
        self._tera_combo.addItem("（タイプ未選択）", "")
        for en, ja in TYPE_EN_TO_JA.items():
            self._tera_combo.addItem(ja, en)
        self._tera_combo.setStyleSheet("QComboBox { font-size: 15px; min-height: 32px; max-height: 32px; padding: 0px; }")
        self._tera_combo.setFixedHeight(32)
        self._tera_combo.setEnabled(False)
        self._tera_combo.currentIndexChanged.connect(self._emit)
        tera_row.addWidget(self._tera_combo, 1)
        layout.addWidget(self._tera_wrap)
        self._tera_wrap.setVisible(False)

        def _make_rank_row(label_text: str, adj_cb):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(70)
            lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;")
            row.addWidget(lbl)
            d_btn = QPushButton("−")
            d_btn.setFixedSize(42, 32)
            d_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #f38ba8;color:#f38ba8;"
                "font-weight:bold;border-radius:4px;font-size:15px;padding:0px;margin:0px;"
                "min-height:32px;max-height:32px;}"
                "QPushButton:hover{background:#3b3240;}"
            )
            rank_lbl = QLabel(" 0")
            rank_lbl.setFixedSize(42, 32)
            rank_lbl.setAlignment(Qt.AlignCenter)
            rank_lbl.setStyleSheet(
                "font-weight:bold;font-size:15px;color:#cdd6f4;background:#181825;"
                "border:1px solid #45475a;border-radius:4px;padding:0px;margin:0px;"
                "min-height:32px;max-height:32px;"
            )
            u_btn = QPushButton("+")
            u_btn.setFixedSize(42, 32)
            u_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #a6e3a1;color:#a6e3a1;"
                "font-weight:bold;border-radius:4px;font-size:15px;padding:0px;margin:0px;"
                "min-height:32px;max-height:32px;}"
                "QPushButton:hover{background:#2f3c36;}"
            )
            d_btn.clicked.connect(lambda: adj_cb(-1))
            u_btn.clicked.connect(lambda: adj_cb(1))
            row.addWidget(d_btn)
            row.addWidget(rank_lbl)
            row.addWidget(u_btn)
            row.addStretch()
            return row, rank_lbl

        self._ac_rank = 0
        self._bd_rank = 0
        ac_row, self._ac_rank_lbl = _make_rank_row("ACランク:", self._adj_ac_rank)
        bd_row, self._bd_rank_lbl = _make_rank_row("BDランク:", self._adj_bd_rank)
        layout.addLayout(ac_row)
        layout.addLayout(bd_row)
        layout.addWidget(_sep())

        # EV slider collapsible section
        ev_toggle_row = QHBoxLayout()
        ev_toggle_row.setContentsMargins(0, 0, 0, 0)
        ev_toggle_row.setSpacing(4)
        self._ev_toggle_btn = QPushButton("▷ 努力値/性格")
        self._ev_toggle_btn.setCheckable(True)
        self._ev_toggle_btn.setChecked(False)
        self._ev_toggle_btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#89b4fa;"
            "font-size:15px;font-weight:bold;text-align:left;padding:0;}"
            "QPushButton:hover{color:#cdd6f4;}"
        )
        self._ev_toggle_btn.clicked.connect(lambda _: self._toggle_ev_section())
        ev_toggle_row.addWidget(self._ev_toggle_btn)
        ev_toggle_row.addStretch()
        layout.addLayout(ev_toggle_row)

        self._ev_section = QWidget()
        self._ev_section.setVisible(False)
        ev_section_layout = QVBoxLayout(self._ev_section)
        ev_section_layout.setContentsMargins(0, 2, 0, 2)
        ev_section_layout.setSpacing(3)

        # EV sliders for H, A, B, C, D, S
        for slider_attr, val_attr, lbl_attr, label_char in (
            ("_ev_slider_h", "_ev_val_lbl_h", "_stat_lbl_h", "H"),
            ("_ev_slider_a", "_ev_val_lbl_a", "_stat_lbl_a", "A"),
            ("_ev_slider_b", "_ev_val_lbl_b", "_stat_lbl_b", "B"),
            ("_ev_slider_c", "_ev_val_lbl_c", "_stat_lbl_c", "C"),
            ("_ev_slider_d", "_ev_val_lbl_d", "_stat_lbl_d", "D"),
            ("_ev_slider_s", "_ev_val_lbl_s", "_stat_lbl_s", "S"),
        ):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)
            stat_lbl = QLabel("{}(---)".format(label_char))
            stat_lbl.setFixedWidth(50)
            stat_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            stat_lbl.setStyleSheet("font-size:16px;font-weight:bold;color:#cdd6f4;")
            setattr(self, lbl_attr, stat_lbl)
            row.addWidget(stat_lbl)
            minus_btn = QPushButton("\u2212")
            minus_btn.setFixedSize(28, 28)
            minus_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #f38ba8;color:#f38ba8;"
                "font-weight:bold;border-radius:3px;font-size:16px;padding:0;}"
                "QPushButton:hover{background:#3b3240;}"
            )
            row.addWidget(minus_btn)
            row.addStretch()
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 32)
            slider.setValue(0)
            slider.setFixedHeight(28)
            slider.valueChanged.connect(self._emit)
            setattr(self, slider_attr, slider)
            minus_btn.clicked.connect(lambda _, s=slider: s.setValue(max(0, s.value() - 1)))
            plus_btn = QPushButton("+")
            plus_btn.setFixedSize(28, 28)
            plus_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #a6e3a1;color:#a6e3a1;"
                "font-weight:bold;border-radius:3px;font-size:16px;padding:0;}"
                "QPushButton:hover{background:#2f3c36;}"
            )
            plus_btn.clicked.connect(lambda _, s=slider: s.setValue(min(32, s.value() + 1)))
            val_lbl = QLabel("0")
            val_lbl.setFixedWidth(15)
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_lbl.setStyleSheet("font-size:13px;color:#a6adc8;")
            setattr(self, val_attr, val_lbl)
            row.addWidget(slider, 1)
            row.addStretch()
            row.addWidget(plus_btn)
            row.addWidget(val_lbl)
            ev_section_layout.addLayout(row)
            slider.valueChanged.connect(val_lbl.setNum)

        # Nature button (inside collapsible section)
        nat_row = QHBoxLayout()
        nat_row.setContentsMargins(0, 4, 0, 0)
        nat_row.setSpacing(4)
        nat_lbl = QLabel("性格")
        nat_lbl.setFixedWidth(50)
        nat_lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;")
        nat_row.addWidget(nat_lbl)
        self._nat_btn = QPushButton("がんばりや（補正なし）")
        self._nat_btn.setFixedHeight(32)
        self._nat_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._nat_btn.setStyleSheet(
            "QPushButton{font-size:15px;text-align:left;padding:0 6px;"
            "background:#313244;border:1px solid #45475a;border-radius:4px;}"
            "QPushButton:hover{border-color:#89b4fa;}"
        )
        self._nat_btn.clicked.connect(self._open_nature_dialog)
        nat_row.addWidget(self._nat_btn, 1)
        self._panel_nature: str = "がんばりや"
        ev_section_layout.addLayout(nat_row)

        layout.addWidget(self._ev_section)

        self._disguise_cb = QCheckBox("ばけのかわ有効")
        self._disguise_cb.setVisible(False)
        self._disguise_cb.toggled.connect(self._emit)
        layout.addWidget(self._disguise_cb)

        self._hp_pct_spin = QSpinBox()
        self._hp_pct_spin.setRange(1, 100)
        self._hp_pct_spin.setValue(100)
        self._hp_pct_spin.setSuffix("%")
        self._hp_pct_spin.setVisible(False)
        self._hp_pct_spin.valueChanged.connect(self._emit)
        layout.addWidget(self._hp_pct_spin)
        self._ability_lbl = QLabel("")
        self._ability_lbl.setVisible(False)
        layout.addWidget(self._ability_lbl)

    def set_pokemon(self, p: Optional[PokemonInstance]) -> None:
        if p is None:
            self._base_pokemon = None
            self._name_lbl.setText("（未設定）")
            self._ability_lbl.setText("")
            self._hp_pct_spin.blockSignals(True)
            self._hp_pct_spin.setValue(100)
            self._hp_pct_spin.blockSignals(False)
            self._tera_cb.blockSignals(True)
            self._tera_cb.setChecked(False)
            self._tera_cb.blockSignals(False)
            self._tera_combo.blockSignals(True)
            self._tera_combo.setCurrentIndex(0)
            self._tera_combo.blockSignals(False)
            self._tera_combo.setEnabled(False)
            self._set_panel_nature("まじめ", emit=False)
            for _s in (self._ev_slider_h, self._ev_slider_a, self._ev_slider_b,
                        self._ev_slider_c, self._ev_slider_d, self._ev_slider_s):
                _s.blockSignals(True)
                _s.setValue(0)
                _s.blockSignals(False)
            self._sync_ev_val_lbls()
            self._ac_rank = 0
            self._bd_rank = 0
            self._ac_rank_lbl.setText(" 0")
            self._bd_rank_lbl.setText(" 0")
            self._disguise_cb.setVisible(False)
            self._disguise_cb.blockSignals(True)
            self._disguise_cb.setChecked(False)
            self._disguise_cb.blockSignals(False)
            for lbl_attr, ch in (
                ("_stat_lbl_h", "H"), ("_stat_lbl_a", "A"), ("_stat_lbl_b", "B"),
                ("_stat_lbl_c", "C"), ("_stat_lbl_d", "D"), ("_stat_lbl_s", "S"),
            ):
                getattr(self, lbl_attr).setText("{}(---)".format(ch))
            self._current_key = ""
            return

        self._base_pokemon = copy.deepcopy(p)
        self._name_lbl.setText(_FORM_CANONICAL_NAME.get(p.name_ja or "", p.name_ja or "---"))
        self._ability_lbl.setText("特性: {}".format(p.ability or "---"))
        key = "{}|{}|{}|{}|{}|{}|{}|{}|{}".format(
            p.species_id, p.name_ja or "", p.ability or "",
            p.ev_hp, p.ev_attack, p.ev_defense,
            p.ev_sp_attack, p.ev_sp_defense, p.ev_speed,
        )
        if self._current_key != key:
            pct = 100
            max_hp = p.max_hp or p.hp
            if p.current_hp > 0 and max_hp > 0:
                pct = int(round(max(1.0, min(100.0, p.current_hp / max_hp * 100.0))))
            elif p.current_hp_percent > 0:
                pct = int(round(max(1.0, min(100.0, p.current_hp_percent))))
            self._hp_pct_spin.blockSignals(True)
            self._hp_pct_spin.setValue(pct)
            self._hp_pct_spin.blockSignals(False)
            self._ac_rank = 0
            self._bd_rank = 0
            self._ac_rank_lbl.setText(" 0")
            self._bd_rank_lbl.setText(" 0")

            ev_map = [
                (self._ev_slider_h, max(0, int((p.ev_hp or 0) / 8))),
                (self._ev_slider_a, max(0, int((p.ev_attack or 0) / 8))),
                (self._ev_slider_b, max(0, int((p.ev_defense or 0) / 8))),
                (self._ev_slider_c, max(0, int((p.ev_sp_attack or 0) / 8))),
                (self._ev_slider_d, max(0, int((p.ev_sp_defense or 0) / 8))),
                (self._ev_slider_s, max(0, int((p.ev_speed or 0) / 8))),
            ]
            for _s, _v in ev_map:
                _s.blockSignals(True)
                _s.setValue(_v)
                _s.blockSignals(False)
            self._sync_ev_val_lbls()
            self._set_panel_nature(p.nature or "まじめ", emit=False)

            tera = p.terastal_type or ""
            enable_tera = bool(tera) and self._tera_visible
            self._tera_cb.blockSignals(True)
            self._tera_cb.setChecked(enable_tera)
            self._tera_cb.blockSignals(False)
            idx = self._tera_combo.findData(tera)
            if idx < 0:
                idx = 0
            self._tera_combo.blockSignals(True)
            self._tera_combo.setCurrentIndex(idx)
            self._tera_combo.blockSignals(False)
            self._tera_combo.setEnabled(enable_tera)

            self._disguise_cb.blockSignals(True)
            self._disguise_cb.setChecked(False)
            self._disguise_cb.blockSignals(False)
            self._current_key = key

        self._disguise_cb.setVisible(p.ability == "ばけのかわ")
        self._update_stat_display(p)

    def rank(self) -> int:
        return self._ac_rank

    def ac_rank(self) -> int:
        return self._ac_rank

    def bd_rank(self) -> int:
        return self._bd_rank

    def panel_nature(self) -> str:
        return self._panel_nature

    def nat_mult(self, stat_key: str = "defense") -> float:
        return _nature_mult_from_name(self._panel_nature, stat_key)

    def current_hp_percent(self) -> int:
        return self._hp_pct_spin.value()

    def terastal_type(self) -> str:
        if not self._tera_visible:
            return ""
        if not self._tera_cb.isChecked():
            return ""
        return self._tera_combo.currentData() or ""

    def ev_hp_pts(self) -> int:
        return self._ev_slider_h.value()

    def ev_attack_pts(self) -> int:
        return self._ev_slider_a.value()

    def ev_defense_pts(self) -> int:
        return self._ev_slider_b.value()

    def ev_sp_attack_pts(self) -> int:
        return self._ev_slider_c.value()

    def ev_sp_defense_pts(self) -> int:
        return self._ev_slider_d.value()

    def ev_speed_pts(self) -> int:
        return self._ev_slider_s.value()

    def ev_points(self) -> int:
        """後方互換: B/D の大きい方を返す"""
        return max(self._ev_slider_b.value(), self._ev_slider_d.value())

    def use_sp_defense(self) -> bool:
        """後方互換: D >= B のとき True"""
        return self._ev_slider_d.value() >= self._ev_slider_b.value()

    def set_tera_visible(self, visible: bool) -> None:
        self._tera_visible = bool(visible)
        self._tera_wrap.setVisible(self._tera_visible)
        if not self._tera_visible:
            self._tera_cb.blockSignals(True)
            self._tera_cb.setChecked(False)
            self._tera_cb.blockSignals(False)
            self._tera_combo.blockSignals(True)
            self._tera_combo.setCurrentIndex(0)
            self._tera_combo.blockSignals(False)
            self._tera_combo.setEnabled(False)
            self._emit()

    def disguise_intact(self) -> bool:
        return (not self._disguise_cb.isHidden()) and self._disguise_cb.isChecked()

    def update_stat_display(self, p: Optional[PokemonInstance]) -> None:
        if p:
            self._update_stat_display(p)

    def _toggle_ev_section(self, from_sync: bool = False) -> None:
        visible = self._ev_toggle_btn.isChecked()
        self._ev_section.setVisible(visible)
        self._ev_toggle_btn.setText("▽ 努力値/性格" if visible else "▷ 努力値/性格")
        if not from_sync:
            self.ev_section_toggled.emit(visible)

    def sync_ev_section(self, visible: bool) -> None:
        self._ev_toggle_btn.blockSignals(True)
        self._ev_toggle_btn.setChecked(visible)
        self._ev_toggle_btn.blockSignals(False)
        self._ev_section.setVisible(visible)
        self._ev_toggle_btn.setText("▽ 努力値/性格" if visible else "▷ 努力値/性格")

    def _sync_ev_val_lbls(self) -> None:
        for slider_attr, val_attr in (
            ("_ev_slider_h", "_ev_val_lbl_h"),
            ("_ev_slider_a", "_ev_val_lbl_a"),
            ("_ev_slider_b", "_ev_val_lbl_b"),
            ("_ev_slider_c", "_ev_val_lbl_c"),
            ("_ev_slider_d", "_ev_val_lbl_d"),
            ("_ev_slider_s", "_ev_val_lbl_s"),
        ):
            getattr(self, val_attr).setText(str(getattr(self, slider_attr).value()))

    def reset_to_base(self) -> None:
        p = self._base_pokemon
        if p is None:
            return
        pct = 100
        max_hp = p.max_hp or p.hp
        if p.current_hp > 0 and max_hp > 0:
            pct = int(round(max(1.0, min(100.0, p.current_hp / max_hp * 100.0))))
        elif p.current_hp_percent > 0:
            pct = int(round(max(1.0, min(100.0, p.current_hp_percent))))
        self._hp_pct_spin.blockSignals(True)
        self._hp_pct_spin.setValue(pct)
        self._hp_pct_spin.blockSignals(False)
        self._ac_rank = 0
        self._bd_rank = 0
        self._ac_rank_lbl.setText(" 0")
        self._bd_rank_lbl.setText(" 0")
        ev_map = [
            (self._ev_slider_h, max(0, int((p.ev_hp or 0) / 8))),
            (self._ev_slider_a, max(0, int((p.ev_attack or 0) / 8))),
            (self._ev_slider_b, max(0, int((p.ev_defense or 0) / 8))),
            (self._ev_slider_c, max(0, int((p.ev_sp_attack or 0) / 8))),
            (self._ev_slider_d, max(0, int((p.ev_sp_defense or 0) / 8))),
            (self._ev_slider_s, max(0, int((p.ev_speed or 0) / 8))),
        ]
        for _s, _v in ev_map:
            _s.blockSignals(True)
            _s.setValue(_v)
            _s.blockSignals(False)
        self._sync_ev_val_lbls()
        self._set_panel_nature(p.nature or "まじめ", emit=False)
        tera = p.terastal_type or ""
        enable_tera = bool(tera) and self._tera_visible
        self._tera_cb.blockSignals(True)
        self._tera_cb.setChecked(enable_tera)
        self._tera_cb.blockSignals(False)
        idx = self._tera_combo.findData(tera)
        if idx < 0:
            idx = 0
        self._tera_combo.blockSignals(True)
        self._tera_combo.setCurrentIndex(idx)
        self._tera_combo.blockSignals(False)
        self._tera_combo.setEnabled(enable_tera)
        self._disguise_cb.blockSignals(True)
        self._disguise_cb.setChecked(False)
        self._disguise_cb.blockSignals(False)
        self._update_stat_display(p)
        self._emit()

    def _set_panel_nature(self, nature: str, emit: bool = True) -> None:
        from src.constants import NATURES_JA
        nature = nature if nature in NATURES_JA else "まじめ"
        self._panel_nature = nature
        boost, reduce = NATURES_JA.get(nature, (None, None))
        if boost and reduce:
            from src.ui.pokemon_edit_dialog import _STAT_LABELS
            text = "{}  (↑{} / ↓{})".format(
                nature,
                _STAT_LABELS.get(boost, boost),
                _STAT_LABELS.get(reduce, reduce),
            )
        else:
            text = "{}（補正なし）".format(nature)
        self._nat_btn.setText(text)
        if emit:
            self._emit()

    def _open_nature_dialog(self) -> None:
        from src.ui.pokemon_edit_dialog import NatureSelectDialog
        from src.data import database as db
        usage_name = (self._base_pokemon.usage_name or self._base_pokemon.name_ja) if self._base_pokemon else ""
        ranked = db.get_natures_by_usage(usage_name)[:4] if usage_name else []
        dlg = NatureSelectDialog(self._panel_nature, ranked_natures=ranked, parent=self)
        if dlg.exec_():
            self._set_panel_nature(dlg.selected_nature())

    def _adj_ac_rank(self, delta: int) -> None:
        self._ac_rank = max(-6, min(6, self._ac_rank + delta))
        self._ac_rank_lbl.setText("{:+d}".format(self._ac_rank) if self._ac_rank != 0 else " 0")
        self._emit()

    def _adj_bd_rank(self, delta: int) -> None:
        self._bd_rank = max(-6, min(6, self._bd_rank + delta))
        self._bd_rank_lbl.setText("{:+d}".format(self._bd_rank) if self._bd_rank != 0 else " 0")
        self._emit()

    def _on_tera_changed(self, checked: bool) -> None:
        self._tera_combo.setEnabled(checked)
        self._emit()

    def _update_stat_display(self, p: PokemonInstance) -> None:
        self._stat_lbl_h.setText("H({})".format(p.hp or p.max_hp or "---"))
        self._stat_lbl_a.setText("A({})".format(p.attack))
        self._stat_lbl_b.setText("B({})".format(p.defense))
        self._stat_lbl_c.setText("C({})".format(p.sp_attack))
        self._stat_lbl_d.setText("D({})".format(p.sp_defense))
        self._stat_lbl_s.setText("S({})".format(p.speed))

    def _toggle_actions(self) -> None:
        self._actions_visible = not self._actions_visible
        self._action_row_wrap.setVisible(self._actions_visible)

    def _emit(self) -> None:
        self.changed.emit()


# ── Header cards ──────────────────────────────────────────────────────────

def _label_fit_text(lbl: "QLabel", text: str, base_px: int = 13, min_px: int = 10) -> None:
    """Set text on label, shrinking pixel font size to fit, then elide."""
    from PyQt5.QtGui import QFont, QFontMetrics
    if not text:
        lbl.setText("")
        return
    w = lbl.width()
    if w <= 0:
        lbl.setText(text)
        return
    f = QFont(lbl.font())
    for px in range(base_px, min_px - 1, -1):
        f.setPixelSize(px)
        fm = QFontMetrics(f)
        if fm.horizontalAdvance(text) <= w:
            lbl.setFont(f)
            lbl.setText(text)
            return
    f.setPixelSize(min_px)
    fm = QFontMetrics(f)
    lbl.setFont(f)
    lbl.setText(fm.elidedText(text, Qt.ElideRight, w))


class _PokemonCard(QWidget):
    edit_requested = pyqtSignal()
    form_change_requested = pyqtSignal()
    ability_change_requested = pyqtSignal()
    item_change_requested = pyqtSignal()
    _SPRITE_SIZE = 72
    _CARD_HEIGHT = 84

    def __init__(self, role_text: str, role_color: str, parent=None):
        super().__init__(parent)
        self._pokemon: Optional[PokemonInstance] = None
        self.setFixedHeight(self._CARD_HEIGHT)
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet(
            "QFrame{background:#181825;border:1px solid #45475a;border-radius:6px;}")
        frame.setFixedHeight(self._CARD_HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(frame)

        frame_vbox = QVBoxLayout(frame)
        frame_vbox.setContentsMargins(8, 6, 4, 6)
        frame_vbox.setSpacing(2)

        frame_row = QHBoxLayout()
        frame_row.setSpacing(4)

        inner = QVBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(2)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self._role_lbl = QLabel(role_text)
        self._role_lbl.setStyleSheet(f"color:{role_color};font-size:12px;font-weight:bold;")
        row1.addWidget(self._role_lbl)
        self._name_lbl = QLabel("（未設定）")
        self._name_lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;background:#181825;border:1px solid #45475a;border-radius:4px;padding:4px;")
        self._name_lbl.setWordWrap(False)
        row1.addWidget(self._name_lbl, 1)
        inner.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(4)
        self._ability_lbl = QLabel("")
        self._ability_lbl.setStyleSheet(
            "color:#a6adc8;font-size:13px;text-decoration:underline;"
            "background:transparent;border-radius:3px;padding:1px 3px;")
        self._ability_lbl.setWordWrap(False)
        self._ability_lbl.setCursor(Qt.PointingHandCursor)
        self._ability_lbl.mousePressEvent = lambda _: self.ability_change_requested.emit()
        row2.addWidget(self._ability_lbl, 1)
        self._item_lbl = QLabel("")
        self._item_lbl.setStyleSheet(
            "color:#f9e2af;font-size:13px;text-decoration:underline;"
            "background:transparent;border-radius:3px;padding:1px 3px;")
        self._item_lbl.setWordWrap(False)
        self._item_lbl.setCursor(Qt.PointingHandCursor)
        self._item_lbl.mousePressEvent = lambda _: self.item_change_requested.emit()
        row2.addWidget(self._item_lbl, 1)
        inner.addLayout(row2)

        self._form_btn = QPushButton("フォルムチェンジ")
        self._form_btn.setFixedHeight(12)
        self._form_btn.setStyleSheet(
            "QPushButton{font-size:12px;background:#313244;color:#A6E3A1;"
            "border:1px solid #45475a;border-radius:3px;padding:-6 4px;}"
            "QPushButton:hover{background:#45475a;}"
        )
        self._form_btn.clicked.connect(self.form_change_requested.emit)
        sp = self._form_btn.sizePolicy()
        sp.setRetainSizeWhenHidden(False)
        self._form_btn.setSizePolicy(sp)
        self._form_btn.hide()
        inner.addWidget(self._form_btn)
        inner.addStretch()

        frame_row.addLayout(inner, 1)

        self._sprite_lbl = QLabel()
        self._sprite_lbl.setFixedSize(self._SPRITE_SIZE, self._SPRITE_SIZE)
        self._sprite_lbl.setAlignment(Qt.AlignCenter)
        frame_row.addWidget(self._sprite_lbl)

        frame_vbox.addLayout(frame_row)

    def set_pokemon(self, custom: Optional[PokemonInstance]) -> None:
        self._pokemon = custom
        if custom:
            from src.ui.ui_utils import sprite_pixmap_or_zukan
            pm = sprite_pixmap_or_zukan(
                custom.name_ja or "",
                self._SPRITE_SIZE,
                self._SPRITE_SIZE,
                name_en=custom.name_en or "",
            )
            self._sprite_lbl.setPixmap(pm if pm else QPixmap())
        else:
            self._sprite_lbl.setPixmap(QPixmap())
        self._refresh_text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_text()

    def _refresh_text(self) -> None:
        p = self._pokemon
        if p:
            display_name = _FORM_CANONICAL_NAME.get(p.name_ja or "", p.name_ja or "---")
            self._name_lbl.setText(display_name)
            _label_fit_text(self._ability_lbl, p.ability or "", 13)
            _label_fit_text(self._item_lbl, p.item or "", 13)
            next_form = _next_form_name(p.name_ja or "")
            if next_form:
                next_display = _FORM_CANONICAL_NAME.get(next_form, next_form)
                self._form_btn.setText("→ {}".format(next_display))
                self._form_btn.show()
            else:
                self._form_btn.hide()
        else:
            self._name_lbl.setText("（未設定）")
            self._ability_lbl.setText("")
            self._item_lbl.setText("")
            self._form_btn.hide()


class _AttackerCard(_PokemonCard):
    def __init__(self, parent=None):
        super().__init__("自分", "#F38BA8", parent)


class _DefenderCard(_PokemonCard):
    def __init__(self, parent=None):
        super().__init__("相手", "#89B4FA", parent)


# ── Stealth rock display ──────────────────────────────────────────────────

class _StealthRockRow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        iro = QLabel("ステロ:")
        iro.setStyleSheet("color:#a6adc8;font-size:12px;")
        layout.addWidget(iro)
        self._lbl = QLabel("---")
        self._lbl.setStyleSheet("font-size:12px;color:#f9e2af;")
        layout.addWidget(self._lbl)
        layout.addStretch()

    def refresh_data(self, defender_types: list[str], hp_custom: int,
                     hp_hbd0: int, hp_hbd252: int,
                     show_bulk_rows: bool = True) -> None:
        from src.calc.damage_calc import calc_stealth_rock_damage
        parts = []
        if hp_custom > 0:
            d = calc_stealth_rock_damage(hp_custom, defender_types)
            parts.append("調整:{} ({:.1f}%)".format(d, d/hp_custom*100))
        if show_bulk_rows and hp_hbd0 > 0:
            d = calc_stealth_rock_damage(hp_hbd0, defender_types)
            parts.append("無振り:{} ({:.1f}%)".format(d, d/hp_hbd0*100))
        if show_bulk_rows and hp_hbd252 > 0:
            d = calc_stealth_rock_damage(hp_hbd252, defender_types)
            parts.append("極振り:{} ({:.1f}%)".format(d, d/hp_hbd252*100))
        self._lbl.setText("   ".join(parts) if parts else "---")


# ── Ability / Item quick-pick helpers ────────────────────────────────────

def _pick_ability(pokemon: "PokemonInstance", parent: QWidget) -> "str | None":
    from src.ui.pokemon_edit_dialog import SuggestComboBox, _build_ranked_options, _unique
    from src.constants import ABILITIES_JA
    from src.data import database as db
    all_abilities = sorted(_unique(list(ABILITIES_JA)))
    usage_name = pokemon.usage_name or pokemon.name_ja
    ranked = _unique(db.get_abilities_by_usage(usage_name) if usage_name else [])
    items, sep = _build_ranked_options(ranked, all_abilities)
    return _show_pick_dialog("特性を選択", items, sep, pokemon.ability or "", parent)


def _pick_item(pokemon: "PokemonInstance", parent: QWidget) -> "str | None":
    from src.ui.pokemon_edit_dialog import SuggestComboBox, _build_ranked_options, _unique
    from src.constants import ITEMS_JA
    from src.data import database as db
    from src.data.item_catalog import get_item_names
    all_items = sorted(_unique(list(ITEMS_JA) + get_item_names()))
    usage_name = pokemon.usage_name or pokemon.name_ja
    ranked = _unique(db.get_items_by_usage(usage_name) if usage_name else [])
    items, sep = _build_ranked_options(ranked, all_items)
    return _show_pick_dialog("持ち物を選択", items, sep, pokemon.item or "", parent)


def _show_pick_dialog(
    title: str,
    items: list,
    separator_after: "int | None",
    current: str,
    parent: QWidget,
) -> "str | None":
    from PyQt5.QtWidgets import QDialogButtonBox
    from src.ui.pokemon_edit_dialog import SuggestComboBox
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(320)
    lay = QVBoxLayout(dlg)
    combo = SuggestComboBox(parent=dlg)
    combo.set_items(items, preserve_text=False, separator_after=separator_after)
    combo.set_text(current)
    lay.addWidget(combo)
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)
    if dlg.exec_():
        return combo.current_text_stripped()
    return None


# ── Party slot (攻守交替 bottom) ──────────────────────────────────────────

class _PartySlot(QFrame):
    clicked_signal = pyqtSignal(int)
    context_menu_requested = pyqtSignal(int, object)
    _SPRITE_SIZE = 72

    def __init__(self, idx: int, parent=None):
        super().__init__(parent)
        self._idx = idx
        self.setFrameShape(QFrame.StyledPanel)
        self.setFixedSize(78, 78)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QFrame{background:#313244;border:1px solid #45475a;border-radius:4px;}"
            "QFrame:hover{border-color:#89b4fa;}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        self._sprite_lbl = QLabel()
        self._sprite_lbl.setFixedSize(self._SPRITE_SIZE, self._SPRITE_SIZE)
        self._sprite_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._sprite_lbl, 0, Qt.AlignCenter)

    def set_name(self, name: str, attack_active: bool = False, defense_active: bool = False, sprite_name: str = "") -> None:
        sprite = sprite_name or name
        if sprite:
            from src.ui.ui_utils import sprite_pixmap_or_zukan
            pm = sprite_pixmap_or_zukan(sprite, self._SPRITE_SIZE, self._SPRITE_SIZE)
            self._sprite_lbl.setPixmap(pm if pm else QPixmap())
        else:
            self._sprite_lbl.setPixmap(QPixmap())
        if attack_active:
            border = "#a6e3a1"
        elif defense_active:
            border = "#f9e2af"
        else:
            border = "#45475a"
        self.setStyleSheet(
            "QFrame{{background:#313244;border:2px solid {};border-radius:4px;}}"
            "QFrame:hover{{border-color:#89b4fa;}}".format(border))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            self.context_menu_requested.emit(self._idx, event.globalPos())
            event.accept()
            return
        self.clicked_signal.emit(self._idx)
        super().mousePressEvent(event)


# ── Utility ───────────────────────────────────────────────────────────────

def _sep() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet("QFrame{border:none;border-top:1px solid #45475a;}")
    return line


# ── Main DamagePanel ──────────────────────────────────────────────────────

class DamagePanel(QWidget):
    attacker_changed = pyqtSignal(object)   # emitted when attacker pokemon changes
    defender_changed = pyqtSignal(object)   # emitted when defender pokemon changes
    registry_maybe_changed = pyqtSignal()

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
        self._weather_grp.set_button_metrics(font_size=14, height=28, min_width=65, pad_h=6, pad_v=2)
        self._weather_grp.changed.connect(self.recalculate)
        _weather_col.addWidget(self._weather_grp)
        wf_row.addLayout(_weather_col)

        _terrain_col = QVBoxLayout()
        _terrain_col.setContentsMargins(0, 0, 0, 0)
        _terrain_col.setSpacing(2)
        _terrain_col.addWidget(_row_label("フィールド"))
        self._terrain_grp = _RadioGroup(["エレキ", "グラス", "ミスト", "サイコ"])
        self._terrain_grp.set_button_metrics(font_size=14, height=28, min_width=65, pad_h=6, pad_v=2)
        self._terrain_grp.changed.connect(self.recalculate)
        _terrain_col.addWidget(self._terrain_grp)
        wf_row.addLayout(_terrain_col)

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
        atk_cond1b = QHBoxLayout()        # 常時ボタン2行目: フェアリーオーラ・ダークオーラ・てだすけ
        atk_cond1b.setContentsMargins(0, 0, 0, 0)
        atk_cond1b.setSpacing(4)
        self._burn_btn = _ToggleBtn("やけど")
        self._crit_btn = _ToggleBtn("急所")
        self._fairy_aura_btn = _ToggleBtn("フェアリーオーラ")
        self._dark_aura_btn = _ToggleBtn("ダークオーラ")
        self._charge_btn = _ToggleBtn("じゅうでん")
        self._helping_btn = _ToggleBtn("てだすけ")
        self._steel_spirit_btn = _ToggleBtn("はがねのせいしん")
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
            btn.setFixedHeight(28)
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
        for btn in (self._fairy_aura_btn, self._dark_aura_btn, self._helping_btn, self._steel_spirit_btn):
            atk_cond1b.addWidget(btn)

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
        self_side_col.addLayout(atk_cond_ability)
        self_side_col.addLayout(atk_cond4)
        self_side_col.addLayout(atk_cond1a)
        self_side_col.addLayout(atk_cond1b)

        # 自分側 防御補助 (相手→自分 計算に使用)
        self_side_col.addSpacing(8)
        self_side_col.addWidget(_row_label("  防御側:"))
        self_def_cond = QHBoxLayout()
        self_def_cond.setContentsMargins(0, 0, 0, 4)
        self_def_cond.setSpacing(4)
        self._self_reflect_btn = _ToggleBtn("リフレクター")
        self._self_lightscreen_btn = _ToggleBtn("ひかりのかべ")
        self._self_friend_guard_btn = _ToggleBtn("フレンドガード")
        for btn in (self._self_reflect_btn, self._self_lightscreen_btn, self._self_friend_guard_btn):
            btn.setFixedHeight(28)
            btn.setMinimumWidth(70)
            btn.toggled.connect(lambda _: self.recalculate())
            self_def_cond.addWidget(btn)
        self_def_cond.addStretch()
        self_side_col.addLayout(self_def_cond)
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
        opp_atk_cond1b = QHBoxLayout()          # 常時ボタン2行目: フェアリーオーラ・ダークオーラ・てだすけ
        opp_atk_cond1b.setContentsMargins(0, 0, 0, 0)
        opp_atk_cond1b.setSpacing(4)
        self._opp_burn_btn = _ToggleBtn("やけど")
        self._opp_crit_btn = _ToggleBtn("急所")
        self._opp_fairy_aura_btn = _ToggleBtn("フェアリーオーラ")
        self._opp_dark_aura_btn = _ToggleBtn("ダークオーラ")
        self._opp_charge_btn = _ToggleBtn("じゅうでん")
        self._opp_helping_btn = _ToggleBtn("てだすけ")
        self._opp_steel_spirit_btn = _ToggleBtn("はがねのせいしん")
        for btn in (self._opp_burn_btn, self._opp_crit_btn, self._opp_fairy_aura_btn,
                    self._opp_dark_aura_btn, self._opp_charge_btn, self._opp_helping_btn,
                    self._opp_steel_spirit_btn):
            btn.setFixedHeight(28)
            btn.setMinimumWidth(70)
            btn.toggled.connect(lambda _: self.recalculate())
        for btn in (self._opp_burn_btn, self._opp_crit_btn, self._opp_charge_btn):
            opp_atk_cond1a.addWidget(btn)
        for btn in (self._opp_fairy_aura_btn, self._opp_dark_aura_btn, self._opp_helping_btn, self._opp_steel_spirit_btn):
            opp_atk_cond1b.addWidget(btn)
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
        opp_side_col.addLayout(opp_atk_cond_ability)
        opp_side_col.addLayout(opp_atk_cond4)
        opp_side_col.addLayout(opp_atk_cond1a)
        opp_side_col.addLayout(opp_atk_cond1b)

        # 相手側 防御補助 (自分→相手 計算に使用)
        opp_side_col.addSpacing(8)
        opp_side_col.addWidget(_row_label("  防御側:"))
        def_cond = QHBoxLayout()
        def_cond.setContentsMargins(0, 0, 0, 4)
        def_cond.setSpacing(4)
        self._reflect_btn = _ToggleBtn("リフレクター")
        self._lightscreen_btn = _ToggleBtn("ひかりのかべ")
        self._friend_guard_btn = _ToggleBtn("フレンドガード")
        for btn in (self._reflect_btn, self._lightscreen_btn, self._friend_guard_btn):
            btn.setFixedHeight(28)
            btn.setMinimumWidth(70)
            btn.toggled.connect(lambda _: self.recalculate())
            def_cond.addWidget(btn)
        def_cond.addStretch()
        opp_side_col.addLayout(def_cond)
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
        db.save_pokemon(pokemon)
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

    def set_opponent_options(self, options: list[PokemonInstance]) -> None:
        if not options:
            return
        self._opp_party = [copy.deepcopy(p) if p else None for p in options[:6]]
        self._def_custom = copy.deepcopy(options[0])
        self._def_species_name = options[0].name_ja or ""
        self._def_party_side = "opp"
        self._def_party_idx = 0
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
            weather, terrain, reflect, lightscreen, helping, fairy_aura, dark_aura
        )
        _field_d_rev = smogon_field_to_dict(
            weather, terrain, self_reflect, self_lightscreen, opp_helping, fairy_aura, dark_aura
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
                if effective_move.name_ja == "ウェザーボール":
                    weather_ball_type = {
                        "sun": "fire",
                        "rain": "water",
                        "sand": "rock",
                        "hail": "ice",
                    }.get(weather, "")
                    if weather_ball_type:
                        resolved_type = weather_ball_type
                resolved_category = resolve_effective_move_category(
                    atk, effective_move, atk_rank=rank, terastal_type=tera,
                )
                if resolved_type != effective_move.type_name or resolved_category != effective_move.category:
                    effective_move = dataclasses.replace(
                        effective_move, type_name=resolved_type, category=resolved_category
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
                if def_types_override:
                    _custom_d["teraType"] = TYPE_TO_SMOGON.get(def_types_override[0], "")

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

                _mv_d_opp = smogon_move_to_dict(
                    opp_move_info, is_crit=_opp_is_crit,
                    hits=_opp_hits if _opp_hits > 1 else 0,
                    bp_override=_opp_pow_override,
                    forced_type=_opp_skin_forced_type,
                    bp_multiplier=_opp_skin_bp_mult,
                )

                _self_types = atk.types or ["normal"]
                _self_ability = atk.ability or ""
                _opp_effective_type = _opp_skin_forced_type or opp_move_info.type_name
                _opp_type_eff = move_type_effectiveness(
                    opp_move_info, _opp_effective_type, _self_types, _self_ability
                )

                def _call_bridge_rev(opp_atk_d: dict) -> tuple[int, int, int, bool]:
                    self_hp = atk.hp if atk.hp > 0 else 1
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
                    terastal_type=self._def_custom.terastal_type or "",
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
                    ev_atk=0,
                    ev_spa=0,
                    nature_en="Hardy",
                    ability_en=_opp_atk_en,
                    item_en=_opp_item_en,
                    atk_rank=_opp_def_ac_rank,
                    is_physical=_is_opp_phys,
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
                    ev_atk=252 if _is_opp_phys else 0,
                    ev_spa=0 if _is_opp_phys else 252,
                    nature_en=_opp_best_nat_en,
                    ability_en=_opp_atk_en,
                    item_en=_opp_item_en,
                    atk_rank=_opp_def_ac_rank,
                    is_physical=_is_opp_phys,
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
                        terastal_type=self._def_custom.terastal_type or "",
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
                    self._reflect_btn, self._lightscreen_btn, self._friend_guard_btn,
                    self._opp_burn_btn, self._opp_crit_btn,
                    self._opp_fairy_aura_btn, self._opp_dark_aura_btn,
                    self._opp_charge_btn, self._opp_helping_btn, self._opp_steel_spirit_btn,
                    self._opp_overgrow_btn, self._opp_blaze_btn, self._opp_torrent_btn,
                    self._opp_swarm_btn, self._opp_toxic_boost_btn,
                    self._opp_stakeout_btn, self._opp_flash_fire_btn,
                    self._opp_protosynthesis_btn, self._opp_quark_drive_btn,
                    self._opp_analytic_btn, self._opp_flare_boost_btn, self._opp_guts_btn):
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


def _row_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color:#89b4fa;font-size:14px;font-weight:bold;")
    return lbl
