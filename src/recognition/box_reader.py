"""
Reads the Pokemon box/storage screen to auto-register a Pokemon.
Extraction flow:
1) Moves / Ability OCR
2) Candidate species from name OCR + ability (DB-only, no network)
3) Name OCR resolved against the candidates
4) EV/nature re-estimation from actual stats
"""
import re

import cv2
import numpy as np

from src.capture import ocr_engine
from src.constants import (
    BOX_ABILITY_ROI,
    BOX_EV_ROIS,
    BOX_MOVE_ROIS,
    BOX_POKEMON_NAME_ROI,
    BOX_STAT_ROIS,
    EV_POINT_FACTOR,
    NATURES_JA,
    TYPE_JA_TO_EN,
)
from src.data import database as db
from src.models import PokemonInstance
from src.recognition import text_matcher

_PLAUSIBLE_SPECIES_FIT_SCORE = 2600.0


def _match_species_names_top_n(raw_text: str, top_n: int = 5) -> list[tuple[str, float]]:
    """Return up to top_n (species_name_ja, score) sorted descending. DB-only, no network."""
    raw = text_matcher.normalize_ocr_text(raw_text)
    if not raw:
        return []
    raw_fold = raw.casefold()

    results: list[tuple[str, float]] = []
    for cand in text_matcher._species_names():
        cand_norm = text_matcher.normalize_ocr_text(cand)
        if not cand_norm:
            continue
        cand_fold = cand_norm.casefold()
        if cand_fold == raw_fold:
            results.append((cand, 1.0))
            continue
        score = text_matcher._candidate_score(raw_fold, cand_fold)
        if score >= text_matcher._min_ratio_for_length(len(raw_fold)) - 0.05:
            results.append((cand, score))

    results.sort(key=lambda item: -item[1])
    return results[:top_n]


def _crop(frame: np.ndarray, roi: tuple) -> np.ndarray:
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


def _try_ocr_with_variants(image: np.ndarray, allowlist: str | None = None) -> list[str]:
    """Try multiple preprocessing variants and return the first successful OCR lines."""
    if image is None or image.size == 0:
        return []
    import cv2
    variants: list[tuple[str, np.ndarray]] = []

    base = image.copy()
    if image.ndim == 2:
        base = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    variants.append(("base", base))
    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    variants.append(("gray", gray))

    variants.append(("resize_x2", cv2.resize(gray, (0, 0), fx=2, fy=2, interpolation=cv2.INTER_CUBIC)))
    variants.append(("resize_x3", cv2.resize(gray, (0, 0), fx=3, fy=3, interpolation=cv2.INTER_CUBIC)))

    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        variants.append(("clahe", clahe.apply(gray)))
    except Exception:
        pass

    variants.append(("gauss3", cv2.GaussianBlur(gray, (3, 3), 0)))
    variants.append(("median3", cv2.medianBlur(gray, 3)))

    try:
        variants.append(("adaptive", cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)))
    except Exception:
        pass
    try:
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(("otsu", otsu))
    except Exception:
        pass

    kernel = np.ones((3, 3), np.uint8)
    try:
        adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        variants.append(("open", cv2.morphologyEx(adaptive, cv2.MORPH_OPEN, kernel)))
        variants.append(("close", cv2.morphologyEx(adaptive, cv2.MORPH_CLOSE, kernel)))
        variants.append(("dilate", cv2.dilate(adaptive, kernel, iterations=1)))
        variants.append(("erode", cv2.erode(adaptive, kernel, iterations=1)))
    except Exception:
        pass

    try:
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        inv = cv2.bitwise_not(th)
        variants.append(("inv", inv))
    except Exception:
        pass

    try:
        kernel_sharp = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharp = cv2.filter2D(gray, -1, kernel_sharp)
        variants.append(("sharp", sharp))
    except Exception:
        pass

    for name, var in variants:
        try:
            texts = ocr_engine.read_text(var, allowlist=allowlist)
        except Exception:
            texts = ocr_engine.read_text(var)
        if texts:
            print(f"[BOX_OCR] variant '{name}' -> {texts}")
            return texts

    try:
        texts = ocr_engine.read_text(image)
        if texts:
            print(f"[BOX_OCR] fallback original -> {texts}")
            return texts
    except Exception:
        pass
    return []


def _preprocess(region: np.ndarray) -> np.ndarray:
    if region.size == 0:
        return region
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if float(thresh.mean()) < 127:
        thresh = cv2.bitwise_not(thresh)
    return thresh


