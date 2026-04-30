from __future__ import annotations

# Reuse symbols/helpers defined in pokemon_edit_dialog.py.
from src.ui import pokemon_edit_dialog as _base

for _k, _v in _base.__dict__.items():
    if not _k.startswith("__"):
        globals()[_k] = _v

class NatureSelectDialog(QDialog):
    def __init__(self, current_nature: str, ranked_natures: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("性格を選択")
        self.setMinimumWidth(700)
        self._selected_nature = current_nature if current_nature in NATURES_JA else "まじめ"
        self._ranked_natures = ranked_natures or []
        self._build_ui()

    def _make_cell_button(self, label: str, nature: str) -> QPushButton:
        button = QPushButton(label)
        button.setMinimumHeight(44)
        if nature:
            button.clicked.connect(lambda: self._choose(nature))
        else:
            button.setEnabled(False)
            button.setText("—")
        return button

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        info = QLabel("横が上昇補正、縦が下降補正です。")
        info.setStyleSheet("color: #a6adc8;")
        layout.addWidget(info)

        grid = QGridLayout()
        grid.setHorizontalSpacing(2)
        grid.setVerticalSpacing(2)

        top_left = QLabel("")
        top_left.setFixedHeight(40)
        grid.addWidget(top_left, 0, 0)

        for col, stat_key in enumerate(_NATURE_MATRIX_ORDER, start=1):
            header = QLabel(_STAT_LABELS[stat_key])
            header.setAlignment(Qt.AlignCenter)
            header.setMinimumHeight(40)
            header.setStyleSheet(
                "background-color: #e86666; color: white; font-weight: bold; border: 1px solid #2b2d42;"
            )
            grid.addWidget(header, 0, col)

        for row, reduce_stat in enumerate(_NATURE_MATRIX_ORDER, start=1):
            row_header = QLabel(_STAT_LABELS[reduce_stat])
            row_header.setAlignment(Qt.AlignCenter)
            row_header.setMinimumHeight(40)
            row_header.setStyleSheet(
                "background-color: #6aa7ff; color: white; font-weight: bold; border: 1px solid #2b2d42;"
            )
            grid.addWidget(row_header, row, 0)

            for col, boost_stat in enumerate(_NATURE_MATRIX_ORDER, start=1):
                nature = "" if reduce_stat == boost_stat else _find_nature(boost_stat, reduce_stat)
                button = self._make_cell_button(nature or "—", nature)
                button.setStyleSheet(
                    "QPushButton { background-color: #f5f5f5; color: #11111b; border: 1px solid #555; }"
                    "QPushButton:disabled { background-color: #f0f0f0; color: #666; border: 1px solid #777; }"
                )
                grid.addWidget(button, row, col)

        layout.addLayout(grid)

        bottom_row = QHBoxLayout()

        neutral_box = QGroupBox("補正なし")
        neutral_layout = QVBoxLayout(neutral_box)
        neutral_button = QPushButton("がんばりや")
        neutral_button.setMinimumHeight(32)
        neutral_button.clicked.connect(lambda: self._choose("がんばりや"))
        neutral_layout.addWidget(neutral_button)
        neutral_box.setMaximumWidth(180)
        bottom_row.addWidget(neutral_box, 0)

        ranking_box = QGroupBox("使用率 上位4つ")
        ranking_layout = QGridLayout(ranking_box)
        for index in range(4):
            if index < len(self._ranked_natures):
                nature = self._ranked_natures[index]
                button = QPushButton("{}位\n{}".format(index + 1, nature))
                button.setMinimumHeight(52)
                button.clicked.connect(lambda _, value=nature: self._choose(value))
            else:
                button = QPushButton("{}位\n-".format(index + 1))
                button.setMinimumHeight(52)
                button.setEnabled(False)
            ranking_layout.addWidget(button, 0, index)
        bottom_row.addWidget(ranking_box, 1)
        layout.addLayout(bottom_row)

        cancel_button = QPushButton("閉じる")
        cancel_button.clicked.connect(self.reject)
        layout.addWidget(cancel_button)

    def _choose(self, nature: str) -> None:
        self._selected_nature = nature
        self.accept()

    def selected_nature(self) -> str:
        return self._selected_nature


class PokemonSelectDialog(QDialog):
    def __init__(self, current_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("ポケモンを選択")
        self.setMinimumSize(820, 920)
        self._selected_name = current_name.strip()
        self._entries = _build_pokemon_picker_entries()
        self._sort_mode = "usage"
        self._type_filters: set[str] = set()
        self._icon_job_id = 0
        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel("使用率順とタイプ条件でポケモンを選択できます。")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("名前や図鑑番号で検索")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._refresh_list)
        layout.addWidget(self._search_edit)

        # タイプ絞り込み（3列×6行グリッド）
        self._type_box = QGroupBox("タイプ絞り込み")
        type_layout = QVBoxLayout(self._type_box)
        type_layout.setContentsMargins(6, 6, 6, 6)

        type_grid = QGridLayout()
        type_grid.setHorizontalSpacing(4)
        type_grid.setVerticalSpacing(4)

        self._type_buttons: dict[str, TypeIconButton] = {}
        for index, type_en in enumerate(TYPE_EN_TO_JA):
            button = TypeIconButton(type_en, show_label=False)
            button.toggled.connect(lambda checked, value=type_en: self._on_type_toggled(value, checked))
            self._type_buttons[type_en] = button
            type_grid.addWidget(button, index // 6, index % 6)

        grid_wrap = QHBoxLayout()
        grid_wrap.setContentsMargins(0, 0, 0, 0)
        grid_wrap.addLayout(type_grid)
        grid_wrap.addStretch()
        type_layout.addLayout(grid_wrap)

        layout.addWidget(self._type_box)

        sort_row = QHBoxLayout()
        self._sort_buttons: dict[str, ChipButton] = {}
        for key, label in (
            ("usage", "採用順"),
            ("dex", "図鑑順"),
            ("name", "名前順"),
        ):
            button = ChipButton(label, "#74c7ec")
            button.clicked.connect(lambda _, value=key: self._set_sort_mode(value))
            sort_row.addWidget(button)
            self._sort_buttons[key] = button
        sort_row.addStretch()
        layout.addLayout(sort_row)

        self._result_label = QLabel("")
        self._result_label.setStyleSheet("color: #a6adc8; font-size: 14px;")
        layout.addWidget(self._result_label)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setIconSize(QSize(78, 78))
        self._list.setStyleSheet("QListWidget { font-size: 15px; }")
        self._list.itemDoubleClicked.connect(lambda *_: self._accept_selection())
        layout.addWidget(self._list, 1)

        button_row = QHBoxLayout()
        clear_button = QPushButton("未設定にする")
        clear_button.clicked.connect(self._clear_selection)
        button_row.addWidget(clear_button)
        button_row.addStretch()
        cancel_button = QPushButton("キャンセル")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        choose_button = QPushButton("選択")
        choose_button.clicked.connect(self._accept_selection)
        button_row.addWidget(choose_button)
        layout.addLayout(button_row)

        self._apply_button_state()

    def _apply_button_state(self) -> None:
        for type_en, button in self._type_buttons.items():
            button.blockSignals(True)
            button.setChecked(type_en in self._type_filters)
            button.blockSignals(False)
            button._update_style(button.isChecked())

        for key, button in self._sort_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == self._sort_mode)
            button.blockSignals(False)
            button._update_style(button.isChecked())

    def _clear_type_filters(self) -> None:
        self._type_filters.clear()
        self._apply_button_state()
        self._refresh_list()

    def _on_type_toggled(self, type_name: str, checked: bool) -> None:
        if checked:
            self._type_filters.add(type_name)
        else:
            self._type_filters.discard(type_name)
        self._apply_button_state()
        self._refresh_list()

    def _set_sort_mode(self, sort_mode: str) -> None:
        self._sort_mode = sort_mode
        self._apply_button_state()
        self._refresh_list()

    def _matches_keyword(self, entry: PokemonPickerEntry, keyword: str) -> bool:
        if not keyword:
            return True

        lowered = keyword.lower()
        normalized_number = lowered.replace("no.", "").replace("no", "").replace(".", "").strip()
        if normalized_number.isdigit():
            digits = normalized_number.lstrip("0") or "0"
            dex_digits = entry.dex_no.replace("-", "").lstrip("0") or "0"
            return digits in dex_digits

        return (
            lowered in entry.display_name.lower()
            or lowered in entry.name_en.lower()
            or lowered in entry.species_lookup_name.lower()
        )

    def _sort_key(self, entry: PokemonPickerEntry):
        if self._sort_mode == "name":
            return (entry.display_name,)
        if self._sort_mode == "dex":
            return (_dex_sort_key(entry.dex_no), entry.display_name)
        usage_missing = 0 if entry.usage_rank else 1
        usage_rank = entry.usage_rank or 9999
        return (usage_missing, usage_rank, _dex_sort_key(entry.dex_no), entry.display_name)

    def _format_item_text(self, entry: PokemonPickerEntry) -> str:
        type_text = " / ".join(TYPE_EN_TO_JA.get(type_name, type_name) for type_name in entry.type_names)
        usage_text = "使用率{}位".format(entry.usage_rank) if entry.usage_rank else "ローカル種族"
        name = entry.display_name or entry.species_lookup_name or "?"
        dex = (entry.dex_no or "").strip()
        if dex == "0000" or not dex:
            return "{}\n{}   {}".format(
                name,
                type_text,
                usage_text,
            )
        return "{}\nNo.{}   {}   {}".format(
            name,
            dex,
            type_text,
            usage_text,
        )

    def _refresh_list(self) -> None:
        keyword = self._search_edit.text().strip()
        self._list.clear()
        self._icon_job_id += 1
        current_job_id = self._icon_job_id

        filtered: list[PokemonPickerEntry] = []
        for entry in self._entries:
            if not self._matches_keyword(entry, keyword):
                continue
            if self._type_filters and not self._type_filters.issubset(set(entry.type_names)):
                continue
            filtered.append(entry)

        filtered.sort(key=self._sort_key)
        visible_entries = filtered[:_POKEMON_RESULT_LIMIT]
        if len(filtered) > len(visible_entries):
            self._result_label.setText(
                "{}件中 {}件を表示。タイプ切替後に画像を順次読み込みます。".format(
                    len(filtered),
                    len(visible_entries),
                )
            )
        else:
            self._result_label.setText("{}件".format(len(filtered)))

        selected_item: QListWidgetItem | None = None
        placeholder = _placeholder_pokemon_icon(78)
        for entry in visible_entries:
            item = QListWidgetItem(placeholder, self._format_item_text(entry))
            item.setData(Qt.UserRole, entry.display_name)
            item.setData(Qt.UserRole + 1, entry.image_url)
            item.setData(Qt.UserRole + 2, entry.display_name)
            item.setData(Qt.UserRole + 3, entry.name_en)
            item.setSizeHint(QSize(0, 94))
            self._list.addItem(item)
            if entry.display_name == self._selected_name:
                selected_item = item

        if selected_item:
            self._list.setCurrentItem(selected_item)
            self._list.scrollToItem(selected_item)
        elif self._list.count() > 0:
            self._list.setCurrentRow(0)

        QTimer.singleShot(0, lambda job_id=current_job_id: self._load_icons_step(job_id, 0))

    def _load_icons_step(self, job_id: int, start_index: int) -> None:
        if job_id != self._icon_job_id:
            return
        count = self._list.count()
        if start_index >= count:
            return

        end_index = min(start_index + 8, count)
        from src.ui.ui_utils import sprite_pixmap_or_zukan as _sprite_or_zukan
        for row in range(start_index, end_index):
            item = self._list.item(row)
            image_url = item.data(Qt.UserRole + 1) or ""
            label = item.data(Qt.UserRole + 2) or ""
            name_en = item.data(Qt.UserRole + 3) or ""
            pm = _sprite_or_zukan(label, 78, 78, name_en=name_en)
            icon = QIcon(pm) if pm else QIcon(_pokemon_pixmap(image_url, 78, 78, label))
            item.setIcon(icon)

        QTimer.singleShot(0, lambda: self._load_icons_step(job_id, end_index))

    def _accept_selection(self) -> None:
        item = self._list.currentItem()
        if not item:
            QMessageBox.information(self, "情報", "ポケモンを選択してください")
            return
        self._selected_name = item.data(Qt.UserRole) or ""
        self.accept()

    def _clear_selection(self) -> None:
        self._selected_name = ""
        self.accept()

    def selected_name(self) -> str:
        return self._selected_name


class MyBoxSelectDialog(QDialog):
    """登録済みポケモン（自分PT）からポケモンを選ぶダイアログ。"""

    def __init__(self, title: str = "自分PT", parent=None):
        super().__init__(parent)
        self.setWindowTitle("ボックスから選択")
        self.setFixedWidth(720)
        self.setMinimumHeight(660)
        self._selected_pokemon: PokemonInstance | None = None
        self._all_entries: list[PokemonInstance] = db.load_all_pokemon()
        self._type_filters: set[str] = set()
        self._build_ui()
        self._refresh_grid()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self._type_box = QGroupBox("タイプ絞り込み")
        type_layout = QVBoxLayout(self._type_box)
        type_layout.setContentsMargins(6, 6, 6, 6)

        type_grid = QGridLayout()
        type_grid.setHorizontalSpacing(4)
        type_grid.setVerticalSpacing(4)

        self._type_buttons: dict[str, TypeIconButton] = {}
        for index, type_en in enumerate(TYPE_EN_TO_JA):
            button = TypeIconButton(type_en, show_label=False)
            button.toggled.connect(lambda checked, v=type_en: self._on_type_toggled(v, checked))
            self._type_buttons[type_en] = button
            type_grid.addWidget(button, index // 6, index % 6)

        grid_wrap = QHBoxLayout()
        grid_wrap.setContentsMargins(0, 0, 0, 0)
        grid_wrap.addLayout(type_grid)
        grid_wrap.addStretch()
        type_layout.addLayout(grid_wrap)
        layout.addWidget(self._type_box)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(2, 2, 2, 2)
        self._grid_layout.setHorizontalSpacing(4)
        self._grid_layout.setVerticalSpacing(4)
        self._scroll.setWidget(self._grid_widget)
        layout.addWidget(self._scroll, 1)

        self._apply_button_state()

    def _apply_button_state(self) -> None:
        for type_en, button in self._type_buttons.items():
            button.blockSignals(True)
            button.setChecked(type_en in self._type_filters)
            button.blockSignals(False)
            button._update_style(button.isChecked())

    def _clear_type_filters(self) -> None:
        self._type_filters.clear()
        self._apply_button_state()
        self._refresh_grid()

    def _on_type_toggled(self, type_name: str, checked: bool) -> None:
        if checked:
            self._type_filters.add(type_name)
        else:
            self._type_filters.discard(type_name)
        self._apply_button_state()
        self._refresh_grid()

    def _get_type_names(self, p: PokemonInstance) -> list[str]:
        from src.data.database import get_species_by_id, get_species_by_name_ja
        species = get_species_by_id(p.species_id) if p.species_id else None
        if species is None and p.name_ja:
            species = get_species_by_name_ja(p.name_ja)
        if species:
            types = [species.type1] if species.type1 else []
            if species.type2:
                types.append(species.type2)
            return types
        return []

    def _refresh_grid(self) -> None:
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        from src.ui.ui_utils import sprite_pixmap_or_zukan

        filtered: list[PokemonInstance] = []
        for p in self._all_entries:
            if self._type_filters:
                types = set(self._get_type_names(p))
                if not self._type_filters.issubset(types):
                    continue
            filtered.append(p)
        filtered.sort(key=lambda p: (-(p.db_id or 0),))

        cols = 6
        cell_w = 112
        cell_h = 112
        sprite_size = 72
        for col in range(cols):
            self._grid_layout.setColumnStretch(col, 0)
        self._grid_layout.setColumnStretch(cols, 1)
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
            cell.setFixedSize(cell_w, cell_h)
            cell.setCursor(Qt.PointingHandCursor)
            cell.setToolTip("ダブルクリックで反映")
            cell.setStyleSheet(
                "QFrame { border: 2px solid #45475a; border-radius: 4px; background: #1e1e2e; }"
                "QFrame:hover { border: 2px solid #89b4fa; background: #2a2a3e; }"
            )
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(0)

            sprite_lbl = QLabel()
            sprite_lbl.setFixedSize(sprite_size, sprite_size)
            sprite_lbl.setAlignment(Qt.AlignCenter)
            sprite_lbl.setStyleSheet("border: none;")
            pm = sprite_pixmap_or_zukan(p.name_ja, sprite_size, sprite_size, name_en=p.name_en or "")
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

            def _on_double_click(_event, poke=p):
                self._selected_pokemon = poke
                self.accept()

            cell.mouseDoubleClickEvent = _on_double_click
            cell.setContextMenuPolicy(Qt.CustomContextMenu)
            def _on_ctx_menu(pos, poke=p, widget=cell):
                menu = QMenu(widget)
                act_apply = menu.addAction("反映")
                action = menu.exec_(widget.mapToGlobal(pos))
                if action == act_apply:
                    self._selected_pokemon = poke
                    self.accept()
            cell.customContextMenuRequested.connect(_on_ctx_menu)
            self._grid_layout.addWidget(cell, idx // cols, idx % cols)

        remainder = len(filtered) % cols
        if remainder:
            for col in range(remainder, cols):
                spacer = QWidget()
                spacer.setFixedSize(cell_w, cell_h)
                self._grid_layout.addWidget(spacer, len(filtered) // cols, col)
        next_row = (len(filtered) + cols - 1) // cols
        self._grid_layout.setRowStretch(next_row, 1)

    def selected_pokemon(self) -> PokemonInstance | None:
        return self._selected_pokemon


class _MoveSlotButton(QPushButton):
    """技スロットボタン：ダブルクリックまたは右クリック「クリア」でクリア。"""

    def __init__(self, slot_idx: int, dialog: "MoveSelectDialog") -> None:
        super().__init__()
        self._slot_idx = slot_idx
        self._dialog = dialog
        self.setMinimumHeight(40)
        self.setFocusPolicy(Qt.NoFocus)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self._dialog._clear_slot(self._slot_idx)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        action = menu.addAction("クリア")
        action.triggered.connect(lambda: self._dialog._clear_slot(self._slot_idx))
        menu.exec_(self.mapToGlobal(pos))


class MoveSelectDialog(QDialog):
    def __init__(
        self,
        species_id: int | None,
        pokemon_name: str,
        current_move: str = "",
        parent=None,
        usage_name: str | None = None,
        current_moves: list[str] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("技を選択")
        self.setMinimumSize(720, 760)
        self._species_id = species_id
        self._pokemon_name = pokemon_name
        self._usage_name = (usage_name or pokemon_name).strip()
        self._selected_move = current_move.strip()
        if current_moves is not None:
            self._slot_moves: list[str] = (list(current_moves) + ["", "", "", ""])[:4]
        else:
            self._slot_moves = [current_move.strip(), "", "", ""]
        self._learnset_ready = True
        self._all_moves = self._load_moves()
        self._search_only_moves = self._build_search_only_moves()
        self._usage_order = {
            name: index
            for index, name in enumerate(db.get_moves_by_usage(self._usage_name), start=1)
        }
        self._category_filter = "non_status"
        self._type_filter = ""
        self._sort_mode = "usage"
        self._tooltip_shown = False
        self._build_ui()
        self._list.viewport().installEventFilter(self)
        self._refresh_list()

    def _load_moves(self) -> list[MoveInfo]:
        if self._species_id:
            species_moves = db.get_moves_for_species(self._species_id)
            self._learnset_ready = bool(species_moves)

            move_map: dict[str, MoveInfo] = {}
            for move in species_moves:
                move_map[move.name_ja] = move

            # Learnset に無くても使用率に載っている技は候補として表示する。
            usage_moves = db.get_moves_by_usage(self._usage_name)
            for move_name in usage_moves:
                if move_name in move_map:
                    continue
                move = db.get_move_by_name_ja(move_name)
                if move:
                    move_map[move_name] = move

            if self._selected_move and self._selected_move not in move_map:
                move = db.get_move_by_name_ja(self._selected_move)
                if move:
                    move_map[self._selected_move] = move

            for _slot_mv in self._slot_moves:
                if _slot_mv and _slot_mv not in move_map:
                    move = db.get_move_by_name_ja(_slot_mv)
                    if move:
                        move_map[_slot_mv] = move

            if move_map:
                return list(move_map.values())
        return db.get_all_moves()

    def _build_search_only_moves(self) -> list[MoveInfo]:
        """技一覧は learnset+使用率を基本にし、検索時のみそれ以外も表示する。"""
        all_moves = db.get_all_moves()
        base_names = {move.name_ja for move in self._all_moves}
        return [move for move in all_moves if move.name_ja not in base_names]

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        self._category_buttons: dict[str, ChipButton] = {}
        for key in ("all", "physical", "special", "status"):
            button = ChipButton(_CATEGORY_LABELS[key], "#89b4fa")
            button.toggled.connect(lambda checked, value=key: self._on_category_toggled(value, checked))
            title_row.addWidget(button)
            self._category_buttons[key] = button
        title_row.addStretch()
        title = QLabel("候補: {}".format(self._pokemon_name or "全技"))
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        title_row.addWidget(title)
        layout.addLayout(title_row)

        if not self._learnset_ready and self._species_id:
            hint = QLabel("learnset が未取得です。PokeAPI取得後は覚える技だけを表示します。")
            hint.setStyleSheet("color: #f9e2af; font-size: 13px;")
            layout.addWidget(hint)

        # タイプ絞り込み（4列グリッド）
        self._type_box = QGroupBox("タイプ絞り込み")
        type_layout = QVBoxLayout(self._type_box)
        type_layout.setContentsMargins(6, 6, 6, 6)

        type_grid = QGridLayout()
        type_grid.setHorizontalSpacing(4)
        type_grid.setVerticalSpacing(4)

        self._type_buttons: dict[str, TypeIconButton] = {}
        for index, type_en in enumerate(TYPE_EN_TO_JA):
            button = TypeIconButton(type_en, show_label=False)
            button.toggled.connect(lambda checked, value=type_en: self._on_type_toggled(value, checked))
            self._type_buttons[type_en] = button
            type_grid.addWidget(button, index // 6, index % 6)

        grid_wrap = QHBoxLayout()
        grid_wrap.setContentsMargins(0, 0, 0, 0)
        grid_wrap.addLayout(type_grid)
        grid_wrap.addStretch()
        type_layout.addLayout(grid_wrap)

        layout.addWidget(self._type_box)

        sort_row = QHBoxLayout()
        self._sort_buttons: dict[str, ChipButton] = {}
        for key, label in (
            ("usage", "採用順"),
            ("name", "名前順"),
            ("power", "威力順"),
            ("pp", "PP順"),
        ):
            button = ChipButton(label, "#74c7ec")
            button.clicked.connect(lambda _, value=key: self._set_sort_mode(value))
            sort_row.addWidget(button)
            self._sort_buttons[key] = button
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("わざ名で検索")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._refresh_list)
        sort_row.addWidget(self._search_edit)
        layout.addLayout(sort_row)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setStyleSheet(
            "QListWidget { font-size: 15px; }"
            "QListWidget::item { padding: 0px; margin: 0px; border-bottom: 1px solid #2b2f3f; }"
            "QListWidget::item:selected { background: #1b2a43; }"
        )
        self._list.itemDoubleClicked.connect(lambda *_: self._add_to_slot())
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_list_context_menu)
        layout.addWidget(self._list, 1)

        slot_row = QHBoxLayout()
        slot_row.setSpacing(4)
        self._slot_buttons: list[_MoveSlotButton] = []
        for i in range(4):
            btn = _MoveSlotButton(i, self)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            slot_row.addWidget(btn)
            self._slot_buttons.append(btn)
        layout.addLayout(slot_row)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(4)
        confirm_btn = QPushButton("反映")
        confirm_btn.setMinimumHeight(40)
        confirm_btn.setStyleSheet(
            "QPushButton { background-color: #89b4fa; color: #1e1e2e; font-weight: bold; "
            "font-size: 15px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #b4d0fa; }"
        )
        confirm_btn.clicked.connect(self._confirm_selection)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.setMinimumHeight(40)
        cancel_btn.setStyleSheet(
            "QPushButton { background-color: #45475a; color: #cdd6f4; font-weight: bold; font-size: 15px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #585b70; }"
        )
        cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(confirm_btn, 2)
        bottom_row.addWidget(cancel_btn, 2)
        layout.addLayout(bottom_row)

        self._apply_filter_button_state()
        self._update_slot_buttons()



    def _apply_filter_button_state(self) -> None:
        for key, button in self._category_buttons.items():
            button.blockSignals(True)
            checked = key == self._category_filter or (key == "all" and self._category_filter == "non_status")
            button.setChecked(checked)
            button.blockSignals(False)
            button._update_style(button.isChecked())

        for key, button in self._type_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == self._type_filter)
            button.blockSignals(False)
            button._update_style(button.isChecked())

        for key, button in self._sort_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == self._sort_mode)
            button.blockSignals(False)
            button._update_style(button.isChecked())

    def _on_category_toggled(self, category: str, checked: bool) -> None:
        if checked:
            self._category_filter = category
        else:
            self._category_filter = "all"
        self._apply_filter_button_state()
        self._refresh_list()

    def _clear_type_filter(self) -> None:
        self._type_filter = ""
        self._apply_filter_button_state()
        self._refresh_list()

    def _on_type_toggled(self, type_name: str, checked: bool) -> None:
        if checked:
            self._type_filter = type_name
        else:
            self._type_filter = ""
        self._apply_filter_button_state()
        self._refresh_list()

    def _set_sort_mode(self, sort_mode: str) -> None:
        self._sort_mode = sort_mode
        self._apply_filter_button_state()
        self._refresh_list()

    def _sort_key(self, move: MoveInfo):
        usage_rank = self._usage_order.get(move.name_ja, 9999)
        in_usage = 0 if move.name_ja in self._usage_order else 1
        if self._sort_mode == "name":
            return (move.name_ja,)
        if self._sort_mode == "power":
            return (-move.power, in_usage, usage_rank, move.name_ja)
        if self._sort_mode == "pp":
            return (-move.pp, in_usage, usage_rank, move.name_ja)
        return (in_usage, usage_rank, move.name_ja)

    def _refresh_list(self) -> None:
        keyword = self._search_edit.text().strip()
        normalized_kw = _normalize_kana(keyword.lower()) if keyword else ""
        self._list.clear()

        moves: list[MoveInfo] = []
        added_names: set[str] = set()
        for move in self._all_moves:
            if normalized_kw and normalized_kw not in _normalize_kana(move.name_ja.lower()):
                continue
            if self._category_filter == "non_status" and move.category == "status":
                continue
            if self._category_filter not in ("all", "non_status") and move.category != self._category_filter:
                continue
            if self._type_filter and move.type_name != self._type_filter:
                continue
            added_names.add(move.name_ja)
            moves.append(move)

        if keyword:
            for move in self._search_only_moves:
                if move.name_ja in added_names:
                    continue
                if normalized_kw not in _normalize_kana(move.name_ja.lower()):
                    continue
                if self._category_filter == "non_status" and move.category == "status":
                    continue
                if self._category_filter not in ("all", "non_status") and move.category != self._category_filter:
                    continue
                if self._type_filter and move.type_name != self._type_filter:
                    continue
                moves.append(move)

        moves.sort(key=self._sort_key)
        selected_item: QListWidgetItem | None = None
        for move in moves:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, move.name_ja)
            item.setSizeHint(QSize(0, 50))
            self._list.addItem(item)
            band = MoveBandRow(move, self._usage_order.get(move.name_ja), self._list)
            self._list.setItemWidget(item, band)
            if move.name_ja == self._selected_move:
                selected_item = item

        if selected_item:
            self._list.setCurrentItem(selected_item)
            self._list.scrollToItem(selected_item)
        # デフォルトでは無選択状態にするため、elseブロック（setCurrentRow(0)）を削除

    def _add_to_slot(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        move_name = item.data(Qt.UserRole) or ""
        if not move_name:
            return
        for i in range(4):
            if not self._slot_moves[i]:
                self._slot_moves[i] = move_name
                self._update_slot_buttons()
                return
        QMessageBox.warning(
            self, "わざスロットが満杯",
            "わざが4つすべて入っています。\n"
            "各わざボタンをダブルクリックするか、右クリックメニュー「クリア」で空きを作ってください。",
        )

    def _clear_slot(self, slot: int) -> None:
        self._slot_moves[slot] = ""
        self._update_slot_buttons()

    def _update_slot_buttons(self) -> None:
        for i, btn in enumerate(self._slot_buttons):
            name = self._slot_moves[i]
            if name:
                btn.setText(name)
                move = db.get_move_by_name_ja(name)
                if move:
                    bg = TYPE_COLORS.get(move.type_name, "#45475a")
                    text_color = _best_text_color(bg)
                    btn.setStyleSheet(
                        "QPushButton {{ background-color: {bg}; color: {tc}; border-radius: 4px; "
                        "font-weight: bold; padding: 4px 8px; }}"
                        "QPushButton:hover {{ border: 2px solid #f9e2af; }}".format(bg=bg, tc=text_color)
                    )
                else:
                    btn.setStyleSheet(
                        "QPushButton { background-color: #585b70; color: #ffffff; border-radius: 4px; "
                        "font-weight: bold; padding: 4px 8px; }"
                    )
            else:
                btn.setText("（空き）")
                btn.setStyleSheet(
                    "QPushButton { background-color: #313244; color: #585b70; border-radius: 4px; "
                    "border: 1px solid #585b70; padding: 4px 8px; }"
                )

    def _confirm_selection(self) -> None:
        self.accept()

    def _clear_selection(self) -> None:
        self._slot_moves = ["", "", "", ""]
        self._update_slot_buttons()

    def selected_move(self) -> str:
        return self._slot_moves[0]

    def selected_moves(self) -> list[str]:
        return list(self._slot_moves)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._list.viewport() and event.type() == QEvent.ToolTip:
            if not self._tooltip_shown:
                self._tooltip_shown = True
                QToolTip.showText(event.globalPos(), "ダブルクリックで技スロットに追加", self._list)
            return True
        return super().eventFilter(obj, event)

    def _on_list_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        action = menu.addAction("選択")
        action.triggered.connect(self._add_to_slot)
        menu.exec_(self._list.viewport().mapToGlobal(pos))

