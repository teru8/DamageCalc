from __future__ import annotations

import logging
import sys
from pathlib import Path

import cv2
import numpy as np

from src.data import database as db
from src.recognition import champions_sprite_matcher

_logger = logging.getLogger(__name__)

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
    except (OSError, ValueError):
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
    corr = float(cv2.matchTemplate(q_gray, t_gray, cv2.TM_CCOEFF_NORMED)[0][0])
    corr = max(0.0, min(1.0, (corr + 1.0) * 0.5))

    return color_score * 0.70 + corr * 0.30


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


def _detect_type_groups(slot: np.ndarray, slot_index: int = -1) -> list[list[str]]:
    ranked_icons: list[tuple[int, float, list[str]]] = []
    for icon_index, rel_roi in enumerate(_TYPE_ICON_REL_ROIS):
        icon = _rel_crop(slot, rel_roi)
        if icon.size == 0:
            continue
        ranked = _rank_icon_types(icon, top_k=6)
        if not ranked:
            continue
        best_score = float(ranked[0][1])
        second_score = float(ranked[1][1]) if len(ranked) >= 2 else 0.0
        min_score = 0.50
        if best_score < min_score:
            _logger.debug("[type_icon] slot=%d icon=%d REJECTED best=%.3f < min=%.2f", slot_index, icon_index, best_score, min_score)
            continue
        # Guard against unstable top-1 predictions at low confidence.
        if best_score < 0.42 and (best_score - second_score) < 0.07:
            _logger.debug("[type_icon] slot=%d icon=%d REJECTED low_margin best=%.3f margin=%.3f", slot_index, icon_index, best_score, best_score - second_score)
            continue
        cutoff = max(0.16, best_score - 0.12)
        group = [name for name, score in ranked if float(score) >= cutoff][:4]
        if not group:
            continue
        _logger.debug("[type_icon] slot=%d icon=%d ACCEPTED best=%.3f group=%s", slot_index, icon_index, best_score, group)
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


def _type_exact_species_names(
    primary_types: list[str],
    season_species: list,
    sprite_names: set[str],
) -> list[str]:
    """Return name_ja list where the species has a sprite AND exactly matches the detected types."""
    if not primary_types:
        return []
    target = set(primary_types)
    seen_ids: set[int] = set()
    seen_names: set[str] = set()
    names: list[str] = []
    for species in sorted(season_species, key=lambda s: (s.species_id, s.name_ja)):
        name = str(species.name_ja or "").strip()
        if not name or name not in sprite_names:
            continue
        own = {species.type1, species.type2}
        own.discard("")
        if own != target:
            continue
        if species.species_id in seen_ids:
            continue
        seen_ids.add(species.species_id)
        if name in seen_names:
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
        _logger.debug("[sprite_match] no ranked results for candidates=%s", candidate_names)
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
    if top_score < 0.23:
        return "", "", False, ordered_names, top_score
    if top_score < 0.50 and margin < 0.020:
        return "", "", False, ordered_names, top_score
    if top_score < 0.30 and margin < 0.060:
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

    sprite_names: set[str] = set(champions_sprite_matcher._refs_by_name().keys())

    results: list[dict] = []
    for index, roi in enumerate(_OPP_SLOT_ROIS):
        slot = _crop(frame, roi)

        type_groups = _detect_type_groups(slot, slot_index=index)
        primary_types = [group[0] for group in type_groups if group]
        candidate_names = _type_exact_species_names(primary_types, season_species, sprite_names)
        _logger.debug("[candidates] slot=%d types=%s → %s", index, primary_types, candidate_names)
        if len(candidate_names) == 1:
            picked_name, picked_form, picked_shiny, ranked_candidates, confidence = candidate_names[0], "", False, candidate_names, 1.0
            _logger.debug("[decided] slot=%d → %s (single candidate)", index, picked_name)
        else:
            picked_name, picked_form, picked_shiny, ranked_candidates, confidence = _match_species_by_sprite(
                slot,
                candidate_names,
            )

        results.append(
            _slot_result(
                index=index,
                occupied=True,  # opponent always has 6 Pokémon
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
