from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QFontMetrics
from PyQt5.QtWidgets import QFrame, QLabel


def label_fit_text(lbl: QLabel, text: str, base_px: int = 13, min_px: int = 10) -> None:
    """Set text on label, shrinking pixel font size to fit, then elide."""
    if not text:
        lbl.setText("")
        return
    w = lbl.width()
    if w <= 0:
        lbl.setText(text)
        return
    f = QFont(lbl.font())
    for px in range(base_px, min_px - 1, -1):
        f.setPixelSize(px)
        fm = QFontMetrics(f)
        if fm.horizontalAdvance(text) <= w:
            lbl.setFont(f)
            lbl.setText(text)
            return
    f.setPixelSize(min_px)
    fm = QFontMetrics(f)
    lbl.setFont(f)
    lbl.setText(fm.elidedText(text, Qt.ElideRight, w))


def sep() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet("QFrame{border:none;border-top:1px solid #45475a;}")
    return line


def row_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color:#89b4fa;font-size:14px;font-weight:bold;")
    return lbl