def _read_text(frame: np.ndarray, roi: tuple) -> str:
    region = _crop(frame, roi)
    texts = _try_ocr_with_variants(region)
    if not texts:
        texts = _try_ocr_with_variants(_preprocess(region))
    return " ".join(texts).strip()


def _read_text_candidates(frame: np.ndarray, roi: tuple, preprocess: bool = True) -> list[str]:
    region = _crop(frame, roi)
    if region.size == 0:
        return []

    candidates: list[str] = []
    # Try multiple preprocessing variants and gather unique candidates
    variants = [region]
    if preprocess:
        variants.append(_preprocess(region))
    # include additional variants via the helper function by invoking it (it will run OCR on many variants)
    # but we also want to keep any direct results
    for var in variants:
        texts = _try_ocr_with_variants(var)
        for text in texts:
            text = text.strip()
            if text and text not in candidates:
                candidates.append(text)
    return candidates


def _read_number_candidates(frame: np.ndarray, roi: tuple, min_value: int, max_value: int) -> list[int]:
    x1, y1, x2, y2 = roi
    roi_variants = [
        (x1, y1, x2, y2),
        (x1 - 3, y1, x2 + 3, y2),
        (x1, y1 - 2, x2, y2 + 2),
        (x1 - 5, y1 - 2, x2 + 5, y2 + 2),
    ]

    values: list[int] = []
    for variant in roi_variants:
        region = _crop(frame, variant)
        if region.size == 0:
            continue
        # Try allowlist digits first across multiple variants
        texts = _try_ocr_with_variants(region, allowlist="0123456789/")
        if not texts:
            texts = _try_ocr_with_variants(_preprocess(region), allowlist="0123456789/")
        if not texts:
            texts = _try_ocr_with_variants(region)
        for text in texts:
            joined = re.sub(r"\s+", "", text or "")
            for token in re.findall(r"\d+", joined):
                try:
                    value = int(token)
                except ValueError:
                    continue
                if min_value <= value <= max_value:
                    values.append(value)
    return values


def _pick_number(candidates: list[int], default: int = 0, prefer_non_zero: bool = False) -> int:
    if not candidates:
        return default

    counts: dict[int, int] = {}
    for value in candidates:
        counts[value] = counts.get(value, 0) + 1

    best_value = default
    best_count = -1
    for value, count in counts.items():
        if count > best_count or (count == best_count and value < best_value):
            best_value = value
            best_count = count

    if prefer_non_zero and best_value == 0:
        non_zero = [(value, count) for value, count in counts.items() if value > 0]
        if non_zero:
            non_zero.sort(key=lambda item: (-item[1], item[0]))
            # OCR misses often become 0; if non-zero has near score, trust it.
            if non_zero[0][1] >= max(1, best_count - 1):
                return non_zero[0][0]
    return best_value


def _read_stat_value(frame: np.ndarray, roi: tuple) -> int:
    values = _read_number_candidates(frame, roi, 0, 999)
    return _pick_number(values, default=0, prefer_non_zero=False)


def _read_ev_point(frame: np.ndarray, roi: tuple) -> int:
    values = _read_number_candidates(frame, roi, 0, 32)
    return _pick_number(values, default=0, prefer_non_zero=True)


def _read_box_name_candidates(frame: np.ndarray) -> tuple[list[str], list[str]]:
    x1, y1, x2, y2 = BOX_POKEMON_NAME_ROI
    roi_variants = [
        (x1, y1, x2, y2),
        (x1 + 4, y1 + 4, x2 - 4, y2 - 4),
        (x1 + 8, y1 + 8, x2 - 8, y2 - 8),
    ]

    raw_candidates: list[str] = []
    for roi in roi_variants:
        for text in _read_text_candidates(frame, roi):
            if text not in raw_candidates:
                raw_candidates.append(text)

    print("[BOX_OCR] 名前候補: {}".format(raw_candidates))

    species_candidates: list[str] = []
    for raw in raw_candidates:
        matched = text_matcher.match_species_name(raw)
        if matched and matched not in species_candidates:
            species_candidates.append(matched)
    return raw_candidates, species_candidates


