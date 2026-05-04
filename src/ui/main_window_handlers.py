"""Extracted methods from main_window.py."""
from __future__ import annotations

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot


def _bootstrap() -> None:
    from src.ui import main_window as _mw
    globals().update(_mw.__dict__)

def _current_usage_season(self) -> str:
    _bootstrap()
    if self._option_season_combo:
        text = self._option_season_combo.currentText()
        if text and text.strip():
            return db.normalize_season_token(text)
    return db.get_active_usage_season()



def _on_usage_season_changed(self, text: str) -> None:
    _bootstrap()
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
    _bootstrap()
    self._damage_tera_visible = bool(checked)
    self._damage_panel.set_terastal_controls_visible(self._damage_tera_visible)
    self._save_settings(damage_show_terastal=self._damage_tera_visible)



def _toggle_damage_bulk_option(self, checked: bool) -> None:
    _bootstrap()
    self._damage_panel._set_bulk_rows_visible(bool(checked))
    self._save_settings(damage_show_bulk=bool(checked))



def _toggle_damage_double_option(self, checked: bool) -> None:
    _bootstrap()
    self._damage_panel._set_battle_format("double" if checked else "single")
    self._save_settings(damage_battle_double=bool(checked))



def _toggle_detailed_log_option(self, checked: bool) -> None:
    _bootstrap()
    self._detailed_log_enabled = bool(checked)
    self._save_settings(detailed_log_enabled=self._detailed_log_enabled)


def _on_webhook_url_changed(self) -> None:
    _bootstrap()
    if not hasattr(self, "_webhook_url_edit") or self._webhook_url_edit is None:
        return
    url = self._webhook_url_edit.text().strip()
    self._save_settings(webhook_url=url)

# ── Background tasks ──────────────────────────────────────────────



def _start_background_tasks(self) -> None:
    _bootstrap()
    self._ocr_thread = OcrInitThread(use_gpu=False)
    self._ocr_thread.finished.connect(self._on_ocr_ready)
    self._ocr_thread.start()

    settings = self._load_settings()
    if settings.get("sample_party_applied"):
        return
    status = db.get_local_data_status()
    if status["species_count"] == 0 or status["move_count"] == 0:
        self._sample_party_pending = True
        self._log("DBが空のため PokeAPI データを自動取得します...")
        self._show_loading_overlay("PokeAPI データを取得中...\nしばらくお待ちください")
        self._fetch_pokeapi_data()
    else:
        self._apply_sample_party()

# ── Slots ─────────────────────────────────────────────────────────



def _apply_sample_party(self) -> None:
    _bootstrap()
    party = _parse_sample_party()
    if not party:
        return
    none_padded: list[PokemonInstance | None] = list(party) + [None] * (6 - len(party))
    self._battle_state.my_party = none_padded[:]
    self._battle_state.opponent_party = none_padded[:]
    if party:
        self._battle_state.my_pokemon = party[0]
        self._battle_state.opponent_pokemon = party[0]
    self._sync_battle_state_to_panels()
    self._save_settings(sample_party_applied=True)
    self._log("サンプルパーティを適用しました（{}体）".format(len(party)))



def _fetch_pokeapi_data(self) -> None:
    _bootstrap()
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
    _bootstrap()
    season = self._current_usage_season()
    scraper_cls, usage_sources, usage_default, import_error = self._get_usage_scraper_symbols()
    if scraper_cls is None:
        QMessageBox.information(
            self,
            "使用率取得は利用不可",
            "usage_scraper が見つからないため、この環境では使用率取得を実行できません。\n\n{}".format(import_error or ""),
        )
        return
    source = self._option_source_combo.currentData() if self._option_source_combo else usage_default
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
    self._scraper = scraper_cls(season=season, source=source)
    self._scraper.progress.connect(self._on_usage_progress)
    self._scraper.finished.connect(self._on_scraper_done)
    self._set_fetch_buttons_enabled(False)
    source_label = usage_sources.get(source, source)
    self._status_bar.showMessage("使用率データ取得を開始 [{}] [{}]".format(season, source_label))
    self._log("使用率データ取得を開始 [{}] [{}]".format(season, source_label))
    self._scraper.start()



def _refresh_cameras(self) -> None:
    _bootstrap()
    self._cam_combo.clear()
    cameras = VideoThread.list_cameras()
    for idx, name in cameras:
        self._cam_combo.addItem(name, idx)
    if not cameras:
        self._cam_combo.addItem("カメラなし", -1)



def _toggle_camera(self) -> None:
    _bootstrap()
    if self._video_thread and self._video_thread.isRunning():
        self._stop_live_battle_tracking(show_message=False, write_log=False)
        self._stop_opponent_party_auto_detect(show_message=False, write_log=False)
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
    _bootstrap()
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



def eventFilter(self, obj, event):
    _bootstrap()
    from PyQt5.QtCore import QEvent
    from PyQt5.QtGui import QMouseEvent
    if obj == self._fetch_usage_btn and event.type() == QEvent.MouseButtonDblClick:
        if getattr(sys, "frozen", False):
            return True
        me = QMouseEvent(event)
        if me.button() == Qt.RightButton:
            self._show_usage_password_dialog()
            return True
    return QMainWindow.eventFilter(self, obj, event)

