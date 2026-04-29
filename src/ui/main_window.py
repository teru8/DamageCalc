from __future__ import annotations
import copy
import json
from datetime import datetime
from pathlib import Path

import cv2
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QLabel, QComboBox, QPushButton,
    QStatusBar, QGroupBox, QListWidget, QListWidgetItem,
    QProgressBar, QCheckBox, QMessageBox, QTextEdit,
    QDialog, QInputDialog, QLineEdit, QGridLayout,
    QMenu, QAction, QScrollArea, QFrame,
)
from PyQt5.QtCore import Qt, pyqtSlot, QTimer, QThread, QObject, pyqtSignal
from PyQt5.QtGui import QPixmap

from src.models import PokemonInstance, BattleState
from src.capture.video_thread import VideoThread
from src.capture.ocr_engine import OcrInitThread
from src.data.pokeapi_client import PokeApiLoader
from src.data.usage_scraper import UsageScraper, USAGE_SOURCES, USAGE_SOURCE_DEFAULT
from src.data import database as db
from src.recognition import text_matcher
from src.recognition import opponent_party_reader
from src.recognition import live_battle_reader
from src.constants import OCR_INTERVAL_MS, TYPE_EN_TO_JA
from src.ui.battle_panel import PartySlot
from src.ui.damage_panel import DamagePanel
from src.ui.pokemon_edit_dialog import ChipButton, TypeIconButton
from src.ui.ui_utils import open_pokemon_edit_dialog

