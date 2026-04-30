from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.models import PokemonInstance
from src.ui.damage_panel_forms import FORM_NAME_TO_GROUP
from src.ui.damage_panel_forms import canonical_display_name
from src.ui.damage_panel_forms import next_form_name
from src.ui.damage_panel_ui_helpers import label_fit_text


class PokemonCard(QWidget):
    edit_requested = pyqtSignal()
    form_change_requested = pyqtSignal()
    ability_change_requested = pyqtSignal()
    item_change_requested = pyqtSignal()
    _SPRITE_SIZE = 72
    _CARD_HEIGHT = 84

    def __init__(self, role_text: str, role_color: str, parent=None):
        super().__init__(parent)
        self._pokemon: Optional[PokemonInstance] = None
        self.setFixedHeight(self._CARD_HEIGHT)
        frame = QFrame(self)
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet(
            "QFrame{background:#181825;border:1px solid #45475a;border-radius:6px;}")
        frame.setFixedHeight(self._CARD_HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(frame)

        frame_vbox = QVBoxLayout(frame)
        frame_vbox.setContentsMargins(8, 6, 4, 6)
        frame_vbox.setSpacing(2)

        frame_row = QHBoxLayout()
        frame_row.setSpacing(4)

        inner = QVBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(2)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self._role_lbl = QLabel(role_text)
        self._role_lbl.setStyleSheet(f"color:{role_color};font-size:12px;font-weight:bold;")
        row1.addWidget(self._role_lbl)
        self._name_lbl = QLabel("（未設定）")
        self._name_lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;background:#181825;border:1px solid #45475a;border-radius:4px;padding:4px;")
        self._name_lbl.setWordWrap(False)
        row1.addWidget(self._name_lbl, 1)
        inner.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(4)
        self._ability_lbl = QLabel("")
        self._ability_lbl.setStyleSheet(
            "color:#a6adc8;font-size:13px;text-decoration:underline;"
            "background:transparent;border-radius:3px;padding:1px 3px;")
        self._ability_lbl.setWordWrap(False)
        self._ability_lbl.setCursor(Qt.PointingHandCursor)
        self._ability_lbl.mousePressEvent = lambda _: self.ability_change_requested.emit()
        row2.addWidget(self._ability_lbl, 1)
        self._item_lbl = QLabel("")
        self._item_lbl.setStyleSheet(
            "color:#f9e2af;font-size:13px;text-decoration:underline;"
            "background:transparent;border-radius:3px;padding:1px 3px;")
        self._item_lbl.setWordWrap(False)
        self._item_lbl.setCursor(Qt.PointingHandCursor)
        self._item_lbl.mousePressEvent = lambda _: self.item_change_requested.emit()
        row2.addWidget(self._item_lbl, 1)
        inner.addLayout(row2)

        self._form_btn = QPushButton("フォルムチェンジ")
        self._form_btn.setFixedHeight(12)
        self._form_btn.setStyleSheet(
            "QPushButton{font-size:12px;background:#313244;color:#A6E3A1;"
            "border:1px solid #45475a;border-radius:3px;padding:-6 4px;}"
            "QPushButton:hover{background:#45475a;}"
        )
        self._form_btn.clicked.connect(self.form_change_requested.emit)
        sp = self._form_btn.sizePolicy()
        sp.setRetainSizeWhenHidden(False)
        self._form_btn.setSizePolicy(sp)
        self._form_btn.hide()
        inner.addWidget(self._form_btn)
        inner.addStretch()

        frame_row.addLayout(inner, 1)

        self._sprite_lbl = QLabel()
        self._sprite_lbl.setFixedSize(self._SPRITE_SIZE, self._SPRITE_SIZE)
        self._sprite_lbl.setAlignment(Qt.AlignCenter)
        frame_row.addWidget(self._sprite_lbl)

        frame_vbox.addLayout(frame_row)

    def set_pokemon(self, custom: Optional[PokemonInstance]) -> None:
        self._pokemon = custom
        if custom:
            from src.ui.ui_utils import sprite_pixmap_or_zukan
            pm = sprite_pixmap_or_zukan(
                custom.name_ja or "",
                self._SPRITE_SIZE,
                self._SPRITE_SIZE,
                name_en=custom.name_en or "",
            )
            self._sprite_lbl.setPixmap(pm if pm else QPixmap())
        else:
            self._sprite_lbl.setPixmap(QPixmap())
        self._refresh_text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_text()

    def _refresh_text(self) -> None:
        p = self._pokemon
        if p:
            display_name = canonical_display_name(p.name_ja or "")
            self._name_lbl.setText(display_name)
            label_fit_text(self._ability_lbl, p.ability or "", 13)
            label_fit_text(self._item_lbl, p.item or "", 13)
            next_form = next_form_name(p.name_ja or "", FORM_NAME_TO_GROUP)
            if next_form:
                next_display = canonical_display_name(next_form)
                self._form_btn.setText("→ {}".format(next_display))
                self._form_btn.show()
            else:
                self._form_btn.hide()
        else:
            self._name_lbl.setText("（未設定）")
            self._ability_lbl.setText("")
            self._item_lbl.setText("")
            self._form_btn.hide()


class AttackerCard(PokemonCard):
    def __init__(self, parent=None):
        super().__init__("自分", "#F38BA8", parent)


class DefenderCard(PokemonCard):
    def __init__(self, parent=None):
        super().__init__("相手", "#89B4FA", parent)
