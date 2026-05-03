from __future__ import annotations


from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from src.constants import MULTI_HIT_MOVES_JA, TYPE_COLORS, TYPE_EN_TO_JA
from src.models import MoveInfo
from src.ui.damage_panel_icons import category_icon
from src.ui.damage_panel_power import power_option_value, variable_power_options
from src.ui.damage_panel_widgets import DmgRow


class MoveSection(QWidget):
    """Header + damage bars for a single move slot (self or opponent)."""
    move_change_requested = pyqtSignal(int)   # slot index

    # row_labels: (custom_label, bulk0_label, bulk32_label)
    _LEFT_LABELS  = ("Adj.", "HBD:0", "HBD:32")
    _RIGHT_LABELS = ("Adj.",   "AC:0",  "AC:32")
    _ROW_COLOR_ADJ = "#cba6f7"
    _ROW_COLOR_BULK0 = "#89b4fa"
    _ROW_COLOR_BULK32 = "#f38ba8"

    def __init__(self, slot: int, right_side: bool = False, parent=None):
        super().__init__(parent)
        self._slot = slot
        self._right_side = right_side
        self._move: MoveInfo | None = None
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

        type_cat_wrap = QWidget()
        type_cat_row = QHBoxLayout(type_cat_wrap)
        type_cat_row.setContentsMargins(0, 0, 0, 0)
        type_cat_row.setSpacing(4)
        self._type_lbl = QLabel("")
        self._type_lbl.setFixedWidth(50)
        self._type_lbl.setFixedHeight(22)
        self._type_lbl.setAlignment(Qt.AlignCenter)
        self._type_lbl.setStyleSheet(
            "border-radius:3px;color:white;font-size:11px;font-weight:bold;"
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
            self._pow_combo.setFixedHeight(25)
            self._pow_combo.setMinimumHeight(25)
            self._pow_combo.setMaximumHeight(25)
            self._pow_combo.setStyleSheet(
                "QComboBox{font-size:13px; min-height:25px; max-height:25px; padding:0px 18px 0px 4px;}"
                "QComboBox::drop-down{width:14px;}"
            )
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
            self._hit_spin.setFixedHeight(25)
            self._hit_spin.setMinimumHeight(25)
            self._hit_spin.setMaximumHeight(25)
            self._hit_spin.setStyleSheet(
                "QSpinBox{font-size:13px; min-height:25px; max-height:25px; padding:0px 4px;}"
            )
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

        self._row_custom = DmgRow(labels[0], color=self._ROW_COLOR_ADJ)
        self._row_hbd0 = DmgRow(labels[1], color=self._ROW_COLOR_BULK0)
        self._row_hbd252 = DmgRow(labels[2], color=self._ROW_COLOR_BULK32)
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
        preferred_power = power_option_value(preferred_data)
        exact_index = -1
        power_index = -1
        for index, (label, option_data) in enumerate(options):
            self._pow_combo.addItem(label, option_data)
            if preferred_data is not None and option_data == preferred_data and exact_index < 0:
                exact_index = index
            if preferred_power > 0 and power_option_value(option_data) == preferred_power and power_index < 0:
                power_index = index
        if exact_index >= 0:
            selected_index = exact_index
        elif power_index >= 0:
            selected_index = power_index
        if self._pow_combo.count() > 0:
            self._pow_combo.setCurrentIndex(selected_index)
        self._pow_combo.blockSignals(False)

    def setup_move(self, move: MoveInfo | None) -> None:
        prev_pow_data = self._pow_combo.currentData()
        prev_hit = self._hit_spin.value()
        prev_is_var = not self._pow_combo.isHidden()
        prev_is_multi = not self._hit_spin.isHidden()
        self._move = move
        if move is None:
            self._last_move_name = ""
            self._details_visible = False
            self._type_lbl.setText("")
            self._type_lbl.setStyleSheet("border-radius:3px;color:white;font-size:13px;font-weight:bold;")
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
        _pm = _type_pm(move.type_name, self._type_lbl.width(), self._type_lbl.height())
        if _pm:
            self._type_lbl.setPixmap(_pm)
            self._type_lbl.setText("")
            self._type_lbl.setStyleSheet("border-radius:3px;")
        else:
            type_ja = TYPE_EN_TO_JA.get(move.type_name, move.type_name)
            color = TYPE_COLORS.get(move.type_name, "#888888")
            self._type_lbl.setPixmap(QPixmap())
            self._type_lbl.setText(type_ja)
            self._type_lbl.setStyleSheet(
                "background-color:{};border-radius:3px;color:white;"
                "font-size:11px;font-weight:bold;".format(color))
        self._cat_icon_lbl.setPixmap(category_icon(move.category, 66, 22))
        self._name_lbl.setText(move.name_ja)
        same_move = self._last_move_name == move.name_ja
        if not same_move:
            self._details_visible = False

        self._pow_lbl.setText(str(move.power) if move.power else "---")
        self._acc_lbl.setText(str(move.accuracy) if move.accuracy else "---")
        self._eff_lbl.setText("")
        self._has_modifier_notes = False
        self._status_note.setVisible(False)

        options = variable_power_options(move)
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

    @staticmethod
    def _is_zero_damage_result(data: tuple[int, int, int, bool] | None) -> bool:
        if data is None:
            return False
        mn, mx, hp, is_error = data
        # hp=1 「/」。
        return (not is_error) and hp > 1 and mn == 0 and mx == 0

    def update_results(
        self,
        custom: tuple[int, int, int, bool] | None,
        bulk0: tuple[int, int, int, bool],
        bulk32: tuple[int, int, int, bool],
        show_bulk_rows: bool = True,
    ) -> None:
        """Each tuple is (min_dmg, max_dmg, defender_hp, is_error)."""
        self._show_bulk_rows = bool(show_bulk_rows)
        # , 0
        self._details_visible = False
        self._apply_detail_visibility()
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

        def _apply(row: DmgRow, data: tuple[int, int, int, bool] | None, show: bool) -> None:
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

        # 0,
        # 3(/)。
        visible_results: list[tuple[int, int, int, bool]] = []
        if custom is not None:
            visible_results.append(custom)
        if self._show_bulk_rows:
            visible_results.append(bulk0)
            visible_results.append(bulk32)
        if visible_results and all(self._is_zero_damage_result(result) for result in visible_results):
            self._row_custom.setVisible(False)
            self._row_hbd0.setVisible(False)
            self._row_hbd252.setVisible(False)
            self._details_visible = True
            self._apply_detail_visibility()

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
        return power_option_value(self._pow_combo.currentData())

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

