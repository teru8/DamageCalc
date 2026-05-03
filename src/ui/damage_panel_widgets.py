from __future__ import annotations


from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPainter
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.ui.damage_panel_math import bar_color
from src.ui.damage_panel_math import bar_variation_color
from src.ui.damage_panel_math import hp_color
from src.ui.damage_panel_math import n_hit_ko
from src.ui.damage_panel_math import round1


class ToggleBtn(QPushButton):
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
        font_size: int | None = None,
        pad_h: int | None = None,
        pad_v: int | None = None,
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


class RadioGroup(QWidget):
    """Row of mutually exclusive toggle buttons."""

    changed = pyqtSignal()

    def __init__(self, options: list[str], parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(3)
        self._btns: dict[str, ToggleBtn] = {}
        self._value = "none"
        for lbl in options:
            btn = ToggleBtn(lbl)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _, l=lbl: self._click(l))
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            layout.addWidget(btn, 1)
            self._btns[lbl] = btn

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


class DmgBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(16)
        self._mn = 0.0
        self._mx = 0.0
        self._error_mode = False
        self._empty = True

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

        remaining_worst = max(0.0, 100.0 - mx_draw)
        hp_bar_color = QColor(hp_color(remaining_worst))
        p.fillRect(0, 0, w, h, hp_bar_color)

        if mx_draw <= 0:
            p.setPen(QColor("#000000"))
            p.drawRect(0, 0, w - 1, h - 1)
            return
        s = w / 100.0
        guaranteed_w = int(mn_draw * s)
        uncertain_w = int(max(0.0, mx_draw - mn_draw) * s)
        dmg_color = QColor("#101015")
        var_color = QColor(bar_variation_color(mn, mx))
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


class DmgRow(QWidget):
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

        self._bar = DmgBar()
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
        mn_pct = round1(min_dmg / hp * 100)
        mx_pct = round1(max_dmg / hp * 100)
        self._bar.set_range(mn_pct, mx_pct)
        if max_dmg == 0:
            self._detail_txt.setText("0-0 (0.0~0.0%)")
            self._detail_txt.setStyleSheet("font-size:14px;color:#585b70;")
            self._ko_txt.setText("")
            return
        hits_str = n_hit_ko(min_dmg, max_dmg, hp)
        self._detail_txt.setText("{}-{} ({:.1f}~{:.1f}%)".format(min_dmg, max_dmg, mn_pct, mx_pct))
        self._ko_txt.setText(hits_str)
        color = bar_color(mn_pct, mx_pct)
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