def _species_candidates_from_name_and_ability(
    raw_name_candidates: list[str],
    ability: str,
    moves: list[str],
) -> list[str]:
    """
    Candidate species list built from OCR name candidates + ability + moves.
    All lookups are DB-only (no network calls).

    Scoring:
      - Name fuzzy-match: up to 5.0 (proportional to match score)
      - Ability usage match: +2.0
      - Each matched move:  +1.0 (capped at 3.0 total from moves)
    """
    usage_rank = db.get_species_usage_rank_map()
    scores: dict[str, float] = {}

    # 1. Name-based candidates (fuzzy match against all species names)
    for raw in raw_name_candidates:
        for name, score in _match_species_names_top_n(raw, top_n=8):
            name_score = score * 5.0
            if scores.get(name, 0.0) < name_score:
                scores[name] = name_score

    # 2. Ability-based candidates
    if ability:
        for name in db.get_species_names_by_ability_usage(ability):
            scores[name] = scores.get(name, 0.0) + 2.0

    # 3. Move-based bonus (DB join; capped contribution)
    unique_moves = []
    for move_name in moves:
        if move_name and move_name not in unique_moves:
            unique_moves.append(move_name)
    move_bonus: dict[str, float] = {}
    for move_name in unique_moves:
        for name in db.get_species_names_by_move(move_name):
            move_bonus[name] = min(move_bonus.get(name, 0.0) + 1.0, 3.0)
    for name, bonus in move_bonus.items():
        scores[name] = scores.get(name, 0.0) + bonus

    if not scores:
        return []

    # Filter to top candidates and sort by usage rank
    top_score = max(scores.values())
    floor_score = max(1.0, top_score - 2.0)
    filtered = [
        (name, score)
        for name, score in scores.items()
        if score >= floor_score
    ]
    if len(filtered) < 8:
        filtered = sorted(scores.items(), key=lambda item: -item[1])[:8]

    def sort_key(item: tuple[str, float]) -> tuple[int, int, float, str]:
        name, score = item
        usage_priority = 0 if name in usage_rank else 1
        usage_value = usage_rank.get(name, 9999)
        return (usage_priority, usage_value, -score, name)

    ranked = sorted(filtered, key=sort_key)
    return [name for name, _ in ranked]


def _select_species_name(
    raw_candidates: list[str],
    ocr_species_candidates: list[str],
    contextual_candidates: list[str],
    stats: dict[str, int],
    raw_ev_points: dict[str, int],
) -> str:
    # Try contextual candidates in priority order, but validate with stat plausibility.
    if contextual_candidates:
        candidate_order: list[str] = []
        for name in contextual_candidates + ocr_species_candidates:
            if name and name not in candidate_order:
                candidate_order.append(name)

        fit_scores: dict[str, float] = {}
        for name in candidate_order:
            fit_score, _, _, _ = _estimate_species_fit(name, stats, raw_ev_points)
            fit_scores[name] = fit_score

        # Choose the candidate with the best (smallest) fit score instead of
        # returning the first candidate below threshold. This prevents ordering
        # bias when contextual candidates are many and a later OCR candidate
        # actually fits better.
        best_name = min(
            candidate_order,
            key=lambda name: (fit_scores.get(name, float("inf")), candidate_order.index(name)),
        )
        best_fit = fit_scores.get(best_name, float("inf"))
        if best_fit <= _PLAUSIBLE_SPECIES_FIT_SCORE:
            print(
                "[BOX_OCR] 名前決定(適合度優先): {}  fit={:.1f}".format(
                    best_name,
                    best_fit,
                )
            )
            return best_name

        # Fallback: keep previous behavior preferring OCR-based candidates
        if ocr_species_candidates:
            print("[BOX_OCR] 名前マッチ: {}".format(ocr_species_candidates[0]))
            return ocr_species_candidates[0]

    if ocr_species_candidates:
        print("[BOX_OCR] 名前マッチ: {}".format(ocr_species_candidates[0]))
        return ocr_species_candidates[0]

    filtered = [
        text_matcher.normalize_ocr_text(text)
        for text in raw_candidates
        if len(text_matcher.normalize_ocr_text(text)) >= 2
    ]
    filtered = [text for text in filtered if text]
    if filtered:
        filtered.sort(key=len, reverse=True)
        return filtered[0]
    return ""


