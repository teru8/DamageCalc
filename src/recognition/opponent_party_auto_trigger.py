from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

_MATCH_THRESHOLD = 0.85
_BASE_FRAME_W = 1280
_BASE_FRAME_H = 720
_TEMPLATE_SPECS: list[tuple[tuple[int, int, int, int], str]] = [
    ((88, 609, 182, 649), "assets/templates/temp1.png"),
    ((229, 606, 331, 652), "assets/templates/temp2.png"),
]
_TEMPLATE_CACHE: dict[str, np.ndarray | None] = {}
_TEMPLATE_PATH_CACHE: dict[str, Path | None] = {}


def _read_image_color(path: Path) -> np.ndarray | None:
    """Unicode-safe image loader for Windows paths."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except (OSError, ValueError):
        return None
    if data.size == 0:
        return None
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        return None
    return img


def _load_template(template_path: str) -> np.ndarray | None:
    cached = _TEMPLATE_CACHE.get(template_path)
    if cached is not None or template_path in _TEMPLATE_CACHE:
        return cached
    candidate_paths: list[Path] = [Path.cwd() / template_path]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidate_paths.append(exe_dir / template_path)
        candidate_paths.append(exe_dir / "_internal" / template_path)
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        if str(meipass):
            candidate_paths.append(meipass / template_path)
    tmpl = None
    basename = Path(template_path).name
    cached_path = _TEMPLATE_PATH_CACHE.get(template_path)
    if cached_path is not None and cached_path.exists():
        tmpl = _read_image_color(cached_path)
        if tmpl is not None and tmpl.size > 0:
            _TEMPLATE_CACHE[template_path] = tmpl
            return tmpl
    for abs_path in candidate_paths:
        if not abs_path.exists():
            continue
        tmpl = _read_image_color(abs_path)
        if tmpl is not None and tmpl.size > 0:
            _TEMPLATE_PATH_CACHE[template_path] = abs_path
            break
    if tmpl is None or tmpl.size == 0:
        # Fallback: executable , 。
        search_roots: list[Path] = []
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).parent
            search_roots.extend([exe_dir, exe_dir / "_internal"])
            meipass = Path(getattr(sys, "_MEIPASS", ""))
            if str(meipass):
                search_roots.append(meipass)
        else:
            search_roots.append(Path.cwd())
        for root in search_roots:
            if not root.exists():
                continue
            try:
                for found in root.rglob(basename):
                    tmpl = _read_image_color(found)
                    if tmpl is not None and tmpl.size > 0:
                        _TEMPLATE_PATH_CACHE[template_path] = found
                        break
                if tmpl is not None and tmpl.size > 0:
                    break
            except OSError:
                continue
    if tmpl is None or tmpl.size == 0:
        _TEMPLATE_CACHE[template_path] = None
        _TEMPLATE_PATH_CACHE[template_path] = None
        return None
    _TEMPLATE_CACHE[template_path] = tmpl
    return tmpl


def has_all_slot_types(frame_bgr: np.ndarray) -> bool:
    """Return True if all 6 opponent slots have at least one type icon detected."""
    from src.recognition.opponent_party_reader import _OPP_SLOT_ROIS, _crop, _detect_type_groups  # noqa: PLC0415
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return False
    import cv2  # noqa: PLC0415
    h, w = frame_bgr.shape[:2]
    if (h, w) != (720, 1280):
        frame_bgr = cv2.resize(frame_bgr, (1280, 720))
    for index, roi in enumerate(_OPP_SLOT_ROIS):
        slot = _crop(frame_bgr, roi)
        type_groups = _detect_type_groups(slot, slot_index=index)
        if not type_groups:
            return False
    return True


def should_trigger_auto_detect(frame_bgr: np.ndarray) -> bool:
    matched, _ = evaluate_auto_detect(frame_bgr)
    return matched


def evaluate_auto_detect(frame_bgr: np.ndarray) -> tuple[bool, list[tuple[str, float, str]]]:
    """Return (matched, [(template_name, score, reason), ...]). score is TM_CCOEFF_NORMED."""
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return False, []
    h, w = frame_bgr.shape[:2]
    sx = float(w) / float(_BASE_FRAME_W)
    sy = float(h) / float(_BASE_FRAME_H)
    scores: list[tuple[str, float, str]] = []
    all_matched = True
    for (x1, y1, x2, y2), template_path in _TEMPLATE_SPECS:
        # 1280x720 。。
        rx1 = int(round(x1 * sx))
        ry1 = int(round(y1 * sy))
        rx2 = int(round(x2 * sx))
        ry2 = int(round(y2 * sy))
        if rx1 < 0 or ry1 < 0 or rx2 > w or ry2 > h or rx2 <= rx1 or ry2 <= ry1:
            scores.append((Path(template_path).name, -1.0, "out_of_bounds"))
            all_matched = False
            continue
        crop = frame_bgr[ry1:ry2, rx1:rx2]
        tmpl = _load_template(template_path)
        if tmpl is None:
            scores.append((Path(template_path).name, -1.0, "template_missing"))
            all_matched = False
            continue
        if crop.shape[0] != tmpl.shape[0] or crop.shape[1] != tmpl.shape[1]:
            try:
                cmp_img = cv2.resize(crop, (tmpl.shape[1], tmpl.shape[0]), interpolation=cv2.INTER_LINEAR)
            except cv2.error:
                scores.append((Path(template_path).name, -1.0, "resize_error"))
                all_matched = False
                continue
        else:
            cmp_img = crop
        try:
            cmp_gray = cv2.cvtColor(cmp_img, cv2.COLOR_BGR2GRAY)
            tmpl_gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)
            score = float(cv2.matchTemplate(cmp_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)[0, 0])
        except cv2.error:
            scores.append((Path(template_path).name, -1.0, "match_error"))
            all_matched = False
            continue
        if not np.isfinite(score):
            scores.append((Path(template_path).name, -1.0, "nan_score"))
            all_matched = False
            continue
        scores.append((
            Path(template_path).name,
            score,
            "ok(ccoeff={:.3f})".format(score),
        ))
        if score < _MATCH_THRESHOLD:
            all_matched = False
    matched = all_matched and len(scores) == len(_TEMPLATE_SPECS)
    return matched, scores
