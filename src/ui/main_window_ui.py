"""Extracted methods from main_window.py."""
from __future__ import annotations


def _bootstrap() -> None:
    from src.ui import main_window as _mw
    globals().update(_mw.__dict__)

def _get_usage_scraper_symbols(self):
    _bootstrap()
    try:
        from src.data.usage_scraper import UsageScraper, USAGE_SOURCES, USAGE_SOURCE_DEFAULT

        return UsageScraper, dict(USAGE_SOURCES), str(USAGE_SOURCE_DEFAULT), None
    except ImportError as exc:
        return None, dict(_USAGE_SOURCES_FALLBACK), _USAGE_SOURCE_DEFAULT_FALLBACK, str(exc)

# ── UI Build ──────────────────────────────────────────────────────



def _build_ui(self) -> None:
    _bootstrap()
    old_damage_panel = getattr(self, "_damage_panel", None)
    if old_damage_panel is not None:
        try:
            old_damage_panel.attacker_changed.disconnect(self._on_damage_panel_atk_changed)
            old_damage_panel.defender_changed.disconnect(self._on_damage_panel_def_changed)
            old_damage_panel.registry_maybe_changed.disconnect(self._refresh_registry_list)
            old_damage_panel.bridge_payload_logged.disconnect(self._on_bridge_payload_log)
        except (RuntimeError, TypeError):
            pass

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
    self._damage_panel.bridge_payload_logged.connect(self._on_bridge_payload_log)
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

    combined_row = QHBoxLayout()
    combined_row.setContentsMargins(0, 0, 0, 0)
    combined_row.setSpacing(4)

    switcher_col = QVBoxLayout()
    switcher_col.setContentsMargins(0, 0, 0, 0)
    switcher_col.setSpacing(4)

    self._tab_damage_btn = QPushButton("ダ\nメ\n|\nジ\n計\n算")
    self._tab_damage_btn.setCheckable(True)
    self._tab_damage_btn.setFlat(True)
    self._tab_damage_btn.setFixedSize(40, 130)
    self._tab_damage_btn.setStyleSheet(
        "QPushButton{"
        "font-weight:bold;border-top-left-radius:0px;border-bottom-left-radius:0px;"
        "border-top-right-radius:4px;border-bottom-right-radius:4px;font-size:13px;padding:0px;margin:0px;"
        "min-height:130px;max-height:130px;min-width:40px;max-width:40px;"
        "border-left:0px;border-top:1px solid #45475a;border-right:1px solid #45475a;border-bottom:1px solid #45475a;}"
        "QPushButton:checked{background-color:#1E1E2E;color:#CDD6F4;}"
        "QPushButton:checked:disabled{background-color:#1E1E2E;color:#CDD6F4;}"
        "QPushButton:!checked{background-color:#CDD6F4;color:#1E1E2E;}"
        "QPushButton:!checked:disabled{background-color:#CDD6F4;color:#1E1E2E;}"
        "QPushButton:!checked:hover{background-color:#89b4fa;color:#1E1E2E;}"
    )
    self._tab_damage_btn.clicked.connect(lambda: self._tabs.setCurrentIndex(0) if self._tabs.currentIndex() != 0 else None)
    switcher_col.addWidget(self._tab_damage_btn)

    self._tab_box_btn = QPushButton("ボ\nッ\nク\nス")
    self._tab_box_btn.setCheckable(True)
    self._tab_box_btn.setFlat(True)
    self._tab_box_btn.setFixedSize(40, 90)
    self._tab_box_btn.setStyleSheet(
        "QPushButton{"
        "font-weight:bold;border-top-left-radius:0px;border-bottom-left-radius:0px;"
        "border-top-right-radius:4px;border-bottom-right-radius:4px;font-size:13px;padding:0px;margin:0px;"
        "min-height:90px;max-height:90px;min-width:40px;max-width:40px;"
        "border-left:0px;border-top:1px solid #45475a;border-right:1px solid #45475a;border-bottom:1px solid #45475a;}"
        "QPushButton:checked{background-color:#1E1E2E;color:#CDD6F4;}"
        "QPushButton:checked:disabled{background-color:#1E1E2E;color:#CDD6F4;}"
        "QPushButton:!checked{background-color:#CDD6F4;color:#1E1E2E;}"
        "QPushButton:!checked:disabled{background-color:#CDD6F4;color:#1E1E2E;}"
        "QPushButton:!checked:hover{background-color:#89b4fa;color:#1E1E2E;}"
    )
    self._tab_box_btn.clicked.connect(lambda: self._tabs.setCurrentIndex(1) if self._tabs.currentIndex() != 1 else None)
    switcher_col.addWidget(self._tab_box_btn)
    switcher_col.addStretch()

    combined_row.addLayout(switcher_col)

    left_column = QVBoxLayout()
    left_column.setContentsMargins(0, 0, 0, 0)
    left_column.setSpacing(4)

    opt_row = QHBoxLayout()
    opt_row.setSpacing(4)
    opt_row.setContentsMargins(0, 0, 0, 0)
    self._options_btn = QPushButton("オプション")
    self._options_btn.clicked.connect(self._open_options_dialog)
    opt_row.addWidget(self._options_btn)
    self._shot_btn = QPushButton("キャプチャ")
    self._shot_btn.clicked.connect(self._save_screenshot)
    opt_row.addWidget(self._shot_btn)
    self._auto_detect_btn = QPushButton("相手PT自動検出")
    self._auto_detect_btn.setStyleSheet(
        "QPushButton { background-color: #f38ba8; color: #11111b; font-weight: bold; }"
    )
    self._auto_detect_btn.setCheckable(True)
    self._auto_detect_btn.toggled.connect(self._on_auto_detect_toggled)
    self._refresh_auto_detect_button_style()
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

    self._main_log_edit = QTextEdit()
    self._main_log_edit.setReadOnly(True)
    self._main_log_edit.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    self._main_log_edit.setLineWrapMode(QTextEdit.NoWrap)
    self._main_log_edit.setMaximumWidth(250)
    self._main_log_edit.setStyleSheet(
        "QTextEdit{background:#1e1e2e;color:#cdd6f4;border:1px solid #45475a;"
        "border-radius:4px;font-size:11px;}"
    )
    combined_row.addWidget(self._main_log_edit, 1)

    cam_layout.addLayout(combined_row, 0)

    self._damage_side = self._damage_panel.side_panel
    cam_layout.addWidget(self._damage_side, 1)
    self._damage_side.setVisible(False)
    self._detect_opponent_btn = QPushButton("相手PT検出")
    _detect_base_w = self._detect_opponent_btn.sizeHint().width()
    self._detect_opponent_btn.setFixedSize(
        max(1, int(_detect_base_w * 1.14)),
        56,
    )
    self._detect_opponent_btn.setMinimumHeight(56)
    self._detect_opponent_btn.setMaximumHeight(56)
    self._detect_opponent_btn.setStyleSheet(
        "QPushButton{background:#313244;border:1px solid #f38ba8;color:#f38ba8;"
        "font-weight:bold;border-radius:4px;font-size:13px;padding:0 8px;"
        "min-height:56px;max-height:56px;}"
        "QPushButton:hover{background:#4a2b35;}"
        "QPushButton:disabled{border-color:#585b70;color:#585b70;}"
    )
    self._detect_opponent_btn.clicked.connect(self._auto_detect_opponent_party)
    self._damage_panel.set_opp_party_action_widget(self._detect_opponent_btn)

    self._box_side = self._build_box_side_panel()
    self._box_side_scroll = QScrollArea()
    self._box_side_scroll.setWidgetResizable(True)
    self._box_side_scroll.setFrameShape(QFrame.NoFrame)
    self._box_side_scroll.setWidget(self._box_side)
    cam_layout.addWidget(self._box_side_scroll, 1)
    self._box_side_scroll.setVisible(False)

    cam_layout.addStretch()

    self._cam_panel.setFixedWidth(_CAM_PANEL_WIDTH)

    # Add widgets to splitter (camera right by default)
    self._splitter.addWidget(self._right_panel)
    self._splitter.addWidget(self._cam_panel)
    self._root_layout.addWidget(self._splitter)

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
    _bootstrap()
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(6, 6, 6, 6)

    btn_row = QHBoxLayout()
    read_box_btn = QPushButton("ボックスから読み込む")
    read_box_btn.setStyleSheet("QPushButton { background-color: #89b4fa; color: #1e1e2e; font-weight: bold; }")
    read_box_btn.clicked.connect(self._read_box_and_register)
    btn_row.addWidget(read_box_btn)
    add_btn = QPushButton("+ 新規登録")
    add_btn.clicked.connect(self._open_register_input_dialog)
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

    btn_row.addStretch()
    layout.addLayout(btn_row)

    # (3×6)
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

    box_group = QGroupBox("ボックス")
    box_group_layout = QVBoxLayout(box_group)
    box_group_layout.setContentsMargins(6, 4, 6, 6)

    self._reg_scroll = QScrollArea()
    self._reg_scroll.setWidgetResizable(True)
    self._reg_scroll.setFrameShape(QFrame.NoFrame)
    self._reg_scroll.setMinimumHeight(180)
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
    _bootstrap()
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(6)

    party_box = QGroupBox("自分のパーティ")
    party_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    party_layout = QVBoxLayout(party_box)

    party_row = QHBoxLayout()
    party_row.setContentsMargins(0, 0, 0, 0)
    party_row.setSpacing(6)
    self._box_my_panel = _MyPartyPanel(self)
    self._box_my_panel.dropped_signal.connect(self._on_my_party_panel_dropped)
    self._box_my_panel.clear_signal.connect(self._on_my_party_panel_cleared)
    self._box_my_panel.context_menu_signal.connect(self._on_my_party_panel_context_menu)
    party_row.addWidget(self._box_my_panel, 1)
    self._box_my_save_btn = QPushButton("保\n存")
    self._box_my_save_btn.setFixedWidth(41)
    self._box_my_save_btn.setFixedHeight(self._box_my_panel.minimumHeight())
    self._box_my_save_btn.clicked.connect(self._save_party_preset)
    party_row.addWidget(self._box_my_save_btn)
    party_layout.addLayout(party_row)
    layout.addWidget(party_box)

    saved_box = QGroupBox("保存済みパーティ")
    saved_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    saved_layout = QVBoxLayout(saved_box)
    saved_layout.setContentsMargins(6, 6, 6, 6)
    saved_layout.setSpacing(4)
    saved_scroll = QScrollArea()
    saved_scroll.setWidgetResizable(True)
    saved_scroll.setFrameShape(QFrame.NoFrame)
    saved_scroll.setMinimumHeight(240)
    saved_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    saved_widget = QWidget()
    self._saved_party_list_layout = QVBoxLayout(saved_widget)
    self._saved_party_list_layout.setContentsMargins(0, 0, 0, 0)
    self._saved_party_list_layout.setSpacing(4)
    saved_scroll.setWidget(saved_widget)
    saved_layout.addWidget(saved_scroll)
    layout.addWidget(saved_box)
    layout.setStretch(0, 0)
    layout.setStretch(1, 1)
    return widget



