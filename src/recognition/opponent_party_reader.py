from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

from src.data import database as db
from src.recognition import champions_sprite_matcher

# Opponent party rows on 1280x720 battle party screen.
_OPP_SLOT_ROIS = [
    (1038, 102, 1238, 180),
    (1038, 186, 1238, 264),
    (1038, 270, 1238, 350),
    (1038, 354, 1238, 432),
    (1038, 438, 1238, 516),
    (1038, 522, 1238, 600),
]

# Relative ROIs inside a slot.
# Keep sprite crop away from extreme left background while avoiding right icon bleed.
_SPRITE_REL_ROI = (34, 6, 119, 72)
_TYPE_ICON_REL_ROIS = [
    (127, 8, 158, 39),
    (160, 8, 191, 39),
]

def _asset_roots() -> list[Path]:
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        roots.append(exe_dir / "assets")
        roots.append(exe_dir / "_internal" / "assets")
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        if str(meipass):
            roots.append(meipass / "assets")
    else:
        project_root = Path(__file__).resolve().parents[2]
        roots.append(project_root / "assets")
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


_TYPE_TEMPLATE_DIRS = [
    root / "templates" / "types" for root in _asset_roots()
] + [
    root / "type_icon_templates" for root in _asset_roots()
]
_TYPE_TEMPLATE_SIZE = 32
_TYPE_TEMPLATE_CACHE: dict[str, list[np.ndarray]] | None = None
_TYPE_ICON_INNER_PAD = 2

_ALL_TYPES: set[str] = {
    "normal",
    "fire",
    "water",
    "electric",
    "grass",
    "ice",
    "fighting",
    "poison",
    "ground",
    "flying",
    "psychic",
    "bug",
    "rock",
    "ghost",
    "dragon",
    "dark",
    "steel",
    "fairy",
}


