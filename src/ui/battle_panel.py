from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGroupBox, QPushButton, QProgressBar, QComboBox,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap

from src.models import PokemonInstance, BattleState
from src.constants import TYPE_COLORS
from src.ui.styles import TYPE_BADGE_STYLE, HP_BAR_STYLE


class TypeBadge(QLabel):
    _W, _H = 46, 20

    def __init__(self, type_name: str = "", parent=None):
        super().__init__(parent)
        self.setFixedSize(self._W, self._H)
        self.setAlignment(Qt.AlignCenter)
        self.set_type(type_name)

    def set_type(self, type_name: str) -> None:
        from src.ui.ui_utils import type_pixmap
        from src.constants import TYPE_EN_TO_JA
        pm = type_pixmap(type_name, self._W, self._H) if type_name else None
        if pm:
            self.setPixmap(pm)
            self.setText("")
            self.setStyleSheet("")
        else:
            self.setPixmap(QPixmap())
            ja = TYPE_EN_TO_JA.get(type_name, type_name) if type_name else "---"
            self.setText(ja)
            color = TYPE_COLORS.get(type_name, "#888888")
            self.setStyleSheet(TYPE_BADGE_STYLE.format(color=color))


class HpBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(10)
        layout.addWidget(self._bar)

        self._label = QLabel("--- / ---")
        self._label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._label)

    def set_actual(self, current: int, maximum: int) -> None:
        if maximum <= 0:
            return
        pct = max(0, min(100, int(current / maximum * 100)))
        self._bar.setValue(pct)
        self._label.setText("{} / {}".format(current, maximum))
        self._update_color(pct)

    def set_percent(self, pct: float) -> None:
        ipct = max(0, min(100, int(pct)))
        self._bar.setValue(ipct)
        self._label.setText("{:.1f}%".format(pct))
        self._update_color(ipct)

    def _update_color(self, pct: int) -> None:
        if pct > 50:
            style = HP_BAR_STYLE["high"]
        elif pct > 20:
            style = HP_BAR_STYLE["medium"]
        elif pct > 0:
            style = HP_BAR_STYLE["low"]
        else:
            style = HP_BAR_STYLE["empty"]
        self._bar.setStyleSheet(
            "QProgressBar::chunk {{ {} }}"
            "QProgressBar {{ background-color: #313244; border: 1px solid #45475a; border-radius: 3px; }}".format(style)
        )


class PokemonCard(QFrame):
    edit_requested = pyqtSignal(object)

    def __init__(self, label: str, is_opponent: bool = False, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("QFrame { background-color: #181825; border: 1px solid #45475a; border-radius: 6px; }")
        self.setFixedHeight(130)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        header = QHBoxLayout()
        side_lbl = QLabel(label)
        side_lbl.setStyleSheet("color: #89b4fa; font-weight: bold; font-size: 11px;")
        header.addWidget(side_lbl)
        header.addStretch()
        if not is_opponent:
            edit_btn = QPushButton("編集")
            edit_btn.setFixedSize(42, 20)
            edit_btn.clicked.connect(self._on_edit)
            header.addWidget(edit_btn)
        layout.addLayout(header)

        name_row = QHBoxLayout()
        self._name_lbl = QLabel("---")
        bold = QFont()
        bold.setBold(True)
        bold.setPointSize(14)
        self._name_lbl.setFont(bold)
        name_row.addWidget(self._name_lbl)
        name_row.addSpacing(6)
        self._type1_badge = TypeBadge("")
        self._type2_badge = TypeBadge("")
        self._type2_badge.setVisible(False)
        name_row.addWidget(self._type1_badge)
        name_row.addWidget(self._type2_badge)
        name_row.addStretch()
        layout.addLayout(name_row)

        self._hp_bar = HpBar()
        layout.addWidget(self._hp_bar)

        self._pokemon = None  # type: PokemonInstance | None

    def update_pokemon(self, p: PokemonInstance) -> None:
        self._pokemon = p
        self._name_lbl.setText(p.name_ja or "---")

        types = p.types or []
        self._type1_badge.set_type(types[0] if types else "")
        if len(types) > 1:
            self._type2_badge.set_type(types[1])
            self._type2_badge.setVisible(True)
        else:
            self._type2_badge.setVisible(False)

        if p.max_hp > 0:
            self._hp_bar.set_actual(p.current_hp, p.max_hp)
        elif p.current_hp_percent >= 0:
            self._hp_bar.set_percent(p.current_hp_percent)

    def clear(self) -> None:
        self._pokemon = None
        self._name_lbl.setText("---")
        self._hp_bar.set_percent(100)
        self._type1_badge.set_type("")
        self._type2_badge.setVisible(False)

    def _on_edit(self) -> None:
        self.edit_requested.emit(self._pokemon)

    @staticmethod
    def _ja(type_en: str) -> str:
        from src.constants import TYPE_EN_TO_JA
        return TYPE_EN_TO_JA.get(type_en, type_en)


class PartySlot(QFrame):
    clicked_signal = pyqtSignal(int)

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self._index = index
        self.setFrameShape(QFrame.StyledPanel)
        self.setFixedSize(100, 56)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QFrame { background-color: #313244; border: 1px solid #45475a; border-radius: 4px; }
            QFrame:hover { border-color: #89b4fa; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(2)
        self._name_lbl = QLabel("---")
        self._name_lbl.setAlignment(Qt.AlignCenter)
        self._name_lbl.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._name_lbl)
        self._hp_bar = QProgressBar()
        self._hp_bar.setRange(0, 100)
        self._hp_bar.setValue(100)
        self._hp_bar.setFixedHeight(6)
        self._hp_bar.setTextVisible(False)
        layout.addWidget(self._hp_bar)

    def set_pokemon(self, name: str, hp_pct: float) -> None:
        self._name_lbl.setText(name or "---")
        ipct = max(0, min(100, int(hp_pct)))
        self._hp_bar.setValue(ipct)
        color = "#a6e3a1" if ipct > 50 else "#f9e2af" if ipct > 20 else "#f38ba8"
        self._hp_bar.setStyleSheet(
            "QProgressBar::chunk {{ background-color: {}; border-radius: 2px; }}"
            "QProgressBar {{ background-color: #45475a; border: none; border-radius: 2px; }}".format(color)
        )

    def set_active(self, active: bool) -> None:
        border = "#a6e3a1" if active else "#45475a"
        self.setStyleSheet(
            "QFrame {{ background-color: #313244; border: 2px solid {}; border-radius: 4px; }}"
            "QFrame:hover {{ border-color: #89b4fa; }}".format(border)
        )

    def mousePressEvent(self, event) -> None:
        self.clicked_signal.emit(self._index)
        super().mousePressEvent(event)