def _build_options_dialog(self) -> None:
    _bootstrap()
    from src.ui.ui_utils import make_dialog
    self._options_dialog = make_dialog(self)
    self._options_dialog.setWindowTitle("オプション")
    self._options_dialog.setModal(False)
    self._options_dialog.setMinimumSize(760, 600)

    layout = QVBoxLayout(self._options_dialog)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)
    content_row = QHBoxLayout()
    content_row.setContentsMargins(0, 0, 0, 0)
    content_row.setSpacing(8)
    left_col = QVBoxLayout()
    left_col.setContentsMargins(0, 0, 0, 0)
    left_col.setSpacing(8)
    right_col = QVBoxLayout()
    right_col.setContentsMargins(0, 0, 0, 0)
    right_col.setSpacing(8)
    layout.addLayout(content_row, 1)
    content_row.addLayout(left_col, 1)
    content_row.addLayout(right_col, 1)

    data_box = QGroupBox("データ更新")
    data_layout = QVBoxLayout(data_box)
    fetch_row = QHBoxLayout()
    self._fetch_api_btn = QPushButton("PokeAPI取得")
    self._fetch_api_btn.clicked.connect(self._fetch_pokeapi_data)
    fetch_row.addWidget(self._fetch_api_btn)
    self._fetch_usage_btn = QPushButton("使用率取得")
    self._fetch_usage_btn.setEnabled(False)
    self._fetch_usage_btn.installEventFilter(self)
    fetch_row.addWidget(self._fetch_usage_btn)
    check_integrity_btn = QPushButton("整合性チェック")
    check_integrity_btn.clicked.connect(self._run_data_integrity_check)
    fetch_row.addWidget(check_integrity_btn)
    fetch_row.addStretch()
    data_layout.addLayout(fetch_row)
    self._option_data_status_lbl = QLabel()
    self._option_data_status_lbl.setStyleSheet("color: #a6adc8; font-size: 11px;")
    data_layout.addWidget(self._option_data_status_lbl)
    data_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    data_box.setFixedHeight(140)
    left_col.addWidget(data_box)

    damage_box = QGroupBox("ダメージ計算")
    damage_layout = QVBoxLayout(damage_box)
    self._option_damage_tera_cb = QCheckBox("テラスタル設定を表示")
    self._option_damage_tera_cb.toggled.connect(self._toggle_damage_tera_option)
    damage_layout.addWidget(self._option_damage_tera_cb)

    self._option_damage_bulk_cb = QCheckBox("無振り/極振りダメージを表示")
    self._option_damage_bulk_cb.setChecked(True)
    self._option_damage_bulk_cb.toggled.connect(self._toggle_damage_bulk_option)
    damage_layout.addWidget(self._option_damage_bulk_cb)

    self._option_damage_double_cb = QCheckBox("ダブルバトル（仮）")
    self._option_damage_double_cb.toggled.connect(self._toggle_damage_double_option)
    damage_layout.addWidget(self._option_damage_double_cb)
    reset_btn = QPushButton("パーティ全リセット")
    reset_btn.setStyleSheet("QPushButton { color: #f38ba8; border: 1px solid #f38ba8; font-weight: bold; }")
    reset_btn.clicked.connect(self._reset_all_party)
    damage_layout.addWidget(reset_btn)
    damage_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    damage_box.setFixedHeight(170)

    left_col.addWidget(damage_box)

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
    cam_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    cam_box.setFixedHeight(90)
    left_col.addWidget(cam_box)

    other_box = QGroupBox("その他")
    other_layout = QVBoxLayout(other_box)
    self._topmost_cb = QCheckBox("最前面")
    self._topmost_cb.toggled.connect(self._toggle_topmost)
    other_layout.addWidget(self._topmost_cb)
    self._option_detailed_log_cb = QCheckBox("詳細ログ")
    self._option_detailed_log_cb.toggled.connect(self._toggle_detailed_log_option)
    other_layout.addWidget(self._option_detailed_log_cb)
    webhook_row = QHBoxLayout()
    webhook_row.setSpacing(4)
    webhook_row.addWidget(QLabel("Discord Webhook URL:"))
    from PyQt5.QtWidgets import QLineEdit
    self._webhook_url_edit = QLineEdit()
    self._webhook_url_edit.setPlaceholderText("https://discord.com/api/webhooks/...")
    self._webhook_url_edit.editingFinished.connect(self._on_webhook_url_changed)
    webhook_row.addWidget(self._webhook_url_edit, 1)
    other_layout.addLayout(webhook_row)
    other_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    left_col.addWidget(other_box)

    log_box = QGroupBox("ログ")
    log_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    log_layout = QVBoxLayout(log_box)
    log_layout.setContentsMargins(6, 6, 6, 6)
    self._log_edit = QTextEdit()
    self._log_edit.setReadOnly(True)
    log_layout.addWidget(self._log_edit, 1)
    log_btn_row = QHBoxLayout()
    option_log_clear_btn = QPushButton("ログクリア")
    option_log_clear_btn.clicked.connect(self._log_edit.clear)
    log_btn_row.addWidget(option_log_clear_btn, 1)
    option_log_export_btn = QPushButton("ログをTXT出力")
    option_log_export_btn.clicked.connect(self._export_log_to_txt)
    log_btn_row.addWidget(option_log_export_btn, 1)
    log_layout.addLayout(log_btn_row)
    right_col.addWidget(log_box, 1)

    close_btn = QPushButton("閉じる")
    close_btn.clicked.connect(self._options_dialog.close)
    layout.addWidget(close_btn)

    self._refresh_usage_season_options()
    self._refresh_data_status()
    if self._option_damage_tera_cb:
        self._option_damage_tera_cb.blockSignals(True)
        self._option_damage_tera_cb.setChecked(self._damage_tera_visible)
        self._option_damage_tera_cb.blockSignals(False)
    if self._option_detailed_log_cb:
        self._option_detailed_log_cb.blockSignals(True)
        self._option_detailed_log_cb.setChecked(self._detailed_log_enabled)
        self._option_detailed_log_cb.blockSignals(False)