def _read_image_color(path: Path) -> np.ndarray | None:
    """Unicode-safe image loader for Windows paths."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except Exception:
        return None
    if data.size == 0:
        return None
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        return None
    return img


def _crop(frame: np.ndarray, roi: tuple[int, int, int, int]) -> np.ndarray:
    if frame is None or frame.size == 0:
        return np.empty((0, 0, 3), dtype=np.uint8)
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = roi
    x1 = max(0, min(w, x1))
    x2 = max(0, min(w, x2))
    y1 = max(0, min(h, y1))
    y2 = max(0, min(h, y2))
    if x2 <= x1 or y2 <= y1:
        return np.empty((0, 0, 3), dtype=np.uint8)
    return frame[y1:y2, x1:x2]


def _rel_crop(frame: np.ndarray, rel_roi: tuple[int, int, int, int]) -> np.ndarray:
    return _crop(frame, rel_roi)


def _slot_occupied(slot: np.ndarray) -> bool:
    sprite = _rel_crop(slot, _SPRITE_REL_ROI)
    if sprite.size == 0:
        return False
    gray = cv2.cvtColor(sprite, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(sprite, cv2.COLOR_BGR2HSV)
    std = float(gray.std())
    sat_mean = float(hsv[:, :, 1].mean())
    return std >= 9.0 or sat_mean >= 30.0


def _normalize_type_name(raw: str) -> str:
    name = (raw or "").strip().casefold()
    if not name:
        return ""
    aliases = {
        "glass": "grass",
        "fig": "fighting",
    }
    name = aliases.get(name, name)
    return name if name in _ALL_TYPES else ""


def _load_type_templates() -> dict[str, list[np.ndarray]]:
    global _TYPE_TEMPLATE_CACHE
    if _TYPE_TEMPLATE_CACHE is not None:
        return _TYPE_TEMPLATE_CACHE

    templates: dict[str, list[np.ndarray]] = {}
    for base_dir in _TYPE_TEMPLATE_DIRS:
        if not base_dir.exists():
            continue
        for path in sorted(base_dir.glob("*.png")):
            type_name = _normalize_type_name(path.stem.split("__", 1)[0])
            if not type_name:
                continue
            img = _read_image_color(path)
            if img is None or img.size == 0:
                continue
            icon = cv2.resize(img, (_TYPE_TEMPLATE_SIZE, _TYPE_TEMPLATE_SIZE), interpolation=cv2.INTER_AREA)
            templates.setdefault(type_name, []).append(icon)
    _TYPE_TEMPLATE_CACHE = templates
    return templates


def _icon_symbol_mask(icon_bgr: np.ndarray) -> np.ndarray:
    if icon_bgr is None or icon_bgr.size == 0:
        return np.zeros((0, 0), dtype=np.uint8)
    hsv = cv2.cvtColor(icon_bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(np.float32)
    val = hsv[:, :, 2].astype(np.float32)
    mask = ((sat < 96.0) & (val > 140.0)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8), iterations=1)
    return mask


def _dice_score(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    if mask_a.size == 0 or mask_b.size == 0 or mask_a.shape != mask_b.shape:
        return 0.0
    a = mask_a > 0
    b = mask_b > 0
    den = float(a.sum() + b.sum())
    if den <= 0:
        return 0.0
    inter = float((a & b).sum())
    return float((2.0 * inter) / den)


def _icon_template_score(query_icon: np.ndarray, template_icon: np.ndarray) -> float:
    query = cv2.resize(query_icon, (_TYPE_TEMPLATE_SIZE, _TYPE_TEMPLATE_SIZE), interpolation=cv2.INTER_AREA)
    template = cv2.resize(template_icon, (_TYPE_TEMPLATE_SIZE, _TYPE_TEMPLATE_SIZE), interpolation=cv2.INTER_AREA)

    q_hsv = cv2.cvtColor(query, cv2.COLOR_BGR2HSV)
    t_hsv = cv2.cvtColor(template, cv2.COLOR_BGR2HSV)
    q_hist = cv2.calcHist([q_hsv], [0, 1], None, [18, 8], [0, 180, 0, 256])
    t_hist = cv2.calcHist([t_hsv], [0, 1], None, [18, 8], [0, 180, 0, 256])
    q_hist = cv2.normalize(q_hist, None).flatten()
    t_hist = cv2.normalize(t_hist, None).flatten()
    color_score = 1.0 - float(cv2.compareHist(q_hist, t_hist, cv2.HISTCMP_BHATTACHARYYA))
    color_score = float(max(0.0, min(1.0, color_score)))

    q_gray = cv2.cvtColor(query, cv2.COLOR_BGR2GRAY)
    t_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    q_edge = (cv2.Canny(q_gray, 60, 140) > 0).astype(np.uint8)
    t_edge = (cv2.Canny(t_gray, 60, 140) > 0).astype(np.uint8)
    edge_score = _dice_score(q_edge, t_edge)

    symbol_score = _dice_score(_icon_symbol_mask(query), _icon_symbol_mask(template))
    corr = float(cv2.matchTemplate(q_gray, t_gray, cv2.TM_CCOEFF_NORMED)[0][0])
    corr = max(0.0, min(1.0, (corr + 1.0) * 0.5))

    return color_score * 0.50 + edge_score * 0.28 + symbol_score * 0.14 + corr * 0.08


def _rank_icon_types(icon: np.ndarray, top_k: int = 6) -> list[tuple[str, float]]:
    if icon is None or icon.size == 0:
        return []
    # Trim icon border to reduce row-highlight/frame noise.
    if (
        _TYPE_ICON_INNER_PAD > 0
        and icon.shape[0] > _TYPE_ICON_INNER_PAD * 2 + 2
        and icon.shape[1] > _TYPE_ICON_INNER_PAD * 2 + 2
    ):
        icon = icon[
            _TYPE_ICON_INNER_PAD:-_TYPE_ICON_INNER_PAD,
            _TYPE_ICON_INNER_PAD:-_TYPE_ICON_INNER_PAD,
        ]
    templates = _load_type_templates()
    if not templates:
        return []

    ranked: list[tuple[str, float]] = []
    for type_name, refs in templates.items():
        best = 0.0
        for ref in refs:
            score = _icon_template_score(icon, ref)
            if score > best:
                best = score
        if best > 0.08:
            ranked.append((type_name, float(best)))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked[:max(1, int(top_k))]


def _detect_type_groups(slot: np.ndarray) -> list[list[str]]:
    ranked_icons: list[tuple[int, float, list[str]]] = []
    for icon_index, rel_roi in enumerate(_TYPE_ICON_REL_ROIS):
        icon = _rel_crop(slot, rel_roi)
        if icon.size == 0:
            continue
        ranked = _rank_icon_types(icon, top_k=6)
        if not ranked:
            continue
        best_score = float(ranked[0][1])
        min_score = 0.24 if icon_index == 0 else 0.30
        if best_score < min_score:
            continue
        cutoff = max(0.16, best_score - 0.12)
        group = [name for name, score in ranked if float(score) >= cutoff][:4]
        if not group:
            continue
        ranked_icons.append((icon_index, best_score, group))

    if len(ranked_icons) >= 2:
        left = next((row for row in ranked_icons if row[0] == 0), None)
        right = next((row for row in ranked_icons if row[0] == 1), None)
        if left and right and left[2] and right[2] and left[2][0] == right[2][0]:
            if right[1] < left[1] * 0.80:
                ranked_icons = [left]
            elif left[1] < right[1] * 0.80:
                ranked_icons = [right]

    ranked_icons.sort(key=lambda row: row[0])
    return [group for _, _, group in ranked_icons]


def _species_matches_type_groups(type_groups: list[list[str]], type1: str, type2: str) -> bool:
    if not type_groups:
        return True
    own = {type1, type2}
    own.discard("")
    if not own:
        return False
    return any(bool(own.intersection(group)) for group in type_groups)


def _species_matches_all_type_groups(type_groups: list[list[str]], type1: str, type2: str) -> bool:
    if not type_groups:
        return True
    own = {type1, type2}
    own.discard("")
    if not own:
        return False
    for group in type_groups:
        if not own.intersection(group):
            return False
    return True


def _species_matches_primary_types(primary_types: list[str], type1: str, type2: str) -> bool:
    if not primary_types:
        return True
    own = {type1, type2}
    own.discard("")
    return all(pt in own for pt in primary_types)


def _species_matches_any_primary(primary_types: list[str], type1: str, type2: str) -> bool:
    if not primary_types:
        return True
    own = {type1, type2}
    own.discard("")
    return any(pt in own for pt in primary_types)


def _type_filtered_species_names(
    type_groups: list[list[str]],
    season_species: list,
) -> list[str]:
    if not type_groups:
        return []
    primary_types = [group[0] for group in type_groups if group and group[0]]

    strict_primary = [
        s for s in season_species
        if _species_matches_primary_types(primary_types, s.type1, s.type2)
    ]
    strict_hit = [
        s for s in season_species
        if _species_matches_all_type_groups(type_groups, s.type1, s.type2)
    ]
    relaxed_primary = [
        s for s in season_species
        if _species_matches_any_primary(primary_types, s.type1, s.type2)
    ]
    relaxed_hit = [
        s for s in season_species
        if _species_matches_type_groups(type_groups, s.type1, s.type2)
    ]
    candidates = strict_primary or strict_hit or relaxed_primary or relaxed_hit
    if not candidates:
        return []
    seen_ids: set[int] = set()
    seen_names: set[str] = set()
    names: list[str] = []
    for species in sorted(candidates, key=lambda s: (s.species_id, s.name_ja)):
        if species.species_id in seen_ids:
            continue
        seen_ids.add(species.species_id)
        name = str(species.name_ja or "").strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        names.append(name)

    return names


def _match_species_by_sprite(
    slot: np.ndarray,
    candidate_names: list[str],
) -> tuple[str, str, bool, list[str], float]:
    """Return (name_ja, form, is_shiny, ordered_candidate_names, confidence)."""
    if not candidate_names or not champions_sprite_matcher.is_ready():
        return "", "", False, [], 0.0

    sprite = _rel_crop(slot, _SPRITE_REL_ROI)
    if sprite.size == 0:
        return "", "", False, [], 0.0

    ranked = champions_sprite_matcher.match_sprite(
        sprite,
        candidate_names,
        top_k=min(10, len(candidate_names)),
    )
    if not ranked:
        return "", "", False, [], 0.0

    top = ranked[0]
    top_name = str(top["name_ja"])
    top_form = str(top["form"])
    top_shiny = bool(top["is_shiny"])
    top_score = float(top["score"])
    ordered_names = [r["name_ja"] for r in ranked]
    second_score = float(ranked[1]["score"]) if len(ranked) >= 2 else 0.0
    margin = top_score - second_score

    # Keep thresholds permissive, but avoid low-confidence ties.
    if top_score < 0.27:
        return "", "", False, ordered_names, top_score
    if top_score < 0.50 and margin < 0.020:
        return "", "", False, ordered_names, top_score
    return top_name, top_form, top_shiny, ordered_names, top_score


def _slot_result(
    index: int,
    occupied: bool,
    primary_types: list[str],
    type_groups: list[list[str]],
    picked_name: str,
    picked_form: str,
    picked_shiny: bool,
    species_candidates: list[str],
    confidence: float,
) -> dict:
    return {
        "slot_index": index,
        "occupied": occupied,
        "name_ja": picked_name,
        "form": picked_form,
        "is_shiny": picked_shiny,
        "confidence": float(confidence),
        "types": primary_types,
        "type_groups": type_groups,
        "species_candidates": species_candidates,
    }


def detect_opponent_party(frame: np.ndarray, season: str | None = None) -> list[dict]:
    if frame is None or frame.size == 0:
        return []
    if frame.shape[:2] != (720, 1280):
        frame = cv2.resize(frame, (1280, 720))

    season_token = db.normalize_season_token(season)
    season_pool = db.get_usage_pool_species_names(season_token)
    pool_set = set(season_pool)

    all_species = db.get_all_species()
    season_species = [s for s in all_species if s.name_ja in pool_set] if pool_set else []

    results: list[dict] = []
    for index, roi in enumerate(_OPP_SLOT_ROIS):
        slot = _crop(frame, roi)
        if slot.size == 0 or not _slot_occupied(slot):
            results.append(
                _slot_result(
                    index=index,
                    occupied=False,
                    primary_types=[],
                    type_groups=[],
                    picked_name="",
                    picked_form="",
                    picked_shiny=False,
                    species_candidates=[],
                    confidence=0.0,
                )
            )
            continue

        type_groups = _detect_type_groups(slot)
        primary_types = [group[0] for group in type_groups if group]
        candidate_names = _type_filtered_species_names(type_groups, season_species)
        picked_name, picked_form, picked_shiny, ranked_candidates, confidence = _match_species_by_sprite(
            slot,
            candidate_names,
        )

        results.append(
            _slot_result(
                index=index,
                occupied=True,
                primary_types=primary_types,
                type_groups=type_groups,
                picked_name=picked_name,
                picked_form=picked_form,
                picked_shiny=picked_shiny,
                species_candidates=ranked_candidates,
                confidence=confidence,
            )
        )

    return results
