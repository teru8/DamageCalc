from __future__ import annotations

import difflib
import re
import unicodedata

from src.constants import ABILITIES_JA, TYPE_JA_TO_EN
from src.data import database as db

_species_cache: list[str] | None = None
_move_cache: list[str] | None = None
_ability_cache: list[str] | None = None
_cache_generation: int = -1  # tracks db.get_write_generation() at last load

_TEXT_REPLACEMENTS = str.maketrans({
    "　": "",
    " ": "",
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "‐": "-",
    "－": "-",
    "―": "-",
    "ー": "ー",
    "：": ":",
    "･": "・",
})
_DISALLOWED_RE = re.compile(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠ー・:()\-+＋♂♀']")
_SMALL_KANA_REPLACEMENTS = str.maketrans({
    "ぁ": "あ",
    "ぃ": "い",
    "ぅ": "う",
    "ぇ": "え",
    "ぉ": "お",
    "ゃ": "や",
    "ゅ": "ゆ",
    "ょ": "よ",
    "っ": "つ",
    "ゎ": "わ",
    "ァ": "ア",
    "ィ": "イ",
    "ゥ": "ウ",
    "ェ": "エ",
    "ォ": "オ",
    "ャ": "ヤ",
    "ュ": "ユ",
    "ョ": "ヨ",
    "ッ": "ツ",
    "ヮ": "ワ",
})
_DAKUTEN_RE = re.compile(r"[\u3099\u309A]")


def clear_caches() -> None:
    global _species_cache, _move_cache, _ability_cache, _cache_generation
    _species_cache = None
    _move_cache = None
    _ability_cache = None
    _cache_generation = -1


def _check_generation() -> None:
    """Invalidate caches if the DB has been written since last load."""
    global _cache_generation
    current = db.get_write_generation()
    if current != _cache_generation:
        clear_caches()
        _cache_generation = current


def normalize_ocr_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.translate(_TEXT_REPLACEMENTS)
    text = _DISALLOWED_RE.sub("", text)
    return text.strip()


def _species_names() -> list[str]:
    global _species_cache
    _check_generation()
    if _species_cache:
        return _species_cache
    names = db.get_all_species_names_ja()
    if names:
        _species_cache = names
    return names


def _move_names() -> list[str]:
    global _move_cache
    _check_generation()
    if _move_cache:
        return _move_cache
    names = db.get_all_move_names_ja()
    if names:
        _move_cache = names
    return names


def _ability_names() -> list[str]:
    global _ability_cache
    _check_generation()
    if _ability_cache:
        return _ability_cache
    names = _unique(_normalize_candidates(list(ABILITIES_JA) + db.get_all_usage_ability_names()))
    _ability_cache = names
    return names


def _normalize_candidates(items: list[str]) -> list[str]:
    return [normalize_ocr_text(item) or item for item in items]


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = (item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _candidate_score(raw_norm: str, cand_norm: str) -> float:
    if not raw_norm or not cand_norm:
        return 0.0
    score = difflib.SequenceMatcher(None, raw_norm, cand_norm).ratio()
    raw_loose = _loose_japanese(raw_norm)
    cand_loose = _loose_japanese(cand_norm)
    if raw_loose and cand_loose:
        loose = difflib.SequenceMatcher(None, raw_loose, cand_loose).ratio()
        if raw_loose in cand_loose or cand_loose in raw_loose:
            loose += 0.08
        score = max(score, min(loose + 0.05, 1.0))
    if raw_norm in cand_norm or cand_norm in raw_norm:
        score += 0.12
    if raw_norm[:1] == cand_norm[:1]:
        score += 0.03
    if raw_norm[-1:] == cand_norm[-1:]:
        score += 0.03
    return min(score, 1.0)


def _loose_japanese(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    decomposed = _DAKUTEN_RE.sub("", decomposed)
    recomposed = unicodedata.normalize("NFC", decomposed)
    return recomposed.translate(_SMALL_KANA_REPLACEMENTS)


def _min_ratio_for_length(length: int) -> float:
    if length <= 2:
        return 0.95
    if length <= 4:
        return 0.78
    if length <= 6:
        return 0.68
    return 0.60


def best_match(
    text: str,
    candidates: list[str],
    min_ratio: float | None = None,
    fallback_to_raw: bool = False,
) -> str:
    raw = normalize_ocr_text(text)
    if not raw:
        return ""
    if not candidates:
        return raw if fallback_to_raw else ""

    best_name = ""
    best_score = 0.0
    raw_fold = raw.casefold()
    for cand in candidates:
        cand_norm = normalize_ocr_text(cand)
        if not cand_norm:
            continue
        cand_fold = cand_norm.casefold()
        if cand_fold == raw_fold:
            return cand
        score = _candidate_score(raw_fold, cand_fold)
        if score > best_score:
            best_name = cand
            best_score = score

    threshold = min_ratio if min_ratio is not None else _min_ratio_for_length(len(raw_fold))
    if best_score >= threshold:
        return best_name
    return raw if fallback_to_raw else ""


def match_species_name(text: str, fallback_to_raw: bool = False) -> str:
    return best_match(text, _species_names(), fallback_to_raw=fallback_to_raw)


def match_move_name(text: str) -> str:
    matched = best_match(text, _move_names())
    if matched:
        return matched
    return best_match(text, _move_names(), min_ratio=0.60)


def match_ability_name(text: str) -> str:
    raw = normalize_ocr_text(text)
    if not raw:
        return ""
    candidates = _ability_names()
    for cand in candidates:
        if normalize_ocr_text(cand) == raw:
            return cand
    return best_match(text, candidates, min_ratio=0.56)


def match_type_name(text: str) -> str:
    return best_match(text, list(TYPE_JA_TO_EN.keys()), min_ratio=0.55)