# ── Logging ───────────────────────────────────────────────────────



def _fetch_usage_data_with_source(self, season: str, source: str) -> None:
    _bootstrap()
    scraper_cls, usage_sources, _, import_error = self._get_usage_scraper_symbols()
    if scraper_cls is None:
        QMessageBox.information(
            self,
            "使用率取得は利用不可",
            "usage_scraper が見つからないため、この環境では使用率取得を実行できません。\n\n{}".format(import_error or ""),
        )
        return
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
    self._scraper = scraper_cls(season=season, source=source)
    self._scraper.progress.connect(self._on_usage_progress)
    self._scraper.finished.connect(self._on_scraper_done)
    self._set_fetch_buttons_enabled(False)
    source_label = usage_sources.get(source, source)
    self._status_bar.showMessage("使用率データ取得を開始 [{}] [{}]".format(season, source_label))
    self._log("使用率データ取得を開始 [{}] [{}]".format(season, source_label))
    self._scraper.start()



def _log(self, msg: str) -> None:
    _bootstrap()
    ts = datetime.now().strftime("%H:%M:%S")
    log_text = "[{}] {}".format(ts, msg)
    if self._log_edit:
        self._log_edit.append(log_text)
    if self._main_log_edit:
        self._main_log_edit.append(log_text)
        self._main_log_edit.horizontalScrollBar().setValue(0)
    self._status_bar.showMessage(log_text)



def _on_bridge_payload_log(self, msg: str) -> None:
    _bootstrap()
    if not self._detailed_log_enabled:
        return
    self._log(msg)



def _export_log_to_txt(self) -> None:
    _bootstrap()
    if not self._log_edit:
        return
    text = self._log_edit.toPlainText().strip()
    if not text:
        self._status_bar.showMessage("ログが空のため出力をスキップしました", 3000)
        return
    default_name = "app_log_{}.txt".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    logs_dir = Path.cwd() / "logs"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    default_path = logs_dir / default_name
    selected_path, _ = QFileDialog.getSaveFileName(
        self,
        "ログをTXT出力",
        str(default_path),
        "Text files (*.txt);;All files (*.*)",
    )
    if not selected_path:
        return
    try:
        Path(selected_path).write_text(text + "\n", encoding="utf-8")
    except OSError as exc:
        self._log("[ERROR] ログ出力失敗: {}".format(exc))
        return
    self._log("ログを出力しました: {}".format(selected_path))



def _init_battle_state(self) -> None:
    _bootstrap()
    self._battle_state = BattleState(
        my_party=[None] * 6,
        opponent_party=[None] * 6,
    )



def _ensure_party_slots(self) -> None:
    _bootstrap()
    self._battle_state.my_party = (self._battle_state.my_party + [None] * 6)[:6]
    self._battle_state.opponent_party = (self._battle_state.opponent_party + [None] * 6)[:6]



def _sync_battle_state_to_panels(self) -> None:
    _bootstrap()
    self._ensure_party_slots()
    self._update_box_party_ui()
    self._syncing_battle_state_to_panels = True
    try:
        self._damage_panel.set_my_party(self._battle_state.my_party)
        if self._battle_state.my_pokemon:
            self._damage_panel.set_my_pokemon(self._battle_state.my_pokemon)

        if any(self._battle_state.opponent_party):
            self._damage_panel.set_opponent_options(
                list(self._battle_state.opponent_party),
                active=copy.deepcopy(self._battle_state.opponent_pokemon),
            )
    finally:
        self._syncing_battle_state_to_panels = False



def _on_party_slot_clicked(self, index: int, is_my: bool) -> None:
    _bootstrap()
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



def _on_my_party_panel_dropped(self, name_ja: str) -> None:
    _bootstrap()
    self._try_add_to_my_party(name_ja, source="D&D")



def _try_add_to_my_party(self, name_ja: str, source: str = "click") -> None:
    _bootstrap()
    self._ensure_party_slots()
    pokemon = next((p for p in self._registered_pokemon if p and p.name_ja == name_ja), None)
    if pokemon is None:
        return
    empty_idx = next((i for i, p in enumerate(self._battle_state.my_party) if p is None), -1)
    if empty_idx < 0:
        self._log("自分PT追加失敗[{}]: 空きスロットがありません".format(source))
        self._status_bar.showMessage("自分PTに空きがありません", 3000)
        return
    previous = self._battle_state.my_party[empty_idx]
    self._battle_state.my_party[empty_idx] = copy.deepcopy(pokemon)
    if (
        not self._battle_state.my_pokemon
        or (
            previous is not None
            and self._battle_state.my_pokemon.name_ja == previous.name_ja
        )
    ):
        self._battle_state.my_pokemon = copy.deepcopy(pokemon)
    self._sync_battle_state_to_panels()