def _open_options_dialog(self) -> None:
    _bootstrap()
    if not self._options_dialog:
        return
    self._refresh_usage_season_options(self._current_usage_season())
    if self._option_damage_tera_cb:
        self._option_damage_tera_cb.blockSignals(True)
        self._option_damage_tera_cb.setChecked(self._damage_tera_visible)
        self._option_damage_tera_cb.blockSignals(False)
    if self._option_detailed_log_cb:
        self._option_detailed_log_cb.blockSignals(True)
        self._option_detailed_log_cb.setChecked(self._detailed_log_enabled)
        self._option_detailed_log_cb.blockSignals(False)
    on_top = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
    self._options_dialog.setWindowFlag(Qt.WindowStaysOnTopHint, on_top)
    self._options_dialog.show()
    self._options_dialog.raise_()
    self._options_dialog.activateWindow()



def _set_fetch_buttons_enabled(self, enabled: bool) -> None:
    _bootstrap()
    if self._fetch_api_btn:
        self._fetch_api_btn.setEnabled(enabled)
    if self._fetch_usage_btn:
        self._fetch_usage_btn.setEnabled(enabled and not getattr(sys, "frozen", False))



def _refresh_usage_season_options(self, selected: str | None = None) -> None:
    _bootstrap()
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



def _apply_splitter_layout(self) -> None:
    _bootstrap()
    self._splitter.insertWidget(1, self._cam_panel)