def _infer_nature_and_fix_evs(
    species_name: str,
    stats: dict[str, int],
    raw_ev_points: dict[str, int],
) -> tuple[str, dict[str, int]]:
    score, best_nature, best_evs, best_predicted = _estimate_species_fit(
        species_name,
        stats,
        raw_ev_points,
    )
    if score == float("inf"):
        print("[BOX_OCR] 性格推定: 種族データなし (name='{}')".format(species_name))
        return "まじめ", raw_ev_points

    # Recompute predicted stats from species base stats and the estimated EVs
    from src.calc.damage_calc import calc_stat
    species = db.get_species_by_name_ja(species_name)
    if not species:
        # fallback: report estimated EVs but can't compute predicted stats
        boost_stat, reduce_stat = NATURES_JA.get(best_nature, (None, None))
        print("[BOX_OCR] 性格推定: boost={} reduce={}".format(boost_stat, reduce_stat))
        return best_nature, best_evs

    boost_stat, reduce_stat = NATURES_JA.get(best_nature, (None, None))
    stat_order = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]
    base_map = {
        "hp": species.base_hp,
        "attack": species.base_attack,
        "defense": species.base_defense,
        "sp_attack": species.base_sp_attack,
        "sp_defense": species.base_sp_defense,
        "speed": species.base_speed,
    }

    for key in stat_order:
        base = base_map.get(key, 0)
        is_hp = key == "hp"
        if key == "hp":
            nature_mult = 1.0
        else:
            if boost_stat == key:
                nature_mult = 1.1
            elif reduce_stat == key:
                nature_mult = 0.9
            else:
                nature_mult = 1.0

        points = int(best_evs.get(key, int(raw_ev_points.get(key, 0))))
        ev = points * EV_POINT_FACTOR
        predicted = calc_stat(base, 31, ev, is_hp=is_hp, nature_mult=nature_mult)
        print(
            "[BOX_OCR] EV再推定 {} raw_pt={} -> pt={} predicted={}".format(
                key,
                int(raw_ev_points.get(key, 0)),
                points,
                int(predicted),
            )
        )

    print("[BOX_OCR] 性格推定: boost={} reduce={}".format(boost_stat, reduce_stat))
    return best_nature, best_evs


def _estimate_species_fit(
    species_name: str,
    stats: dict[str, int],
    raw_ev_points: dict[str, int],
) -> tuple[float, str, dict[str, int], dict[str, int]]:
    from src.calc.damage_calc import calc_stat

    species = db.get_species_by_name_ja(species_name)
    if not species:
        return float("inf"), "まじめ", dict(raw_ev_points), {}

    stat_order = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]
    base_map = {
        "hp": species.base_hp,
        "attack": species.base_attack,
        "defense": species.base_defense,
        "sp_attack": species.base_sp_attack,
        "sp_defense": species.base_sp_defense,
        "speed": species.base_speed,
    }

    best_nature = "まじめ"
    best_evs = dict(raw_ev_points)
    best_predicted: dict[str, int] = {}
    best_score: float | None = None

    for nature_name, (boost, reduce) in NATURES_JA.items():
        total_score = 0.0
        estimated: dict[str, int] = {}
        predicted_map: dict[str, int] = {}
        for key in stat_order:
            actual = int(stats.get(key, 0))
            raw_point = int(raw_ev_points.get(key, 0))
            base = base_map[key]
            if actual <= 0 or base <= 0:
                estimated[key] = raw_point
                predicted_map[key] = actual
                continue

            if key == "hp":
                nature_mult = 1.0
                is_hp = True
            else:
                is_hp = False
                if boost == key:
                    nature_mult = 1.1
                elif reduce == key:
                    nature_mult = 0.9
                else:
                    nature_mult = 1.0

            best_local = None
            for points in range(33):
                ev = points * EV_POINT_FACTOR
                predicted = calc_stat(base, 31, ev, is_hp=is_hp, nature_mult=nature_mult)
                stat_diff = abs(predicted - actual)
                ev_diff = abs(points - raw_point)
                score = (stat_diff * 100.0) + ev_diff
                if best_local is None or score < best_local[0]:
                    best_local = (score, points, predicted)

            if best_local is None:
                estimated[key] = raw_point
                predicted_map[key] = actual
                total_score += 1000.0
                continue

            score, points, predicted = best_local
            estimated[key] = points
            predicted_map[key] = predicted
            total_score += score

        total_score += abs(sum(estimated.values()) - 66) * 2.0
        if best_score is None or total_score < best_score:
            best_score = total_score
            best_nature = nature_name
            best_evs = estimated
            best_predicted = predicted_map

    if best_score is None:
        return float("inf"), "まじめ", dict(raw_ev_points), {}
    return best_score, best_nature, best_evs, best_predicted