def _on_registry_cell_left_click(self, name_ja: str) -> None:
    _bootstrap()
    self._try_add_to_my_party(name_ja, source="左クリック")



def _on_my_party_panel_cleared(self) -> None:
    _bootstrap()
    self._battle_state.my_party = [None] * 6
    self._battle_state.my_pokemon = None
    self._sync_battle_state_to_panels()



def _on_my_party_panel_context_menu(self, global_pos) -> None:
    _bootstrap()
    menu = QMenu(self)
    act_clear = QAction("削除", menu)
    act_clear.triggered.connect(self._on_my_party_panel_cleared)
    menu.addAction(act_clear)
    act_save = QAction("保存", menu)
    act_save.triggered.connect(lambda: self._save_party_preset(to_top=True))
    menu.addAction(act_save)
    menu.exec_(global_pos)



def _on_party_slot_dropped(self, index: int, name_ja: str) -> None:
    _bootstrap()
    self._ensure_party_slots()
    pokemon = next((p for p in self._registered_pokemon if p and p.name_ja == name_ja), None)
    if pokemon is None:
        return
    previous = self._battle_state.my_party[index]
    self._battle_state.my_party[index] = copy.deepcopy(pokemon)
    if (
        not self._battle_state.my_pokemon
        or (
            previous is not None
            and self._battle_state.my_pokemon.name_ja == previous.name_ja
        )
    ):
        self._battle_state.my_pokemon = copy.deepcopy(pokemon)
    self._sync_battle_state_to_panels()



def _on_party_slot_cleared(self, index: int) -> None:
    _bootstrap()
    self._ensure_party_slots()
    previous = self._battle_state.my_party[index]
    self._battle_state.my_party[index] = None
    if previous and self._battle_state.my_pokemon and self._battle_state.my_pokemon.name_ja == previous.name_ja:
        self._battle_state.my_pokemon = copy.deepcopy(
            next((p for p in self._battle_state.my_party if p), None)
        )
    self._sync_battle_state_to_panels()



def _select_registered_pokemon(self, title: str, current_name: str = "") -> tuple[bool, PokemonInstance | None]:
    _bootstrap()
    self._refresh_registry_list()
    if not self._registered_pokemon:
        QMessageBox.information(self, "情報", "登録済みポケモンがありません。")
        return False, None
    available: list[PokemonInstance] = list(self._registered_pokemon)

    from src.ui.ui_utils import make_dialog
    dlg = make_dialog(self)
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
    _bootstrap()
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
    self._show_loading_overlay("相手PT検出中...")
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
        self._log("相手PT検出[{}]: {}".format(season, " | ".join(summary)))
        self._status_bar.showMessage("相手PTを検出しました")
    finally:
        self._hide_loading_overlay()
        self._set_auto_detect_enabled(True)



def _on_auto_detect_toggled(self, checked: bool) -> None:
    _bootstrap()
    checked = bool(checked)
    if checked:
        if not self._video_thread or not self._video_thread.isRunning():
            QMessageBox.information(self, "情報", "カメラを接続してください")
            if self._auto_detect_btn:
                self._auto_detect_btn.blockSignals(True)
                self._auto_detect_btn.setChecked(False)
                self._auto_detect_btn.blockSignals(False)
                self._refresh_auto_detect_button_style()
            return
        self._opp_auto_detect_timer.start()
        self._refresh_auto_detect_button_style()
        self._status_bar.showMessage("相手PT自動検出を開始しました", 3000)
        self._log("相手PT自動検出: ON")
        return
    self._stop_opponent_party_auto_detect(show_message=True, write_log=True)



def _stop_opponent_party_auto_detect(self, show_message: bool, write_log: bool) -> None:
    _bootstrap()
    was_active = self._opp_auto_detect_timer.isActive()
    self._opp_auto_detect_timer.stop()
    self._auto_detect_pending = False
    if self._auto_detect_btn and self._auto_detect_btn.isChecked():
        self._auto_detect_btn.blockSignals(True)
        self._auto_detect_btn.setChecked(False)
        self._auto_detect_btn.blockSignals(False)
    self._refresh_auto_detect_button_style()
    if was_active and show_message:
        self._status_bar.showMessage("相手PT自動検出を停止しました", 3000)
    if was_active and write_log:
        self._log("相手PT自動検出: OFF")



def _poll_opponent_party_auto_detect(self) -> None:
    _bootstrap()
    if self._auto_detect_pending:
        return
    if time.monotonic() < self._auto_detect_cooldown_until:
        return
    if not self._video_thread or not self._video_thread.isRunning():
        return
    frame = self._video_thread.get_last_frame()
    if frame is None or frame.size == 0:
        return
    self._dump_auto_detect_debug_frame(frame)
    matched, scores = opponent_party_auto_trigger.evaluate_auto_detect(frame)
    has_first_type = opponent_party_reader.has_first_slot_type(frame) if matched else False
    now = time.monotonic()
    if self._detailed_log_enabled and now - self._auto_detect_score_log_last >= 1.0:
        self._auto_detect_score_log_last = now
        score_text = " / ".join(
            "{}={:.3f}[{}]".format(name, score, reason) if reason.startswith("ok") else "{}=N/A({})".format(name, reason)
            for name, score, reason in scores
        ) or "score=N/A"
        self._log(
            "相手PT自動検出スコア: {} (閾値 ccorr>=0.850 or sqdiff<=0.150, 追加条件: 1体目タイプ検出={})".format(
                score_text,
                "OK" if has_first_type else "NG",
            )
        )
    if not matched or not has_first_type:
        return
    self._auto_detect_pending = True
    self._auto_detect_cooldown_until = time.monotonic() + 120.0

    def _run_detect() -> None:
        try:
            self._auto_detect_opponent_party()
        finally:
            self._auto_detect_pending = False

    QTimer.singleShot(100, _run_detect)



