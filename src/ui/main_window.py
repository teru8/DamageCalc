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
    """コード内埋め込みのサンプルパーティを解析して PokemonInstance リストを返す。"""
    text = _SAMPLE_PARTY_TEXT
    lines = [line.strip() for line in text.splitlines() if line.strip()]
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
        # Line 0: name @ item
        head = block_lines[0].split("@")
        name_ja = head[0].strip()
        item = head[1].strip() if len(head) > 1 else ""
        # Line 1:
        tera_ja = block_lines[1].split(":")[-1].strip() if ":" in block_lines[1] else ""
        tera_en = TYPE_JA_TO_EN.get(tera_ja, "")
        # Line 2:
        ability = block_lines[2].split(":")[-1].strip() if ":" in block_lines[2] else ""
        # Line 3:
        nature = block_lines[3].split(":")[-1].strip() if ":" in block_lines[3] else "まじめ"
        # Line 4: (EV)-...
        parts = block_lines[4].split("-")
        stats: list[int] = []
        evs: list[int] = []
        for p in parts[:6]:
            m = stat_re.match(p.strip())
            if m:
                stats.append(int(m.group(1)))
                evs.append(int(m.group(2)) if m.group(2) else 0)
            else:
                stats.append(0)
                evs.append(0)
        while len(stats) < 6:
            stats.append(0)
            evs.append(0)
        # Line 5:
        moves = [m.strip() for m in block_lines[5].split("/")][:4]
        # DB
        species = db.get_species_by_name_ja(name_ja)
        p = PokemonInstance(
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
        result.append(p)
    return result


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DamageCalc α — Pokemon Champions")
        self.setMinimumSize(_RIGHT_PANEL_MIN_WIDTH + _CAM_PANEL_WIDTH + _WINDOW_WIDTH_PADDING, 720)

        self._battle_state = BattleState()
        self._registered_pokemon: list[PokemonInstance] = []
        self._video_thread: VideoThread | None = None
        self._api_loader: PokeApiLoader | None = None
        self._scraper: QThread | None = None
        self._party_presets: list[dict] = []
        self._fetch_api_btn: QPushButton | None = None
        self._fetch_usage_btn: QPushButton | None = None
        self._option_data_status_lbl: QLabel | None = None
        self._option_damage_tera_cb: QCheckBox | None = None
        self._option_damage_bulk_cb: QCheckBox | None = None
        self._option_damage_double_cb: QCheckBox | None = None
        self._option_detailed_log_cb: QCheckBox | None = None
        self._webhook_url_edit: "QLineEdit | None" = None
        self._option_season_combo: QComboBox | None = None
        self._option_source_combo: QComboBox | None = None
        self._options_dialog: QDialog | None = None
        self._tab_damage_btn: QPushButton | None = None
        self._tab_box_btn: QPushButton | None = None
        self._box_side_scroll: QScrollArea | None = None
        self._box_type_filter: set[str] = set()
        self._box_type_buttons: dict[str, object] = {}
        self._log_edit: QTextEdit | None = None
        self._main_log_edit: QTextEdit | None = None
        self._detect_opponent_btn: QPushButton | None = None
        self._auto_detect_btn: QPushButton | None = None
        self._auto_detect_pending = False
        self._auto_detect_cooldown_until = 0.0
        self._auto_detect_score_log_last = 0.0
        self._auto_detect_debug_dump_last = 0.0
        self._damage_tera_visible = False
        self._detailed_log_enabled = False
        self._sample_party_pending = False
        self._syncing_battle_state_to_panels = False
        self._saved_party_list_layout: QVBoxLayout | None = None
        self._live_battle_timer = QTimer(self)
        self._live_battle_timer.setInterval(max(300, int(OCR_INTERVAL_MS)))
        self._live_battle_timer.timeout.connect(self._poll_live_battle)
        self._live_battle_signature = ""
        self._opp_auto_detect_timer = QTimer(self)
        self._opp_auto_detect_timer.setInterval(250)
        self._opp_auto_detect_timer.timeout.connect(self._poll_opponent_party_auto_detect)

        db.init_db()
        self._registered_pokemon = db.load_all_pokemon()
        self._init_battle_state()

        self._build_ui()
        self._sync_battle_state_to_panels()
        self._apply_saved_settings()
        self._load_party_presets()
        self._apply_top_saved_party_on_startup()
        self._refresh_party_presets_ui()
        self._set_initial_window_size()
        self._start_background_tasks()

    def _get_usage_scraper_symbols(self):
        from src.ui.main_window_ui import _get_usage_scraper_symbols as _impl
        return _impl(self)

    def _build_ui(self) -> None:
        from src.ui.main_window_ui import _build_ui as _impl
        return _impl(self)

    def _build_registry_tab(self) -> QWidget:
        from src.ui.main_window_ui import _build_registry_tab as _impl
        return _impl(self)

    def _build_box_side_panel(self) -> QWidget:
        from src.ui.main_window_ui import _build_box_side_panel as _impl
        return _impl(self)

    def _build_options_dialog(self) -> None:
        from src.ui.main_window_ui import _build_options_dialog as _impl
        return _impl(self)

    def _open_options_dialog(self) -> None:
        from src.ui.main_window_ui import _open_options_dialog as _impl
        return _impl(self)

    def _set_fetch_buttons_enabled(self, enabled: bool) -> None:
        from src.ui.main_window_ui import _set_fetch_buttons_enabled as _impl
        return _impl(self, enabled)

    def _refresh_usage_season_options(self, selected: str | None = None) -> None:
        from src.ui.main_window_ui import _refresh_usage_season_options as _impl
        return _impl(self, selected)

    def _current_usage_season(self) -> str:
        from src.ui.main_window_handlers import _current_usage_season as _impl
        return _impl(self)

    def _on_usage_season_changed(self, text: str) -> None:
        from src.ui.main_window_handlers import _on_usage_season_changed as _impl
        return _impl(self, text)

    def _toggle_damage_tera_option(self, checked: bool) -> None:
        from src.ui.main_window_handlers import _toggle_damage_tera_option as _impl
        return _impl(self, checked)

    def _toggle_damage_bulk_option(self, checked: bool) -> None:
        from src.ui.main_window_handlers import _toggle_damage_bulk_option as _impl
        return _impl(self, checked)

    def _toggle_damage_double_option(self, checked: bool) -> None:
        from src.ui.main_window_handlers import _toggle_damage_double_option as _impl
        return _impl(self, checked)

    def _toggle_detailed_log_option(self, checked: bool) -> None:
        from src.ui.main_window_handlers import _toggle_detailed_log_option as _impl
        return _impl(self, checked)

    def _start_background_tasks(self) -> None:
        from src.ui.main_window_handlers import _start_background_tasks as _impl
        return _impl(self)

    @pyqtSlot(bool, str)
    def _on_ocr_ready(self, ok: bool, err: str) -> None:
        if ok:
            self._status_bar.showMessage("OCR 初期化完了")
            self._log("OCR 初期化完了")
        else:
            self._log("[ERROR] OCR 初期化失敗: {}".format(err))

    @pyqtSlot(int, str)
    def _on_api_progress(self, pct: int, msg: str) -> None:
        self._status_bar.showMessage(msg)
        if self._sample_party_pending:
            self._show_loading_overlay("PokeAPI データを取得中... {}%\n{}".format(pct, msg))

    @pyqtSlot()
    def _on_api_done(self) -> None:
        text_matcher.clear_caches()
        self._set_fetch_buttons_enabled(True)
        self._refresh_data_status()
        self._status_bar.showMessage("PokeAPIデータ取得完了")
        self._log("PokeAPIデータ取得完了")
        if self._sample_party_pending:
            self._sample_party_pending = False
            self._hide_loading_overlay()
            self._apply_sample_party()

    def _apply_sample_party(self) -> None:
        from src.ui.main_window_handlers import _apply_sample_party as _impl
        return _impl(self)

    @pyqtSlot(bool, str)
    def _on_scraper_done(self, ok: bool, msg: str) -> None:
        self._set_fetch_buttons_enabled(True)
        self._refresh_usage_season_options(self._current_usage_season())
        self._refresh_data_status()
        self._status_bar.showMessage(msg)
        self._log(msg)

    @pyqtSlot(int, str)
    def _on_usage_progress(self, pct: int, msg: str) -> None:
        self._status_bar.showMessage(msg)

    def _fetch_pokeapi_data(self) -> None:
        from src.ui.main_window_handlers import _fetch_pokeapi_data as _impl
        return _impl(self)

    def _fetch_usage_data(self) -> None:
        from src.ui.main_window_handlers import _fetch_usage_data as _impl
        return _impl(self)

    def _run_data_integrity_check(self) -> None:
        from src.ui.main_window_handlers import _run_data_integrity_check as _impl
        return _impl(self)

    @pyqtSlot(QPixmap)
    def _on_frame(self, pixmap: QPixmap) -> None:
        self._preview_lbl.setPixmap(
            pixmap.scaled(self._preview_lbl.width(), self._preview_lbl.height(),
                          Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # ── Camera control ────────────────────────────────────────────────

    def _refresh_cameras(self) -> None:
        from src.ui.main_window_handlers import _refresh_cameras as _impl
        return _impl(self)

    def _toggle_camera(self) -> None:
        from src.ui.main_window_handlers import _toggle_camera as _impl
        return _impl(self)

    def _save_screenshot(self) -> None:
        from src.ui.main_window_handlers import _save_screenshot as _impl
        return _impl(self)

    def _apply_splitter_layout(self) -> None:
        from src.ui.main_window_ui import _apply_splitter_layout as _impl
        return _impl(self)

    def _set_initial_window_size(self) -> None:
        from src.ui.main_window_ui import _set_initial_window_size as _impl
        return _impl(self)

    def _on_damage_tab_visibility(self, index: int) -> None:
        from src.ui.main_window_ui import _on_damage_tab_visibility as _impl
        return _impl(self, index)

    def _sync_tab_switcher_buttons(self, index: int) -> None:
        from src.ui.main_window_ui import _sync_tab_switcher_buttons as _impl
        return _impl(self, index)

    def eventFilter(self, obj, event):
        from src.ui.main_window_handlers import eventFilter as _impl
        return _impl(self, obj, event)

    def _show_usage_password_dialog(self) -> None:
        from src.ui.main_window_ui import _show_usage_password_dialog as _impl
        return _impl(self)

    def _show_usage_fetch_dialog(self) -> None:
        from src.ui.main_window_ui import _show_usage_fetch_dialog as _impl
        return _impl(self)

    def _fetch_usage_data_with_source(self, season: str, source: str) -> None:
        from src.ui.main_window_handlers import _fetch_usage_data_with_source as _impl
        return _impl(self, season, source)

    def _log(self, msg: str) -> None:
        from src.ui.main_window_handlers import _log as _impl
        return _impl(self, msg)

    def _on_bridge_payload_log(self, msg: str) -> None:
        from src.ui.main_window_handlers import _on_bridge_payload_log as _impl
        return _impl(self, msg)

    def _export_log_to_txt(self) -> None:
        from src.ui.main_window_handlers import _export_log_to_txt as _impl
        return _impl(self)

    def _init_battle_state(self) -> None:
        from src.ui.main_window_handlers import _init_battle_state as _impl
        return _impl(self)

    def _ensure_party_slots(self) -> None:
        from src.ui.main_window_handlers import _ensure_party_slots as _impl
        return _impl(self)

    def _sync_battle_state_to_panels(self) -> None:
        from src.ui.main_window_handlers import _sync_battle_state_to_panels as _impl
        return _impl(self)

    def _on_party_slot_clicked(self, index: int, is_my: bool) -> None:
        from src.ui.main_window_handlers import _on_party_slot_clicked as _impl
        return _impl(self, index, is_my)

    def _on_my_party_panel_dropped(self, name_ja: str) -> None:
        from src.ui.main_window_handlers import _on_my_party_panel_dropped as _impl
        return _impl(self, name_ja)

    def _try_add_to_my_party(self, name_ja: str, source: str = "click") -> None:
        from src.ui.main_window_handlers import _try_add_to_my_party as _impl
        return _impl(self, name_ja, source)

    def _on_registry_cell_left_click(self, name_ja: str) -> None:
        from src.ui.main_window_handlers import _on_registry_cell_left_click as _impl
        return _impl(self, name_ja)

    def _on_my_party_panel_cleared(self) -> None:
        from src.ui.main_window_handlers import _on_my_party_panel_cleared as _impl
        return _impl(self)

    def _on_my_party_panel_context_menu(self, global_pos) -> None:
        from src.ui.main_window_handlers import _on_my_party_panel_context_menu as _impl
        return _impl(self, global_pos)

    def _on_party_slot_dropped(self, index: int, name_ja: str) -> None:
        from src.ui.main_window_handlers import _on_party_slot_dropped as _impl
        return _impl(self, index, name_ja)

    def _on_party_slot_cleared(self, index: int) -> None:
        from src.ui.main_window_handlers import _on_party_slot_cleared as _impl
        return _impl(self, index)

    def _select_registered_pokemon(self, title: str, current_name: str = "") -> tuple[bool, PokemonInstance | None]:
        from src.ui.main_window_handlers import _select_registered_pokemon as _impl
        return _impl(self, title, current_name)

    def _auto_detect_opponent_party(self) -> None:
        from src.ui.main_window_handlers import _auto_detect_opponent_party as _impl
        return _impl(self)

    def _on_auto_detect_toggled(self, checked: bool) -> None:
        from src.ui.main_window_handlers import _on_auto_detect_toggled as _impl
        return _impl(self, checked)

    def _stop_opponent_party_auto_detect(self, show_message: bool, write_log: bool) -> None:
        from src.ui.main_window_handlers import _stop_opponent_party_auto_detect as _impl
        return _impl(self, show_message, write_log)

    def _refresh_auto_detect_button_style(self) -> None:
        from src.ui.main_window_ui import _refresh_auto_detect_button_style as _impl
        return _impl(self)

    def _poll_opponent_party_auto_detect(self) -> None:
        from src.ui.main_window_handlers import _poll_opponent_party_auto_detect as _impl
        return _impl(self)

    def _dump_auto_detect_debug_frame(self, frame) -> None:
        from src.ui.main_window_handlers import _dump_auto_detect_debug_frame as _impl
        return _impl(self, frame)

    def _toggle_live_battle_tracking(self, enabled: bool) -> None:
        from src.ui.main_window_handlers import _toggle_live_battle_tracking as _impl
        return _impl(self, enabled)

    def _stop_live_battle_tracking(self, show_message: bool, write_log: bool) -> None:
        from src.ui.main_window_handlers import _stop_live_battle_tracking as _impl
        return _impl(self, show_message, write_log)

    def _poll_live_battle(self) -> None:
        from src.ui.main_window_handlers import _poll_live_battle as _impl
        return _impl(self)

    def _apply_live_battle_data(self, live_data: dict) -> tuple[bool, str]:
        from src.ui.main_window_handlers import _apply_live_battle_data as _impl
        return _impl(self, live_data)

    @staticmethod
    def _party_member_by_name(
        party: list[PokemonInstance | None],
        name_ja: str,
    ) -> PokemonInstance | None:
        target = (name_ja or "").strip()
        if not target:
            return None
        for member in party:
            if member and member.name_ja == target:
                return member
        return None

    def _build_usage_template_pokemon(self, name_ja: str) -> PokemonInstance | None:
        from src.ui.main_window_handlers import _build_usage_template_pokemon as _impl
        return _impl(self, name_ja)

    def _read_box_and_register(self) -> None:
        from src.ui.main_window_handlers import _read_box_and_register as _impl
        return _impl(self)

    def _apply_box_ocr(self, data: dict) -> None:
        from src.ui.main_window_handlers import _apply_box_ocr as _impl
        return _impl(self, data)

    def _show_loading_overlay(self, message: str = "読み込み中...") -> None:
        from src.ui.main_window_ui import _show_loading_overlay as _impl
        return _impl(self, message)

    def _hide_loading_overlay(self) -> None:
        from src.ui.main_window_ui import _hide_loading_overlay as _impl
        return _impl(self)

    def _start_box_read_thread(self, frame: object) -> None:
        from src.ui.main_window_handlers import _start_box_read_thread as _impl
        return _impl(self, frame)

    def _refresh_registry_list(self) -> None:
        from src.ui.main_window_handlers import _refresh_registry_list as _impl
        return _impl(self)

    def _open_edit_dialog(self, pokemon) -> None:
        from src.ui.main_window_handlers import _open_edit_dialog as _impl
        return _impl(self, pokemon)

    def _open_register_input_dialog(self) -> None:
        from src.ui.main_window_handlers import _open_register_input_dialog as _impl
        return _impl(self)

    def _parse_pokemon_text_block(self, text: str) -> tuple[PokemonInstance | None, str | None]:
        from src.ui.main_window_handlers import _parse_pokemon_text_block as _impl
        return _impl(self, text)

    def _edit_selected_pokemon(self) -> None:
        from src.ui.main_window_handlers import _edit_selected_pokemon as _impl
        return _impl(self)

    def _delete_selected_pokemon(self) -> None:
        from src.ui.main_window_handlers import _delete_selected_pokemon as _impl
        return _impl(self)

    def _copy_selected_pokemon_info(self) -> None:
        from src.ui.main_window_handlers import _copy_selected_pokemon_info as _impl
        return _impl(self)

    def _format_pokemon_export_text(self, pokemon: PokemonInstance) -> str:
        from src.ui.main_window_handlers import _format_pokemon_export_text as _impl
        return _impl(self, pokemon)

    def _on_registry_context_menu(self, pos) -> None:
        from src.ui.main_window_handlers import _on_registry_context_menu as _impl
        return _impl(self, pos)

    def _on_registry_context_menu_for_cell(self, global_pos) -> None:
        from src.ui.main_window_handlers import _on_registry_context_menu_for_cell as _impl
        return _impl(self, global_pos)

    def _on_damage_panel_atk_changed(self, pokemon: PokemonInstance | None) -> None:
        from src.ui.main_window_handlers import _on_damage_panel_atk_changed as _impl
        return _impl(self, pokemon)

    def _on_damage_panel_def_changed(self, pokemon: PokemonInstance | None) -> None:
        from src.ui.main_window_handlers import _on_damage_panel_def_changed as _impl
        return _impl(self, pokemon)

    def _find_registered(self, name_ja: str) -> PokemonInstance | None:
        from src.ui.main_window_handlers import _find_registered as _impl
        return _impl(self, name_ja)

    def _fill_species(self, pokemon: PokemonInstance) -> None:
        from src.ui.main_window_handlers import _fill_species as _impl
        return _impl(self, pokemon)

    def _serialize_pokemon(self, pokemon: PokemonInstance | None) -> dict | None:
        from src.ui.main_window_handlers import _serialize_pokemon as _impl
        return _impl(self, pokemon)

    def _deserialize_pokemon(self, payload: dict | None) -> PokemonInstance | None:
        from src.ui.main_window_handlers import _deserialize_pokemon as _impl
        return _impl(self, payload)

    def _load_party_presets(self) -> None:
        from src.ui.main_window_handlers import _load_party_presets as _impl
        return _impl(self)

    def _apply_top_saved_party_on_startup(self) -> None:
        from src.ui.main_window_handlers import _apply_top_saved_party_on_startup as _impl
        return _impl(self)

    def _refresh_party_presets_ui(self, selected_name: str = "") -> None:
        from src.ui.main_window_ui import _refresh_party_presets_ui as _impl
        return _impl(self, selected_name)

    def _update_box_party_ui(self) -> None:
        from src.ui.main_window_ui import _update_box_party_ui as _impl
        return _impl(self)

    @staticmethod
    def _active_index(party: list[PokemonInstance | None], active: PokemonInstance | None) -> int:
        if not active or not active.name_ja:
            return -1
        for index, pokemon in enumerate(party):
            if pokemon and pokemon.name_ja == active.name_ja:
                return index
        return -1

    def _set_auto_detect_enabled(self, enabled: bool) -> None:
        from src.ui.main_window_ui import _set_auto_detect_enabled as _impl
        return _impl(self, enabled)

    def _save_party_preset(self, to_top: bool = False) -> None:
        from src.ui.main_window_handlers import _save_party_preset as _impl
        return _impl(self, to_top)

    def _on_saved_party_panel_context_menu(self, index: int, global_pos) -> None:
        from src.ui.main_window_handlers import _on_saved_party_panel_context_menu as _impl
        return _impl(self, index, global_pos)

    def _load_party_preset_at(self, index: int) -> None:
        from src.ui.main_window_handlers import _load_party_preset_at as _impl
        return _impl(self, index)

    def _delete_party_preset_at(self, index: int) -> None:
        from src.ui.main_window_handlers import _delete_party_preset_at as _impl
        return _impl(self, index)

    def _reorder_party_preset(self, from_index: int, to_index: int) -> None:
        from src.ui.main_window_handlers import _reorder_party_preset as _impl
        return _impl(self, from_index, to_index)

    def _move_saved_party_to_top(self, index: int) -> None:
        from src.ui.main_window_handlers import _move_saved_party_to_top as _impl
        return _impl(self, index)

    def _reset_all_party(self) -> None:
        from src.ui.main_window_handlers import _reset_all_party as _impl
        return _impl(self)

    def nativeEvent(self, event_type: bytes, message: object) -> tuple[bool, int]:
        from src.ui.main_window_handlers import nativeEvent as _impl
        return _impl(self, event_type, message)

    def _toggle_topmost(self, checked: bool) -> None:
        from src.ui.main_window_ui import _toggle_topmost as _impl
        return _impl(self, checked)

    def _refresh_data_status(self) -> None:
        from src.ui.main_window_ui import _refresh_data_status as _impl
        return _impl(self)

    def _settings_path(self) -> Path:
        from src.ui.main_window_handlers import _settings_path as _impl
        return _impl(self)

    def _load_settings(self) -> dict:
        from src.ui.main_window_handlers import _load_settings as _impl
        return _impl(self)

    def _save_settings(self, **kwargs) -> None:
        from src.ui.main_window_handlers import _save_settings as _impl
        return _impl(self, **kwargs)

    def _apply_saved_settings(self) -> None:
        from src.ui.main_window_handlers import _apply_saved_settings as _impl
        return _impl(self)

    def _auto_connect_saved_camera(self) -> None:
        from src.ui.main_window_handlers import _auto_connect_saved_camera as _impl
        return _impl(self)

    def closeEvent(self, event) -> None:
        from src.ui.main_window_handlers import closeEvent as _impl
        return _impl(self, event)