def _set_initial_window_size(self) -> None:
    _bootstrap()
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
    _bootstrap()
    damage_idx = self._tabs.indexOf(self._damage_panel)
    box_idx = 1
    self._damage_side.setVisible(index == damage_idx)
    is_box = index == box_idx and index != damage_idx
    self._box_side_scroll.setVisible(is_box)
    if is_box:
        self._refresh_party_presets_ui()
    self._sync_tab_switcher_buttons(index)



def _sync_tab_switcher_buttons(self, index: int) -> None:
    _bootstrap()
    if self._tab_damage_btn:
        self._tab_damage_btn.setChecked(index == 0)
        self._tab_damage_btn.setEnabled(index != 0)
    if self._tab_box_btn:
        self._tab_box_btn.setChecked(index == 1)
        self._tab_box_btn.setEnabled(index != 1)

# ── Event Filter ───────────────────────────────────────────────────



def _show_usage_password_dialog(self) -> None:
    _bootstrap()
    from datetime import date
    from PyQt5.QtWidgets import QLineEdit
    today = date.today().strftime("%Y%m%d")
    
    password, ok = QInputDialog.getText(
        self,
        "",
        "",
        echo=QLineEdit.Password,
    )
    
    if not ok or not password:
        return
    
    if password == today:
        self._show_usage_fetch_dialog()
    else:
        QMessageBox.warning(self, "エラー", "パスワードが間違っています。")