def _dump_auto_detect_debug_frame(self, frame) -> None:
    _bootstrap()
    now = time.monotonic()
    if now - self._auto_detect_debug_dump_last < 2.0:
        return
    self._auto_detect_debug_dump_last = now
    try:
        import cv2
        import numpy as np
        from pathlib import Path

        dbg = frame.copy()
        if dbg is None or getattr(dbg, "size", 0) == 0:
            return
        h, w = dbg.shape[:2]
        base_w, base_h = 1280.0, 720.0
        sx, sy = w / base_w, h / base_h
        rects = [
            ((88, 609, 182, 649), "temp1", (0, 255, 255)),
            ((229, 606, 331, 652), "temp2", (255, 255, 0)),
        ]
        for (x1, y1, x2, y2), label, color in rects:
            rx1 = int(round(x1 * sx))
            ry1 = int(round(y1 * sy))
            rx2 = int(round(x2 * sx))
            ry2 = int(round(y2 * sy))
            cv2.rectangle(dbg, (rx1, ry1), (rx2, ry2), color, 2)
            cv2.putText(
                dbg,
                "{} ({},{})-({},{})".format(label, rx1, ry1, rx2, ry2),
                (max(0, rx1), max(18, ry1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )
        out_dir = Path.cwd() / "captures" / "auto_detect_debug"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        out_path = out_dir / "opp_auto_detect_{}.png".format(ts)
        cv2.imwrite(str(out_path), dbg)
    except (ImportError, OSError, ValueError, TypeError) as exc:
        if self._detailed_log_enabled:
            self._log("[WARN] 自動検出デバッグ画像の保存失敗: {}".format(exc))
        return



def _toggle_live_battle_tracking(self, enabled: bool) -> None:
    _bootstrap()
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
    _bootstrap()
    was_active = self._live_battle_timer.isActive()
    self._live_battle_timer.stop()
    if was_active and show_message:
        self._status_bar.showMessage("試合中監視を停止しました", 3000)
    if was_active and write_log:
        self._log("試合中監視: OFF")



def _poll_live_battle(self) -> None:
    _bootstrap()
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
    except (RuntimeError, ValueError, TypeError) as e:
        self._log("[ERROR] 試合中監視エラー: {}".format(e))
        return

    changed, summary = self._apply_live_battle_data(live_data)
    if changed:
        self._sync_battle_state_to_panels()
        if summary and summary != self._live_battle_signature:
            self._live_battle_signature = summary
            self._log("試合中更新: {}".format(summary))



def _apply_live_battle_data(self, live_data: dict) -> tuple[bool, str]:
    _bootstrap()
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



def _build_usage_template_pokemon(self, name_ja: str) -> PokemonInstance | None:
    _bootstrap()
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
        terastal_type="normal",
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
    non_status_candidates: list[str] = []
    for move_name in move_candidates:
        move_info = db.get_move_by_name_ja(move_name)
        if move_info and move_info.category != "status":
            non_status_candidates.append(move_name)
    pokemon.moves = (non_status_candidates + ["", "", "", ""])[:4]

    from src.calc.calc_utils import fill_stats_from_species

    fill_stats_from_species(pokemon, species)
    pokemon.max_hp = pokemon.hp
    pokemon.current_hp = pokemon.hp
    pokemon.current_hp_percent = 100.0
    return pokemon



def _read_box_and_register(self) -> None:
    _bootstrap()
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
    _bootstrap()
    pokemon = data.get("pokemon")
    if not pokemon or not pokemon.name_ja:
        return
    self._fill_species(pokemon)
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
        except (RuntimeError, ValueError, TypeError) as e:
            self.error.emit(str(e))



def _start_box_read_thread(self, frame: object) -> None:
    _bootstrap()
    self._show_loading_overlay("ボックス読み込み中...")
    worker = _BoxReadWorker(frame)
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
    _bootstrap()
    self._registered_pokemon = db.load_all_pokemon()
    type_filter: set[str] = getattr(self, "_box_type_filter", set())
    filtered = [
        p for p in self._registered_pokemon
        if not type_filter or type_filter.issubset(set(p.types or []))
    ]

    if not hasattr(self, "_reg_grid_layout"):
        return

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

        cell = _DraggableCell(p.name_ja)
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
        cell.clicked_signal.connect(self._on_registry_cell_left_click)
        cell.setContextMenuPolicy(Qt.CustomContextMenu)
        cell.customContextMenuRequested.connect(_make_ctx_handler(pokemon_ref, cell))

        self._reg_grid_layout.addWidget(cell, idx // _COLS, idx % _COLS)

    remainder = len(filtered) % _COLS
    if remainder:
        for col in range(remainder, _COLS):
            spacer = QWidget()
            spacer.setFixedSize(_CELL_W, _CELL_H)
            self._reg_grid_layout.addWidget(spacer, len(filtered) // _COLS, col)

    next_row = (len(filtered) + _COLS - 1) // _COLS
    self._reg_grid_layout.setRowStretch(next_row, 1)



def _open_edit_dialog(self, pokemon) -> None:
    _bootstrap()
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



def _open_register_input_dialog(self) -> None:
    _bootstrap()
    from src.ui.ui_utils import make_dialog
    dlg = make_dialog(self)
    dlg.setWindowTitle("新規登録")
    dlg.setMinimumWidth(640)
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(8)

    guide = QLabel("下記フォーマットを貼り付けて保存できます。")
    guide.setStyleSheet("color:#a6adc8; font-size:12px;")
    layout.addWidget(guide)

    editor = QPlainTextEdit()
    editor.setPlaceholderText(
        "{name_ja} @ {item}\n"
        "テラスタイプ: {terastal_type}\n"
        "特性: {ability}\n"
        "性格: {nature}\n"
        "{hp}({ev_hp})-{attack}({ev_attack})-{defense}({ev_defense})-{sp_attack}({ev_sp_attack})-{sp_defense}({ev_sp_defense})-{speed}({ev_speed})\n"
        "{move1} / {move2} / {move3} / {move4}"
    )
    editor.setMinimumHeight(220)
    layout.addWidget(editor)

    row = QHBoxLayout()
    row.setSpacing(6)
    save_btn = QPushButton("保存")
    cancel_btn = QPushButton("キャンセル")
    row.addWidget(save_btn)
    row.addWidget(cancel_btn)
    layout.addLayout(row)

    gui_btn = QPushButton("GUIで設定")
    layout.addWidget(gui_btn)

    def on_save() -> None:
        text = editor.toPlainText().strip()
        pokemon, error = self._parse_pokemon_text_block(text)
        if pokemon is None:
            QMessageBox.warning(dlg, "入力エラー", error or "フォーマットを確認してください。")
            return
        new_id = db.save_pokemon(pokemon)
        pokemon.db_id = new_id
        self._refresh_registry_list()
        self._status_bar.showMessage("ポケモンを登録しました", 3000)
        dlg.accept()

    def on_gui() -> None:
        dlg.accept()
        self._open_edit_dialog(None)

    save_btn.clicked.connect(on_save)
    cancel_btn.clicked.connect(dlg.reject)
    gui_btn.clicked.connect(on_gui)
    dlg.exec_()



def _parse_pokemon_text_block(self, text: str) -> tuple[PokemonInstance | None, str | None]:
    _bootstrap()
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if len(lines) < 6:
        return None, "行数が不足しています（最低6行）。"

    head = lines[0]
    m_head = re.match(r"^(.+?)\s*@\s*(.+)$", head)
    if not m_head:
        return None, "1行目は「名前 @ 持ち物」形式で入力してください。"
    name_ja = (m_head.group(1) or "").strip()
    item = (m_head.group(2) or "").strip()
    if item == "もちものなし":
        item = ""

    def _extract(prefix: str, line: str) -> str:
        if not line.startswith(prefix):
            return ""
        return line[len(prefix):].strip()

    tera_ja = _extract("テラスタイプ:", lines[1]) or "ノーマル"
    ability = _extract("特性:", lines[2])
    nature = _extract("性格:", lines[3])
    if not ability or not nature:
        return None, "特性・性格の行を確認してください。"

    stats_line = lines[4]
    parts = [part.strip() for part in stats_line.split("-")]
    if len(parts) != 6:
        return None, "実数値行は「H-A-B-C-D-S」の6項目で入力してください。"

    def _parse_stat_part(part: str) -> tuple[int, int]:
        m = re.match(r"^(\d+)(?:\((\d+)\))?$", part)
        if not m:
            raise ValueError
        stat_val = int(m.group(1))
        ev_display = int(m.group(2)) if m.group(2) else 0
        ev_internal = (ev_display + 4) if ev_display > 0 else 0
        return stat_val, ev_internal

    try:
        parsed = [_parse_stat_part(part) for part in parts]
    except ValueError:
        return None, "実数値行の形式が不正です。"

    move_line = lines[5]
    moves = [m.strip() for m in move_line.split("/") if m.strip()]
    if not moves:
        return None, "技行が不正です。"

    tera_ja_to_en = {**{v: k for k, v in TYPE_EN_TO_JA.items()}, "ステラ": "stellar"}
    terastal_type = tera_ja_to_en.get(tera_ja, "normal")

    pokemon = PokemonInstance(
        name_ja=name_ja,
        item=item,
        ability=ability,
        nature=nature,
        terastal_type=terastal_type,
        hp=parsed[0][0],
        attack=parsed[1][0],
        defense=parsed[2][0],
        sp_attack=parsed[3][0],
        sp_defense=parsed[4][0],
        speed=parsed[5][0],
        ev_hp=parsed[0][1],
        ev_attack=parsed[1][1],
        ev_defense=parsed[2][1],
        ev_sp_attack=parsed[3][1],
        ev_sp_defense=parsed[4][1],
        ev_speed=parsed[5][1],
        moves=(moves + ["", "", "", ""])[:4],
        current_hp=parsed[0][0],
        max_hp=parsed[0][0],
    )
    self._fill_species(pokemon)
    return pokemon, None



def _edit_selected_pokemon(self) -> None:
    _bootstrap()
    p = getattr(self, "_reg_selected_pokemon", None)
    if not p:
        return
    self._open_edit_dialog(p)



def _delete_selected_pokemon(self) -> None:
    _bootstrap()
    p = getattr(self, "_reg_selected_pokemon", None)
    if p and p.db_id:
        db.delete_pokemon(p.db_id)
        self._reg_selected_pokemon = None
        self._refresh_registry_list()



def _copy_selected_pokemon_info(self) -> None:
    _bootstrap()
    p = getattr(self, "_reg_selected_pokemon", None)
    if not p:
        return
    text = self._format_pokemon_export_text(p)
    QApplication.clipboard().setText(text)
    self._status_bar.showMessage("ポケモン情報をコピーしました", 3000)



def _format_pokemon_export_text(self, pokemon: PokemonInstance) -> str:
    _bootstrap()
    tera_ja_map: dict[str, str] = {**TYPE_EN_TO_JA, "stellar": "ステラ"}
    terastal_type_ja = tera_ja_map.get((pokemon.terastal_type or "").strip(), "ノーマル")
    item_text = (pokemon.item or "").strip() or "もちものなし"

    def _stat_with_ev(stat_value: int, ev_value: int) -> str:
        ev_raw = int(ev_value or 0)
        ev_display = ev_raw - 4 if ev_raw > 0 else 0
        if ev_display > 0:
            return "{}({})".format(int(stat_value or 0), ev_display)
        return str(int(stat_value or 0))

    stats_text = "-".join(
        [
            _stat_with_ev(pokemon.hp, pokemon.ev_hp),
            _stat_with_ev(pokemon.attack, pokemon.ev_attack),
            _stat_with_ev(pokemon.defense, pokemon.ev_defense),
            _stat_with_ev(pokemon.sp_attack, pokemon.ev_sp_attack),
            _stat_with_ev(pokemon.sp_defense, pokemon.ev_sp_defense),
            _stat_with_ev(pokemon.speed, pokemon.ev_speed),
        ]
    )
    moves = (list(pokemon.moves) + ["", "", "", ""])[:4]
    move_text = " / ".join(moves)
    return "\n".join(
        [
            "{} @ {}".format((pokemon.name_ja or "").strip(), item_text),
            "テラスタイプ: {}".format(terastal_type_ja),
            "特性: {}".format((pokemon.ability or "").strip()),
            "性格: {}".format((pokemon.nature or "").strip()),
            stats_text,
            move_text,
        ]
    )



def _on_registry_context_menu(self, pos) -> None:
    _bootstrap()
    pass



def _on_registry_context_menu_for_cell(self, global_pos) -> None:
    _bootstrap()
    menu = QMenu(self)
    act_edit = QAction("編集", menu)
    act_delete = QAction("削除", menu)
    act_copy = QAction("情報をコピー", menu)
    act_edit.triggered.connect(self._edit_selected_pokemon)
    act_delete.triggered.connect(self._delete_selected_pokemon)
    act_copy.triggered.connect(self._copy_selected_pokemon_info)
    menu.addAction(act_copy)
    menu.addAction(act_edit)
    menu.addAction(act_delete)
    menu.exec_(global_pos)



def _on_damage_panel_atk_changed(self, pokemon: PokemonInstance | None) -> None:
    _bootstrap()
    if self._syncing_battle_state_to_panels:
        return
    if hasattr(self._damage_panel, "get_my_party_snapshot"):
        self._battle_state.my_party = self._damage_panel.get_my_party_snapshot()
    if hasattr(self._damage_panel, "get_opp_party_snapshot"):
        self._battle_state.opponent_party = self._damage_panel.get_opp_party_snapshot()
    side = self._damage_panel.attacker_side() if hasattr(self._damage_panel, "attacker_side") else "my"
    copied = copy.deepcopy(pokemon) if pokemon else None
    if side == "opp":
        self._battle_state.opponent_pokemon = copied
    else:
        self._battle_state.my_pokemon = copied
    self._ensure_party_slots()
    self._update_box_party_ui()



def _on_damage_panel_def_changed(self, pokemon: PokemonInstance | None) -> None:
    _bootstrap()
    if self._syncing_battle_state_to_panels:
        return
    if hasattr(self._damage_panel, "get_my_party_snapshot"):
        self._battle_state.my_party = self._damage_panel.get_my_party_snapshot()
    if hasattr(self._damage_panel, "get_opp_party_snapshot"):
        self._battle_state.opponent_party = self._damage_panel.get_opp_party_snapshot()
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
    _bootstrap()
    target = text_matcher.normalize_ocr_text(text_matcher.match_species_name(name_ja))
    if not target:
        return None
    for p in self._registered_pokemon:
        if text_matcher.normalize_ocr_text(p.name_ja) == target:
            return p
    return None



def _fill_species(self, pokemon: PokemonInstance) -> None:
    _bootstrap()
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
            from src.calc.calc_utils import fill_stats_from_species
            fill_stats_from_species(pokemon, species)



def _serialize_pokemon(self, pokemon: PokemonInstance | None) -> dict | None:
    _bootstrap()
    if not pokemon:
        return None
    return {
        "db_id": int(pokemon.db_id) if pokemon.db_id is not None else None,
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
    _bootstrap()
    if not isinstance(payload, dict):
        return None
    pokemon = PokemonInstance()
    for key, value in payload.items():
        if hasattr(pokemon, key):
            setattr(pokemon, key, value)
    if not (pokemon.terastal_type or "").strip():
        pokemon.terastal_type = "normal"
    return pokemon



def _load_party_presets(self) -> None:
    _bootstrap()
    settings = self._load_settings()
    raw_list = settings.get("battle_party_presets_v2", [])
    if isinstance(raw_list, list):
        self._party_presets = [item for item in raw_list if isinstance(item, dict)]
        return
    if isinstance(raw_list, dict):
        migrated_v2 = [value for _, value in sorted(raw_list.items(), key=lambda x: str(x[0])) if isinstance(value, dict)]
        self._party_presets = migrated_v2
        self._save_settings(battle_party_presets_v2=self._party_presets)
        return
    raw_legacy = settings.get("battle_party_presets", {})
    if isinstance(raw_legacy, dict):
        migrated: list[dict] = []
        for _, value in sorted(raw_legacy.items(), key=lambda x: str(x[0])):
            if isinstance(value, dict):
                migrated.append(value)
        self._party_presets = migrated
        self._save_settings(battle_party_presets_v2=self._party_presets)
        return
    self._party_presets = []



def _apply_top_saved_party_on_startup(self) -> None:
    _bootstrap()
    if not self._party_presets:
        return
    preset = self._party_presets[0]
    my_party = [self._deserialize_pokemon(item) for item in preset.get("my_party", [])][:6]
    self._battle_state.my_party = (my_party + [None] * 6)[:6]
    my_active_name = str(preset.get("my_active_name") or "")
    self._battle_state.my_pokemon = copy.deepcopy(
        next((p for p in self._battle_state.my_party if p and p.name_ja == my_active_name), None)
        or next((p for p in self._battle_state.my_party if p), None)
    )
    self._sync_battle_state_to_panels()



def _save_party_preset(self, to_top: bool = False) -> None:
    _bootstrap()
    self._ensure_party_slots()
    entry = {
        "my_party": [self._serialize_pokemon(p) for p in self._battle_state.my_party],
        "opponent_party": [self._serialize_pokemon(p) for p in self._battle_state.opponent_party],
        "my_active_name": self._battle_state.my_pokemon.name_ja if self._battle_state.my_pokemon else "",
        "opp_active_name": self._battle_state.opponent_pokemon.name_ja if self._battle_state.opponent_pokemon else "",
    }
    if to_top:
        self._party_presets.insert(0, entry)
    else:
        self._party_presets.append(entry)
    self._save_settings(battle_party_presets_v2=self._party_presets)
    self._refresh_party_presets_ui()
    self._status_bar.showMessage("パーティを保存しました（{}件）".format(len(self._party_presets)), 4000)
    self._log("PT保存: {}件".format(len(self._party_presets)))



def _on_saved_party_panel_context_menu(self, index: int, global_pos) -> None:
    _bootstrap()
    menu = QMenu(self)
    act_delete = QAction("削除", menu)
    act_delete.triggered.connect(lambda: self._delete_party_preset_at(index))
    menu.addAction(act_delete)
    menu.exec_(global_pos)



def _load_party_preset_at(self, index: int) -> None:
    _bootstrap()
    if index < 0 or index >= len(self._party_presets):
        return
    preset = self._party_presets[index]
    my_party = [self._deserialize_pokemon(item) for item in preset.get("my_party", [])][:6]
    self._battle_state.my_party = (my_party + [None] * 6)[:6]
    my_active_name = str(preset.get("my_active_name") or "")
    self._battle_state.my_pokemon = copy.deepcopy(
        next((p for p in self._battle_state.my_party if p and p.name_ja == my_active_name), None)
        or next((p for p in self._battle_state.my_party if p), None)
    )
    self._sync_battle_state_to_panels()
    self._status_bar.showMessage("保存済みパーティを反映しました", 4000)
    self._log("PT読込")



def _delete_party_preset_at(self, index: int) -> None:
    _bootstrap()
    if index < 0 or index >= len(self._party_presets):
        return
    del self._party_presets[index]
    self._save_settings(battle_party_presets_v2=self._party_presets)
    self._refresh_party_presets_ui()
    self._status_bar.showMessage("保存済みパーティを削除しました", 4000)
    self._log("PT削除")



def _reorder_party_preset(self, from_index: int, to_index: int) -> None:
    _bootstrap()
    if from_index == to_index:
        return
    if from_index < 0 or to_index < 0:
        return
    if from_index >= len(self._party_presets) or to_index >= len(self._party_presets):
        return
    item = self._party_presets.pop(from_index)
    self._party_presets.insert(to_index, item)
    self._save_settings(battle_party_presets_v2=self._party_presets)
    self._refresh_party_presets_ui()
    if self._party_presets:
        self._load_party_preset_at(0)



def _move_saved_party_to_top(self, index: int) -> None:
    _bootstrap()
    if index <= 0 or index >= len(self._party_presets):
        return
    item = self._party_presets.pop(index)
    self._party_presets.insert(0, item)
    self._save_settings(battle_party_presets_v2=self._party_presets)
    self._refresh_party_presets_ui()
    self._load_party_preset_at(0)



def _reset_all_party(self) -> None:
    _bootstrap()
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



def nativeEvent(self, event_type: bytes, message: object) -> tuple[bool, int]:
    _bootstrap()
    if sys.platform == "win32":
        import ctypes.wintypes
        msg = ctypes.wintypes.MSG.from_address(int(message))
        if msg.message == 0x8001:  # WM_USER_FOCUS from second instance
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
            self.show()
            self.raise_()
            self.activateWindow()
            ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
            return True, 0
    return QMainWindow.nativeEvent(self, event_type, message)



def _settings_path(self) -> Path:
    _bootstrap()
    return Path.home() / ".pokemon_damage_calc" / "settings.json"



def _load_settings(self) -> dict:
    _bootstrap()
    try:
        p = self._settings_path()
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return {}



def _save_settings(self, **kwargs) -> None:
    _bootstrap()
    try:
        p = self._settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        current: dict = {}
        if p.exists():
            try:
                current = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
        current.update(kwargs)
        p.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        self._log("[WARN] 設定保存失敗: {}".format(exc))


def _run_data_integrity_check(self) -> None:
    _bootstrap()
    season = self._current_usage_season()
    db.set_active_usage_season(season)
    result = db.check_usage_data_integrity(season)
    summary = result.get("summary", {})
    issues = result.get("issues", [])
    details = result.get("details", {})
    lines = [
        "シーズン: {}".format(result.get("season", season)),
        "species={}, usage={}, option={}, effort={}".format(
            summary.get("species_count", 0),
            summary.get("usage_count", 0),
            summary.get("option_count", 0),
            summary.get("effort_count", 0),
        ),
    ]
    if details.get("json_exists"):
        lines.append("JSON: {}".format(details.get("json_path", "")))
    else:
        lines.append("JSON: 未検出 ({})".format(details.get("json_path", "")))
    if issues:
        lines.append("")
        lines.append("不整合:")
        lines.extend("- {}".format(msg) for msg in issues)
        self._log("[WARN] データ整合性チェック: NG [{}]".format(season))
        QMessageBox.warning(self, "データ整合性チェック", "\n".join(lines))
        return
    self._log("データ整合性チェック: OK [{}]".format(season))
    QMessageBox.information(self, "データ整合性チェック", "\n".join(lines + ["", "不整合は見つかりませんでした。"]))



def _apply_saved_settings(self) -> None:
    _bootstrap()
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
    self._detailed_log_enabled = bool(settings.get("detailed_log_enabled", False))
    if self._option_detailed_log_cb:
        self._option_detailed_log_cb.blockSignals(True)
        self._option_detailed_log_cb.setChecked(self._detailed_log_enabled)
        self._option_detailed_log_cb.blockSignals(False)

    if hasattr(self, "_webhook_url_edit") and self._webhook_url_edit:
        self._webhook_url_edit.blockSignals(True)
        self._webhook_url_edit.setText(settings.get("webhook_url", ""))
        self._webhook_url_edit.blockSignals(False)

    self._refresh_data_status()



def _auto_connect_saved_camera(self) -> None:
    _bootstrap()
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
    _bootstrap()
    self._live_battle_timer.stop()
    self._live_battle_timer.timeout.disconnect()
    self._opp_auto_detect_timer.stop()
    self._opp_auto_detect_timer.timeout.disconnect()
    try:
        self._damage_panel.attacker_changed.disconnect()
        self._damage_panel.defender_changed.disconnect()
        self._damage_panel.registry_maybe_changed.disconnect()
        self._damage_panel.bridge_payload_logged.disconnect()
    except RuntimeError:
        pass
    self._stop_live_battle_tracking(show_message=False, write_log=False)
    self._stop_opponent_party_auto_detect(show_message=False, write_log=False)
    if self._video_thread:
        self._video_thread.stop()
    event.accept()