_RIGHT_PANEL_MIN_WIDTH = 760
_CAM_PANEL_WIDTH = 600
_PREVIEW_W, _PREVIEW_H = 320, 180
_WINDOW_WIDTH_PADDING = 28


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PokéDamageCalc — Pokemon Champions")
        self.setMinimumSize(_RIGHT_PANEL_MIN_WIDTH + _CAM_PANEL_WIDTH + _WINDOW_WIDTH_PADDING, 720)

        self._battle_state = BattleState()
        self._registered_pokemon: list[PokemonInstance] = []
        self._video_thread: VideoThread | None = None
        self._api_loader: PokeApiLoader | None = None
        self._scraper: UsageScraper | None = None
        self._party_presets: dict[str, dict] = {}
        self._fetch_api_btn: QPushButton | None = None
        self._fetch_usage_btn: QPushButton | None = None
        self._option_data_status_lbl: QLabel | None = None
        self._option_damage_tera_cb: QCheckBox | None = None
        self._option_damage_bulk_cb: QCheckBox | None = None
        self._option_damage_double_cb: QCheckBox | None = None
        self._option_season_combo: QComboBox | None = None
        self._option_source_combo: QComboBox | None = None
        self._options_dialog: QDialog | None = None
        self._tab_damage_btn: QPushButton | None = None
        self._tab_box_btn: QPushButton | None = None
        self._box_type_filter: set[str] = set()
        self._box_type_buttons: dict[str, object] = {}
        self._log_edit: QTextEdit | None = None
        self._auto_detect_btn: QPushButton | None = None
        self._damage_tera_visible = False
        self._live_battle_timer = QTimer(self)
        self._live_battle_timer.setInterval(max(300, int(OCR_INTERVAL_MS)))
        self._live_battle_timer.timeout.connect(self._poll_live_battle)
        self._live_battle_signature = ""

        db.init_db()
        self._registered_pokemon = db.load_all_pokemon()
        self._init_battle_state()

        self._build_ui()
        self._sync_battle_state_to_panels()
        self._apply_saved_settings()
        self._load_party_presets()
        self._refresh_party_presets_ui()
        self._set_initial_window_size()
        self._start_background_tasks()

    # ── UI Build ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        self._root_layout = QHBoxLayout(central)
        self._root_layout.setContentsMargins(6, 6, 6, 6)
        self._root_layout.setSpacing(6)

        self._splitter = QSplitter(Qt.Horizontal)

        # ── Right panel (tabs) ────────────────────────────────────────
        self._right_panel = QWidget()
        right_layout = QVBoxLayout(self._right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        self._tabs.tabBar().hide()

        self._damage_panel = DamagePanel()
        self._damage_panel.attacker_changed.connect(self._on_damage_panel_atk_changed)
        self._damage_panel.defender_changed.connect(self._on_damage_panel_def_changed)
        self._damage_panel.registry_maybe_changed.connect(self._refresh_registry_list)
        self._tabs.addTab(self._damage_panel, "ダメージ計算")

        reg_widget = self._build_registry_tab()
        self._tabs.addTab(reg_widget, "ボックス")

        right_layout.addWidget(self._tabs)
        self._right_panel.setMinimumWidth(_RIGHT_PANEL_MIN_WIDTH)
        self._right_panel.setMaximumWidth(_RIGHT_PANEL_MIN_WIDTH)

        # ── Camera panel ─────────────────────────────────────────────
        self._cam_panel = QWidget()
        cam_layout = QVBoxLayout(self._cam_panel)
        cam_layout.setContentsMargins(4, 4, 4, 4)
        cam_layout.setSpacing(0)

        # オプション＆プレビュー＆ログの統合レイアウト
        combined_row = QHBoxLayout()
        combined_row.setContentsMargins(0, 0, 0, 0)
        combined_row.setSpacing(4)

        switcher_col = QVBoxLayout()
        switcher_col.setContentsMargins(0, 0, 0, 0)
        switcher_col.setSpacing(4)

        self._tab_damage_btn = QPushButton("ダ\nメ\n|\nジ\n計\n算")
        self._tab_damage_btn.setCheckable(True)
        self._tab_damage_btn.setFixedSize(40, 130)
        self._tab_damage_btn.setStyleSheet(
            "QPushButton{"
            "font-weight:bold;border-top-left-radius:0px;border-bottom-left-radius:0px;"
            "border-top-right-radius:4px;border-bottom-right-radius:4px;font-size:13px;padding:0px;margin:0px;"
            "min-height:130px;max-height:130px;min-width:40px;max-width:40px;"
            "border-left:0px;}"
        )
        self._tab_damage_btn.clicked.connect(lambda: self._tabs.setCurrentIndex(0))
        switcher_col.addWidget(self._tab_damage_btn)

        self._tab_box_btn = QPushButton("ボ\nッ\nク\nス")
        self._tab_box_btn.setCheckable(True)
        self._tab_box_btn.setFixedSize(40, 90)
        self._tab_box_btn.setStyleSheet(
            "QPushButton{"
            "font-weight:bold;border-top-left-radius:0px;border-bottom-left-radius:0px;"
            "border-top-right-radius:4px;border-bottom-right-radius:4px;font-size:13px;padding:0px;margin:0px;"
            "min-height:90px;max-height:90px;min-width:40px;max-width:40px;"
            "border-left:0px;}"
        )
        self._tab_box_btn.clicked.connect(lambda: self._tabs.setCurrentIndex(1))
        switcher_col.addWidget(self._tab_box_btn)
        switcher_col.addStretch()

        combined_row.addLayout(switcher_col)

        # 左側：オプションボタン + プレビュー
        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(4)

        opt_row = QHBoxLayout()
        opt_row.setSpacing(4)
        opt_row.setContentsMargins(0, 0, 0, 0)
        self._options_btn = QPushButton("オプション")
        self._options_btn.clicked.connect(self._open_options_dialog)
        opt_row.addWidget(self._options_btn)
        self._shot_btn = QPushButton("スクリーンショット保存")
        self._shot_btn.clicked.connect(self._save_screenshot)
        opt_row.addWidget(self._shot_btn)
        self._auto_detect_btn = QPushButton("相手PT検出")
        self._auto_detect_btn.setStyleSheet(
            "QPushButton { background-color: #f38ba8; color: #11111b; font-weight: bold; }"
        )
        self._auto_detect_btn.clicked.connect(self._auto_detect_opponent_party)
        opt_row.addWidget(self._auto_detect_btn)
        opt_row.addStretch()
        left_column.addLayout(opt_row)

        self._preview_lbl = QLabel()
        self._preview_lbl.setFixedSize(_PREVIEW_W, _PREVIEW_H)
        self._preview_lbl.setAlignment(Qt.AlignCenter)
        self._preview_lbl.setStyleSheet(
            "background-color: #000; border: 1px solid #45475a; border-radius: 4px;")
        self._preview_lbl.setText("カメラ未接続")
        left_column.addWidget(self._preview_lbl)

        combined_row.addLayout(left_column)
        cam_layout.addLayout(combined_row, 0)

        # ダメージ計算タブのサイドパネル（攻守詳細＋天気等）
        self._damage_side = self._damage_panel.side_panel
        cam_layout.addWidget(self._damage_side, 1)
        self._damage_side.setVisible(False)

        # ボックスタブのサイドパネル（自分のパーティ）
        self._box_side = self._build_box_side_panel()
        cam_layout.addWidget(self._box_side, 1)
        self._box_side.setVisible(False)

        # 余白を下に寄せる
        cam_layout.addStretch()

        self._cam_panel.setFixedWidth(_CAM_PANEL_WIDTH)

        # Add widgets to splitter (camera right by default)
        self._splitter.addWidget(self._right_panel)
        self._splitter.addWidget(self._cam_panel)
        self._root_layout.addWidget(self._splitter)

        # タブ切り替えでサイドパネルの表示を制御
        self._tabs.currentChanged.connect(self._on_damage_tab_visibility)
        self._on_damage_tab_visibility(self._tabs.currentIndex())  # Initialize
        self._sync_tab_switcher_buttons(self._tabs.currentIndex())

        self._build_options_dialog()
        self._apply_splitter_layout()

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("起動中...")

        self._refresh_cameras()
        self._auto_connect_saved_camera()

    def _build_registry_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)

        btn_row = QHBoxLayout()
        read_box_btn = QPushButton("ボックスから読み込む")
        read_box_btn.setStyleSheet("QPushButton { background-color: #89b4fa; color: #1e1e2e; font-weight: bold; }")
        read_box_btn.clicked.connect(self._read_box_and_register)
        btn_row.addWidget(read_box_btn)
        add_btn = QPushButton("+ 新規登録")
        add_btn.clicked.connect(lambda: self._open_edit_dialog(None))
        btn_row.addWidget(add_btn)

        hint_col = QVBoxLayout()
        hint_col.setSpacing(1)
        self._data_status_lbl = QLabel()
        self._data_status_lbl.setStyleSheet("color: #a6adc8; font-size: 11px;")
        hint_col.addWidget(self._data_status_lbl)
        _box_hint = QLabel("ボックス画面を表示して「ボックスから読み込む」を押すと登録されます。")
        _box_hint.setStyleSheet("color: #a6adc8; font-size: 11px;")
        hint_col.addWidget(_box_hint)
        btn_row.addLayout(hint_col)

        # 編集・削除・自分設定ボタンは右クリックメニューへ移行
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # タイプ絞り込み（3列×6行グリッド）
        type_box = QGroupBox("タイプ絞り込み")
        type_layout = QVBoxLayout(type_box)
        type_layout.setContentsMargins(6, 4, 6, 4)

        type_grid = QGridLayout()
        type_grid.setHorizontalSpacing(4)
        type_grid.setVerticalSpacing(4)
        for col in range(6):
            type_grid.setColumnStretch(col, 1)

        self._box_type_buttons = {}
        for index, type_en in enumerate(TYPE_EN_TO_JA):
            button = TypeIconButton(type_en, show_label=False)
            self._box_type_buttons[type_en] = button
            type_grid.addWidget(button, index // 6, index % 6)

        type_layout.addLayout(type_grid)
        layout.addWidget(type_box)

        def _apply_box_type_state() -> None:
            for key, btn in self._box_type_buttons.items():
                btn.blockSignals(True)
                btn.setChecked(key in self._box_type_filter)
                btn.blockSignals(False)
                btn._update_style(key in self._box_type_filter)

        def _on_box_type_toggled(type_name: str, checked: bool) -> None:
            if checked:
                self._box_type_filter.add(type_name)
            else:
                self._box_type_filter.discard(type_name)
            _apply_box_type_state()
            self._refresh_registry_list()

        for key, btn in self._box_type_buttons.items():
            btn.toggled.connect(lambda checked, value=key: _on_box_type_toggled(value, checked))

        # ── ポケモングリッド表示エリア ──
        box_group = QGroupBox("ボックス")
        box_group_layout = QVBoxLayout(box_group)
        box_group_layout.setContentsMargins(6, 4, 6, 6)

        self._reg_scroll = QScrollArea()
        self._reg_scroll.setWidgetResizable(True)
        self._reg_scroll.setFrameShape(QFrame.NoFrame)
        self._reg_scroll.setMinimumHeight(300)
        self._reg_scroll.setContextMenuPolicy(Qt.CustomContextMenu)
        self._reg_scroll.customContextMenuRequested.connect(self._on_registry_context_menu)
        self._reg_grid_widget = QWidget()
        self._reg_grid_layout = QGridLayout(self._reg_grid_widget)
        self._reg_grid_layout.setContentsMargins(2, 2, 2, 2)
        self._reg_grid_layout.setHorizontalSpacing(4)
        self._reg_grid_layout.setVerticalSpacing(4)
        self._reg_scroll.setWidget(self._reg_grid_widget)
        box_group_layout.addWidget(self._reg_scroll)
        layout.addWidget(box_group)
        self._reg_selected_pokemon: PokemonInstance | None = None

        self._refresh_registry_list()
        self._refresh_data_status()
        return widget

    def _build_box_side_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        party_box = QGroupBox("自分のパーティ")
        party_layout = QVBoxLayout(party_box)

        my_row = QHBoxLayout()
        my_lbl = QLabel("自分:")
        my_lbl.setFixedWidth(36)
        my_row.addWidget(my_lbl)
        self._box_my_slots: list[PartySlot] = []
        for i in range(6):
            slot = PartySlot(i)
            slot.clicked_signal.connect(lambda idx, own=True: self._on_party_slot_clicked(idx, True))
            my_row.addWidget(slot)
            self._box_my_slots.append(slot)
        my_row.addStretch()
        party_layout.addLayout(my_row)

        preset_box = QGroupBox("パーティ保存")
        preset_layout = QHBoxLayout(preset_box)
        preset_layout.setSpacing(6)
        preset_layout.addWidget(QLabel("プリセット:"))
        self._box_preset_combo = QComboBox()
        self._box_preset_combo.setEditable(True)
        self._box_preset_combo.setInsertPolicy(QComboBox.NoInsert)
        self._box_preset_combo.setMinimumWidth(200)
        preset_layout.addWidget(self._box_preset_combo, 1)

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(lambda: self._save_party_preset(self._box_preset_combo.currentText()))
        preset_layout.addWidget(save_btn)
        load_btn = QPushButton("読込")
        load_btn.clicked.connect(lambda: self._load_party_preset(self._box_preset_combo.currentText()))
        preset_layout.addWidget(load_btn)
        del_btn = QPushButton("削除")
        del_btn.setStyleSheet("QPushButton { color: #f38ba8; }")
        del_btn.clicked.connect(lambda: self._delete_party_preset(self._box_preset_combo.currentText()))
        preset_layout.addWidget(del_btn)

        reset_btn = QPushButton("パーティ全リセット")
        reset_btn.setStyleSheet("QPushButton { color: #f38ba8; border: 1px solid #f38ba8; font-weight: bold; }")
        reset_btn.clicked.connect(self._reset_all_party)
        preset_layout.addWidget(reset_btn)

        party_layout.addWidget(preset_box)
        layout.addWidget(party_box)
        layout.addStretch()
        return widget

    def _build_options_dialog(self) -> None:
        self._options_dialog = QDialog(self)
        self._options_dialog.setWindowTitle("オプション")
        self._options_dialog.setModal(False)
        self._options_dialog.setMinimumWidth(420)

        layout = QVBoxLayout(self._options_dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── カメラ ──
        cam_box = QGroupBox("カメラ")
        cam_box_layout = QVBoxLayout(cam_box)
        cam_ctrl = QHBoxLayout()
        cam_ctrl.addWidget(QLabel("カメラ:"))
        self._cam_combo = QComboBox()
        self._cam_combo.setMinimumWidth(140)
        cam_ctrl.addWidget(self._cam_combo)
        self._connect_btn = QPushButton("接続")
        self._connect_btn.clicked.connect(self._toggle_camera)
        cam_ctrl.addWidget(self._connect_btn)
        self._refresh_cam_btn = QPushButton("更新")
        self._refresh_cam_btn.clicked.connect(self._refresh_cameras)
        cam_ctrl.addWidget(self._refresh_cam_btn)
        cam_ctrl.addStretch()
        cam_box_layout.addLayout(cam_ctrl)
        topmost_row = QHBoxLayout()
        self._topmost_cb = QCheckBox("最前面")
        self._topmost_cb.toggled.connect(self._toggle_topmost)
        topmost_row.addWidget(self._topmost_cb)
        topmost_row.addStretch()
        cam_box_layout.addLayout(topmost_row)
        layout.addWidget(cam_box)

        data_box = QGroupBox("データ更新")
        data_layout = QVBoxLayout(data_box)
        season_row = QHBoxLayout()
        season_row.addWidget(QLabel("シーズン:"))
        self._option_season_combo = QComboBox()
        self._option_season_combo.setEditable(True)
        self._option_season_combo.setMinimumWidth(100)
        self._option_season_combo.currentTextChanged.connect(self._on_usage_season_changed)
        season_row.addWidget(self._option_season_combo)
        season_row.addSpacing(20)
        season_row.addWidget(QLabel("データ源:"))
        self._option_source_combo = QComboBox()
        self._option_source_combo.setMinimumWidth(150)
        for source_key, source_label in USAGE_SOURCES.items():
            self._option_source_combo.addItem(source_label, source_key)
        self._option_source_combo.setCurrentIndex(0)
        season_row.addWidget(self._option_source_combo)
        season_row.addStretch()
        data_layout.addLayout(season_row)
        fetch_row = QHBoxLayout()
        self._fetch_api_btn = QPushButton("PokeAPI取得")
        self._fetch_api_btn.clicked.connect(self._fetch_pokeapi_data)
        fetch_row.addWidget(self._fetch_api_btn)
        self._fetch_usage_btn = QPushButton("使用率取得")
        self._fetch_usage_btn.setEnabled(False)
        self._fetch_usage_btn.installEventFilter(self)
        fetch_row.addWidget(self._fetch_usage_btn)
        fetch_row.addStretch()
        data_layout.addLayout(fetch_row)
        self._option_data_status_lbl = QLabel()
        self._option_data_status_lbl.setStyleSheet("color: #a6adc8; font-size: 11px;")
        data_layout.addWidget(self._option_data_status_lbl)
        layout.addWidget(data_box)

        log_box = QGroupBox("ログ")
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(6, 6, 6, 6)
        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setMinimumHeight(180)
        log_layout.addWidget(self._log_edit, 1)
        option_log_clear_btn = QPushButton("ログクリア")
        option_log_clear_btn.setStyleSheet("QPushButton { min-height: 0px; padding: 2px 4px; font-size: 10px; }")
        option_log_clear_btn.setFixedHeight(24)
        option_log_clear_btn.clicked.connect(self._log_edit.clear)
        log_layout.addWidget(option_log_clear_btn, 0)
        layout.addWidget(log_box)

        damage_box = QGroupBox("ダメージ計算")
        damage_layout = QVBoxLayout(damage_box)
        self._option_damage_tera_cb = QCheckBox("右ペーンのテラスタル設定を表示")
        self._option_damage_tera_cb.toggled.connect(self._toggle_damage_tera_option)
        damage_layout.addWidget(self._option_damage_tera_cb)

        self._option_damage_bulk_cb = QCheckBox("無振り/極振りダメージを表示")
        self._option_damage_bulk_cb.setChecked(True)
        self._option_damage_bulk_cb.toggled.connect(self._toggle_damage_bulk_option)
        damage_layout.addWidget(self._option_damage_bulk_cb)

        self._option_damage_double_cb = QCheckBox("ダブルバトルモード（仮）")
        self._option_damage_double_cb.toggled.connect(self._toggle_damage_double_option)
        damage_layout.addWidget(self._option_damage_double_cb)

        layout.addWidget(damage_box)

        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(self._options_dialog.close)
        layout.addWidget(close_btn)

        self._refresh_usage_season_options()
        self._refresh_data_status()
        if self._option_damage_tera_cb:
            self._option_damage_tera_cb.blockSignals(True)
            self._option_damage_tera_cb.setChecked(self._damage_tera_visible)
            self._option_damage_tera_cb.blockSignals(False)

    def _open_options_dialog(self) -> None:
        if not self._options_dialog:
            return
        self._refresh_usage_season_options(self._current_usage_season())
        if self._option_damage_tera_cb:
            self._option_damage_tera_cb.blockSignals(True)
            self._option_damage_tera_cb.setChecked(self._damage_tera_visible)
            self._option_damage_tera_cb.blockSignals(False)
        self._options_dialog.show()
        self._options_dialog.raise_()
        self._options_dialog.activateWindow()

    def _set_fetch_buttons_enabled(self, enabled: bool) -> None:
        if self._fetch_api_btn:
            self._fetch_api_btn.setEnabled(enabled)
        if self._fetch_usage_btn:
            self._fetch_usage_btn.setEnabled(enabled)

    def _refresh_usage_season_options(self, selected: str | None = None) -> None:
        if not self._option_season_combo:
            return
        current = db.normalize_season_token(selected or self._option_season_combo.currentText())
        if not current:
            current = db.get_active_usage_season()
        seasons = list(db.get_available_usage_seasons())
        if current not in seasons:
            seasons.insert(0, current)
        self._option_season_combo.blockSignals(True)
        self._option_season_combo.clear()
        for season in seasons:
            self._option_season_combo.addItem(season)
        if current:
            self._option_season_combo.setEditText(current)
        self._option_season_combo.blockSignals(False)

    def _current_usage_season(self) -> str:
        if self._option_season_combo:
            text = self._option_season_combo.currentText()
            if text and text.strip():
                return db.normalize_season_token(text)
        return db.get_active_usage_season()

    def _on_usage_season_changed(self, text: str) -> None:
        season = db.normalize_season_token(text)
        if not season:
            return
        db.set_active_usage_season(season)
        self._save_settings(usage_season=season)
        if self._option_season_combo and self._option_season_combo.currentText().strip() != season:
            self._option_season_combo.blockSignals(True)
            self._option_season_combo.setEditText(season)
            self._option_season_combo.blockSignals(False)
        self._refresh_data_status()

    def _toggle_damage_tera_option(self, checked: bool) -> None:
        self._damage_tera_visible = bool(checked)
        self._damage_panel.set_terastal_controls_visible(self._damage_tera_visible)
        self._save_settings(damage_show_terastal=self._damage_tera_visible)

    def _toggle_damage_bulk_option(self, checked: bool) -> None:
        self._damage_panel._set_bulk_rows_visible(bool(checked))
        self._save_settings(damage_show_bulk=bool(checked))

    def _toggle_damage_double_option(self, checked: bool) -> None:
        self._damage_panel._set_battle_format("double" if checked else "single")
        self._save_settings(damage_battle_double=bool(checked))

    # ── Background tasks ──────────────────────────────────────────────

    def _start_background_tasks(self) -> None:
        self._ocr_thread = OcrInitThread(use_gpu=False)
        self._ocr_thread.finished.connect(self._on_ocr_ready)
        self._ocr_thread.start()

    # ── Slots ─────────────────────────────────────────────────────────

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

    @pyqtSlot()
    def _on_api_done(self) -> None:
        text_matcher.clear_caches()
        self._set_fetch_buttons_enabled(True)
        self._refresh_data_status()
        self._status_bar.showMessage("PokeAPIデータ取得完了")
        self._log("PokeAPIデータ取得完了")

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
        if self._api_loader and self._api_loader.isRunning():
            return
        self._api_loader = PokeApiLoader()
        self._api_loader.progress.connect(self._on_api_progress)
        self._api_loader.finished.connect(self._on_api_done)
        self._set_fetch_buttons_enabled(False)
        self._status_bar.showMessage("PokeAPIデータ取得を開始")
        self._log("PokeAPIデータ取得を開始")
        self._api_loader.start()

    def _fetch_usage_data(self) -> None:
        season = self._current_usage_season()
        source = self._option_source_combo.currentData() if self._option_source_combo else USAGE_SOURCE_DEFAULT
        db.set_active_usage_season(season)
        status = db.get_local_data_status(season)
        if status["species_count"] == 0 or status["move_count"] == 0:
            QMessageBox.information(
                self,
                "データ不足",
                "先に PokeAPI データを取得してください。",
            )
            return
        if self._scraper and self._scraper.isRunning():
            return
        self._scraper = UsageScraper(season=season, source=source)
        self._scraper.progress.connect(self._on_usage_progress)
        self._scraper.finished.connect(self._on_scraper_done)
        self._set_fetch_buttons_enabled(False)
        source_label = USAGE_SOURCES.get(source, source)
        self._status_bar.showMessage("使用率データ取得を開始 [{}] [{}]".format(season, source_label))
        self._log("使用率データ取得を開始 [{}] [{}]".format(season, source_label))
        self._scraper.start()

    @pyqtSlot(QPixmap)
    def _on_frame(self, pixmap: QPixmap) -> None:
        self._preview_lbl.setPixmap(
            pixmap.scaled(self._preview_lbl.width(), self._preview_lbl.height(),
                          Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # ── Camera control ────────────────────────────────────────────────

    def _refresh_cameras(self) -> None:
        self._cam_combo.clear()
        cameras = VideoThread.list_cameras()
        for idx, name in cameras:
            self._cam_combo.addItem(name, idx)
        if not cameras:
            self._cam_combo.addItem("カメラなし", -1)

    def _toggle_camera(self) -> None:
        if self._video_thread and self._video_thread.isRunning():
            self._stop_live_battle_tracking(show_message=False, write_log=False)
            self._video_thread.stop()
            self._video_thread = None
            self._connect_btn.setText("接続")
            self._preview_lbl.setText("カメラ未接続")
            self._log("カメラ切断")
            return

        idx = self._cam_combo.currentData()
        if idx is None or idx < 0:
            return

        self._video_thread = VideoThread(idx)
        self._video_thread.frame_ready.connect(self._on_frame)
        self._video_thread.start()
        self._connect_btn.setText("切断")
        self._log("カメラ接続: インデックス {}".format(idx))
        self._save_settings(last_camera_index=idx)

    def _save_screenshot(self) -> None:
        if not self._video_thread or not self._video_thread.isRunning():
            QMessageBox.information(self, "情報", "カメラを接続してください")
            return

        frame = self._video_thread.get_last_frame()
        if frame is None or frame.size == 0:
            QMessageBox.information(self, "情報", "保存できるフレームがありません")
            return

        captures_dir = Path.cwd() / "captures"
        captures_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = "{}.png".format(ts)
        out_path = captures_dir / filename

        if not cv2.imwrite(str(out_path), frame):
            QMessageBox.warning(self, "エラー", "スクリーンショット保存に失敗しました")
            return

        self._status_bar.showMessage("保存: {}".format(out_path.name), 5000)
        self._log("スクリーンショット保存: {}".format(out_path))

    # ── Size / position ───────────────────────────────────────────────

    def _apply_splitter_layout(self) -> None:
        self._splitter.insertWidget(1, self._cam_panel)

    def _set_initial_window_size(self) -> None:
        screen = QApplication.primaryScreen()
        if not screen:
            return
        available = screen.availableGeometry()
        target_width = min(
            max(self.minimumWidth(), _RIGHT_PANEL_MIN_WIDTH + _CAM_PANEL_WIDTH + _WINDOW_WIDTH_PADDING),
            available.width(),
        )
        target_height = available.height() - 36
        self.setGeometry(available.left(), available.top(), target_width, target_height)
        self._apply_splitter_layout()

    def _on_damage_tab_visibility(self, index: int) -> None:
        damage_idx = self._tabs.indexOf(self._damage_panel)
        box_idx = 1
        self._damage_side.setVisible(index == damage_idx)
        self._box_side.setVisible(index == box_idx and index != damage_idx)
        self._sync_tab_switcher_buttons(index)

    def _sync_tab_switcher_buttons(self, index: int) -> None:
        if self._tab_damage_btn:
            self._tab_damage_btn.setChecked(index == 0)
        if self._tab_box_btn:
            self._tab_box_btn.setChecked(index == 1)

    # ── Event Filter ───────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        from PyQt5.QtGui import QMouseEvent
        if obj == self._fetch_usage_btn and event.type() == QEvent.MouseButtonDblClick:
            me = QMouseEvent(event)
            if me.button() == Qt.RightButton:
                self._fetch_usage_data()
                return True
        return super().eventFilter(obj, event)

    # ── Logging ───────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        if self._log_edit:
            self._log_edit.append("[{}] {}".format(ts, msg))

    def _init_battle_state(self) -> None:
        self._battle_state = BattleState(
            my_party=[None] * 6,
            opponent_party=[None] * 6,
        )

    def _ensure_party_slots(self) -> None:
        self._battle_state.my_party = (self._battle_state.my_party + [None] * 6)[:6]
        self._battle_state.opponent_party = (self._battle_state.opponent_party + [None] * 6)[:6]

    def _sync_battle_state_to_panels(self) -> None:
        self._ensure_party_slots()
        self._update_box_party_ui()

        self._damage_panel.set_my_party(self._battle_state.my_party)
        if self._battle_state.my_pokemon:
            self._damage_panel.set_my_pokemon(self._battle_state.my_pokemon)

        opp_options: list[PokemonInstance] = []
        if self._battle_state.opponent_pokemon:
            opp_options.append(copy.deepcopy(self._battle_state.opponent_pokemon))
        for pokemon in self._battle_state.opponent_party:
            if not pokemon:
                continue
            if any(existing.name_ja == pokemon.name_ja for existing in opp_options):
                continue
            opp_options.append(copy.deepcopy(pokemon))
        if opp_options:
            self._damage_panel.set_opponent_options(opp_options)

    def _on_party_slot_clicked(self, index: int, is_my: bool) -> None:
        self._ensure_party_slots()
        current_member = self._battle_state.my_party[index] if is_my else self._battle_state.opponent_party[index]
        accepted, selected = self._select_registered_pokemon(
            "自分PT{}番".format(index + 1) if is_my else "相手PT{}番".format(index + 1),
            current_member.name_ja if current_member else "",
        )
        if not accepted:
            return

        target_party = self._battle_state.my_party if is_my else self._battle_state.opponent_party
        previous = target_party[index]
        target_party[index] = copy.deepcopy(selected) if selected else None

        if is_my:
            if selected:
                self._battle_state.my_pokemon = copy.deepcopy(selected)
            elif previous and self._battle_state.my_pokemon and self._battle_state.my_pokemon.name_ja == previous.name_ja:
                self._battle_state.my_pokemon = copy.deepcopy(next((p for p in target_party if p), None))
        else:
            if selected:
                self._battle_state.opponent_pokemon = copy.deepcopy(selected)
            elif previous and self._battle_state.opponent_pokemon and self._battle_state.opponent_pokemon.name_ja == previous.name_ja:
                self._battle_state.opponent_pokemon = copy.deepcopy(next((p for p in target_party if p), None))

        self._sync_battle_state_to_panels()

    def _select_registered_pokemon(self, title: str, current_name: str = "") -> tuple[bool, PokemonInstance | None]:
        self._refresh_registry_list()
        if not self._registered_pokemon:
            QMessageBox.information(self, "情報", "登録済みポケモンがありません。")
            return False, None
        available: list[PokemonInstance] = list(self._registered_pokemon)

        dlg = QDialog(self)
        dlg.setWindowTitle("{} を選択".format(title))
        dlg.setFixedWidth(720)
        dlg.setMinimumHeight(660)
        layout = QVBoxLayout(dlg)

        title_lbl = QLabel("登録済みポケモンから選択します。タイプ絞り込みで候補を絞れます。")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title_lbl)

        search_edit = QLineEdit()
        search_edit.setPlaceholderText("名前・特性・持ち物で検索")
        search_edit.setClearButtonEnabled(True)
        layout.addWidget(search_edit)

        type_box = QGroupBox("タイプ絞り込み")
        type_layout = QVBoxLayout(type_box)
        type_layout.setContentsMargins(6, 6, 6, 6)

        type_grid = QGridLayout()
        type_grid.setHorizontalSpacing(4)
        type_grid.setVerticalSpacing(4)

        type_buttons: dict[str, TypeIconButton] = {}
        for index, type_en in enumerate(TYPE_EN_TO_JA):
            button = TypeIconButton(type_en, show_label=False)
            type_buttons[type_en] = button
            type_grid.addWidget(button, index // 6, index % 6)

        grid_wrap = QHBoxLayout()
        grid_wrap.setContentsMargins(0, 0, 0, 0)
        grid_wrap.addLayout(type_grid)
        grid_wrap.addStretch()
        type_layout.addLayout(grid_wrap)
        layout.addWidget(type_box)

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("並び順:"))
        sort_buttons: dict[str, ChipButton] = {}
        for key, label in (
            ("updated", "更新順"),
            ("name", "名前順"),
            ("type", "タイプ順"),
        ):
            button = ChipButton(label, "#74c7ec")
            sort_buttons[key] = button
            sort_row.addWidget(button)
        sort_row.addStretch()
        layout.addLayout(sort_row)

        list_widget = QListWidget()
        list_widget.itemDoubleClicked.connect(lambda *_: dlg.accept())
        layout.addWidget(list_widget)

        btn_row = QHBoxLayout()
        new_btn = QPushButton("新規")
        clear_btn = QPushButton("クリア")
        select_btn = QPushButton("選択")
        cancel_btn = QPushButton("キャンセル")
        btn_row.addWidget(new_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(select_btn)
        layout.addLayout(btn_row)

        clear_clicked = {"value": False}
        new_selected = {"value": None}
        type_filter = {"value": ""}
        sort_mode = {"value": "updated"}

        def _type_display(pokemon: PokemonInstance) -> str:
            types = [TYPE_EN_TO_JA.get(type_name, type_name) for type_name in (pokemon.types or []) if type_name]
            return " / ".join(types) if types else "---"

        def _apply_filter_button_state() -> None:
            for key, button in type_buttons.items():
                button.blockSignals(True)
                button.setChecked(key == type_filter["value"])
                button.blockSignals(False)
                button._update_style(button.isChecked())

            for key, button in sort_buttons.items():
                button.blockSignals(True)
                button.setChecked(key == sort_mode["value"])
                button.blockSignals(False)
                button._update_style(button.isChecked())

        def _sort_key(order: int, pokemon: PokemonInstance):
            if sort_mode["value"] == "name":
                return (pokemon.name_ja or "", order)
            if sort_mode["value"] == "type":
                first_type = (pokemon.types[0] if pokemon.types else "") if pokemon.types is not None else ""
                type_ja = TYPE_EN_TO_JA.get(first_type, first_type)
                return (type_ja, pokemon.name_ja or "", order)
            return (order,)

        def _matches_keyword(pokemon: PokemonInstance, keyword: str) -> bool:
            if not keyword:
                return True
            haystack = " ".join([
                pokemon.name_ja or "",
                pokemon.name_en or "",
                pokemon.nature or "",
                pokemon.ability or "",
                pokemon.item or "",
            ]).lower()
            return keyword.lower() in haystack

        def _refresh_list() -> None:
            keyword = search_edit.text().strip()
            current_item = list_widget.currentItem()
            current_db_id = current_item.data(Qt.UserRole + 1) if current_item else None
            list_widget.clear()

            filtered: list[tuple[int, PokemonInstance]] = []
            for order, pokemon in enumerate(available):
                if not _matches_keyword(pokemon, keyword):
                    continue
                if type_filter["value"] and type_filter["value"] not in (pokemon.types or []):
                    continue
                filtered.append((order, pokemon))
            filtered.sort(key=lambda x: _sort_key(x[0], x[1]))

            selected_item: QListWidgetItem | None = None
            for _, pokemon in filtered:
                nature_text = (pokemon.nature or "").strip() or "---"
                ability_text = (pokemon.ability or "").strip() or "---"
                item_text = (pokemon.item or "").strip() or "---"
                item = QListWidgetItem(
                    "{}\nタイプ:{}  性格:{}  特性:{}  持ち物:{}".format(
                        pokemon.name_ja or "---",
                        _type_display(pokemon),
                        nature_text,
                        ability_text,
                        item_text,
                    )
                )
                item.setData(Qt.UserRole, pokemon)
                item.setData(Qt.UserRole + 1, pokemon.db_id)
                list_widget.addItem(item)
                if pokemon.db_id and pokemon.db_id == current_db_id:
                    selected_item = item
                elif not selected_item and pokemon.name_ja == current_name:
                    selected_item = item

            if selected_item:
                list_widget.setCurrentItem(selected_item)
                list_widget.scrollToItem(selected_item)
            elif list_widget.count() > 0:
                list_widget.setCurrentRow(0)

        def _set_type_filter(type_name: str) -> None:
            type_filter["value"] = type_name
            _apply_filter_button_state()
            _refresh_list()

        def _set_sort_mode(mode: str) -> None:
            sort_mode["value"] = mode
            _apply_filter_button_state()
            _refresh_list()

        def on_clear() -> None:
            clear_clicked["value"] = True
            dlg.accept()

        def on_new() -> None:
            edit_dialog = open_pokemon_edit_dialog(None, dlg, save_to_db=False)
            if not edit_dialog.exec_():
                return
            created = edit_dialog.get_pokemon()
            if not created:
                return

            new_selected["value"] = copy.deepcopy(created)
            if created.db_id:
                self._refresh_registry_list()
                available.clear()
                available.extend(self._registered_pokemon)
                _refresh_list()
            dlg.accept()

        search_edit.textChanged.connect(lambda _: _refresh_list())
        for key, button in type_buttons.items():
            button.clicked.connect(lambda _=False, value=key: _set_type_filter(value))
        for key, button in sort_buttons.items():
            button.clicked.connect(lambda _=False, value=key: _set_sort_mode(value))

        _apply_filter_button_state()
        _refresh_list()

        new_btn.clicked.connect(on_new)
        clear_btn.clicked.connect(on_clear)
        cancel_btn.clicked.connect(dlg.reject)
        select_btn.clicked.connect(dlg.accept)

        if not dlg.exec_():
            return False, None
        if clear_clicked["value"]:
            return True, None
        if new_selected["value"] is not None:
            return True, new_selected["value"]
        item = list_widget.currentItem()
        if not item:
            return False, None
        selected = item.data(Qt.UserRole)
        return True, copy.deepcopy(selected) if selected else None

    def _auto_detect_opponent_party(self) -> None:
        if not self._video_thread or not self._video_thread.isRunning():
            QMessageBox.information(self, "情報", "カメラを接続してください")
            return
        frame = self._video_thread.get_last_frame()
        if frame is None or frame.size == 0:
            QMessageBox.information(self, "情報", "フレームを取得できませんでした")
            return
        # Freeze the frame at button-press time and keep using this snapshot.
        frame = frame.copy()
        season = self._current_usage_season()
        db.set_active_usage_season(season)
        season_status = db.get_local_data_status(season)
        if int(season_status.get("usage_pokemon_count", 0) or 0) <= 0:
            QMessageBox.information(
                self,
                "使用率データ不足",
                "選択中シーズン [{}] の使用率データがありません。\n先に「使用率取得」を実行してください。".format(season),
            )
            return

        self._set_auto_detect_enabled(False)
        try:
            slot_results = opponent_party_reader.detect_opponent_party(frame, season=season)
            detected_party: list[PokemonInstance | None] = []
            summary: list[str] = []
            for slot in slot_results[:6]:
                if not slot.get("occupied"):
                    detected_party.append(None)
                    summary.append("{}: ---".format(slot["slot_index"] + 1))
                    continue
                slot_types = [str(t) for t in (slot.get("types") or []) if str(t).strip()]
                type_text = "/".join(slot_types) if slot_types else "type:?"
                name = (slot.get("name_ja") or "").strip()
                pokemon = self._build_usage_template_pokemon(name) if name else None
                detected_party.append(pokemon)
                if pokemon:
                    summary.append("{}: {} [{}]".format(slot["slot_index"] + 1, pokemon.name_ja, type_text))
                else:
                    summary.append("{}: --- [{}]".format(slot["slot_index"] + 1, type_text))

            self._battle_state.opponent_party = (detected_party + [None] * 6)[:6]
            self._battle_state.opponent_pokemon = copy.deepcopy(next((p for p in self._battle_state.opponent_party if p), None))
            self._sync_battle_state_to_panels()
            self._log("相手PT自動検出[{}]: {}".format(season, " | ".join(summary)))
            self._status_bar.showMessage("相手PTを自動検出しました [{}]".format(season))
        finally:
            self._set_auto_detect_enabled(True)

    def _toggle_live_battle_tracking(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled:
            if not self._video_thread or not self._video_thread.isRunning():
                QMessageBox.information(self, "情報", "カメラを接続してください")
                return
            if not self._live_battle_timer.isActive():
                self._live_battle_signature = ""
                self._live_battle_timer.start()
                self._status_bar.showMessage("試合中監視を開始しました", 3000)
                self._log("試合中監視: ON")
            return

        self._stop_live_battle_tracking(show_message=True, write_log=True)

    def _stop_live_battle_tracking(self, show_message: bool, write_log: bool) -> None:
        was_active = self._live_battle_timer.isActive()
        self._live_battle_timer.stop()
        if was_active and show_message:
            self._status_bar.showMessage("試合中監視を停止しました", 3000)
        if was_active and write_log:
            self._log("試合中監視: OFF")

    def _poll_live_battle(self) -> None:
        if not self._video_thread or not self._video_thread.isRunning():
            self._stop_live_battle_tracking(show_message=True, write_log=True)
            return
        frame = self._video_thread.get_last_frame()
        if frame is None or frame.size == 0:
            return
        watch_visible, _watch_text = live_battle_reader.is_watch_command_visible(frame)
        if not watch_visible:
            return

        current_my = self._battle_state.my_pokemon.name_ja if self._battle_state.my_pokemon else ""
        current_opp = self._battle_state.opponent_pokemon.name_ja if self._battle_state.opponent_pokemon else ""
        try:
            live_data = live_battle_reader.read_live_battle(
                frame=frame,
                my_party=self._battle_state.my_party,
                opponent_party=self._battle_state.opponent_party,
                current_my_name=current_my,
                current_opp_name=current_opp,
            )
        except Exception as e:
            self._log("[ERROR] 試合中監視エラー: {}".format(e))
            return

        changed, summary = self._apply_live_battle_data(live_data)
        if changed:
            self._sync_battle_state_to_panels()
            if summary and summary != self._live_battle_signature:
                self._live_battle_signature = summary
                self._log("試合中更新: {}".format(summary))

    def _apply_live_battle_data(self, live_data: dict) -> tuple[bool, str]:
        changed = False
        self._ensure_party_slots()

        my_payload = live_data.get("my", {}) if isinstance(live_data, dict) else {}
        opp_payload = live_data.get("opponent", {}) if isinstance(live_data, dict) else {}

        my_name = str(my_payload.get("name_ja") or "").strip()
        opp_name = str(opp_payload.get("name_ja") or "").strip()
        my_member = self._party_member_by_name(self._battle_state.my_party, my_name)
        opp_member = self._party_member_by_name(self._battle_state.opponent_party, opp_name)

        if my_member is None and self._battle_state.my_pokemon:
            my_member = self._party_member_by_name(
                self._battle_state.my_party,
                self._battle_state.my_pokemon.name_ja,
            )
        if opp_member is None and self._battle_state.opponent_pokemon:
            opp_member = self._party_member_by_name(
                self._battle_state.opponent_party,
                self._battle_state.opponent_pokemon.name_ja,
            )
        if my_member is None and self._battle_state.my_pokemon:
            my_member = self._battle_state.my_pokemon
        if opp_member is None and self._battle_state.opponent_pokemon:
            opp_member = self._battle_state.opponent_pokemon

        if my_member:
            my_cur = int(my_payload.get("hp_current", 0) or 0)
            my_max = int(my_payload.get("hp_max", 0) or 0)
            my_pct = float(my_payload.get("hp_percent", -1.0) or -1.0)
            if my_max > 0:
                my_cur = max(0, min(my_cur, my_max))
                if my_member.max_hp != my_max:
                    my_member.max_hp = my_max
                    changed = True
                if my_member.current_hp != my_cur:
                    my_member.current_hp = my_cur
                    changed = True
                new_pct = (float(my_cur) / float(my_max)) * 100.0
                if abs(float(my_member.current_hp_percent) - new_pct) >= 0.2:
                    my_member.current_hp_percent = new_pct
                    changed = True
            elif 0.0 <= my_pct <= 100.0 and my_member.max_hp > 0:
                new_cur = int(round(float(my_member.max_hp) * my_pct / 100.0))
                new_cur = max(0, min(new_cur, my_member.max_hp))
                if my_member.current_hp != new_cur:
                    my_member.current_hp = new_cur
                    changed = True
                if abs(float(my_member.current_hp_percent) - my_pct) >= 0.2:
                    my_member.current_hp_percent = my_pct
                    changed = True

            if (
                not self._battle_state.my_pokemon
                or self._battle_state.my_pokemon.name_ja != my_member.name_ja
                or self._battle_state.my_pokemon.current_hp != my_member.current_hp
                or self._battle_state.my_pokemon.max_hp != my_member.max_hp
            ):
                self._battle_state.my_pokemon = copy.deepcopy(my_member)
                changed = True

        if opp_member:
            opp_pct = float(opp_payload.get("hp_percent", -1.0) or -1.0)
            if 0.0 <= opp_pct <= 100.0:
                if abs(float(opp_member.current_hp_percent) - opp_pct) >= 0.2:
                    opp_member.current_hp_percent = opp_pct
                    changed = True
                if opp_member.max_hp > 0:
                    new_cur = int(round(float(opp_member.max_hp) * opp_pct / 100.0))
                    new_cur = max(0, min(new_cur, opp_member.max_hp))
                    if opp_member.current_hp != new_cur:
                        opp_member.current_hp = new_cur
                        changed = True

            if (
                not self._battle_state.opponent_pokemon
                or self._battle_state.opponent_pokemon.name_ja != opp_member.name_ja
                or abs(float(self._battle_state.opponent_pokemon.current_hp_percent) - float(opp_member.current_hp_percent)) >= 0.2
            ):
                self._battle_state.opponent_pokemon = copy.deepcopy(opp_member)
                changed = True

        my_text = "---"
        if self._battle_state.my_pokemon:
            p = self._battle_state.my_pokemon
            my_text = "{} {}/{}".format(p.name_ja, max(0, int(p.current_hp)), max(0, int(p.max_hp)))
        opp_text = "---"
        if self._battle_state.opponent_pokemon:
            p = self._battle_state.opponent_pokemon
            opp_text = "{} {:.1f}%".format(p.name_ja, float(p.current_hp_percent))
        return changed, "自分 {} | 相手 {}".format(my_text, opp_text)

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
        matched = text_matcher.match_species_name(name_ja)
        if not matched:
            return None
        species = db.get_species_by_name_ja(matched)
        if not species:
            return None

        pokemon = PokemonInstance(
            species_id=species.species_id,
            name_ja=species.name_ja,
            usage_name=species.name_ja,
            name_en=species.name_en,
            types=[t for t in [species.type1, species.type2] if t],
            weight_kg=species.weight_kg,
        )

        abilities = db.get_abilities_by_usage(pokemon.usage_name)
        if abilities:
            pokemon.ability = abilities[0]
        items = db.get_items_by_usage(pokemon.usage_name)
        if items:
            pokemon.item = items[0]
        natures = db.get_natures_by_usage(pokemon.usage_name)
        pokemon.nature = natures[0] if natures else "まじめ"

        spreads = db.get_effort_spreads_by_usage(pokemon.usage_name)
        if spreads:
            hp_pt, attack_pt, defense_pt, sp_attack_pt, sp_defense_pt, speed_pt, _ = spreads[0]
            pokemon.ev_hp = int(hp_pt) * 8
            pokemon.ev_attack = int(attack_pt) * 8
            pokemon.ev_defense = int(defense_pt) * 8
            pokemon.ev_sp_attack = int(sp_attack_pt) * 8
            pokemon.ev_sp_defense = int(sp_defense_pt) * 8
            pokemon.ev_speed = int(speed_pt) * 8

        moves = db.get_moves_by_usage(pokemon.usage_name)
        move_candidates = [move for move in moves if move]
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
        pokemon.moves = (non_status_candidates + ["", "", "", ""])[:4]

        from src.calc.damage_calc import fill_stats_from_species

        fill_stats_from_species(pokemon, species)
        pokemon.max_hp = pokemon.hp
        pokemon.current_hp = pokemon.hp
        pokemon.current_hp_percent = 100.0
        return pokemon

    def _read_box_and_register(self) -> None:
        if not self._video_thread or not self._video_thread.isRunning():
            QMessageBox.information(self, "情報", "カメラを接続してください")
            return
        frame = self._video_thread.get_last_frame()
        if frame is None:
            QMessageBox.information(self, "情報", "フレームを取得できませんでした")
            return
        # Run box OCR in background thread and show loading overlay
        self._start_box_read_thread(frame)

    def _apply_box_ocr(self, data: dict) -> None:
        pokemon = data.get("pokemon")
        if not pokemon or not pokemon.name_ja:
            return
        self._fill_species(pokemon)
        # 常に新規登録する（同一名の複数登録を許可）
        new_id = db.save_pokemon(pokemon)
        pokemon.db_id = new_id
        self._registered_pokemon.append(pokemon)
        self._status_bar.showMessage("{} を自動登録しました".format(pokemon.name_ja))
        self._log("自動登録: {}".format(pokemon.name_ja))
        self._refresh_registry_list()

    # ----------------- Background box read worker and overlay -----------------
    class _BoxReadWorker(QObject):
        finished = pyqtSignal(dict)
        error = pyqtSignal(str)

        def __init__(self, frame: object):
            super().__init__()
            self.frame = frame

        @pyqtSlot()
        def run(self) -> None:
            try:
                from src.recognition import box_reader

                data = box_reader.read_box_screen(self.frame)
                self.finished.emit(data)
            except Exception as e:
                self.error.emit(str(e))

    def _show_loading_overlay(self, message: str = "読み込み中...") -> None:
        try:
            if hasattr(self, "_loading_overlay") and self._loading_overlay:
                self._loading_overlay.raise_()
                return
            overlay = QWidget(self)
            overlay.setObjectName("_loading_overlay")
            overlay.setStyleSheet("background-color: rgba(0, 0, 0, 120);")
            overlay.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            overlay.setGeometry(self.rect())
            layout = QVBoxLayout(overlay)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setAlignment(Qt.AlignCenter)
            lbl = QLabel(message)
            lbl.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
            layout.addWidget(lbl)
            overlay.show()
            overlay.raise_()
            self._loading_overlay = overlay
        except Exception:
            pass

    def _hide_loading_overlay(self) -> None:
        try:
            if hasattr(self, "_loading_overlay") and self._loading_overlay:
                self._loading_overlay.hide()
                self._loading_overlay.deleteLater()
                self._loading_overlay = None
        except Exception:
            pass

    def _start_box_read_thread(self, frame: object) -> None:
        self._show_loading_overlay("ボックス読み込み中...")
        worker = MainWindow._BoxReadWorker(frame)
        thread = QThread(self)
        worker.moveToThread(thread)

        def on_finished(data: dict) -> None:
            thread.quit()
            thread.wait()
            worker.deleteLater()
            self._hide_loading_overlay()
            # Post-process data the same as previous synchronous flow
            if not data.get("name"):
                candidates = ", ".join(data.get("name_candidates", [])[:6]) or "なし"
                QMessageBox.warning(
                    self,
                    "認識失敗",
                    "ボックスのポケモン名を OCR で読めませんでした。\n候補: {}".format(candidates),
                )
                return

            ev_points = data.get("ev_points", {})
            ev_total = sum(ev_points.values())
            if ev_total != 66:
                dlg = QMessageBox(self)
                dlg.setWindowTitle("努力値確認")
                dlg.setText(
                    "努力値の合計が {} 点です（正常: 66 点）。\n"
                    "OCR の読み取りミスの可能性があります。".format(ev_total)
                )
                dlg.addButton("そのまま登録", QMessageBox.AcceptRole)
                rescan_btn = dlg.addButton("再スキャン", QMessageBox.ResetRole)
                cancel_btn = dlg.addButton("キャンセル", QMessageBox.RejectRole)
                dlg.exec_()
                clicked = dlg.clickedButton()
                if clicked == rescan_btn:
                    # start another background read
                    self._start_box_read_thread(frame)
                    return
                elif clicked == cancel_btn:
                    return

            self._apply_box_ocr(data)

        def on_error(msg: str) -> None:
            thread.quit()
            thread.wait()
            worker.deleteLater()
            self._hide_loading_overlay()
            QMessageBox.warning(self, "エラー", "読み込みに失敗しました:\n{}".format(msg))

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        thread.started.connect(worker.run)
        thread.start()

    # ── Registry ─────────────────────────────────────────────────────

    def _refresh_registry_list(self) -> None:
        self._registered_pokemon = db.load_all_pokemon()
        type_filter: set[str] = getattr(self, "_box_type_filter", set())
        filtered = [
            p for p in self._registered_pokemon
            if not type_filter or type_filter.issubset(set(p.types or []))
        ]

        # グリッドウィジェットが存在しない場合は従来のリストにフォールバック
        if not hasattr(self, "_reg_grid_layout"):
            return

        # 既存セルをクリア
        while self._reg_grid_layout.count():
            item = self._reg_grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        from src.ui.ui_utils import sprite_pixmap_or_zukan

        _COLS = 6
        _CELL_W = 112
        _CELL_H = 112
        _SPRITE_SIZE = 72

        for idx, p in enumerate(filtered):
            ev_pairs = [
                ("H", p.ev_hp // 8),
                ("A", p.ev_attack // 8),
                ("B", p.ev_defense // 8),
                ("C", p.ev_sp_attack // 8),
                ("D", p.ev_sp_defense // 8),
                ("S", p.ev_speed // 8),
            ]
            ev_pairs = [(lbl, v) for lbl, v in ev_pairs if v > 0]
            ev_pairs.sort(key=lambda x: (-x[1], "HABCDS".find(x[0]) if x[0] in "HABCDS" else 9))
            top2_ev = " ".join("{}:{}".format(lbl, v) for lbl, v in ev_pairs[:2]) if ev_pairs else "無振り"
            item_text = (p.item or "").strip() or "なし"

            cell = QFrame()
            cell.setFrameShape(QFrame.StyledPanel)
            cell.setFixedSize(_CELL_W, _CELL_H)
            cell.setProperty("pokemon_data", idx)
            cell.setCursor(Qt.PointingHandCursor)
            cell.setStyleSheet(
                "QFrame { border: 2px solid #45475a; border-radius: 4px; background: #1e1e2e; }"
                "QFrame:hover { border: 2px solid #89b4fa; background: #2a2a3e; }"
            )
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(0)

            sprite_lbl = QLabel()
            sprite_lbl.setFixedSize(_SPRITE_SIZE, _SPRITE_SIZE)
            sprite_lbl.setAlignment(Qt.AlignCenter)
            sprite_lbl.setStyleSheet("border: none;")
            pm = sprite_pixmap_or_zukan(p.name_ja, _SPRITE_SIZE, _SPRITE_SIZE, name_en=p.name_en or "")
            if pm:
                sprite_lbl.setPixmap(pm)
            else:
                sprite_lbl.setText(p.name_ja[:4] if p.name_ja else "?")
                sprite_lbl.setStyleSheet("color: #cdd6f4; font-size: 10px;")
            cell_layout.addWidget(sprite_lbl, 0, Qt.AlignHCenter)

            item_lbl = QLabel(item_text)
            item_lbl.setAlignment(Qt.AlignHCenter)
            item_lbl.setFixedHeight(20)
            item_lbl.setStyleSheet("color: #cdd6f4; font-size: 16px; font-weight: bold; border: none;")
            cell_layout.addWidget(item_lbl)

            ev_lbl = QLabel(top2_ev)
            ev_lbl.setAlignment(Qt.AlignHCenter)
            ev_lbl.setFixedHeight(20)
            ev_lbl.setStyleSheet("color: #a6e3a1; font-size: 16px; font-weight: bold; border: none;")
            cell_layout.addWidget(ev_lbl)

            pokemon_ref = p

            def _make_ctx_handler(poke: PokemonInstance, widget: QFrame):
                def handler(pos):
                    self._reg_selected_pokemon = poke
                    self._on_registry_context_menu_for_cell(widget.mapToGlobal(pos))
                return handler

            cell.mouseDoubleClickEvent = lambda e, poke=pokemon_ref: (
                self.__setattr__("_reg_selected_pokemon", poke) or self._edit_selected_pokemon()
            )
            cell.setContextMenuPolicy(Qt.CustomContextMenu)
            cell.customContextMenuRequested.connect(_make_ctx_handler(pokemon_ref, cell))

            self._reg_grid_layout.addWidget(cell, idx // _COLS, idx % _COLS)

        # 残り列をストレッチで埋める
        remainder = len(filtered) % _COLS
        if remainder:
            for col in range(remainder, _COLS):
                spacer = QWidget()
                spacer.setFixedSize(_CELL_W, _CELL_H)
                self._reg_grid_layout.addWidget(spacer, len(filtered) // _COLS, col)

        # 縦方向のストレッチで左上揃えを維持
        next_row = (len(filtered) + _COLS - 1) // _COLS
        self._reg_grid_layout.setRowStretch(next_row, 1)

    def _open_edit_dialog(self, pokemon) -> None:
        base_name = pokemon.name_ja if pokemon else ""
        dlg = open_pokemon_edit_dialog(pokemon, self)
        if dlg.exec_():
            self._refresh_registry_list()
            updated = dlg.get_pokemon()
            if not updated or not base_name:
                return

            self._ensure_party_slots()
            for index, member in enumerate(self._battle_state.my_party):
                if member and member.name_ja == base_name:
                    self._battle_state.my_party[index] = copy.deepcopy(updated)

            if self._battle_state.my_pokemon and self._battle_state.my_pokemon.name_ja == base_name:
                self._battle_state.my_pokemon = copy.deepcopy(updated)

            self._sync_battle_state_to_panels()

    def _edit_selected_pokemon(self) -> None:
        p = getattr(self, "_reg_selected_pokemon", None)
        if not p:
            return
        self._open_edit_dialog(p)

    def _delete_selected_pokemon(self) -> None:
        p = getattr(self, "_reg_selected_pokemon", None)
        if p and p.db_id:
            db.delete_pokemon(p.db_id)
            self._reg_selected_pokemon = None
            self._refresh_registry_list()

    def _on_registry_context_menu(self, pos) -> None:
        pass  # スクロールエリア全体の右クリックは無視（セル右クリックで処理）

    def _on_registry_context_menu_for_cell(self, global_pos) -> None:
        menu = QMenu(self)
        act_edit = QAction("編集", menu)
        act_delete = QAction("削除", menu)
        act_edit.triggered.connect(self._edit_selected_pokemon)
        act_delete.triggered.connect(self._delete_selected_pokemon)
        menu.addAction(act_edit)
        menu.addAction(act_delete)
        menu.exec_(global_pos)

    def _on_damage_panel_atk_changed(self, pokemon: PokemonInstance | None) -> None:
        side = self._damage_panel.attacker_side() if hasattr(self._damage_panel, "attacker_side") else "my"
        copied = copy.deepcopy(pokemon) if pokemon else None
        if side == "opp":
            self._battle_state.opponent_pokemon = copied
        else:
            self._battle_state.my_pokemon = copied
        self._ensure_party_slots()
        self._update_box_party_ui()

    def _on_damage_panel_def_changed(self, pokemon: PokemonInstance | None) -> None:
        side = self._damage_panel.defender_side() if hasattr(self._damage_panel, "defender_side") else "opp"
        copied = copy.deepcopy(pokemon) if pokemon else None
        if side == "my":
            self._battle_state.my_pokemon = copied
        else:
            self._battle_state.opponent_pokemon = copied
        self._ensure_party_slots()
        self._update_box_party_ui()

    # ── Helpers ───────────────────────────────────────────────────────

    def _find_registered(self, name_ja: str) -> PokemonInstance | None:
        target = text_matcher.normalize_ocr_text(text_matcher.match_species_name(name_ja))
        if not target:
            return None
        for p in self._registered_pokemon:
            if text_matcher.normalize_ocr_text(p.name_ja) == target:
                return p
        return None

    def _fill_species(self, pokemon: PokemonInstance) -> None:
        matched_name = text_matcher.match_species_name(pokemon.name_ja)
        if not matched_name:
            return
        pokemon.name_ja = matched_name
        species = db.get_species_by_name_ja(pokemon.name_ja)
        if species:
            pokemon.species_id = species.species_id
            pokemon.name_en = species.name_en
            pokemon.types = [t for t in [species.type1, species.type2] if t]
            pokemon.weight_kg = species.weight_kg
            if pokemon.hp == 0:
                from src.calc.damage_calc import fill_stats_from_species
                fill_stats_from_species(pokemon, species)

    def _serialize_pokemon(self, pokemon: PokemonInstance | None) -> dict | None:
        if not pokemon:
            return None
        return {
            "species_id": int(pokemon.species_id),
            "name_ja": pokemon.name_ja,
            "name_en": pokemon.name_en,
            "types": list(pokemon.types),
            "weight_kg": float(pokemon.weight_kg),
            "level": int(pokemon.level),
            "nature": pokemon.nature,
            "ability": pokemon.ability,
            "item": pokemon.item,
            "hp": int(pokemon.hp),
            "attack": int(pokemon.attack),
            "defense": int(pokemon.defense),
            "sp_attack": int(pokemon.sp_attack),
            "sp_defense": int(pokemon.sp_defense),
            "speed": int(pokemon.speed),
            "ev_hp": int(pokemon.ev_hp),
            "ev_attack": int(pokemon.ev_attack),
            "ev_defense": int(pokemon.ev_defense),
            "ev_sp_attack": int(pokemon.ev_sp_attack),
            "ev_sp_defense": int(pokemon.ev_sp_defense),
            "ev_speed": int(pokemon.ev_speed),
            "iv_hp": int(pokemon.iv_hp),
            "iv_attack": int(pokemon.iv_attack),
            "iv_defense": int(pokemon.iv_defense),
            "iv_sp_attack": int(pokemon.iv_sp_attack),
            "iv_sp_defense": int(pokemon.iv_sp_defense),
            "iv_speed": int(pokemon.iv_speed),
            "moves": list(pokemon.moves),
            "current_hp": int(pokemon.current_hp),
            "current_hp_percent": float(pokemon.current_hp_percent),
            "max_hp": int(pokemon.max_hp),
            "status": pokemon.status,
            "terastal_type": pokemon.terastal_type,
        }

    def _deserialize_pokemon(self, payload: dict | None) -> PokemonInstance | None:
        if not isinstance(payload, dict):
            return None
        pokemon = PokemonInstance()
        for key, value in payload.items():
            if hasattr(pokemon, key):
                setattr(pokemon, key, value)
        return pokemon

    def _load_party_presets(self) -> None:
        settings = self._load_settings()
        raw = settings.get("battle_party_presets", {})
        if not isinstance(raw, dict):
            self._party_presets = {}
            return
        self._party_presets = {
            str(name): value
            for name, value in raw.items()
            if isinstance(name, str) and isinstance(value, dict)
        }

    def _refresh_party_presets_ui(self, selected_name: str = "") -> None:
        names = sorted(self._party_presets.keys())
        self._set_box_preset_names(names, selected_name)

    def _set_box_preset_names(self, names: list[str], selected_name: str = "") -> None:
        if not hasattr(self, "_box_preset_combo"):
            return
        current = selected_name.strip() or self._box_preset_combo.currentText()
        self._box_preset_combo.blockSignals(True)
        self._box_preset_combo.clear()
        for name in names:
            self._box_preset_combo.addItem(name)
        self._box_preset_combo.blockSignals(False)
        if current:
            index = self._box_preset_combo.findText(current)
            if index >= 0:
                self._box_preset_combo.setCurrentIndex(index)
            else:
                self._box_preset_combo.setEditText(current)
        elif self._box_preset_combo.count() > 0:
            self._box_preset_combo.setCurrentIndex(0)
        else:
            self._box_preset_combo.setEditText("")

    def _update_box_party_ui(self) -> None:
        if not hasattr(self, "_box_my_slots"):
            return
        for i, slot in enumerate(self._box_my_slots):
            if i < len(self._battle_state.my_party) and self._battle_state.my_party[i]:
                p = self._battle_state.my_party[i]
                pct = (p.current_hp / p.max_hp * 100) if p.max_hp > 0 else p.current_hp_percent
                slot.set_pokemon(p.name_ja, pct)
            else:
                slot.set_pokemon("", 100)
            slot.set_active(False)
        my_active = self._active_index(self._battle_state.my_party, self._battle_state.my_pokemon)
        if 0 <= my_active < len(self._box_my_slots):
            self._box_my_slots[my_active].set_active(True)

    @staticmethod
    def _active_index(party: list[PokemonInstance | None], active: PokemonInstance | None) -> int:
        if not active or not active.name_ja:
            return -1
        for index, pokemon in enumerate(party):
            if pokemon and pokemon.name_ja == active.name_ja:
                return index
        return -1

    def _set_auto_detect_enabled(self, enabled: bool) -> None:
        if not self._auto_detect_btn:
            return
        enabled = bool(enabled)
        self._auto_detect_btn.setEnabled(enabled)
        self._auto_detect_btn.setText("相手PT検出" if enabled else "検出中...")

    

    def _save_party_preset(self, preset_name: str) -> None:
        name = (preset_name or "").strip()
        if not name:
            name, ok = QInputDialog.getText(self, "PT保存", "プリセット名:")
            if not ok:
                return
            name = (name or "").strip()
        if not name:
            return

        self._ensure_party_slots()
        self._party_presets[name] = {
            "my_party": [self._serialize_pokemon(p) for p in self._battle_state.my_party],
            "opponent_party": [self._serialize_pokemon(p) for p in self._battle_state.opponent_party],
            "my_active_name": self._battle_state.my_pokemon.name_ja if self._battle_state.my_pokemon else "",
            "opp_active_name": self._battle_state.opponent_pokemon.name_ja if self._battle_state.opponent_pokemon else "",
        }
        self._save_settings(battle_party_presets=self._party_presets)
        self._refresh_party_presets_ui(selected_name=name)
        self._status_bar.showMessage("PTプリセットを保存しました: {}".format(name), 4000)
        self._log("PT保存: {}".format(name))

    def _load_party_preset(self, preset_name: str) -> None:
        name = (preset_name or "").strip()
        if not name or name not in self._party_presets:
            QMessageBox.information(self, "情報", "読込対象のプリセットを選択してください。")
            return

        preset = self._party_presets.get(name, {})
        my_party = [self._deserialize_pokemon(item) for item in preset.get("my_party", [])][:6]
        opp_party = [self._deserialize_pokemon(item) for item in preset.get("opponent_party", [])][:6]
        self._battle_state.my_party = (my_party + [None] * 6)[:6]
        self._battle_state.opponent_party = (opp_party + [None] * 6)[:6]

        my_active_name = str(preset.get("my_active_name") or "")
        opp_active_name = str(preset.get("opp_active_name") or "")

        self._battle_state.my_pokemon = copy.deepcopy(
            next((p for p in self._battle_state.my_party if p and p.name_ja == my_active_name), None)
            or next((p for p in self._battle_state.my_party if p), None)
        )
        self._battle_state.opponent_pokemon = copy.deepcopy(
            next((p for p in self._battle_state.opponent_party if p and p.name_ja == opp_active_name), None)
            or next((p for p in self._battle_state.opponent_party if p), None)
        )

        self._sync_battle_state_to_panels()
        self._refresh_party_presets_ui(selected_name=name)
        self._status_bar.showMessage("PTプリセットを読み込みました: {}".format(name), 4000)
        self._log("PT読込: {}".format(name))

    def _delete_party_preset(self, preset_name: str) -> None:
        name = (preset_name or "").strip()
        if not name or name not in self._party_presets:
            QMessageBox.information(self, "情報", "削除対象のプリセットを選択してください。")
            return
        if QMessageBox.question(
            self,
            "削除確認",
            "PTプリセット「{}」を削除しますか？".format(name),
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        del self._party_presets[name]
        self._save_settings(battle_party_presets=self._party_presets)
        self._refresh_party_presets_ui()
        self._status_bar.showMessage("PTプリセットを削除しました: {}".format(name), 4000)
        self._log("PT削除: {}".format(name))

    def _reset_all_party(self) -> None:
        if QMessageBox.question(
            self,
            "パーティ全リセット",
            "自分PT・相手PT・現在の選出をすべてクリアしますか？",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return

        self._battle_state.my_party = [None] * 6
        self._battle_state.opponent_party = [None] * 6
        self._battle_state.my_pokemon = None
        self._battle_state.opponent_pokemon = None
        self._sync_battle_state_to_panels()
        self._status_bar.showMessage("パーティを全リセットしました", 4000)
        self._log("PT全リセット")

    def _toggle_topmost(self, checked: bool) -> None:
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        self.show()

    def _refresh_data_status(self) -> None:
        season = self._current_usage_season()
        db.set_active_usage_season(season)
        status = db.get_local_data_status(season)
        text = (
            "ローカルデータ: 種族{} / 技{} / learnset{} / 使用率{} [{}]".format(
                status["species_count"],
                status["move_count"],
                status["learnset_species_count"],
                status["usage_pokemon_count"],
                season,
            )
        )
        if hasattr(self, "_data_status_lbl") and self._data_status_lbl:
            self._data_status_lbl.setText(text)
        if self._option_data_status_lbl:
            self._option_data_status_lbl.setText(text)

    # ── Settings persistence ──────────────────────────────────────────

    def _settings_path(self) -> Path:
        return Path.home() / ".pokemon_damage_calc" / "settings.json"

    def _load_settings(self) -> dict:
        try:
            p = self._settings_path()
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_settings(self, **kwargs) -> None:
        try:
            p = self._settings_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            current: dict = {}
            if p.exists():
                try:
                    current = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    pass
            current.update(kwargs)
            p.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _apply_saved_settings(self) -> None:
        settings = self._load_settings()
        season = db.normalize_season_token(settings.get("usage_season", db.DEFAULT_USAGE_SEASON))
        db.set_active_usage_season(season)
        self._refresh_usage_season_options(season)
        self._damage_tera_visible = bool(settings.get("damage_show_terastal", False))
        self._damage_panel.set_terastal_controls_visible(self._damage_tera_visible)
        if self._option_damage_tera_cb:
            self._option_damage_tera_cb.blockSignals(True)
            self._option_damage_tera_cb.setChecked(self._damage_tera_visible)
            self._option_damage_tera_cb.blockSignals(False)

        show_bulk = bool(settings.get("damage_show_bulk", True))
        self._damage_panel._set_bulk_rows_visible(show_bulk, refresh=False)
        if self._option_damage_bulk_cb:
            self._option_damage_bulk_cb.blockSignals(True)
            self._option_damage_bulk_cb.setChecked(show_bulk)
            self._option_damage_bulk_cb.blockSignals(False)

        is_double = bool(settings.get("damage_battle_double", False))
        self._damage_panel._set_battle_format("double" if is_double else "single")
        if self._option_damage_double_cb:
            self._option_damage_double_cb.blockSignals(True)
            self._option_damage_double_cb.setChecked(is_double)
            self._option_damage_double_cb.blockSignals(False)

        self._refresh_data_status()

    def _auto_connect_saved_camera(self) -> None:
        settings = self._load_settings()
        last_idx = settings.get("last_camera_index")
        if last_idx is None:
            return
        for i in range(self._cam_combo.count()):
            if self._cam_combo.itemData(i) == last_idx:
                self._cam_combo.setCurrentIndex(i)
                self._toggle_camera()
                self._log("前回のカメラに自動接続 (index {})".format(last_idx))
                return

    def closeEvent(self, event) -> None:
        self._stop_live_battle_tracking(show_message=False, write_log=False)
        if self._video_thread:
            self._video_thread.stop()
        event.accept()