def _show_usage_fetch_dialog(self) -> None:
    _bootstrap()
    from src.ui.ui_utils import make_dialog
    dlg = make_dialog(self)
    dlg.setWindowTitle("使用率取得設定")
    dlg.setMinimumWidth(400)
    
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)
    
    season_row = QHBoxLayout()
    season_row.addWidget(QLabel("シーズン:"))
    season_combo = QComboBox()
    season_combo.setEditable(True)
    season_combo.setMinimumWidth(150)
    seasons = list(db.get_available_usage_seasons())
    current = db.get_active_usage_season()
    if current not in seasons:
        seasons.insert(0, current)
    for season in seasons:
        season_combo.addItem(season)
    if current:
        season_combo.setEditText(current)
    season_row.addWidget(season_combo)
    season_row.addStretch()
    layout.addLayout(season_row)
    
    source_row = QHBoxLayout()
    source_row.addWidget(QLabel("データ源:"))
    source_combo = QComboBox()
    source_combo.setMinimumWidth(150)
    _, usage_sources, _, _ = self._get_usage_scraper_symbols()
    for source_key, source_label in usage_sources.items():
        source_combo.addItem(source_label, source_key)
    # pokedb_tokyo
    for i in range(source_combo.count()):
        if source_combo.itemData(i) == "pokedb_tokyo":
            source_combo.setCurrentIndex(i)
            break
    source_row.addWidget(source_combo)
    source_row.addStretch()
    layout.addLayout(source_row)
    
    btn_row = QHBoxLayout()
    start_btn = QPushButton("開始")
    cancel_btn = QPushButton("キャンセル")
    btn_row.addStretch()
    btn_row.addWidget(cancel_btn)
    btn_row.addWidget(start_btn)
    layout.addLayout(btn_row)
    
    def on_start():
        season = db.normalize_season_token(season_combo.currentText())
        source = source_combo.currentData()
        if not season:
            QMessageBox.warning(dlg, "エラー", "シーズンを入力してください。")
            return
        db.set_active_usage_season(season)
        dlg.accept()
        self._fetch_usage_data_with_source(season, source)
    
    start_btn.clicked.connect(on_start)
    cancel_btn.clicked.connect(dlg.reject)
    
    dlg.exec_()



