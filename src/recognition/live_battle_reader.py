from __future__ import annotations

import difflib
import re

import cv2
import numpy as np

from src.capture import ocr_engine
from src.models import PokemonInstance
from src.constants import MY_HP_ROI, OPP_HP_ROI
from src.recognition import champions_sprite_matcher, text_matcher

# Battle HUD icon areas (1280x720).
_OPP_HUD_SPRITE_ROI = (930, 8, 1068, 102)
_MY_HUD_SPRITE_ROI = (0, 620, 128, 720)
_WATCH_COMMAND_ROI = (1070, 260, 1275, 340)


def _crop(frame: np.ndarray, roi: tuple[int, int, int, int]) -> np.ndarray:
    if frame is None or frame.size == 0:
        return np.empty((0, 0, 3), dtype=np.uint8)
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = roi
    x1 = max(0, min(w, int(x1)))
    x2 = max(0, min(w, int(x2)))
    y1 = max(0, min(h, int(y1)))
    y2 = max(0, min(h, int(y2)))
    if x2 <= x1 or y2 <= y1:
        return np.empty((0, 0, 3), dtype=np.uint8)
    return frame[y1:y2, x1:x2]


def _read_text(frame: np.ndarray, roi: tuple[int, int, int, int], allowlist: str | None = None) -> str:
    region = _crop(frame, roi)
    if region.size == 0:
        return ""
    texts = ocr_engine.read_text(region, allowlist=allowlist)
    if not texts:
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        texts = ocr_engine.read_text(cv2.cvtColor(th, cv2.COLOR_GRAY2BGR), allowlist=allowlist)
    return " ".join(texts).strip()


def _parse_hp_actual(text: str) -> tuple[int, int]:
    m = re.search(r"(\d+)\s*/\s*(\d+)", text or "")
    if m:
        cur = int(m.group(1))
        mx = int(m.group(2))
        if mx > 0:
            return max(0, min(cur, mx)), mx
    return 0, 0


