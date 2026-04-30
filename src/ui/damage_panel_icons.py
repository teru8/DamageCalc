from __future__ import annotations

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QBrush, QFont, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF

from src.data import zukan_client

_ICON_CACHE: dict[str, QPixmap] = {}
_REMOTE_ICON_CACHE: dict[str, QPixmap] = {}
_CATEGORY_ICON_URLS = {
    "physical": "https://play.pokemonshowdown.com/sprites/categories/Physical.png",
    "special": "https://play.pokemonshowdown.com/sprites/categories/Special.png",
    "status": "https://play.pokemonshowdown.com/sprites/categories/Status.png",
}


def game_badge(text: str, c_top: str, c_bottom: str, width: int, height: int, font_size: int = 10) -> QPixmap:
    key = "{}|{}|{}|{}|{}|{}".format(text, c_top, c_bottom, width, height, font_size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    pm = QPixmap(width, height)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    grad = QLinearGradient(0, 0, 0, height)
    grad.setColorAt(0.0, QColor(c_top))
    grad.setColorAt(1.0, QColor(c_bottom))
    p.setBrush(QBrush(grad))
    p.setPen(QPen(QColor("#dce2ff"), 1))
    p.drawRoundedRect(0, 0, width - 1, height - 1, 6, 6)

    p.setPen(QColor("#ffffff"))
    f = QFont("Yu Gothic UI", font_size)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, text)
    p.end()

    _ICON_CACHE[key] = pm
    return pm


def remote_icon(url: str, width: int, height: int) -> QPixmap | None:
    cache_key = "{}|{}|{}".format(url, width, height)
    cached = _REMOTE_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    payload = zukan_client.get_cached_asset_bytes(url)
    if not payload:
        return None
    source = QPixmap()
    if not source.loadFromData(payload):
        return None
    scaled = source.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    _REMOTE_ICON_CACHE[cache_key] = scaled
    return scaled


def category_icon(category: str, width: int = 66, height: int = 22) -> QPixmap:
    url = _CATEGORY_ICON_URLS.get(category, "")
    if url:
        icon = remote_icon(url, width, height)
        if icon is not None:
            return icon
    fallback = {
        "physical": ("ぶつり", "#f87f5a", "#d44936"),
        "special": ("とくしゅ", "#67a8ff", "#3b69d8"),
        "status": ("へんか", "#9da5bc", "#707993"),
    }.get(category, ("-", "#9da5bc", "#707993"))
    return game_badge(fallback[0], fallback[1], fallback[2], width, height, 9)


def battle_stat_icon(kind: str, width: int = 60, height: int = 22) -> QPixmap:
    key = "stat:{}:{}:{}".format(kind, width, height)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    text = "威力" if kind == "power" else "命中"
    top_color = "#f7c46a" if kind == "power" else "#8bd6a2"
    bottom_color = "#d18931" if kind == "power" else "#4f9c6f"
    icon_color = "#fff6de" if kind == "power" else "#eafff1"

    pm = QPixmap(width, height)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    grad = QLinearGradient(0, 0, 0, height)
    grad.setColorAt(0.0, QColor(top_color))
    grad.setColorAt(1.0, QColor(bottom_color))
    p.setBrush(QBrush(grad))
    p.setPen(QPen(QColor("#dce2ff"), 1))
    p.drawRoundedRect(0, 0, width - 1, height - 1, 7, 7)

    gx = 8
    gy = height // 2
    p.setPen(QPen(QColor(icon_color), 2))
    if kind == "power":
        points = [
            (gx, gy - 6), (gx + 3, gy - 1), (gx + 9, gy - 1),
            (gx + 4, gy + 2), (gx + 6, gy + 7), (gx, gy + 3),
            (gx - 6, gy + 7), (gx - 4, gy + 2), (gx - 9, gy - 1),
            (gx - 3, gy - 1),
        ]
        poly = QPolygonF([QPointF(float(px), float(py)) for px, py in points])
        p.setBrush(QColor(icon_color))
        p.drawPolygon(poly)
    else:
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(gx - 7, gy - 7, 14, 14)
        p.drawLine(gx - 10, gy, gx + 10, gy)
        p.drawLine(gx, gy - 10, gx, gy + 10)
        p.setBrush(QColor(icon_color))
        p.drawEllipse(gx - 2, gy - 2, 4, 4)

    p.setPen(QColor("#ffffff"))
    f = QFont("Yu Gothic UI", 9)
    f.setBold(True)
    p.setFont(f)
    p.drawText(20, 0, width - 20, height, Qt.AlignCenter, text)
    p.end()

    _ICON_CACHE[key] = pm
    return pm
