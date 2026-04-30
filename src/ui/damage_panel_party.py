from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout


class PartySlot(QFrame):
    clicked_signal = pyqtSignal(int)
    context_menu_requested = pyqtSignal(int, object)
    _SPRITE_SIZE = 72

    def __init__(self, idx: int, parent=None):
        super().__init__(parent)
        self._idx = idx
        self.setFrameShape(QFrame.StyledPanel)
        self.setFixedSize(78, 78)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QFrame{background:#313244;border:1px solid #45475a;border-radius:4px;}"
            "QFrame:hover{border-color:#89b4fa;}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        self._sprite_lbl = QLabel()
        self._sprite_lbl.setFixedSize(self._SPRITE_SIZE, self._SPRITE_SIZE)
        self._sprite_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._sprite_lbl, 0, Qt.AlignCenter)

    def set_name(self, name: str, attack_active: bool = False, defense_active: bool = False, sprite_name: str = "") -> None:
        sprite = sprite_name or name
        if sprite:
            from src.ui.ui_utils import sprite_pixmap_or_zukan
            pm = sprite_pixmap_or_zukan(sprite, self._SPRITE_SIZE, self._SPRITE_SIZE)
            self._sprite_lbl.setPixmap(pm if pm else QPixmap())
        else:
            self._sprite_lbl.setPixmap(QPixmap())
        if attack_active:
            border = "#a6e3a1"
        elif defense_active:
            border = "#f9e2af"
        else:
            border = "#45475a"
        self.setStyleSheet(
            "QFrame{{background:#313244;border:2px solid {};border-radius:4px;}}"
            "QFrame:hover{{border-color:#89b4fa;}}".format(border))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            self.context_menu_requested.emit(self._idx, event.globalPos())
            event.accept()
            return
        self.clicked_signal.emit(self._idx)
        super().mousePressEvent(event)
