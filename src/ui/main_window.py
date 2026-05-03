from __future__ import annotations
import copy
import ctypes
import json
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
from src.data.pokeapi_client import PokeApiLoader
from src.data import database as db
from src.recognition import text_matcher
from src.recognition import opponent_party_reader
from src.recognition import live_battle_reader
from src.recognition import opponent_party_auto_trigger
from src.constants import OCR_INTERVAL_MS, TYPE_EN_TO_JA
from src.ui.damage_panel import DamagePanel
from src.ui.main_window_panels import _DraggableCell, _SavedPartyPanel, _MyPartyPanel
from src.ui.main_window_camera_state import CameraRuntimeState
from src.ui.main_window_runtime.camera import CameraManager
from src.ui.main_window_runtime.cleanup import RuntimeCleanupManager
from src.ui.main_window_runtime.data_fetch import DataFetchManager
from src.ui.main_window_ocr_manager import OcrRetryManager
from src.ui.main_window_runtime.ocr_init import OcrInitManager
from src.ui.main_window_runtime.settings import SettingsStore
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
        self._webhook_url_edit: QLineEdit | None = None
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
        self._ocr_thread: OcrInitThread | None = None
        self._init_runtime_states()
        self._init_timers()

        self._initialize_application_state()

    def _init_runtime_states(self) -> None:
        self._camera_manager = CameraManager()
        self._camera_state = CameraRuntimeState(active=False)
        self._cleanup_manager = RuntimeCleanupManager()
        self._data_fetch_manager = DataFetchManager()
        self._ocr_init_manager = OcrInitManager()
        self._ocr_retry_manager = OcrRetryManager(max_retries=3, retry_delay_ms=2000)
        self._settings_store = SettingsStore.default()

    def _init_timers(self) -> None:
        self._ocr_retry_timer = QTimer(self)
        self._ocr_retry_timer.setSingleShot(True)
        self._ocr_retry_timer.timeout.connect(self._start_ocr_init_thread)

        self._live_battle_timer = QTimer(self)
        self._live_battle_timer.setInterval(max(300, int(OCR_INTERVAL_MS)))
        self._live_battle_timer.timeout.connect(self._poll_live_battle)
        self._live_battle_signature = ""

        self._opp_auto_detect_timer = QTimer(self)
        self._opp_auto_detect_timer.setInterval(250)
        self._opp_auto_detect_timer.timeout.connect(self._poll_opponent_party_auto_detect)

    def _initialize_application_state(self) -> None:
        # Phase 1: persistent data and in-memory battle state.
        self._initialize_database_state()
        # Phase 2: widgets, bindings, and initial view sync.
        self._initialize_ui_state()
        # Phase 3: async workers and deferred startup tasks.
        self._start_background_tasks()

    def _initialize_database_state(self) -> None:
        db.init_db()
        self._registered_pokemon = db.load_all_pokemon()
        self._init_battle_state()

    def _initialize_ui_state(self) -> None:
        self._build_ui()
        self._sync_battle_state_to_panels()
        self._apply_saved_settings()
        self._load_party_presets()
        self._apply_top_saved_party_on_startup()
        self._refresh_party_presets_ui()
        self._set_initial_window_size()

    def _get_usage_scraper_symbols(self):
        from src.ui.main_window_ui import _get_usage_scraper_symbols as get_usage_scraper_symbols_fn
        return get_usage_scraper_symbols_fn(self)

    def _build_ui(self) -> None:
        from src.ui.main_window_ui import _build_ui as build_ui_fn
        return build_ui_fn(self)

    def _build_registry_tab(self) -> QWidget:
        from src.ui.main_window_ui import _build_registry_tab as build_registry_tab_fn
        return build_registry_tab_fn(self)

    def _build_box_side_panel(self) -> QWidget:
        from src.ui.main_window_ui import _build_box_side_panel as build_box_side_panel_fn
        return build_box_side_panel_fn(self)

    def _build_options_dialog(self) -> None:
        from src.ui.main_window_ui import _build_options_dialog as build_options_dialog_fn
        return build_options_dialog_fn(self)

    def _open_options_dialog(self) -> None:
        from src.ui.main_window_ui import _open_options_dialog as open_options_dialog_fn
        return open_options_dialog_fn(self)

    def _set_fetch_buttons_enabled(self, enabled: bool) -> None:
        from src.ui.main_window_ui import _set_fetch_buttons_enabled as set_fetch_buttons_enabled_fn
        return set_fetch_buttons_enabled_fn(self, enabled)

    def _refresh_usage_season_options(self, selected: str | None = None) -> None:
        from src.ui.main_window_ui import _refresh_usage_season_options as refresh_usage_season_options_fn
        return refresh_usage_season_options_fn(self, selected)

    def _current_usage_season(self) -> str:
        from src.ui.main_window_handlers import _current_usage_season as current_usage_season_fn
        return current_usage_season_fn(self)

    def _on_usage_season_changed(self, text: str) -> None:
        from src.ui.main_window_handlers import _on_usage_season_changed as on_usage_season_changed_fn
        return on_usage_season_changed_fn(self, text)

    def _toggle_damage_tera_option(self, checked: bool) -> None:
        from src.ui.main_window_handlers import _toggle_damage_tera_option as toggle_damage_tera_option_fn
        return toggle_damage_tera_option_fn(self, checked)

    def _toggle_damage_bulk_option(self, checked: bool) -> None:
        from src.ui.main_window_handlers import _toggle_damage_bulk_option as toggle_damage_bulk_option_fn
        return toggle_damage_bulk_option_fn(self, checked)

    def _toggle_damage_double_option(self, checked: bool) -> None:
        from src.ui.main_window_handlers import _toggle_damage_double_option as toggle_damage_double_option_fn
        return toggle_damage_double_option_fn(self, checked)

    def _toggle_detailed_log_option(self, checked: bool) -> None:
        from src.ui.main_window_handlers import _toggle_detailed_log_option as toggle_detailed_log_option_fn
        return toggle_detailed_log_option_fn(self, checked)

    def _on_webhook_url_changed(self) -> None:
        from src.ui.main_window_handlers import _on_webhook_url_changed as on_webhook_url_changed_fn
        return on_webhook_url_changed_fn(self)

    def _start_background_tasks(self) -> None:
        from src.ui.main_window_handlers import _start_background_tasks as start_background_tasks_fn
        return start_background_tasks_fn(self)

    def _start_ocr_init_thread(self) -> None:
        self._ocr_init_manager.start(self)

    @pyqtSlot(bool, str)
    def _on_ocr_ready(self, ok: bool, err: str) -> None:
        self._ocr_init_manager.on_ready(self, ok, err)

    def _handle_ocr_init_failure(self, err: str) -> None:
        self._ocr_init_manager.handle_failure(self, err)

    def _schedule_ocr_retry_if_available(self) -> None:
        self._ocr_init_manager.schedule_retry_if_available(self)

    @pyqtSlot(int, str)
    def _on_api_progress(self, pct: int, msg: str) -> None:
        self._status_bar.showMessage(msg)
        if self._sample_party_pending:
            self._show_loading_overlay("PokeAPI データを取得中... {}%\n{}".format(pct, msg))

    @pyqtSlot()
    def _on_api_done(self) -> None:
        self._set_fetch_buttons_enabled(True)
        self._refresh_data_status()
        self._status_bar.showMessage("PokeAPIデータ取得完了")
        self._log("PokeAPIデータ取得完了")
        if self._sample_party_pending:
            self._sample_party_pending = False
            self._hide_loading_overlay()
            self._apply_sample_party()

    def _apply_sample_party(self) -> None:
        from src.ui.main_window_handlers import _apply_sample_party as _apply_sample_party_fn
        return _apply_sample_party_fn(self)

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
        from src.ui.main_window_handlers import _fetch_pokeapi_data as _fetch_pokeapi_data_fn
        return _fetch_pokeapi_data_fn(self)

    def _fetch_usage_data(self) -> None:
        from src.ui.main_window_handlers import _fetch_usage_data as _fetch_usage_data_fn
        return _fetch_usage_data_fn(self)

    def _run_data_integrity_check(self) -> None:
        from src.ui.main_window_handlers import _run_data_integrity_check as _run_data_integrity_check_fn
        return _run_data_integrity_check_fn(self)

    @pyqtSlot(QPixmap)
    def _on_frame(self, pixmap: QPixmap) -> None:
        self._preview_lbl.setPixmap(
            pixmap.scaled(self._preview_lbl.width(), self._preview_lbl.height(),
                          Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # ── Camera control ────────────────────────────────────────────────

    def _refresh_cameras(self) -> None:
        from src.ui.main_window_handlers import _refresh_cameras as _refresh_cameras_fn
        return _refresh_cameras_fn(self)

    def _toggle_camera(self) -> None:
        from src.ui.main_window_handlers import _toggle_camera as _toggle_camera_fn
        return _toggle_camera_fn(self)

    def _save_screenshot(self) -> None:
        from src.ui.main_window_handlers import _save_screenshot as _save_screenshot_fn
        return _save_screenshot_fn(self)

    def _apply_splitter_layout(self) -> None:
        from src.ui.main_window_ui import _apply_splitter_layout as _apply_splitter_layout_fn
        return _apply_splitter_layout_fn(self)

    def _set_initial_window_size(self) -> None:
        from src.ui.main_window_ui import _set_initial_window_size as _set_initial_window_size_fn
        return _set_initial_window_size_fn(self)

    def _on_damage_tab_visibility(self, index: int) -> None:
        from src.ui.main_window_ui import _on_damage_tab_visibility as _on_damage_tab_visibility_fn
        return _on_damage_tab_visibility_fn(self, index)

    def _sync_tab_switcher_buttons(self, index: int) -> None:
        from src.ui.main_window_ui import _sync_tab_switcher_buttons as _sync_tab_switcher_buttons_fn
        return _sync_tab_switcher_buttons_fn(self, index)

    def eventFilter(self, obj, event):
        from src.ui.main_window_handlers import eventFilter as eventFilter_fn
        return eventFilter_fn(self, obj, event)

    def _show_usage_password_dialog(self) -> None:
        from src.ui.main_window_ui import _show_usage_password_dialog as _show_usage_password_dialog_fn
        return _show_usage_password_dialog_fn(self)

    def _show_usage_fetch_dialog(self) -> None:
        from src.ui.main_window_ui import _show_usage_fetch_dialog as _show_usage_fetch_dialog_fn
        return _show_usage_fetch_dialog_fn(self)

    def _fetch_usage_data_with_source(self, season: str, source: str) -> None:
        from src.ui.main_window_handlers import _fetch_usage_data_with_source as _fetch_usage_data_with_source_fn
        return _fetch_usage_data_with_source_fn(self, season, source)

    def _log(self, msg: str) -> None:
        from src.ui.main_window_handlers import _log as _log_fn
        return _log_fn(self, msg)

    def _on_bridge_payload_log(self, msg: str) -> None:
        from src.ui.main_window_handlers import _on_bridge_payload_log as _on_bridge_payload_log_fn
        return _on_bridge_payload_log_fn(self, msg)

    def _export_log_to_txt(self) -> None:
        from src.ui.main_window_handlers import _export_log_to_txt as _export_log_to_txt_fn
        return _export_log_to_txt_fn(self)

    def _init_battle_state(self) -> None:
        from src.ui.main_window_handlers import _init_battle_state as _init_battle_state_fn
        return _init_battle_state_fn(self)

    def _ensure_party_slots(self) -> None:
        from src.ui.main_window_handlers import _ensure_party_slots as _ensure_party_slots_fn
        return _ensure_party_slots_fn(self)

    def _sync_battle_state_to_panels(self) -> None:
        from src.ui.main_window_handlers import _sync_battle_state_to_panels as _sync_battle_state_to_panels_fn
        return _sync_battle_state_to_panels_fn(self)

    def _on_party_slot_clicked(self, index: int, is_my: bool) -> None:
        from src.ui.main_window_handlers import _on_party_slot_clicked as _on_party_slot_clicked_fn
        return _on_party_slot_clicked_fn(self, index, is_my)

    def _on_my_party_panel_dropped(self, name_ja: str) -> None:
        from src.ui.main_window_handlers import _on_my_party_panel_dropped as _on_my_party_panel_dropped_fn
        return _on_my_party_panel_dropped_fn(self, name_ja)

    def _try_add_to_my_party(self, name_ja: str, source: str = "click") -> None:
        from src.ui.main_window_handlers import _try_add_to_my_party as _try_add_to_my_party_fn
        return _try_add_to_my_party_fn(self, name_ja, source)

    def _on_registry_cell_left_click(self, name_ja: str) -> None:
        from src.ui.main_window_handlers import _on_registry_cell_left_click as _on_registry_cell_left_click_fn
        return _on_registry_cell_left_click_fn(self, name_ja)

    def _on_my_party_panel_cleared(self) -> None:
        from src.ui.main_window_handlers import _on_my_party_panel_cleared as _on_my_party_panel_cleared_fn
        return _on_my_party_panel_cleared_fn(self)

    def _on_my_party_panel_context_menu(self, global_pos) -> None:
        from src.ui.main_window_handlers import _on_my_party_panel_context_menu as _on_my_party_panel_context_menu_fn
        return _on_my_party_panel_context_menu_fn(self, global_pos)

    def _on_party_slot_dropped(self, index: int, name_ja: str) -> None:
        from src.ui.main_window_handlers import _on_party_slot_dropped as _on_party_slot_dropped_fn
        return _on_party_slot_dropped_fn(self, index, name_ja)

    def _on_party_slot_cleared(self, index: int) -> None:
        from src.ui.main_window_handlers import _on_party_slot_cleared as _on_party_slot_cleared_fn
        return _on_party_slot_cleared_fn(self, index)

    def _select_registered_pokemon(self, title: str, current_name: str = "") -> tuple[bool, PokemonInstance | None]:
        from src.ui.main_window_handlers import _select_registered_pokemon as _select_registered_pokemon_fn
        return _select_registered_pokemon_fn(self, title, current_name)

    def _auto_detect_opponent_party(self) -> None:
        from src.ui.main_window_handlers import _auto_detect_opponent_party as _auto_detect_opponent_party_fn
        return _auto_detect_opponent_party_fn(self)

    def _on_auto_detect_toggled(self, checked: bool) -> None:
        from src.ui.main_window_handlers import _on_auto_detect_toggled as _on_auto_detect_toggled_fn
        return _on_auto_detect_toggled_fn(self, checked)

    def _stop_opponent_party_auto_detect(self, show_message: bool, write_log: bool) -> None:
        from src.ui.main_window_handlers import _stop_opponent_party_auto_detect as _stop_opponent_party_auto_detect_fn
        return _stop_opponent_party_auto_detect_fn(self, show_message, write_log)

    def _refresh_auto_detect_button_style(self) -> None:
        from src.ui.main_window_ui import _refresh_auto_detect_button_style as _refresh_auto_detect_button_style_fn
        return _refresh_auto_detect_button_style_fn(self)

    def _poll_opponent_party_auto_detect(self) -> None:
        from src.ui.main_window_handlers import _poll_opponent_party_auto_detect as _poll_opponent_party_auto_detect_fn
        return _poll_opponent_party_auto_detect_fn(self)

    def _dump_auto_detect_debug_frame(self, frame) -> None:
        from src.ui.main_window_handlers import _dump_auto_detect_debug_frame as _dump_auto_detect_debug_frame_fn
        return _dump_auto_detect_debug_frame_fn(self, frame)

    def _toggle_live_battle_tracking(self, enabled: bool) -> None:
        from src.ui.main_window_handlers import _toggle_live_battle_tracking as _toggle_live_battle_tracking_fn
        return _toggle_live_battle_tracking_fn(self, enabled)

    def _stop_live_battle_tracking(self, show_message: bool, write_log: bool) -> None:
        from src.ui.main_window_handlers import _stop_live_battle_tracking as _stop_live_battle_tracking_fn
        return _stop_live_battle_tracking_fn(self, show_message, write_log)

    def _poll_live_battle(self) -> None:
        from src.ui.main_window_handlers import _poll_live_battle as _poll_live_battle_fn
        return _poll_live_battle_fn(self)

    def _apply_live_battle_data(self, live_data: dict) -> tuple[bool, str]:
        from src.ui.main_window_handlers import _apply_live_battle_data as _apply_live_battle_data_fn
        return _apply_live_battle_data_fn(self, live_data)

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
        from src.ui.main_window_handlers import _build_usage_template_pokemon as _build_usage_template_pokemon_fn
        return _build_usage_template_pokemon_fn(self, name_ja)

    def _read_box_and_register(self) -> None:
        from src.ui.main_window_handlers import _read_box_and_register as _read_box_and_register_fn
        return _read_box_and_register_fn(self)

    def _apply_box_ocr(self, data: dict) -> None:
        from src.ui.main_window_handlers import _apply_box_ocr as _apply_box_ocr_fn
        return _apply_box_ocr_fn(self, data)

    def _show_loading_overlay(self, message: str = "読み込み中...") -> None:
        from src.ui.main_window_ui import _show_loading_overlay as _show_loading_overlay_fn
        return _show_loading_overlay_fn(self, message)

    def _hide_loading_overlay(self) -> None:
        from src.ui.main_window_ui import _hide_loading_overlay as _hide_loading_overlay_fn
        return _hide_loading_overlay_fn(self)

    def _start_box_read_thread(self, frame: object) -> None:
        from src.ui.main_window_handlers import _start_box_read_thread as _start_box_read_thread_fn
        return _start_box_read_thread_fn(self, frame)

    def _refresh_registry_list(self) -> None:
        from src.ui.main_window_handlers import _refresh_registry_list as _refresh_registry_list_fn
        return _refresh_registry_list_fn(self)

    def _open_edit_dialog(self, pokemon) -> None:
        from src.ui.main_window_handlers import _open_edit_dialog as _open_edit_dialog_fn
        return _open_edit_dialog_fn(self, pokemon)

    def _open_register_input_dialog(self) -> None:
        from src.ui.main_window_handlers import _open_register_input_dialog as _open_register_input_dialog_fn
        return _open_register_input_dialog_fn(self)

    def _parse_pokemon_text_block(self, text: str) -> tuple[PokemonInstance | None, str | None]:
        from src.ui.main_window_handlers import _parse_pokemon_text_block as _parse_pokemon_text_block_fn
        return _parse_pokemon_text_block_fn(self, text)

    def _edit_selected_pokemon(self) -> None:
        from src.ui.main_window_handlers import _edit_selected_pokemon as _edit_selected_pokemon_fn
        return _edit_selected_pokemon_fn(self)

    def _delete_selected_pokemon(self) -> None:
        from src.ui.main_window_handlers import _delete_selected_pokemon as _delete_selected_pokemon_fn
        return _delete_selected_pokemon_fn(self)

    def _copy_selected_pokemon_info(self) -> None:
        from src.ui.main_window_handlers import _copy_selected_pokemon_info as _copy_selected_pokemon_info_fn
        return _copy_selected_pokemon_info_fn(self)

    def _format_pokemon_export_text(self, pokemon: PokemonInstance) -> str:
        from src.ui.main_window_handlers import _format_pokemon_export_text as _format_pokemon_export_text_fn
        return _format_pokemon_export_text_fn(self, pokemon)

    def _on_registry_context_menu(self, pos) -> None:
        from src.ui.main_window_handlers import _on_registry_context_menu as _on_registry_context_menu_fn
        return _on_registry_context_menu_fn(self, pos)

    def _on_registry_context_menu_for_cell(self, global_pos) -> None:
        from src.ui.main_window_handlers import _on_registry_context_menu_for_cell as _on_registry_context_menu_for_cell_fn
        return _on_registry_context_menu_for_cell_fn(self, global_pos)

    def _on_damage_panel_atk_changed(self, pokemon: PokemonInstance | None) -> None:
        from src.ui.main_window_handlers import _on_damage_panel_atk_changed as _on_damage_panel_atk_changed_fn
        return _on_damage_panel_atk_changed_fn(self, pokemon)

    def _on_damage_panel_def_changed(self, pokemon: PokemonInstance | None) -> None:
        from src.ui.main_window_handlers import _on_damage_panel_def_changed as _on_damage_panel_def_changed_fn
        return _on_damage_panel_def_changed_fn(self, pokemon)

    def _find_registered(self, name_ja: str) -> PokemonInstance | None:
        from src.ui.main_window_handlers import _find_registered as _find_registered_fn
        return _find_registered_fn(self, name_ja)

    def _fill_species(self, pokemon: PokemonInstance) -> None:
        from src.ui.main_window_handlers import _fill_species as _fill_species_fn
        return _fill_species_fn(self, pokemon)

    def _serialize_pokemon(self, pokemon: PokemonInstance | None) -> dict | None:
        from src.ui.main_window_handlers import _serialize_pokemon as _serialize_pokemon_fn
        return _serialize_pokemon_fn(self, pokemon)

    def _deserialize_pokemon(self, payload: dict | None) -> PokemonInstance | None:
        from src.ui.main_window_handlers import _deserialize_pokemon as _deserialize_pokemon_fn
        return _deserialize_pokemon_fn(self, payload)

    def _load_party_presets(self) -> None:
        from src.ui.main_window_handlers import _load_party_presets as _load_party_presets_fn
        return _load_party_presets_fn(self)

    def _apply_top_saved_party_on_startup(self) -> None:
        from src.ui.main_window_handlers import _apply_top_saved_party_on_startup as _apply_top_saved_party_on_startup_fn
        return _apply_top_saved_party_on_startup_fn(self)

    def _refresh_party_presets_ui(self, selected_name: str = "") -> None:
        from src.ui.main_window_ui import _refresh_party_presets_ui as _refresh_party_presets_ui_fn
        return _refresh_party_presets_ui_fn(self, selected_name)

    def _update_box_party_ui(self) -> None:
        from src.ui.main_window_ui import _update_box_party_ui as _update_box_party_ui_fn
        return _update_box_party_ui_fn(self)

    @staticmethod
    def _active_index(party: list[PokemonInstance | None], active: PokemonInstance | None) -> int:
        if not active or not active.name_ja:
            return -1
        for index, pokemon in enumerate(party):
            if pokemon and pokemon.name_ja == active.name_ja:
                return index
        return -1

    def _set_auto_detect_enabled(self, enabled: bool) -> None:
        from src.ui.main_window_ui import _set_auto_detect_enabled as _set_auto_detect_enabled_fn
        return _set_auto_detect_enabled_fn(self, enabled)

    def _save_party_preset(self, to_top: bool = False) -> None:
        from src.ui.main_window_handlers import _save_party_preset as _save_party_preset_fn
        return _save_party_preset_fn(self, to_top)

    def _on_saved_party_panel_context_menu(self, index: int, global_pos) -> None:
        from src.ui.main_window_handlers import _on_saved_party_panel_context_menu as _on_saved_party_panel_context_menu_fn
        return _on_saved_party_panel_context_menu_fn(self, index, global_pos)

    def _load_party_preset_at(self, index: int) -> None:
        from src.ui.main_window_handlers import _load_party_preset_at as _load_party_preset_at_fn
        return _load_party_preset_at_fn(self, index)

    def _delete_party_preset_at(self, index: int) -> None:
        from src.ui.main_window_handlers import _delete_party_preset_at as _delete_party_preset_at_fn
        return _delete_party_preset_at_fn(self, index)

    def _reorder_party_preset(self, from_index: int, to_index: int) -> None:
        from src.ui.main_window_handlers import _reorder_party_preset as _reorder_party_preset_fn
        return _reorder_party_preset_fn(self, from_index, to_index)

    def _move_saved_party_to_top(self, index: int) -> None:
        from src.ui.main_window_handlers import _move_saved_party_to_top as _move_saved_party_to_top_fn
        return _move_saved_party_to_top_fn(self, index)

    def _reset_all_party(self) -> None:
        from src.ui.main_window_handlers import _reset_all_party as _reset_all_party_fn
        return _reset_all_party_fn(self)

    def nativeEvent(self, event_type: bytes, message: object) -> tuple[bool, int]:
        from src.ui.main_window_handlers import nativeEvent as nativeEvent_fn
        return nativeEvent_fn(self, event_type, message)

    def _toggle_topmost(self, checked: bool) -> None:
        from src.ui.main_window_ui import _toggle_topmost as _toggle_topmost_fn
        return _toggle_topmost_fn(self, checked)

    def _refresh_data_status(self) -> None:
        from src.ui.main_window_ui import _refresh_data_status as _refresh_data_status_fn
        return _refresh_data_status_fn(self)

    def _settings_path(self) -> Path:
        from src.ui.main_window_handlers import _settings_path as _settings_path_fn
        return _settings_path_fn(self)

    def _load_settings(self) -> dict:
        from src.ui.main_window_handlers import _load_settings as _load_settings_fn
        return _load_settings_fn(self)

    def _save_settings(self, **kwargs) -> None:
        from src.ui.main_window_handlers import _save_settings as _save_settings_fn
        return _save_settings_fn(self, **kwargs)

    def _apply_saved_settings(self) -> None:
        from src.ui.main_window_handlers import _apply_saved_settings as _apply_saved_settings_fn
        return _apply_saved_settings_fn(self)

    def _auto_connect_saved_camera(self) -> None:
        from src.ui.main_window_handlers import _auto_connect_saved_camera as _auto_connect_saved_camera_fn
        return _auto_connect_saved_camera_fn(self)

    def closeEvent(self, event) -> None:
        from src.ui.main_window_handlers import closeEvent as closeEvent_fn
        return closeEvent_fn(self, event)