def read_box_screen(frame: np.ndarray) -> dict:
    """
    Reads all visible data from the box screen.
    Returns dict keys: name, type1, type2, stats, ev_points, moves, ability, nature, pokemon.
    """
    data: dict = {"state": "box"}

    # Type icons/ROIs were removed; leave type fields blank here.
    data["type1"] = ""
    data["type2"] = ""

    stats: dict[str, int] = {}
    for stat_name, roi in BOX_STAT_ROIS.items():
        value = _read_stat_value(frame, roi)
        stats[stat_name] = value
        print("[BOX_OCR] 実数値 {}: {}".format(stat_name, value))
    data["stats"] = stats

    raw_ev_points: dict[str, int] = {}
    for stat_name, roi in BOX_EV_ROIS.items():
        value = _read_ev_point(frame, roi)
        raw_ev_points[stat_name] = value
        print("[BOX_OCR] 努力値pt(生) {}: {}".format(stat_name, value))

    moves: list[str] = []
    for index, roi in enumerate(BOX_MOVE_ROIS):
        raw_move = _read_text(frame, roi)
        move_name = text_matcher.match_move_name(raw_move)
        print("[BOX_OCR] 技{}: raw='{}' → matched='{}'".format(index + 1, raw_move, move_name))
        if move_name:
            moves.append(move_name)
    data["moves"] = moves

    raw_ability = _read_text(frame, BOX_ABILITY_ROI)
    ability = text_matcher.match_ability_name(raw_ability)
    print("[BOX_OCR] とくせい: raw='{}' → matched='{}'".format(raw_ability, ability))
    data["ability"] = ability

    raw_name_candidates, ocr_species_candidates = _read_box_name_candidates(frame)
    contextual_candidates = _species_candidates_from_name_and_ability(raw_name_candidates, ability, moves)
    if contextual_candidates:
        print("[BOX_OCR] 候補種族(名前/特性): {}".format(contextual_candidates[:12]))
    name = _select_species_name(
        raw_name_candidates,
        ocr_species_candidates,
        contextual_candidates,
        stats,
        raw_ev_points,
    )
    data["name"] = name
    data["name_candidates"] = raw_name_candidates

    nature, ev_points = _infer_nature_and_fix_evs(name, stats, raw_ev_points)
    data["nature"] = nature
    data["ev_points"] = ev_points
    for stat_name in ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]:
        print("[BOX_OCR] 努力値pt(補正後) {}: {}".format(stat_name, ev_points.get(stat_name, 0)))
    print("[BOX_OCR] 性格: {}".format(nature))

    # Recompute final stats from species base + inferred EVs/nature
    from src.calc.damage_calc import calc_stat
    species = db.get_species_by_name_ja(name)
    final_stats = dict(stats)
    if species:
        boost_stat, reduce_stat = NATURES_JA.get(nature, (None, None))
        base_map = {
            "hp": species.base_hp,
            "attack": species.base_attack,
            "defense": species.base_defense,
            "sp_attack": species.base_sp_attack,
            "sp_defense": species.base_sp_defense,
            "speed": species.base_speed,
        }
        for key in ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]:
            base = base_map.get(key, 0)
            is_hp = key == "hp"
            if key == "hp":
                nature_mult = 1.0
            else:
                if boost_stat == key:
                    nature_mult = 1.1
                elif reduce_stat == key:
                    nature_mult = 0.9
                else:
                    nature_mult = 1.0
            points = int(ev_points.get(key, 0))
            ev = points * EV_POINT_FACTOR
            final_stats[key] = int(calc_stat(base, 31, ev, is_hp=is_hp, nature_mult=nature_mult))

    data["stats"] = final_stats

    # types were kept as fields in `data`; assign local vars for compatibility
    type1 = data.get("type1", "")
    type2 = data.get("type2", "")
    types = [type_name for type_name in [type1, type2] if type_name]
    pokemon = PokemonInstance(
        name_ja=name,
        types=types,
        nature=nature,
        ability=ability,
        hp=final_stats.get("hp", 0),
        attack=final_stats.get("attack", 0),
        defense=final_stats.get("defense", 0),
        sp_attack=final_stats.get("sp_attack", 0),
        sp_defense=final_stats.get("sp_defense", 0),
        speed=final_stats.get("speed", 0),
        ev_hp=ev_points.get("hp", 0) * EV_POINT_FACTOR,
        ev_attack=ev_points.get("attack", 0) * EV_POINT_FACTOR,
        ev_defense=ev_points.get("defense", 0) * EV_POINT_FACTOR,
        ev_sp_attack=ev_points.get("sp_attack", 0) * EV_POINT_FACTOR,
        ev_sp_defense=ev_points.get("sp_defense", 0) * EV_POINT_FACTOR,
        ev_speed=ev_points.get("speed", 0) * EV_POINT_FACTOR,
        moves=moves,
    )
    pokemon.max_hp = pokemon.hp
    pokemon.current_hp = pokemon.hp
    data["pokemon"] = pokemon
    return data
