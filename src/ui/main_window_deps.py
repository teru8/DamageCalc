"""Shared dependencies for extracted main_window_* modules."""
from __future__ import annotations

import copy
import ctypes
import json
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import cv2
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QLabel, QComboBox, QPushButton,
    QStatusBar, QGroupBox, QListWidget, QListWidgetItem,
    QProgressBar, QCheckBox, QMessageBox, QTextEdit,
    QDialog, QInputDialog, QLineEdit, QGridLayout, QPlainTextEdit, QFileDialog,
    QMenu, QAction, QScrollArea, QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSlot, QTimer, QThread, QObject, pyqtSignal
from PyQt5.QtGui import QPixmap

from src.models import PokemonInstance, BattleState
from src.capture.video_thread import VideoThread
from src.capture.ocr_engine import OcrInitThread
from src.data.pokeapi_client import PokeApiLoader
from src.data import database as db
from src.recognition import text_matcher
from src.recognition import opponent_party_reader
from src.recognition import live_battle_reader
from src.recognition import opponent_party_auto_trigger
from src.constants import OCR_INTERVAL_MS, TYPE_EN_TO_JA, TYPE_JA_TO_EN
from src.ui.damage_panel import DamagePanel
from src.ui.main_window_panels import _DraggableCell, _SavedPartyPanel, _MyPartyPanel
from src.ui.pokemon_edit_dialog import ChipButton, TypeIconButton
from src.ui.ui_utils import open_pokemon_edit_dialog

_RIGHT_PANEL_MIN_WIDTH = 760
_CAM_PANEL_WIDTH = 600
_PREVIEW_W, _PREVIEW_H = 320, 180
_WINDOW_WIDTH_PADDING = 28
_USAGE_SOURCE_DEFAULT_FALLBACK = "pokedb_tokyo"
_USAGE_SOURCES_FALLBACK = {
    "pokedb_tokyo": "pokedb.tokyo",
}
_SAMPLE_PARTY_TEXT = """\
ガブリアス @ きあいのタスキ
テラスタイプ: ノーマル
特性: さめはだ
性格: ようき
185(12)-182(252)-115-90-105-169(252)
じしん / げきりん / がんせきふうじ / どくづき
アシレーヌ @ オボンのみ
テラスタイプ: ノーマル
特性: げきりゅう
性格: ひかえめ
187(252)-84-94-195(252)-136-82(12)
ムーンフォース / うたかたのアリア / アクアジェット / クイックターン
リザードン @ リザードナイトＹ
テラスタイプ: ノーマル
特性: もうか
性格: おくびょう
155(12)-93-98-161(252)-105-167(252)
ソーラービーム / ニトロチャージ / かえんほうしゃ / フレアドライブ
アーマーガア @ たべのこし
テラスタイプ: ノーマル
特性: プレッシャー
性格: わんぱく
205(252)-107-172(252)-65-105-89(12)
ボディプレス / とんぼがえり / アイアンヘッド / ブレイブバード
ブリジュラス @ たべのこし
テラスタイプ: ノーマル
特性: じきゅうりょく
性格: ひかえめ
167(12)-112-150-194(252)-85-137(252)
ラスターカノン / りゅうせいぐん / １０まんボルト / はどうだん
カバルドン @ オボンのみ
テラスタイプ: ノーマル
特性: すなおこし
性格: わんぱく
215(252)-132-151-79-124(252)-69(12)
じしん / がんせきふうじ / こおりのキバ / じわれ
"""


def _parse_sample_party() -> list[PokemonInstance]:
    """Parse bundled sample party text into PokemonInstance objects."""
    lines = [line.strip() for line in _SAMPLE_PARTY_TEXT.splitlines() if line.strip()]
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if "@" in line and current:
            blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)
    result: list[PokemonInstance] = []
    stat_re = re.compile(r"(\d+)(?:\((\d+)\))?")
    for block_lines in blocks:
        if len(block_lines) < 6:
            continue
        head = block_lines[0].split("@")
        name_ja = head[0].strip()
        item = head[1].strip() if len(head) > 1 else ""
        tera_ja = block_lines[1].split(":")[-1].strip() if ":" in block_lines[1] else ""
        tera_en = TYPE_JA_TO_EN.get(tera_ja, "")
        ability = block_lines[2].split(":")[-1].strip() if ":" in block_lines[2] else ""
        nature = block_lines[3].split(":")[-1].strip() if ":" in block_lines[3] else "まじめ"
        parts = block_lines[4].split("-")
        stats: list[int] = []
        evs: list[int] = []
        for part in parts[:6]:
            match = stat_re.match(part.strip())
            if match:
                stats.append(int(match.group(1)))
                evs.append(int(match.group(2)) if match.group(2) else 0)
            else:
                stats.append(0)
                evs.append(0)
        while len(stats) < 6:
            stats.append(0)
            evs.append(0)
        moves = [move.strip() for move in block_lines[5].split("/")][:4]
        species = db.get_species_by_name_ja(name_ja)
        pokemon = PokemonInstance(
            species_id=species.species_id if species else 0,
            name_ja=name_ja,
            name_en=species.name_en if species else "",
            types=[species.type1] + ([species.type2] if species and species.type2 else []) if species else [],
            weight_kg=species.weight_kg if species else 0.0,
            nature=nature,
            ability=ability,
            item=item,
            hp=stats[0], attack=stats[1], defense=stats[2],
            sp_attack=stats[3], sp_defense=stats[4], speed=stats[5],
            ev_hp=evs[0], ev_attack=evs[1], ev_defense=evs[2],
            ev_sp_attack=evs[3], ev_sp_defense=evs[4], ev_speed=evs[5],
            moves=moves,
            terastal_type=tera_en,
        )
        result.append(pokemon)
    return result