def _parse_hp_percent(text: str) -> float:
    clean = (text or "").replace(" ", "").replace("　", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*[%％]", clean)
    if m:
        value = float(m.group(1))
        if 0.0 <= value <= 100.0:
            return value
    m = re.search(r"(\d+(?:\.\d+)?)", clean)
    if m:
        value = float(m.group(1))
        if 0.0 <= value <= 100.0:
            return value
    return -1.0


def _largest_component(mask: np.ndarray) -> np.ndarray:
    comp = (mask > 0).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(comp, 8)
    if num <= 1:
        return comp
    index = int(np.argmax(stats[1:, cv2.CC_STAT_AREA])) + 1
    return (labels == index).astype(np.uint8)


def _extract_sprite(icon_region: np.ndarray) -> np.ndarray:
    if icon_region is None or icon_region.size == 0:
        return np.empty((0, 0, 3), dtype=np.uint8)
    if icon_region.shape[0] < 8 or icon_region.shape[1] < 8:
        return np.empty((0, 0, 3), dtype=np.uint8)

    h, w = icon_region.shape[:2]
    hsv = cv2.cvtColor(icon_region, cv2.COLOR_BGR2HSV)
    corners = np.concatenate(
        [
            icon_region[:10, :10, :].reshape(-1, 3),
            icon_region[:10, max(0, w - 10):w, :].reshape(-1, 3),
            icon_region[max(0, h - 10):h, :10, :].reshape(-1, 3),
            icon_region[max(0, h - 10):h, max(0, w - 10):w, :].reshape(-1, 3),
        ],
        axis=0,
    )
    bg = corners.mean(axis=0).astype(np.float32)
    diff = np.linalg.norm(icon_region.astype(np.float32) - bg.reshape(1, 1, 3), axis=2)

    sat = hsv[:, :, 1].astype(np.float32)
    val = hsv[:, :, 2].astype(np.float32)
    fg = ((diff > 26.0) & (val > 24.0)) | ((sat > 42.0) & (val > 28.0))
    fg = cv2.morphologyEx(fg.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)
    fg = _largest_component(fg)

    if float(fg.mean()) < 0.04:
        # Fallback: keep a conservative center crop for matcher.
        x1 = int(w * 0.05)
        x2 = int(w * 0.92)
        y1 = int(h * 0.08)
        y2 = int(h * 0.95)
        return icon_region[y1:y2, x1:x2].copy()

    ys, xs = np.where(fg > 0)
    if ys.size == 0:
        return np.empty((0, 0, 3), dtype=np.uint8)
    x1 = max(0, int(xs.min()) - 4)
    x2 = min(w, int(xs.max()) + 5)
    y1 = max(0, int(ys.min()) - 4)
    y2 = min(h, int(ys.max()) + 5)
    return icon_region[y1:y2, x1:x2].copy()


def _unique_party_names(party: list[PokemonInstance | None]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for member in party:
        name = (member.name_ja or "").strip() if member else ""
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _match_sprite_name(
    sprite: np.ndarray,
    candidate_names: list[str],
    current_name: str = "",
) -> tuple[str, float, list[dict]]:
    current_name = (current_name or "").strip()
    if not candidate_names:
        return "", 0.0, []
    if sprite is None or sprite.size == 0 or not champions_sprite_matcher.is_ready():
        if current_name and current_name in candidate_names:
            return current_name, 0.0, []
        return "", 0.0, []

    ranked = champions_sprite_matcher.match_sprite(sprite, candidate_names, top_k=min(6, len(candidate_names)))
    if not ranked:
        if current_name and current_name in candidate_names:
            return current_name, 0.0, []
        return "", 0.0, []

    top_name = str(ranked[0]["name_ja"])
    top_score = float(ranked[0]["score"])
    second_score = float(ranked[1]["score"]) if len(ranked) >= 2 else 0.0
    current_score = 0.0
    for r in ranked:
        if r["name_ja"] == current_name:
            current_score = float(r["score"])
            break

    chosen = ""
    has_current = bool(current_name and current_name in candidate_names)
    if has_current and top_name != current_name:
        # Keep current target unless sprite evidence is strong enough to justify a switch.
        if top_score >= 0.44 and (top_score - current_score) >= 0.12:
            chosen = top_name
        else:
            chosen = current_name
    elif top_name == current_name and top_score >= 0.12:
        chosen = current_name
    elif top_score >= 0.44:
        chosen = top_name
    elif top_score >= 0.32 and (top_score - second_score) >= 0.10 and not has_current:
        chosen = top_name
    elif has_current:
        chosen = current_name

    return chosen, float(top_score), ranked


def is_watch_command_visible(frame: np.ndarray) -> tuple[bool, str]:
    if frame is None or frame.size == 0:
        return False, ""
    if frame.shape[:2] != (720, 1280):
        frame = cv2.resize(frame, (1280, 720))

    raw = _read_text(frame, _WATCH_COMMAND_ROI)
    norm = text_matcher.normalize_ocr_text(raw)
    if not norm:
        return False, ""

    target = "様子を見る"
    target_norm = text_matcher.normalize_ocr_text(target)
    if target_norm in norm:
        return True, norm
    if ("様子" in norm and "見" in norm) or ("ようす" in norm and "み" in norm):
        return True, norm
    ratio = difflib.SequenceMatcher(None, norm, target_norm).ratio()
    return ratio >= 0.62, norm


def read_live_battle(
    frame: np.ndarray,
    my_party: list[PokemonInstance | None],
    opponent_party: list[PokemonInstance | None],
    current_my_name: str = "",
    current_opp_name: str = "",
) -> dict:
    if frame is None or frame.size == 0:
        return {"my": {}, "opponent": {}}
    if frame.shape[:2] != (720, 1280):
        frame = cv2.resize(frame, (1280, 720))

    my_hp_text = _read_text(frame, MY_HP_ROI, allowlist="0123456789./%％")
    my_cur, my_max = _parse_hp_actual(my_hp_text)
    my_pct = (float(my_cur) / float(my_max) * 100.0) if my_max > 0 else -1.0

    opp_hp_text = _read_text(frame, OPP_HP_ROI, allowlist="0123456789./%％")
    opp_pct = _parse_hp_percent(opp_hp_text)

    my_names = _unique_party_names(my_party)
    opp_names = _unique_party_names(opponent_party)
    my_sprite = _extract_sprite(_crop(frame, _MY_HUD_SPRITE_ROI))
    opp_sprite = _extract_sprite(_crop(frame, _OPP_HUD_SPRITE_ROI))

    my_name, my_score, my_ranked = _match_sprite_name(my_sprite, my_names, current_name=current_my_name)
    opp_name, opp_score, opp_ranked = _match_sprite_name(opp_sprite, opp_names, current_name=current_opp_name)

    return {
        "my": {
            "name_ja": my_name,
            "match_score": my_score,
            "match_candidates": [{"name_ja": r["name_ja"], "form": r["form"], "score": float(r["score"])} for r in my_ranked[:4]],
            "hp_current": int(my_cur),
            "hp_max": int(my_max),
            "hp_percent": float(my_pct),
            "hp_text": my_hp_text,
        },
        "opponent": {
            "name_ja": opp_name,
            "match_score": opp_score,
            "match_candidates": [{"name_ja": r["name_ja"], "form": r["form"], "score": float(r["score"])} for r in opp_ranked[:4]],
            "hp_percent": float(opp_pct),
            "hp_text": opp_hp_text,
        },
    }
