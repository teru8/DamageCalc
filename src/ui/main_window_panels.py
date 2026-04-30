from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal, QMimeData
from PyQt5.QtGui import QDrag, QPixmap
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel

from src.models import PokemonInstance


class _DraggableCell(QFrame):
    """ボックスのポケモンセル。ドラッグ開始をサポート。"""
    clicked_signal = pyqtSignal(str)

    def __init__(self, pokemon_name_ja: str, parent=None):
        super().__init__(parent)
        self._pokemon_name_ja = pokemon_name_ja
        self._drag_start_pos = None
        self._drag_started = False

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_started = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not (event.buttons() & Qt.LeftButton) or self._drag_start_pos is None:
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < 8:
            return
        self._drag_started = True
        mime = QMimeData()
        mime.setData("application/x-pokemon-name", self._pokemon_name_ja.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec_(Qt.CopyAction)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and not self._drag_started:
            self.clicked_signal.emit(self._pokemon_name_ja)
        self._drag_start_pos = None
        self._drag_started = False
        super().mouseReleaseEvent(event)


class _SavedPartyPanel(QFrame):
    context_menu_signal = pyqtSignal(int, object)
    reorder_signal = pyqtSignal(int, int)
    move_to_top_signal = pyqtSignal(int)

    def __init__(self, index: int, party_payload: list[dict | None], parent=None):
        super().__init__(parent)
        self._index = index
        self._drag_start_pos = None
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(102)
        self.setAcceptDrops(True)
        self._update_style(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)
        for item in (party_payload + [None] * 6)[:6]:
            layout.addStretch()
            lbl = QLabel()
            lbl.setFixedSize(72, 72)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("border:none;")
            name_ja = str(item.get("name_ja") or "") if isinstance(item, dict) else ""
            name_en = str(item.get("name_en") or "") if isinstance(item, dict) else ""
            if name_ja:
                from src.ui.ui_utils import sprite_pixmap_or_zukan

                pm = sprite_pixmap_or_zukan(name_ja, 68, 68, name_en=name_en)
                if pm:
                    lbl.setPixmap(pm)
                else:
                    lbl.setText(name_ja[:2])
                    lbl.setStyleSheet("color:#cdd6f4; font-size:10px; border:none;")
            layout.addWidget(lbl)
        layout.addStretch()

    def _update_style(self, highlight: bool) -> None:
        border = "#89b4fa" if highlight else "#45475a"
        self.setStyleSheet(
            "QFrame {{ background-color: #313244; border: 2px solid {}; border-radius: 6px; }}"
            "QFrame:hover {{ border-color: #89b4fa; }}".format(border)
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not (event.buttons() & Qt.LeftButton) or self._drag_start_pos is None:
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < 8:
            return
        mime = QMimeData()
        mime.setData("application/x-saved-party-index", str(self._index).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec_(Qt.MoveAction)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat("application/x-saved-party-index"):
            self._update_style(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._update_style(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._update_style(False)
        if not event.mimeData().hasFormat("application/x-saved-party-index"):
            event.ignore()
            return
        raw = bytes(event.mimeData().data("application/x-saved-party-index")).decode("utf-8")
        try:
            from_index = int(raw)
        except ValueError:
            event.ignore()
            return
        self.reorder_signal.emit(from_index, self._index)
        event.acceptProposedAction()

    def contextMenuEvent(self, event) -> None:
        self.context_menu_signal.emit(self._index, event.globalPos())
        super().contextMenuEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.move_to_top_signal.emit(self._index)
        super().mouseDoubleClickEvent(event)


class _MyPartyPanel(QFrame):
    dropped_signal = pyqtSignal(str)
    clear_signal = pyqtSignal()
    context_menu_signal = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(114)
        self.setAcceptDrops(True)
        self.setStyleSheet(
            "QFrame { background-color:#313244; border:2px solid #45475a; border-radius:6px; }"
            "QFrame:hover { border-color:#89b4fa; }"
        )
        self._labels: list[QLabel] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)
        for _ in range(6):
            layout.addStretch()
            lbl = QLabel()
            lbl.setFixedSize(72, 72)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("border:none;")
            self._labels.append(lbl)
            layout.addWidget(lbl)
        layout.addStretch()

    def set_party(self, party: list[PokemonInstance | None], active_idx: int = -1) -> None:
        from src.ui.ui_utils import sprite_pixmap_or_zukan

        for i, lbl in enumerate(self._labels):
            lbl.setStyleSheet("border:none;")
            p = party[i] if i < len(party) else None
            if p and p.name_ja:
                pm = sprite_pixmap_or_zukan(p.name_ja, 68, 68, name_en=p.name_en or "")
                if pm:
                    lbl.setPixmap(pm)
                    lbl.setText("")
                else:
                    lbl.setPixmap(QPixmap())
                    lbl.setText(p.name_ja[:2])
                    lbl.setStyleSheet("color:#cdd6f4; font-size:10px; border:none;")
            else:
                lbl.setPixmap(QPixmap())
                lbl.setText("")
            if i == active_idx:
                lbl.setStyleSheet(lbl.styleSheet() + "border:1px solid #89b4fa; border-radius:4px;")

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat("application/x-pokemon-name"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        if event.mimeData().hasFormat("application/x-pokemon-name"):
            name = bytes(event.mimeData().data("application/x-pokemon-name")).decode("utf-8")
            self.dropped_signal.emit(name)
            event.acceptProposedAction()
            return
        event.ignore()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clear_signal.emit()
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        self.context_menu_signal.emit(event.globalPos())
        super().contextMenuEvent(event)