def _refresh_auto_detect_button_style(self) -> None:
    _bootstrap()
    if not self._auto_detect_btn:
        return
    active = self._auto_detect_btn.isChecked()
    if active:
        self._auto_detect_btn.setText("相手PT自動検出中...")
        self._auto_detect_btn.setStyleSheet(
            "QPushButton { background-color: #11111b; color: #f38ba8; font-weight: bold; border: 1px solid #f38ba8; }"
        )
    else:
        self._auto_detect_btn.setText("相手PT自動検出")
        self._auto_detect_btn.setStyleSheet(
            "QPushButton { background-color: #f38ba8; color: #11111b; font-weight: bold; }"
        )



def _show_loading_overlay(self, message: str = "読み込み中...") -> None:
    _bootstrap()
    try:
        if hasattr(self, "_loading_overlay") and self._loading_overlay:
            labels = self._loading_overlay.findChildren(QLabel)
            if labels:
                labels[0].setText(message)
            self._loading_overlay.raise_()
            self._loading_overlay.show()
            QApplication.processEvents()
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
        QApplication.processEvents()
    except (RuntimeError, AttributeError, TypeError) as exc:
        traceback.print_exc()
        self._log("[ERROR] ローディングオーバーレイ表示失敗: {}".format(exc))



def _hide_loading_overlay(self) -> None:
    _bootstrap()
    try:
        if hasattr(self, "_loading_overlay") and self._loading_overlay:
            self._loading_overlay.hide()
            self._loading_overlay.deleteLater()
            self._loading_overlay = None
    except (RuntimeError, AttributeError, TypeError) as exc:
        self._log("[ERROR] ローディングオーバーレイ非表示失敗: {}".format(exc))



def _refresh_party_presets_ui(self, selected_name: str = "") -> None:
    _bootstrap()
    if self._saved_party_list_layout is None:
        return
    while self._saved_party_list_layout.count():
        item = self._saved_party_list_layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
    if not self._party_presets:
        empty_lbl = QLabel("保存済みパーティはありません")
        empty_lbl.setStyleSheet("color:#a6adc8; font-size:11px;")
        self._saved_party_list_layout.addWidget(empty_lbl)
        self._saved_party_list_layout.addStretch()
        return
    for index, preset in enumerate(self._party_presets):
        row = _SavedPartyPanel(index, list(preset.get("my_party", [])), self)
        row.context_menu_signal.connect(self._on_saved_party_panel_context_menu)
        row.reorder_signal.connect(self._reorder_party_preset)
        row.move_to_top_signal.connect(self._move_saved_party_to_top)
        self._saved_party_list_layout.addWidget(row)
    self._saved_party_list_layout.addStretch()



def _update_box_party_ui(self) -> None:
    _bootstrap()
    if not hasattr(self, "_box_my_panel"):
        return
    my_active = self._active_index(self._battle_state.my_party, self._battle_state.my_pokemon)
    self._box_my_panel.set_party(self._battle_state.my_party, active_idx=my_active)



def _set_auto_detect_enabled(self, enabled: bool) -> None:
    _bootstrap()
    if not self._detect_opponent_btn:
        return
    enabled = bool(enabled)
    self._detect_opponent_btn.setEnabled(enabled)
    self._detect_opponent_btn.setText("相手PT検出" if enabled else "検出中...")





def _toggle_topmost(self, checked: bool) -> None:
    _bootstrap()
    options_was_visible = bool(self._options_dialog and self._options_dialog.isVisible())
    options_pos = self._options_dialog.pos() if self._options_dialog else None
    self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
    self.show()
    if self._options_dialog:
        self._options_dialog.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        if options_was_visible:
            if options_pos is not None:
                self._options_dialog.move(options_pos)
            self._options_dialog.show()
            # setWindowFlag can reorder windows on Windows; restore front order
            # after Qt flushes native window updates.
            QTimer.singleShot(
                0,
                lambda: (
                    self._options_dialog.raise_(),
                    self._options_dialog.activateWindow(),
                ),
            )



def _refresh_data_status(self) -> None:
    _bootstrap()
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



