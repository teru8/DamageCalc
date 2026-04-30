from __future__ import annotations

# Reuse symbols/helpers defined in pokemon_edit_dialog.py before PokemonEditDialog.
from src.ui import pokemon_edit_dialog as _base

for _k, _v in _base.__dict__.items():
    if not _k.startswith("__"):
        globals()[_k] = _v

class PokemonEditDialog(QDialog):
    def __init__(self, pokemon=None, parent=None, save_to_db: bool = True):
        super().__init__(parent)
        self._save_to_db = save_to_db
        self._is_new_entry = pokemon is None
        self._lock_species_selector = (not save_to_db) and (pokemon is not None)
        self._auto_template_key = ""
        self._box_select_requested = False
        self.setWindowTitle("ポケモン登録 / 編集" if save_to_db else "ポケモン編集（ダメージ計算用）")
        self.setMinimumSize(1100, 794)
        self._pokemon = None  # type: PokemonInstance | None
        self._loading = False
        self._updating_stats = False
        self._selected_form_index: int = 0
        self._pane_sort_mode: str = "usage"
        self._pane_type_filters: set[str] = set()
        self._pane_icon_job_id: int = 0
        self._pane_tooltip_shown: bool = False
        self._current_nature = "がんばりや"
        self._selected_moves = ["", "", "", ""]
        self._species_list = db.get_all_species()
        self._form_options_by_base = _build_form_options_by_base(self._species_list)
        self._current_form_options: list[FormOption] = []
        self._picker_entries = _build_pokemon_picker_entries()
        self._picker_entry_map = {entry.display_name: entry for entry in self._picker_entries}
        canonical_names: list[str] = []
        for entry in self._picker_entries:
            if entry.display_name:
                canonical_names.append(entry.display_name)
        self._all_species_names = [
            name
            for name in _unique(canonical_names)
            if name and name not in _REGION_PREFIX_TO_SUB.values() and name not in ("オスのすがた", "メスのすがた", "ロトムのすがた")
        ]
        self._all_abilities = sorted(_unique(list(ABILITIES_JA)))
        self._all_items = sorted(_unique(list(ITEMS_JA) + get_item_names()))
        self._show_terastal_picker = self._should_show_terastal_picker()

        self._build_ui()
        self._pane_refresh_list()
        if pokemon:
            self._load(pokemon)
        else:
            self._set_form_options("")
            self._update_usage_options("")
        self._apply_species_selector_lock()

    def _combo_row(self, *widgets: QWidget) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for index, widget in enumerate(widgets):
            layout.addWidget(widget, 1 if index == 0 else 0)
        return container

    def _build_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # ── 左ペイン ──────────────────────────────────────────────────────
        left_pane = QWidget()
        left_pane.setFixedWidth(380)
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # 基本
        basic_box = QGroupBox("基本")
        basic_form = QFormLayout(basic_box)
        self.name_combo = SuggestComboBox([""] + self._all_species_names)
        self.name_combo.setPlaceholderText("名前を入力または選択")
        basic_form.addRow("名前:", self.name_combo)

        self.ability_combo = SuggestComboBox([""] + self._all_abilities)
        self.ability_combo.setPlaceholderText("特性を入力または選択")
        basic_form.addRow("特性:", self.ability_combo)

        self.item_combo = SuggestComboBox([""] + self._all_items)
        self.item_combo.setPlaceholderText("持ち物を入力または選択")
        basic_form.addRow("持ち物:", self.item_combo)

        self.terastal_combo = QComboBox()
        for type_en, type_ja in _TERASTAL_TYPE_EN_TO_JA.items():
            self.terastal_combo.addItem(type_ja, type_en)
        self.terastal_combo.setCurrentIndex(0)
        if self._show_terastal_picker:
            basic_form.addRow("テラスタイプ:", self.terastal_combo)
        left_layout.addWidget(basic_box)

        # 努力値/性格（スライダー形式）— 順番: 努力値→性格
        stat_box = QGroupBox("努力値/性格")
        stat_layout = QVBoxLayout(stat_box)
        stat_layout.setSpacing(4)

        self._ev_sliders: dict[str, QSlider] = {}
        self._stat_val_labels: dict[str, QLabel] = {}
        self._ev_toggle_buttons: dict[str, QPushButton] = {}
        for key, lbl_text in _STAT_LABELS.items():
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)

            stat_lbl = QLabel("{}(---)".format(lbl_text))
            stat_lbl.setFixedWidth(72)
            stat_lbl.setStyleSheet("font-size:13px;font-weight:bold;color:#cdd6f4;")
            self._stat_val_labels[key] = stat_lbl
            row.addWidget(stat_lbl)

            minus_btn = QPushButton("−")
            minus_btn.setFixedSize(24, 24)
            minus_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #f38ba8;color:#f38ba8;"
                "font-weight:bold;border-radius:3px;font-size:14px;padding:0;}"
                "QPushButton:hover{background:#3b3240;}"
            )
            row.addWidget(minus_btn)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 32)
            slider.setValue(0)
            slider.setFixedHeight(24)
            slider.valueChanged.connect(lambda _, stat_key=key: self._on_ev_changed(stat_key))
            self._ev_sliders[key] = slider
            minus_btn.clicked.connect(lambda _, s=slider: s.setValue(max(0, s.value() - 1)))

            plus_btn = QPushButton("+")
            plus_btn.setFixedSize(24, 24)
            plus_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #a6e3a1;color:#a6e3a1;"
                "font-weight:bold;border-radius:3px;font-size:14px;padding:0;}"
                "QPushButton:hover{background:#2f3c36;}"
            )
            plus_btn.clicked.connect(lambda _, s=slider: s.setValue(min(32, s.value() + 1)))

            val_lbl = QLabel("0")
            val_lbl.setFixedWidth(15)
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_lbl.setStyleSheet("font-size:13px;color:#a6adc8;font-weight:bold;")
            slider.valueChanged.connect(val_lbl.setNum)

            row.addWidget(slider, 1)
            row.addWidget(plus_btn)
            row.addWidget(val_lbl)

            toggle_btn = QPushButton("32振り")
            toggle_btn.setFixedSize(48, 24)
            toggle_btn.setStyleSheet(
                "QPushButton{font-size:13px;font-weight:bold;"
                "background:#313244;border:1px solid #89b4fa;color:#89b4fa;"
                "border-radius:3px;padding:0;}"
                "QPushButton:hover{background:#2a3452;}"
            )
            toggle_btn.clicked.connect(lambda _, s=slider: s.setValue(0 if s.value() == 32 else 32))
            row.addWidget(toggle_btn)

            stat_layout.addLayout(row)
            self._ev_toggle_buttons[key] = toggle_btn

        nature_row = QHBoxLayout()
        nature_row.setContentsMargins(0, 4, 0, 0)
        nature_row.setSpacing(4)
        nature_lbl = QLabel("性格")
        nature_lbl.setFixedWidth(72)
        nature_lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;")
        nature_row.addWidget(nature_lbl)

        self.nature_btn = QPushButton("がんばりや（補正なし）")
        self.nature_btn.setFixedHeight(32)
        self.nature_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.nature_btn.setStyleSheet(
            "QPushButton{font-size:15px;text-align:left;padding:0 6px;"
            "background:#313244;border:1px solid #45475a;border-radius:4px;}"
            "QPushButton:hover{border-color:#89b4fa;}"
        )
        self.nature_btn.clicked.connect(self._select_nature)
        nature_row.addWidget(self.nature_btn, 1)
        stat_layout.addLayout(nature_row)

        left_layout.addWidget(stat_box)

        # わざ
        move_box = QGroupBox("わざ")
        move_layout = QVBoxLayout(move_box)
        move_layout.setContentsMargins(8, 10, 8, 10)
        move_layout.setSpacing(8)
        self._move_buttons: list[QPushButton] = []
        for index in range(4):
            row_widget = QWidget()
            row_widget.setFixedHeight(42)
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            button = QPushButton("わざを選択")
            button.setMinimumHeight(36)
            button.setMaximumHeight(36)
            button.clicked.connect(lambda _, slot=index: self._open_move_dialog(slot))
            row.addWidget(button, 1)
            row.setAlignment(button, Qt.AlignVCenter)
            move_layout.addWidget(row_widget, 0, Qt.AlignTop)
            self._move_buttons.append(button)
        move_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        left_layout.addWidget(move_box)

        left_layout.addStretch()

        footer_layout = QVBoxLayout()
        footer_layout.setSpacing(4)
        footer_layout.setContentsMargins(0, 0, 0, 0)

        first_row = QHBoxLayout()
        first_row.setSpacing(4)

        if not self._save_to_db:
            box_button = QPushButton("ボックス")
            box_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            box_button.setStyleSheet(
                "QPushButton { background-color: #45475a; color: #cdd6f4; font-weight: bold; font-size: 15px; border-radius: 6px; min-height: 32px; max-height: 32px; }"
                "QPushButton:hover { background-color: #585b70; }"
            )
            box_button.clicked.connect(self._on_box_select_clicked)
            first_row.addWidget(box_button, 1)

        cancel_button = QPushButton("キャンセル")
        cancel_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        cancel_button.setStyleSheet(
            "QPushButton { background-color: #45475a; color: #cdd6f4; font-weight: bold; font-size: 15px; border-radius: 6px; min-height: 32px; max-height: 32px; }"
            "QPushButton:hover { background-color: #585b70; }"
        )
        cancel_button.clicked.connect(self.reject)
        first_row.addWidget(cancel_button, 1)

        footer_layout.addLayout(first_row, 1)

        second_row = QHBoxLayout()
        second_row.setSpacing(4)

        if not self._save_to_db:
            apply_button = QPushButton("反映")
            apply_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            apply_button.setStyleSheet(
                "QPushButton { background-color: #89b4fa; color: #1e1e2e; font-weight: bold; font-size: 15px; border-radius: 6px; min-height: 32px; max-height: 32px; }"
                "QPushButton:hover { background-color: #b4d0fa; }"
            )
            apply_button.clicked.connect(self._save)
            second_row.addWidget(apply_button, 1)

            save_button = QPushButton("保存")
            save_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            save_button.setStyleSheet(
                "QPushButton { background-color: #45475a; color: #cdd6f4; font-weight: bold; font-size: 15px; border-radius: 6px; min-height: 32px; max-height: 32px; }"
                "QPushButton:hover { background-color: #585b70; }"
            )
            save_button.clicked.connect(lambda _=False: self._save(save_to_db_override=True))
            second_row.addWidget(save_button, 1)
        else:
            save_button = QPushButton("保存")
            save_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            save_button.setStyleSheet(
                "QPushButton { background-color: #89b4fa; color: #1e1e2e; font-weight: bold; font-size: 15px; border-radius: 6px; min-height: 32px; max-height: 32px; }"
                "QPushButton:hover { background-color: #b4d0fa; }"
            )
            save_button.clicked.connect(self._save)
            second_row.addWidget(save_button, 1)

        footer_layout.addLayout(second_row, 1)

        left_layout.addLayout(footer_layout)

        main_layout.addWidget(left_pane)

        # ── 右ペイン ──────────────────────────────────────────────────────
        right_pane = self._build_right_pane()
        main_layout.addWidget(right_pane, 1)

        self.name_combo.currentTextChanged.connect(self._on_name_changed)
        self.name_combo.currentTextChanged.connect(lambda _: self._pane_refresh_list())
        self.name_combo.lineEdit().textEdited.connect(self._on_name_manually_edited)
        self._pane_list.installEventFilter(self)
        self._set_nature("がんばりや", recalc=False)
        self._refresh_move_buttons()

    def _apply_species_selector_lock(self) -> None:
        self.name_combo.setEnabled(not self._lock_species_selector)

    # ── 右ペイン構築・操作 ──────────────────────────────────────────────

    def _build_right_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        type_box = QGroupBox("タイプ絞り込み")
        type_layout = QVBoxLayout(type_box)
        type_layout.setContentsMargins(6, 6, 6, 6)
        type_grid = QGridLayout()
        type_grid.setHorizontalSpacing(4)
        type_grid.setVerticalSpacing(4)

        self._pane_type_buttons: dict[str, TypeIconButton] = {}
        for index, type_en in enumerate(TYPE_EN_TO_JA):
            button = TypeIconButton(type_en, show_label=False)
            button.toggled.connect(lambda checked, value=type_en: self._pane_on_type_toggled(value, checked))
            self._pane_type_buttons[type_en] = button
            type_grid.addWidget(button, index // 6, index % 6)

        grid_wrap = QHBoxLayout()
        grid_wrap.setContentsMargins(0, 0, 0, 0)
        grid_wrap.addLayout(type_grid)
        grid_wrap.addStretch()
        type_layout.addLayout(grid_wrap)
        layout.addWidget(type_box)

        sort_row = QHBoxLayout()
        self._pane_sort_buttons: dict[str, ChipButton] = {}
        for sort_key, sort_label in (("usage", "採用順"), ("dex", "図鑑順"), ("name", "名前順")):
            btn = ChipButton(sort_label, "#74c7ec")
            btn.clicked.connect(lambda _, value=sort_key: self._pane_set_sort_mode(value))
            sort_row.addWidget(btn)
            self._pane_sort_buttons[sort_key] = btn
        self._pane_result_label = QLabel("")
        self._pane_result_label.setStyleSheet("color: #a6adc8; font-size: 14px;")
        sort_row.addWidget(self._pane_result_label)
        sort_row.addStretch()
        layout.addLayout(sort_row)

        self._pane_list = QListWidget()
        self._pane_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._pane_list.setStyleSheet(
            "QListWidget { font-size: 15px; }"
            "QListWidget::item { padding: 0px; margin: 0px; border-bottom: 1px solid #2b2f3f; }"
            "QListWidget::item:selected { background: #1b2a43; }"
        )
        self._pane_list.itemDoubleClicked.connect(lambda *_: self._on_pokemon_double_clicked())
        self._pane_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._pane_list.customContextMenuRequested.connect(self._on_pane_list_context_menu)
        layout.addWidget(self._pane_list, 1)

        self._pane_apply_button_state()
        return pane

    def _on_pane_list_context_menu(self, pos) -> None:
        item = self._pane_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        action = menu.addAction("選択")
        action.triggered.connect(self._on_pokemon_double_clicked)
        menu.exec_(self._pane_list.viewport().mapToGlobal(pos))

    def _pane_apply_button_state(self) -> None:
        for type_en, button in self._pane_type_buttons.items():
            button.blockSignals(True)
            button.setChecked(type_en in self._pane_type_filters)
            button.blockSignals(False)
            button._update_style(button.isChecked())

        for sort_key, button in self._pane_sort_buttons.items():
            button.blockSignals(True)
            button.setChecked(sort_key == self._pane_sort_mode)
            button.blockSignals(False)
            button._update_style(button.isChecked())

    def _pane_clear_type_filters(self) -> None:
        self._pane_type_filters.clear()
        self._pane_apply_button_state()
        self._pane_refresh_list()

    def _pane_on_type_toggled(self, type_en: str, checked: bool) -> None:
        if checked:
            self._pane_type_filters.add(type_en)
        else:
            self._pane_type_filters.discard(type_en)
        self._pane_apply_button_state()
        self._pane_refresh_list()

    def _pane_set_sort_mode(self, mode: str) -> None:
        self._pane_sort_mode = mode
        self._pane_apply_button_state()
        self._pane_refresh_list()

    def _pane_sort_key(self, entry: PokemonPickerEntry):
        if self._pane_sort_mode == "name":
            return (entry.display_name,)
        if self._pane_sort_mode == "dex":
            return (_dex_sort_key(entry.dex_no), entry.display_name)
        usage_missing = 0 if entry.usage_rank else 1
        return (usage_missing, entry.usage_rank or 9999, _dex_sort_key(entry.dex_no), entry.display_name)

    def _pane_refresh_list(self) -> None:
        keyword = self.name_combo.current_text_stripped()
        self._pane_list.clear()
        self._pane_icon_job_id += 1
        current_job_id = self._pane_icon_job_id

        filtered: list[PokemonPickerEntry] = []
        for entry in self._picker_entries:
            if keyword:
                lowered = _normalize_kana(keyword.lower())
                if not (
                    lowered in _normalize_kana(entry.display_name.lower())
                    or lowered in entry.name_en.lower()
                    or lowered in _normalize_kana(entry.species_lookup_name.lower())
                ):
                    continue
            if self._pane_type_filters and not self._pane_type_filters.issubset(set(entry.type_names)):
                continue
            filtered.append(entry)

        filtered.sort(key=self._pane_sort_key)
        visible = filtered[:_POKEMON_BAND_RESULT_LIMIT]
        if len(filtered) > len(visible):
            self._pane_result_label.setText(
                "{}件中 {}件を表示。タイプ切替後に画像を順次読み込みます。".format(len(filtered), len(visible))
            )
        else:
            self._pane_result_label.setText("{}件".format(len(filtered)))

        current_name = self.name_combo.current_text_stripped()
        selected_item = None
        for entry in visible:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, entry.display_name)
            item.setData(Qt.UserRole + 1, entry.image_url)
            item.setData(Qt.UserRole + 2, entry.display_name)
            item.setData(Qt.UserRole + 3, entry.name_en)
            item.setSizeHint(QSize(0, 72))
            self._pane_list.addItem(item)
            self._pane_list.setItemWidget(item, PokemonBandRow(entry, self._pane_list))
            if entry.display_name == current_name:
                selected_item = item

        if selected_item:
            self._pane_list.setCurrentItem(selected_item)
            self._pane_list.scrollToItem(selected_item)
        # デフォルトでは無選択状態にするため、elseブロック（setCurrentRow(0)）を削除

        QTimer.singleShot(0, lambda job_id=current_job_id: self._pane_load_icons_step(job_id, 0))

    def _pane_load_icons_step(self, job_id: int, start_index: int) -> None:
        if job_id != self._pane_icon_job_id:
            return
        count = self._pane_list.count()
        if start_index >= count:
            return
        end_index = min(start_index + 8, count)
        from src.ui.ui_utils import sprite_pixmap_or_zukan as _sprite_or_zukan
        for row in range(start_index, end_index):
            item = self._pane_list.item(row)
            image_url = item.data(Qt.UserRole + 1) or ""
            label = item.data(Qt.UserRole + 2) or ""
            name_en = item.data(Qt.UserRole + 3) or ""
            pm = _sprite_or_zukan(label, 64, 64, name_en=name_en)
            sprite_pm = pm if pm else _pokemon_pixmap(image_url, 64, 64, label)
            widget = self._pane_list.itemWidget(item)
            if isinstance(widget, PokemonBandRow):
                widget.set_sprite(sprite_pm)
        QTimer.singleShot(0, lambda: self._pane_load_icons_step(job_id, end_index))

    def _on_pokemon_double_clicked(self) -> None:
        item = self._pane_list.currentItem()
        if not item:
            return
        display_name = item.data(Qt.UserRole) or ""
        # フィールドをクリアしてから反映（前の情報が残らないように）
        self._loading = True
        self.ability_combo.set_text("")
        self.item_combo.set_text("")
        self._set_nature("がんばりや", recalc=False)
        for slider in self._ev_sliders.values():
            slider.setValue(0)
        for key in self._ev_sliders:
            self._update_ev_toggle_label(key)
        self._selected_moves = ["", "", "", ""]
        self._refresh_move_buttons()
        self._loading = False
        # テンプレートが再ロードされるよう is_new_entry フラグをリセット
        self._auto_template_key = ""
        self._is_new_entry = True
        self.name_combo.set_text(display_name)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._pane_list and event.type() == QEvent.ToolTip:
            if not self._pane_tooltip_shown:
                self._pane_tooltip_shown = True
                QToolTip.showText(event.globalPos(), "ダブルクリックで反映", self._pane_list)
            return True
        return super().eventFilter(obj, event)

    def _on_name_manually_edited(self, _text: str) -> None:
        """ユーザーが名前欄を直接編集した時にタイプフィルタを全タイプに戻す。"""
        if self._pane_type_filters:
            self._pane_type_filters.clear()
            self._pane_apply_button_state()

    # ── 種族・フォーム解決 ──────────────────────────────────────────────

    def _resolve_species_lookup_name(self, display_name: str) -> str:
        name = (display_name or "").strip()
        if name in self._form_options_by_base:
            return name
        for base_name, options in self._form_options_by_base.items():
            if any(option.display_name == name for option in options):
                return base_name
        entry = self._picker_entry_map.get(name)
        if entry:
            return entry.species_lookup_name
        # Try normalized display name (e.g. ♀ → (メス) display) to find picker entry
        normalized_display = _normalize_picker_display_name(name)
        if normalized_display != name:
            entry2 = self._picker_entry_map.get(normalized_display)
            if entry2:
                return entry2.species_lookup_name
        return name

    def _resolve_loaded_form(self, stored_name: str) -> tuple[str, str | None]:
        name = (stored_name or "").strip()
        if not name:
            return "", None
        if name in self._form_options_by_base:
            return name, name
        for base_name, options in self._form_options_by_base.items():
            for option in options:
                if option.display_name == name:
                    return base_name, option.display_name
        # Also try the normalized display name (e.g. DB stores "イダイトウ♀",
        # but picker uses "イダイトウ(メス)" as display_name).
        normalized = _normalize_picker_display_name(name)
        if normalized != name:
            if normalized in self._form_options_by_base:
                return normalized, normalized
            for base_name, options in self._form_options_by_base.items():
                for option in options:
                    if option.display_name == normalized:
                        return base_name, option.display_name
        return name, None

    def _set_form_options(self, base_name: str, preferred_display_name: str | None = None) -> None:
        base_name = (base_name or "").strip()
        species = db.get_species_by_name_ja(base_name) if base_name else None
        if species:
            default_base = FormOption(
                key="base",
                label="通常",
                display_name=species.name_ja,
                species_lookup_name=species.name_ja,
                base_dex_no="{:04d}".format(species.species_id),
                dex_no="{:04d}".format(species.species_id),
                usage_name=species.name_ja,
                type_names=tuple(type_name for type_name in [species.type1, species.type2] if type_name),
                is_base=True,
            )
            options = self._form_options_by_base.get(species.name_ja, [default_base])
        else:
            options = []

        self._current_form_options = options

        # フォームインデックスを preferred_display_name または name_combo テキストから決定
        index = 0
        effective_display = preferred_display_name or self.name_combo.current_text_stripped()
        if effective_display and options:
            for idx, option in enumerate(options):
                if option.display_name == effective_display:
                    index = idx
                    break
            else:
                if not preferred_display_name and base_name in _DEFAULT_FORM_INDEX:
                    index = min(_DEFAULT_FORM_INDEX[base_name], len(options) - 1)
        elif not preferred_display_name and base_name in _DEFAULT_FORM_INDEX and options:
            index = min(_DEFAULT_FORM_INDEX[base_name], len(options) - 1)
        self._selected_form_index = index

    def _current_form_option(self) -> FormOption | None:
        if not self._current_form_options:
            return None
        index = self._selected_form_index
        if 0 <= index < len(self._current_form_options):
            return self._current_form_options[index]
        return self._current_form_options[0]

    def _usage_lookup_name(self, display_name: str) -> str:
        option = self._current_form_option()
        if option:
            name = option.usage_name
        else:
            name = self._resolve_species_lookup_name(display_name)
        # Normalize full-width parens to half-width (pokedb_tokyo uses half-width)
        return name.replace("（", "(").replace("）", ")")

    def _selected_species(self) -> SpeciesInfo | None:
        lookup_name = self._resolve_species_lookup_name(self.name_combo.current_text_stripped())
        return db.get_species_by_name_ja(lookup_name)

    def _effective_species_for_calc(self) -> SpeciesInfo | None:
        species = self._selected_species()
        if not species:
            return None
        option = self._current_form_option()
        if not option or option.is_base:
            return species

        resolved = _resolve_form_species_from_pokeapi(species, option)
        if resolved:
            return resolved

        base_detail = zukan_client.get_pokemon_detail(option.base_dex_no)
        form_detail = zukan_client.get_pokemon_detail(option.dex_no)
        if not base_detail or not form_detail:
            return species

        def rank(detail: dict, key: str) -> int:
            try:
                return int(detail.get(key) or 0)
            except (TypeError, ValueError):
                return 0

        def scaled(base_value: int, base_rank: int, form_rank: int) -> int:
            if base_value <= 0 or base_rank <= 0 or form_rank <= 0:
                return base_value
            value = int(round(base_value * (form_rank / float(base_rank))))
            return max(1, min(255, value))

        base_hp_rank = rank(base_detail, "spec_hp")
        base_attack_rank = rank(base_detail, "spec_kougeki")
        base_defense_rank = rank(base_detail, "spec_bougyo")
        base_sp_attack_rank = rank(base_detail, "spec_tokukou")
        base_sp_defense_rank = rank(base_detail, "spec_tokubou")
        base_speed_rank = rank(base_detail, "spec_subayasa")

        form_hp_rank = rank(form_detail, "spec_hp")
        form_attack_rank = rank(form_detail, "spec_kougeki")
        form_defense_rank = rank(form_detail, "spec_bougyo")
        form_sp_attack_rank = rank(form_detail, "spec_tokukou")
        form_sp_defense_rank = rank(form_detail, "spec_tokubou")
        form_speed_rank = rank(form_detail, "spec_subayasa")

        return SpeciesInfo(
            species_id=species.species_id,
            name_ja=option.display_name or species.name_ja,
            name_en=species.name_en,
            type1=option.type_names[0] if len(option.type_names) >= 1 else species.type1,
            type2=option.type_names[1] if len(option.type_names) >= 2 else "",
            base_hp=scaled(species.base_hp, base_hp_rank, form_hp_rank),
            base_attack=scaled(species.base_attack, base_attack_rank, form_attack_rank),
            base_defense=scaled(species.base_defense, base_defense_rank, form_defense_rank),
            base_sp_attack=scaled(species.base_sp_attack, base_sp_attack_rank, form_sp_attack_rank),
            base_sp_defense=scaled(species.base_sp_defense, base_sp_defense_rank, form_sp_defense_rank),
            base_speed=scaled(species.base_speed, base_speed_rank, form_speed_rank),
            weight_kg=_safe_float(form_detail.get("omosa"), species.weight_kg),
        )

    def _selected_types(self) -> list[str]:
        option = self._current_form_option()
        if option and option.type_names:
            return list(option.type_names)
        species = self._effective_species_for_calc()
        if not species:
            return []
        return [type_name for type_name in [species.type1, species.type2] if type_name]

    def _set_nature(self, nature: str, recalc: bool = True) -> None:
        nature = nature if nature in NATURES_JA else "まじめ"
        self._current_nature = nature
        boost, reduce = NATURES_JA.get(nature, (None, None))
        if boost and reduce:
            text = "{}  (↑{} / ↓{})".format(
                nature,
                _STAT_LABELS.get(boost, boost),
                _STAT_LABELS.get(reduce, reduce),
            )
        else:
            text = "{}  (補正なし)".format(nature)
        self.nature_btn.setText(text)
        self._update_stat_label_colors()
        if recalc:
            self._recalculate_stats_from_species()

    def _update_stat_label_colors(self) -> None:
        boost, reduce = NATURES_JA.get(self._current_nature, (None, None))
        for stat_key, label in self._stat_val_labels.items():
            base_style = "font-size:13px;font-weight:bold;"
            if stat_key == boost:
                label.setStyleSheet(base_style + "color:#f38ba8;")
            elif stat_key == reduce:
                label.setStyleSheet(base_style + "color:#89b4fa;")
            else:
                label.setStyleSheet(base_style + "color:#cdd6f4;")

    def _form_ability_names(self) -> list[str]:
        option = self._current_form_option()
        result: list[str] = []
        if option:
            detail = zukan_client.get_pokemon_detail(option.dex_no)
            if detail:
                for key in ("tokusei_1", "tokusei_2", "tokusei_3"):
                    ability_name = zukan_client.get_ability_name_by_id(detail.get(key))
                    if ability_name and ability_name not in result:
                        result.append(ability_name)

        # Zukan details often omit hidden abilities for low-usage Pokemon/forms.
        # Supplement from PokeAPI ability list of the effective form.
        species = self._effective_species_for_calc()
        if species and species.name_en:
            for ability_name in _pokeapi_ability_names_for_pokemon(species.name_en):
                if ability_name and ability_name not in result:
                    result.append(ability_name)
        return result

    def _apply_form_ability_default(self) -> None:
        form_abilities = self._form_ability_names()
        if not form_abilities:
            return
        current = self.ability_combo.current_text_stripped()
        if current not in form_abilities:
            self.ability_combo.set_text(form_abilities[0])

    def _update_usage_options(self, pokemon_name: str) -> None:
        usage_name = self._usage_lookup_name(pokemon_name)
        form_abilities = self._form_ability_names()
        usage_abilities = db.get_abilities_by_usage(usage_name) if usage_name else []
        ranked_abilities = _filter_ranked_abilities_for_form(
            form_abilities + usage_abilities,
            form_abilities,
        )
        ability_items, ability_separator = _build_ranked_options(
            ranked_abilities,
            self._all_abilities,
        )
        item_items, item_separator = _build_ranked_options(
            db.get_items_by_usage(usage_name) if usage_name else [],
            self._all_items,
        )

        self.ability_combo.set_items(ability_items, separator_after=ability_separator)
        self.item_combo.set_items(item_items, separator_after=item_separator)

    def _apply_usage_template_defaults(self, pokemon_name: str) -> None:
        usage_name = self._usage_lookup_name(pokemon_name)
        if not usage_name:
            return

        usage_abilities = db.get_abilities_by_usage(usage_name)
        usage_items = db.get_items_by_usage(usage_name)
        usage_natures = db.get_natures_by_usage(usage_name)
        usage_spreads = db.get_effort_spreads_by_usage(usage_name)
        usage_moves = [move for move in db.get_moves_by_usage(usage_name) if move]

        has_usage_template = any([
            bool(usage_abilities),
            bool(usage_items),
            bool(usage_natures),
            bool(usage_spreads),
            bool(usage_moves),
        ])
        if not has_usage_template:
            self._apply_non_usage_template_defaults()
            self._recalculate_stats_from_species()
            return

        form_abilities = self._form_ability_names()
        abilities = _filter_ranked_abilities_for_form(
            usage_abilities,
            form_abilities,
        )
        if abilities:
            self.ability_combo.set_text(abilities[0])
        else:
            self._apply_form_ability_default()

        if usage_items:
            self.item_combo.set_text(usage_items[0])

        if usage_natures:
            self._set_nature(usage_natures[0], recalc=False)
        else:
            self._set_nature("がんばりや", recalc=False)

        if usage_spreads:
            hp_pt, attack_pt, defense_pt, sp_attack_pt, sp_defense_pt, speed_pt, _ = usage_spreads[0]
            spread_map = {
                "hp": hp_pt,
                "attack": attack_pt,
                "defense": defense_pt,
                "sp_attack": sp_attack_pt,
                "sp_defense": sp_defense_pt,
                "speed": speed_pt,
            }
            self._updating_stats = True
            for key, slider in self._ev_sliders.items():
                slider.setValue(max(0, min(32, int(spread_map.get(key, 0)))))
            self._updating_stats = False
            for key in self._ev_sliders:
                self._update_ev_toggle_label(key)
        else:
            self._updating_stats = True
            for slider in self._ev_sliders.values():
                slider.setValue(0)
            self._updating_stats = False
            for key in self._ev_sliders:
                self._update_ev_toggle_label(key)

        move_candidates = usage_moves
        non_status_candidates: list[str] = []
        for move_name in move_candidates:
            move_info = db.get_move_by_name_ja(move_name)
            if move_info and move_info.category != "status":
                non_status_candidates.append(move_name)
        self._selected_moves = (non_status_candidates + ["", "", "", ""])[:4]
        self._refresh_move_buttons()

        self._recalculate_stats_from_species()

    def _apply_non_usage_template_defaults(self) -> None:
        form_abilities = self._form_ability_names()
        if form_abilities:
            self.ability_combo.set_text(form_abilities[0])

        species = self._effective_species_for_calc()
        if not species:
            return

        base_attack = int(species.base_attack or 0)
        base_sp_attack = int(species.base_sp_attack or 0)
        is_attack_higher = base_attack > base_sp_attack
        is_sp_attack_higher = base_sp_attack > base_attack

        spread_map = {
            "hp": 0,
            "attack": 0,
            "defense": 0,
            "sp_attack": 0,
            "sp_defense": 0,
            "speed": 0,
        }

        if is_attack_higher:
            spread_map["hp"] = 2
            spread_map["attack"] = 32
            spread_map["speed"] = 32
            self._set_nature("いじっぱり", recalc=False)
        elif is_sp_attack_higher:
            spread_map["hp"] = 2
            spread_map["sp_attack"] = 32
            spread_map["speed"] = 32
            self._set_nature("ひかえめ", recalc=False)
        else:
            spread_map["hp"] = 2
            spread_map["attack"] = 32
            spread_map["sp_attack"] = 32
            self._set_nature("ゆうかん", recalc=False)

        self._updating_stats = True
        for key, slider in self._ev_sliders.items():
            slider.setValue(max(0, min(32, int(spread_map.get(key, 0)))))
        self._updating_stats = False
        for key in self._ev_sliders:
            self._update_ev_toggle_label(key)

        learned_moves: list[MoveInfo] = []
        if species.species_id:
            learned_moves = db.get_moves_for_species(species.species_id)
        own_types = [type_name for type_name in self._selected_types() if type_name]
        if not own_types:
            own_types = [type_name for type_name in [species.type1, species.type2] if type_name]

        selected_moves: list[str] = []
        if is_attack_higher:
            selected_moves.extend(self._best_stab_moves_by_category(learned_moves, own_types, "physical"))
        elif is_sp_attack_higher:
            selected_moves.extend(self._best_stab_moves_by_category(learned_moves, own_types, "special"))
        else:
            selected_moves.extend(self._best_stab_moves_by_category(learned_moves, own_types, "physical"))
            selected_moves.extend(self._best_stab_moves_by_category(learned_moves, own_types, "special"))

        deduped_moves: list[str] = []
        for move_name in selected_moves:
            if move_name and move_name not in deduped_moves:
                deduped_moves.append(move_name)
        self._selected_moves = (deduped_moves + ["", "", "", ""])[:4]
        self._refresh_move_buttons()

    def _best_stab_moves_by_category(
        self,
        learned_moves: list[MoveInfo],
        own_types: list[str],
        category: str,
    ) -> list[str]:
        results: list[str] = []
        for type_name in own_types[:2]:
            candidates = [
                move for move in learned_moves
                if move.type_name == type_name and move.category == category and int(move.power or 0) > 0
            ]
            if not candidates:
                continue
            best = sorted(
                candidates,
                key=lambda move: (-int(move.power or 0), move.name_ja),
            )[0]
            results.append(best.name_ja)
        return results

    def _update_ev_toggle_label(self, stat_key: str) -> None:
        ev_value = self._ev_sliders[stat_key].value()
        self._ev_toggle_buttons[stat_key].setText("0振り" if ev_value == 32 else "32振り")

    def _recalculate_stats_from_species(self) -> None:
        if self._loading or self._updating_stats:
            return
        species = self._effective_species_for_calc()
        if not species:
            for key, lbl_text in _STAT_LABELS.items():
                self._stat_val_labels[key].setText("{}(---)".format(lbl_text))
            return

        from src.calc.damage_calc import fill_stats_from_species

        temp = PokemonInstance(
            species_id=species.species_id,
            name_ja=species.name_ja,
            name_en=species.name_en,
            types=self._selected_types(),
            weight_kg=species.weight_kg,
            nature=self._current_nature,
            ev_hp=self._ev_sliders["hp"].value() * 8,
            ev_attack=self._ev_sliders["attack"].value() * 8,
            ev_defense=self._ev_sliders["defense"].value() * 8,
            ev_sp_attack=self._ev_sliders["sp_attack"].value() * 8,
            ev_sp_defense=self._ev_sliders["sp_defense"].value() * 8,
            ev_speed=self._ev_sliders["speed"].value() * 8,
        )
        fill_stats_from_species(temp, species)

        for key, lbl_text in _STAT_LABELS.items():
            self._stat_val_labels[key].setText("{}({})".format(lbl_text, getattr(temp, key)))

    def _move_button_style(self, move_name: str) -> str:
        move = db.get_move_by_name_ja(move_name)
        if not move:
            return ""
        background = TYPE_COLORS.get(move.type_name, "#45475a")
        text_color = _best_text_color(background)
        return (
            "QPushButton { background-color: %s; color: %s; border: 1px solid #585b70; "
            "border-radius: 6px; font-weight: bold; text-align: left; padding: 6px 10px; }"
            "QPushButton:hover { border-color: #f9e2af; }"
        ) % (background, text_color)

    def _refresh_move_buttons(self) -> None:
        for index, button in enumerate(self._move_buttons):
            name = self._selected_moves[index]
            button.setText(name if name else "わざを選択")
            if name:
                button.setStyleSheet(self._move_button_style(name))
            else:
                button.setStyleSheet("")

    def _on_name_changed(self, name: str) -> None:
        if self._loading:
            return
        if not name.strip():
            return
        base_name = self._resolve_species_lookup_name(name.strip())
        self._set_form_options(base_name)
        self._update_usage_options(base_name)
        self._apply_form_ability_default()
        template_key = self._usage_lookup_name(base_name)
        if self._is_new_entry and template_key and template_key != self._auto_template_key:
            self._apply_usage_template_defaults(base_name)
            self._auto_template_key = template_key
            return
        self._recalculate_stats_from_species()

    def _on_ev_changed(self, stat_key: str) -> None:
        self._update_ev_toggle_label(stat_key)
        self._recalculate_stats_from_species()

    def _select_nature(self) -> None:
        usage_name = self._usage_lookup_name(self.name_combo.current_text_stripped())
        ranked_natures = db.get_natures_by_usage(usage_name)[:4] if usage_name else []
        dialog = NatureSelectDialog(self._current_nature, ranked_natures, self)
        if dialog.exec_():
            self._set_nature(dialog.selected_nature(), recalc=not self._loading)

    def _open_move_dialog(self, slot: int) -> None:
        species = self._selected_species()
        form_option = self._current_form_option()
        display_name = form_option.display_name if form_option else self.name_combo.current_text_stripped()
        usage_name = self._usage_lookup_name(display_name)
        current_moves = list(self._selected_moves)
        original_move = current_moves[slot]
        current_moves[slot] = ""
        dialog = MoveSelectDialog(
            species.species_id if species else None,
            display_name,
            original_move,
            self,
            usage_name=usage_name,
            current_moves=current_moves,
        )
        if dialog.exec_():
            self._selected_moves = dialog.selected_moves()
            self._refresh_move_buttons()

    def _clear_move(self, slot: int) -> None:
        self._selected_moves[slot] = ""
        self._refresh_move_buttons()

    def _load(self, pokemon: PokemonInstance) -> None:
        self._loading = True
        self._is_new_entry = False
        self._pokemon = pokemon
        base_name, preferred_display = self._resolve_loaded_form(pokemon.name_ja)
        display_base = _normalize_picker_display_name(base_name) if base_name else base_name
        self.name_combo.set_text(display_base)
        self._set_form_options(base_name, preferred_display_name=preferred_display or pokemon.name_ja)
        self._update_usage_options(base_name)
        self.ability_combo.set_text(pokemon.ability)
        self.item_combo.set_text(pokemon.item)
        tera_index = self.terastal_combo.findData((pokemon.terastal_type or "normal"))
        if tera_index < 0:
            tera_index = self.terastal_combo.findData("normal")
        if tera_index >= 0:
            self.terastal_combo.setCurrentIndex(tera_index)
        self._set_nature(pokemon.nature or "まじめ", recalc=False)

        for key, lbl_text in _STAT_LABELS.items():
            stat_val = getattr(pokemon, key, 0)
            ev_pt = getattr(pokemon, "ev_{}".format(key), 0) // 8
            self._stat_val_labels[key].setText("{}({})".format(lbl_text, stat_val))
            self._ev_sliders[key].setValue(ev_pt)
            self._update_ev_toggle_label(key)

        self._selected_moves = (pokemon.moves + ["", "", "", ""])[:4]
        self._refresh_move_buttons()
        self._loading = False

    def _save(self, save_to_db_override: bool = False) -> None:
        base_name = self.name_combo.current_text_stripped()
        if not base_name:
            QMessageBox.warning(self, "エラー", "名前を入力または選択してください")
            return

        lookup_name = self._resolve_species_lookup_name(base_name)
        species = db.get_species_by_name_ja(lookup_name)
        if not species:
            # Usage-only entry (regional form not yet in species_cache).
            # Build a minimal SpeciesInfo from zukan data so saving is still possible.
            zukan_matches = zukan_client.get_pokemon_index()
            zukan_by_name: dict[str, list[zukan_client.ZukanPokemonEntry]] = {}
            for entry in zukan_matches:
                zukan_by_name.setdefault(entry.name_ja, []).append(entry)
            zukan_entry = _resolve_picker_zukan_entry(lookup_name, zukan_by_name)
            if zukan_entry:
                type_names = _zukan_entry_types(zukan_entry)
                species = SpeciesInfo(
                    species_id=0,
                    name_ja=lookup_name,
                    name_en="",
                    type1=type_names[0] if len(type_names) >= 1 else "normal",
                    type2=type_names[1] if len(type_names) >= 2 else "",
                    base_hp=0, base_attack=0, base_defense=0,
                    base_sp_attack=0, base_sp_defense=0, base_speed=0,
                )
            else:
                QMessageBox.warning(
                    self,
                    "エラー",
                    "ポケモン名の候補が見つかりません。\n先に PokeAPI データを取得してください。",
                )
                return

        form_option = self._current_form_option()
        display_name = form_option.display_name if form_option else species.name_ja
        selected_types = list(form_option.type_names) if form_option and form_option.type_names else self._selected_types()
        effective_species = self._effective_species_for_calc() or species

        pokemon = self._pokemon or PokemonInstance()
        pokemon.species_id = species.species_id
        pokemon.name_ja = display_name
        pokemon.usage_name = form_option.usage_name if form_option else species.name_ja
        pokemon.name_en = effective_species.name_en or species.name_en
        pokemon.types = selected_types
        pokemon.weight_kg = effective_species.weight_kg if effective_species.weight_kg > 0 else species.weight_kg
        pokemon.ability = self.ability_combo.current_text_stripped()
        pokemon.item = self.item_combo.current_text_stripped()
        pokemon.terastal_type = str(self.terastal_combo.currentData() or "normal")
        pokemon.nature = self._current_nature

        for key in self._ev_sliders:
            lbl_text = self._stat_val_labels[key].text()
            # ラベルは "HP(207)" 形式 — 括弧内の数値を取得
            try:
                stat_val = int(lbl_text.split("(")[-1].rstrip(")"))
            except (ValueError, IndexError):
                stat_val = 0
            setattr(pokemon, key, stat_val)
            setattr(pokemon, "ev_{}".format(key), self._ev_sliders[key].value() * 8)

        pokemon.max_hp = pokemon.hp
        pokemon.current_hp = pokemon.hp
        pokemon.moves = [move for move in self._selected_moves if move]

        if self._save_to_db or save_to_db_override:
            new_id = db.save_pokemon(pokemon)
            pokemon.db_id = new_id
        self._pokemon = pokemon
        self.accept()

    def _on_box_select_clicked(self) -> None:
        self._box_select_requested = True
        self.reject()

    def box_select_requested(self) -> bool:
        return self._box_select_requested

    def get_pokemon(self):
        return self._pokemon

    def _should_show_terastal_picker(self) -> bool:
        node = self.parent()
        while node is not None:
            if hasattr(node, "_damage_tera_visible"):
                return bool(getattr(node, "_damage_tera_visible", False))
            node = node.parent()
        return False

