"""
OCR engine using Windows built-in OCR (Windows.Media.Ocr / WinRT).
No GPU, no torch — uses what Windows 10/11 already provides.

Result dict structure from winocr.recognize_pil_sync:
  {'text': str, 'lines': [{'text': str, 'words': [{'text': str, 'bounding_rect': {...}}]}]}
"""
import hashlib
import logging
import unicodedata
from collections import OrderedDict
from typing import Any

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal


class _LRUDict(OrderedDict):
    """OrderedDict with a maximum size; evicts the least-recently-used entry."""

    def __init__(self, maxsize: int) -> None:
        super().__init__()
        self._maxsize = maxsize

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)
        self.move_to_end(key)
        if len(self) > self._maxsize:
            self.popitem(last=False)

    def __getitem__(self, key: Any) -> Any:
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value


_OCR_RESULT_CACHE: _LRUDict = _LRUDict(64)


def is_ready() -> bool:
    return True  # Windows OCR needs no heavyweight initialization


def _normalize_lines(lines: list[str], allowlist: str | None = None) -> list[str]:
    allowed = set(allowlist) if allowlist else None
    result: list[str] = []
    seen: set[str] = set()
    for line in lines:
        text = unicodedata.normalize("NFKC", line or "").strip()
        if allowed is not None:
            text = "".join(ch for ch in text if ch in allowed)
        text = text.strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _prepare_variants(image: np.ndarray) -> list[np.ndarray]:
    import cv2

    if image is None or image.size == 0:
        return []

    base = image
    if image.ndim == 2:
        base = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.ndim == 3 and image.shape[2] == 4:
        base = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)

    h, w = base.shape[:2]
    scale = 1
    if h < 44 or w < 180:
        scale = 3
    elif h < 72 or w < 320:
        scale = 2
    if scale > 1:
        base = cv2.resize(base, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    bordered = cv2.copyMakeBorder(
        base, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=(255, 255, 255)
    )

    gray = cv2.cvtColor(bordered, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    gray = cv2.equalizeHist(gray)

    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if float(binary.mean()) < 127:
        binary = cv2.bitwise_not(binary)

    return [bordered, cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)]


def _run_winocr(image: np.ndarray) -> list[str]:
    import cv2
    from PIL import Image
    import winocr

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    result = winocr.recognize_pil_sync(pil_img, "ja")
    return [line.get("text", "").strip() for line in result.get("lines", []) if line.get("text", "").strip()]


def read_text(image: np.ndarray, allowlist: str | None = None) -> list[str]:
    """
    OCR on a BGR numpy image. Returns list of detected text strings (one per line).
    Returns [] on failure.
    """
    cache_key = (hashlib.md5(image.tobytes()).hexdigest(), allowlist)
    if cache_key in _OCR_RESULT_CACHE:
        return _OCR_RESULT_CACHE[cache_key]
    try:
        result: list[str] = []
        for variant in _prepare_variants(image):
            texts = _normalize_lines(_run_winocr(variant), allowlist)
            if texts:
                result = texts
                break
        _OCR_RESULT_CACHE[cache_key] = result
        return result
    except Exception as e:
        logging.warning("read_text failed: %s", e)
        return []


def read_text_with_conf(image: np.ndarray) -> list[tuple[str, float]]:
    """Returns list of (text, 1.0) pairs. Windows OCR does not expose per-word confidence."""
    return [(t, 1.0) for t in read_text(image)]


class OcrInitThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, use_gpu: bool = False):
        super().__init__()
        self.use_gpu = use_gpu

    def run(self) -> None:
        try:
            import winocr
            from PIL import Image
            winocr.recognize_pil_sync(Image.new("RGB", (4, 4)), "ja")
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))
