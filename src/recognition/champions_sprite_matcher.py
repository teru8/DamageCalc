from __future__ import annotations

import json
import logging
import re
import sys
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

_logger = logging.getLogger(__name__)

import cv2
import numpy as np
import requests
from bs4 import BeautifulSoup
from main import APP_USER_AGENT

from src.data import database as db

_BASE_URL = "https://archives.bulbagarden.net"
_CATEGORY_URLS = {
    "normal": _BASE_URL + "/wiki/Category:Champions_menu_sprites",
    "shiny": _BASE_URL + "/wiki/Category:Champions_Shiny_menu_sprites",
}

def _resolve_cache_root() -> Path:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates.append(exe_dir / "assets" / "champions_menu_sprites")
        candidates.append(exe_dir / "_internal" / "assets" / "champions_menu_sprites")
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        if str(meipass):
            candidates.append(meipass / "assets" / "champions_menu_sprites")
    else:
        project_root = Path(__file__).resolve().parents[2]
        candidates.append(project_root / "assets" / "champions_menu_sprites")
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


_CACHE_ROOT = _resolve_cache_root()
_NORMAL_DIR = _CACHE_ROOT / "normal"
_SHINY_DIR = _CACHE_ROOT / "shiny"
_MANIFEST_PATH = _CACHE_ROOT / "manifest.json"
_TIMEOUT_SECONDS = 25

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": APP_USER_AGENT})

_MANIFEST_CACHE: dict | None = None
_REFS_BY_NAME_CACHE: dict[str, list[dict]] | None = None


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

    def get(self, key: Any, default: Any = None) -> Any:
        if key in self:
            value = super().__getitem__(key)
            self.move_to_end(key)
            return value
        return default


_REF_IMAGE_CACHE: _LRUDict = _LRUDict(256)  # numpy sprite arrays

_FILE_NAME_RE = re.compile(
    r"^Menu[_ ]CP[_ ](?P<dex>\d{4})(?:-(?P<form>.*))?$",
    re.IGNORECASE,
)

_MATCH_SCALES = (0.40, 0.50, 0.60, 0.70, 0.82, 0.94)
_MATCH_DX = (-8, -4, 0, 4, 8)
_MATCH_DY = (-12, -8, -4, 0, 4)
_COLOR_DELTA_NORM = 66.0

# Battle-only transformations that never appear on the party screen.
_EXCLUDED_FORMS: frozenset[str] = frozenset({
    "mega", "mega x", "mega y", "mega z",
    "gigantamax",
    "primal",
    "eternamax",
    # (PT base )
    "rainy", "snowy", "sunny",
    "blade",
    "hangry",
    "hero",
})

# Primary (first-priority) color template match on red-filled backgrounds.
_RED_BG_BGRS = (
    (57, 0, 126),   # #7E0039
    (62, 0, 134),   # mid between range
    (68, 0, 141),   # #8D0044
)
_COLOR_MATCH_SCALES = (0.56, 0.68, 0.80)
_COLOR_MATCH_DX = (-4, 0, 4)
_COLOR_MATCH_DY = (-10, -6, -2, 2)
_COLOR_PRIMARY_ACCEPT = 0.57
_COLOR_PRIMARY_MARGIN = 0.018


def _cache_dirs() -> None:
    _NORMAL_DIR.mkdir(parents=True, exist_ok=True)
    _SHINY_DIR.mkdir(parents=True, exist_ok=True)


def _normalize_file_stem(raw_name: str) -> tuple[str, bool]:
    stem = (raw_name or "").strip()
    stem = stem.replace(" ", "_")
    stem = stem.replace("%20", "_")
    shiny = False
    low = stem.casefold()
    if low.endswith("_shiny"):
        stem = stem[:-6]
        shiny = True
    elif low.endswith("-shiny"):
        stem = stem[:-6]
        shiny = True
    return stem, shiny


def _parse_file_name(file_name: str) -> dict | None:
    raw = (file_name or "").strip()
    if not raw:
        return None
    raw = unquote(raw)
    if raw.lower().startswith("file:"):
        raw = raw[5:]
    if not raw.lower().endswith(".png"):
        return None

    stem = raw[:-4]
    norm_stem, shiny_from_name = _normalize_file_stem(stem)
    match = _FILE_NAME_RE.match(norm_stem)
    if not match:
        return None
    dex_text = str(match.group("dex") or "")
    if not dex_text.isdigit():
        return None
    species_id = int(dex_text)
    form = str(match.group("form") or "").strip("_- ")
    form = form.replace("_", " ").strip()
    return {
        "species_id": species_id,
        "form": form,
        "is_shiny_from_name": shiny_from_name,
        "normalized_stem": norm_stem,
    }


def _request_soup(url: str) -> BeautifulSoup:
    response = _SESSION.get(url, timeout=_TIMEOUT_SECONDS)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _collect_file_pages(category_url: str) -> list[str]:
    pages: list[str] = []
    visited: set[str] = set()
    seen_files: set[str] = set()
    current = category_url

    while current and current not in visited:
        visited.add(current)
        soup = _request_soup(current)

        for anchor in soup.select("div#mw-category-media a[href]"):
            href = str(anchor.get("href") or "").strip()
            if not href.startswith("/wiki/File:"):
                continue
            abs_url = urljoin(_BASE_URL, href)
            if abs_url in seen_files:
                continue
            seen_files.add(abs_url)
            pages.append(abs_url)

        next_url = ""
        for anchor in soup.select("a[href]"):
            text = str(anchor.get_text(" ", strip=True) or "").casefold()
            href = str(anchor.get("href") or "").strip()
            if "next page" not in text:
                continue
            if "filefrom=" not in href:
                continue
            abs_url = urljoin(_BASE_URL, href)
            if abs_url in visited:
                continue
            next_url = abs_url
            break
        current = next_url

    return pages


def _full_image_url(file_page_url: str) -> tuple[str, str]:
    soup = _request_soup(file_page_url)
    title_text = ""
    title_elem = soup.select_one("#firstHeading")
    if title_elem:
        title_text = str(title_elem.get_text(" ", strip=True) or "").strip()
    if title_text.lower().startswith("file:"):
        title_text = title_text[5:]

    full_link = soup.select_one("div.fullImageLink a[href]")
    if not full_link:
        return title_text, ""
    href = str(full_link.get("href") or "").strip()
    if not href:
        return title_text, ""
    return title_text, urljoin(_BASE_URL, href)


def _safe_token(text: str) -> str:
    token = re.sub(r"[^0-9A-Za-z_.-]+", "_", (text or "").strip())
    return token.strip("._") or "base"


def _resolve_form_name_ja(name_en: str, form: str) -> str:
    """Return form-specific Japanese name (e.g. 'アローラライチュウ'), or '' if not applicable."""
    from src.data.pokeapi_client import _SPECIAL_FORM_NAME_MAP  # noqa: PLC0415

    base_en = (name_en or "").lower().replace(" ", "-").replace("_", "-")
    form_slug = (form or "").lower().replace(" ", "-").replace("_", "-")
    if not base_en or not form_slug:
        return ""
    prefix = f"{base_en}-{form_slug}"
    if prefix in _SPECIAL_FORM_NAME_MAP:
        return _SPECIAL_FORM_NAME_MAP[prefix]
    # Prefix match handles suffixes like "-breed" (e.g. "tauros-paldea-aqua" → "tauros-paldea-aqua-breed")
    for k, v in _SPECIAL_FORM_NAME_MAP.items():
        if k.startswith(prefix):
            return v
    return ""


def clear_cache() -> None:
    global _MANIFEST_CACHE, _REFS_BY_NAME_CACHE
    _MANIFEST_CACHE = None
    _REFS_BY_NAME_CACHE = None
    _REF_IMAGE_CACHE.clear()


def load_manifest() -> dict:
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is not None:
        return _MANIFEST_CACHE
    if not _MANIFEST_PATH.exists():
        _MANIFEST_CACHE = {"entries": []}
        return _MANIFEST_CACHE
    try:
        _MANIFEST_CACHE = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        _MANIFEST_CACHE = {"entries": []}
    return _MANIFEST_CACHE


def is_ready(min_entries: int = 80) -> bool:
    entries = load_manifest().get("entries") or []
    return isinstance(entries, list) and len(entries) >= min_entries


def _save_manifest(entries: list[dict], note: str = "") -> None:
    payload = {
        "fetched_at": time.time(),
        "source": "bulbagarden-archives",
        "note": note,
        "entries": entries,
    }
    _MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    clear_cache()


def download_catalog(
    force: bool = False,
    include_shiny: bool = True,
    species_ids: set[int] | None = None,
    limit: int | None = None,
) -> dict:
    _cache_dirs()

    category_pairs = [("normal", _CATEGORY_URLS["normal"])]
    if include_shiny:
        category_pairs.append(("shiny", _CATEGORY_URLS["shiny"]))

    all_species = db.get_all_species()
    species_cache: dict[int, tuple[str, str]] = {
        s.species_id: (s.name_ja, s.name_en) for s in all_species
    }
    species_cache_by_name_en: dict[str, str] = {
        s.name_en: s.name_ja for s in all_species if s.name_en
    }
    existing_entries = load_manifest().get("entries") or []
    merged: dict[tuple[int, str, bool, str], dict] = {}
    for row in existing_entries:
        if not isinstance(row, dict):
            continue
        try:
            species_id = int(row.get("species_id"))
        except (TypeError, ValueError):
            continue
        form = str(row.get("form") or "").strip()
        is_shiny = bool(row.get("is_shiny"))
        local_path = str(row.get("local_path") or "").strip()
        if not local_path:
            continue
        key = (species_id, form.casefold(), is_shiny, local_path)
        merged[key] = row

    added_count = 0

    for category, category_url in category_pairs:
        file_pages = _collect_file_pages(category_url)
        for file_page_url in file_pages:
            parsed_url = urlparse(file_page_url)
            file_part = unquote(parsed_url.path.rsplit("/", 1)[-1])
            file_name_from_url = file_part[5:] if file_part.lower().startswith("file:") else file_part
            parsed = _parse_file_name(file_name_from_url)

            title_text = file_name_from_url
            image_url = ""
            if parsed is None:
                title_text, image_url = _full_image_url(file_page_url)
                parsed = _parse_file_name(title_text)
                if parsed is None:
                    continue

            species_id = int(parsed["species_id"])
            if species_ids and species_id not in species_ids:
                continue

            if species_id not in species_cache:
                continue
            name_ja, name_en = species_cache[species_id]
            name_ja = species_cache_by_name_en.get(name_en, name_ja)

            if not image_url:
                title_text, image_url = _full_image_url(file_page_url)
                if not image_url:
                    continue
            parsed_title = _parse_file_name(title_text) or parsed
            form = str(parsed_title.get("form") or parsed.get("form") or "")
            is_shiny = bool(category == "shiny" or parsed_title.get("is_shiny_from_name"))
            out_dir = _SHINY_DIR if is_shiny else _NORMAL_DIR

            suffix = Path(urlparse(image_url).path).suffix or ".png"
            local_name = "{:04d}__{}__{}{}".format(
                species_id,
                _safe_token(form),
                "shiny" if is_shiny else "normal",
                suffix,
            )
            local_path = out_dir / local_name
            if force or not local_path.exists():
                binary = _SESSION.get(image_url, timeout=_TIMEOUT_SECONDS).content
                local_path.write_bytes(binary)

            form_name_ja = _resolve_form_name_ja(name_en, form)
            key = (species_id, form.casefold(), is_shiny, local_name)
            row = {
                "species_id": species_id,
                "name_ja": name_ja,
                "name_en": name_en,
                "form": form,
                "form_name_ja": form_name_ja,
                "is_shiny": is_shiny,
                "category": category,
                "file_page_url": file_page_url,
                "image_url": image_url,
                "local_path": str(local_path.relative_to(_CACHE_ROOT)),
            }
            if key not in merged:
                added_count += 1
            merged[key] = row
            if limit and added_count >= limit:
                break
        if limit and added_count >= limit:
            break

    entries = sorted(
        merged.values(),
        key=lambda row: (
            int(row.get("species_id") or 0),
            1 if bool(row.get("is_shiny")) else 0,
            str(row.get("form") or ""),
            str(row.get("local_path") or ""),
        ),
    )
    _save_manifest(entries, note="download_catalog")
    return {
        "saved_entries": len(entries),
        "added_entries": added_count,
        "cache_root": str(_CACHE_ROOT),
    }


def _refs_by_name() -> dict[str, list[dict]]:
    global _REFS_BY_NAME_CACHE
    if _REFS_BY_NAME_CACHE is not None:
        return _REFS_BY_NAME_CACHE

    grouped: dict[str, list[dict]] = {}
    entries = load_manifest().get("entries") or []
    for row in entries:
        if not isinstance(row, dict):
            continue
        name_ja = str(row.get("name_ja") or "").strip()
        form_name_ja = str(row.get("form_name_ja") or "").strip()
        rel_path = str(row.get("local_path") or "").strip()
        if not name_ja or not rel_path:
            continue
        path = _CACHE_ROOT / rel_path
        if not path.exists():
            continue
        ref = {
            "path": str(path),
            "is_shiny": bool(row.get("is_shiny")),
            "form": str(row.get("form") or ""),
        }
        grouped.setdefault(name_ja, []).append(ref)
        if form_name_ja and form_name_ja != name_ja:
            grouped.setdefault(form_name_ja, []).append(ref)

    for name_ja, rows in grouped.items():
        filtered = [
            row for row in rows
            if (row.get("form") or "").strip().casefold() not in _EXCLUDED_FORMS
        ]
        filtered.sort(key=lambda row: (1 if row.get("is_shiny") else 0, row.get("form") or ""))
        grouped[name_ja] = filtered

    _REFS_BY_NAME_CACHE = grouped
    return grouped


def _load_ref_image(path: str) -> tuple[np.ndarray, np.ndarray] | None:
    try:
        cached = _REF_IMAGE_CACHE.get(path)
    except KeyError:
        cached = None
    if cached is not None:
        return cached

    p = Path(path)
    if not p.exists():
        return None
    data = p.read_bytes()
    arr = np.frombuffer(data, np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    if image is None or image.ndim != 3 or image.shape[2] != 4:
        return None

    alpha = image[:, :, 3]
    ys, xs = np.where(alpha > 10)
    if ys.size == 0:
        return None
    x1, x2 = int(xs.min()), int(xs.max()) + 1
    y1, y2 = int(ys.min()), int(ys.max()) + 1
    rgb = image[y1:y2, x1:x2, :3]
    a = alpha[y1:y2, x1:x2]
    parsed = (rgb, a)
    try:
        _REF_IMAGE_CACHE[path] = parsed
        return _REF_IMAGE_CACHE.get(path, parsed)
    except KeyError:
        return parsed


def _largest_component(mask: np.ndarray) -> np.ndarray:
    comp = mask.astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(comp, 8)
    if num <= 1:
        return comp
    index = int(np.argmax(stats[1:, cv2.CC_STAT_AREA])) + 1
    return (labels == index).astype(np.uint8)


def _query_mask(sprite: np.ndarray) -> np.ndarray:
    h, w = sprite.shape[:2]
    work = sprite.copy()
    flood_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
    # Slightly looser border flood-fill to remove red UI gradients.
    lo = (14, 34, 34)
    up = (14, 34, 34)

    for x in range(0, w, 4):
        for y in (0, h - 1):
            if flood_mask[y + 1, x + 1] == 0:
                cv2.floodFill(
                    work,
                    flood_mask,
                    (x, y),
                    (0, 0, 0),
                    lo,
                    up,
                    flags=4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8),
                )
    for y in range(0, h, 4):
        for x in (0, w - 1):
            if flood_mask[y + 1, x + 1] == 0:
                cv2.floodFill(
                    work,
                    flood_mask,
                    (x, y),
                    (0, 0, 0),
                    lo,
                    up,
                    flags=4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8),
                )

    fg = (flood_mask[1:-1, 1:-1] == 0).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    fg = _largest_component(fg)
    return fg


def _query_features(sprite: np.ndarray) -> dict | None:
    if sprite is None or sprite.size == 0:
        return None
    if sprite.ndim == 2:
        sprite = cv2.cvtColor(sprite, cv2.COLOR_GRAY2BGR)

    mask = _query_mask(sprite)
    if float(mask.mean()) < 0.01:
        return None

    gray = cv2.cvtColor(sprite, cv2.COLOR_BGR2GRAY)
    edge = cv2.Canny(gray, 60, 140)
    edge = ((edge > 0) & (mask > 0))
    lab = cv2.cvtColor(sprite, cv2.COLOR_BGR2LAB).astype(np.float32)
    return {
        "sprite": sprite,
        "mask": mask.astype(np.uint8),
        "edge": edge,
        "gray": gray,
        "lab": lab,
        "height": int(sprite.shape[0]),
        "width": int(sprite.shape[1]),
    }


def _compose_reference_with_bg(
    ref_rgb: np.ndarray,
    ref_alpha: np.ndarray,
    bg_bgr: tuple[int, int, int],
) -> np.ndarray:
    if ref_rgb.size == 0 or ref_alpha.size == 0:
        return np.empty((0, 0, 3), dtype=np.uint8)
    alpha = np.clip(ref_alpha.astype(np.float32) / 255.0, 0.0, 1.0)[:, :, None]
    bg = np.empty_like(ref_rgb, dtype=np.uint8)
    bg[:, :] = bg_bgr
    mixed = ref_rgb.astype(np.float32) * alpha + bg.astype(np.float32) * (1.0 - alpha)
    return np.clip(mixed, 0.0, 255.0).astype(np.uint8)


def _masked_corrcoef(gray_a: np.ndarray, gray_b: np.ndarray, mask: np.ndarray) -> float:
    if gray_a.shape != gray_b.shape or gray_a.shape != mask.shape:
        return 0.0
    valid = mask > 0
    if int(valid.sum()) < 16:
        return 0.0
    a = gray_a[valid].astype(np.float32)
    b = gray_b[valid].astype(np.float32)
    a -= float(a.mean())
    b -= float(b.mean())
    den = float(np.sqrt((a * a).sum() * (b * b).sum()))
    if den <= 1e-6:
        return 0.0
    corr = float((a * b).sum() / den)
    corr = max(-1.0, min(1.0, corr))
    return (corr + 1.0) * 0.5


def _score_reference_by_color_fill(query: dict, ref_rgb: np.ndarray, ref_alpha: np.ndarray) -> float:
    h = int(query["height"])
    w = int(query["width"])
    qlab = query["lab"]
    qgray = query["gray"]
    best_score = 0.0

    for scale in _COLOR_MATCH_SCALES:
        target_h = max(8, int(h * scale))
        target_w = max(8, int(ref_rgb.shape[1] * target_h / max(1, ref_rgb.shape[0])))
        if target_w >= w - 2:
            target_w = w - 2
            target_h = max(8, int(ref_rgb.shape[0] * target_w / max(1, ref_rgb.shape[1])))

        resized_rgb = cv2.resize(ref_rgb, (target_w, target_h), interpolation=cv2.INTER_AREA)
        resized_alpha = cv2.resize(ref_alpha, (target_w, target_h), interpolation=cv2.INTER_AREA)
        local_mask = (resized_alpha > 24).astype(np.uint8)
        if int(local_mask.sum()) < 20:
            continue

        # Include nearby background around sprite body.
        focus_mask = cv2.dilate(local_mask, np.ones((5, 5), np.uint8), iterations=1)
        if int(focus_mask.sum()) < 20:
            continue

        prepared_refs: list[tuple[np.ndarray, np.ndarray]] = []
        for bg_bgr in _RED_BG_BGRS:
            rendered = _compose_reference_with_bg(resized_rgb, resized_alpha, bg_bgr)
            prepared_refs.append(
                (
                    cv2.cvtColor(rendered, cv2.COLOR_BGR2LAB).astype(np.float32),
                    cv2.cvtColor(rendered, cv2.COLOR_BGR2GRAY),
                )
            )

        for dx in _COLOR_MATCH_DX:
            for dy in _COLOR_MATCH_DY:
                ox = (w - target_w) // 2 + int(dx)
                oy = h - target_h - 2 + int(dy)
                if ox < 0 or oy < 0 or ox + target_w > w or oy + target_h > h:
                    continue

                q_patch_lab = qlab[oy:oy + target_h, ox:ox + target_w]
                q_patch_gray = qgray[oy:oy + target_h, ox:ox + target_w]

                for ref_lab, ref_gray in prepared_refs:
                    delta = np.abs(q_patch_lab - ref_lab)
                    mean_delta = float(delta[focus_mask > 0].mean())
                    color_score = max(0.0, 1.0 - mean_delta / _COLOR_DELTA_NORM)
                    corr = _masked_corrcoef(q_patch_gray, ref_gray, focus_mask)
                    score = color_score * 0.20 + corr * 0.80
                    if score > best_score:
                        best_score = score

    return best_score


def _score_reference(query: dict, ref_rgb: np.ndarray, ref_alpha: np.ndarray) -> float:
    h = int(query["height"])
    w = int(query["width"])
    qmask = query["mask"]
    qedge = query["edge"]
    qlab = query["lab"]
    qmask_sum = float((qmask > 0).sum())
    qedge_sum = float(qedge.sum())
    best_score = 0.0

    for scale in _MATCH_SCALES:
        target_h = max(8, int(h * scale))
        target_w = max(8, int(ref_rgb.shape[1] * target_h / max(1, ref_rgb.shape[0])))
        if target_w >= w - 2:
            target_w = w - 2
            target_h = max(8, int(ref_rgb.shape[0] * target_w / max(1, ref_rgb.shape[1])))

        resized_rgb = cv2.resize(ref_rgb, (target_w, target_h), interpolation=cv2.INTER_AREA)
        resized_alpha = cv2.resize(ref_alpha, (target_w, target_h), interpolation=cv2.INTER_AREA)
        local_mask = (resized_alpha > 35).astype(np.uint8)
        if local_mask.sum() < 12:
            continue
        local_edge = (
            (cv2.Canny(cv2.cvtColor(resized_rgb, cv2.COLOR_BGR2GRAY), 60, 140) > 0)
            & (local_mask > 0)
        )
        local_lab = cv2.cvtColor(resized_rgb, cv2.COLOR_BGR2LAB).astype(np.float32)
        local_mask_bin = local_mask > 0
        local_mask_sum = float(local_mask_bin.sum())
        local_edge_sum = float(local_edge.sum())

        for dx in _MATCH_DX:
            for dy in _MATCH_DY:
                ox = (w - target_w) // 2 + int(dx)
                oy = h - target_h - 2 + int(dy)
                if ox < 0 or oy < 0 or ox + target_w > w or oy + target_h > h:
                    continue

                q_patch_mask = qmask[oy:oy + target_h, ox:ox + target_w] > 0
                inter_mask = local_mask_bin & q_patch_mask
                inter = float(inter_mask.sum())
                union = local_mask_sum + qmask_sum - inter
                if union <= 0:
                    continue
                iou = inter / union
                if iou < 0.07:
                    continue

                q_patch_edge = qedge[oy:oy + target_h, ox:ox + target_w]
                edge_inter = float((local_edge & q_patch_edge).sum())
                edge_den = local_edge_sum + qedge_sum
                edge_dice = (2.0 * edge_inter / edge_den) if edge_den > 0 else 0.0

                if inter > 0.0:
                    q_patch_lab = qlab[oy:oy + target_h, ox:ox + target_w]
                    delta = np.abs(q_patch_lab - local_lab)
                    mean_delta = float(delta[inter_mask].mean())
                    color_score = max(0.0, 1.0 - mean_delta / _COLOR_DELTA_NORM)
                else:
                    color_score = 0.0

                score = iou * 0.46 + edge_dice * 0.28 + color_score * 0.26
                if score > best_score:
                    best_score = score

    return best_score


def match_sprite(
    sprite: np.ndarray,
    candidate_names: list[str],
    top_k: int = 6,
) -> list[dict]:
    """Return matches sorted by score descending.

    Each dict contains: name_ja, form, is_shiny, score.
    Form variants (gender, regional, item-based) are scored individually.
    """
    if not candidate_names:
        return []
    refs_by_name = _refs_by_name()
    if not refs_by_name:
        return []

    query = _query_features(sprite)
    if not query:
        return []

    def _ref_key(name_ja: str, ref: dict) -> tuple[str, str, bool]:
        return (name_ja, str(ref.get("form") or ""), bool(ref.get("is_shiny")))

    def _to_result(key: tuple[str, str, bool], score: float) -> dict:
        return {
            "name_ja": key[0],
            "form": key[1],
            "is_shiny": key[2],
            "score": float(min(score, 1.0)),
        }

    # Stage 1: color-fill matching — score each (name_ja, form, is_shiny) entry.
    color_scores: dict[tuple[str, str, bool], float] = {}
    for name_ja in candidate_names:
        for ref in refs_by_name.get(name_ja) or []:
            parsed = _load_ref_image(str(ref.get("path") or ""))
            if not parsed:
                continue
            score = _score_reference_by_color_fill(query, parsed[0], parsed[1])
            key = _ref_key(name_ja, ref)
            if score > color_scores.get(key, 0.0):
                color_scores[key] = score

    color_results = sorted(
        [_to_result(k, v) for k, v in color_scores.items() if v > 0.16],
        key=lambda x: x["score"],
        reverse=True,
    )
    if _logger.isEnabledFor(logging.DEBUG):
        debug_all = sorted(
            [_to_result(k, v) for k, v in color_scores.items() if v > 0.0],
            key=lambda x: x["score"],
            reverse=True,
        )
    if _logger.isEnabledFor(logging.DEBUG) and debug_all:
        top5 = debug_all[:5]
        lines = ", ".join(
            f"{r['name_ja']}({r['form'] or 'base'})={'shiny' if r['is_shiny'] else 'n'}:{r['score']:.3f}"
            for r in top5
        )
        _logger.debug("[color_fill] %s", lines)

    if color_results:
        top_color = float(color_results[0]["score"])
        if top_color >= _COLOR_PRIMARY_ACCEPT:
            return color_results[:max(1, int(top_k))]

    # Stage 2 fallback: shape/edge-aware matching.
    shape_scores: dict[tuple[str, str, bool], float] = {}
    for name_ja in candidate_names:
        for ref in refs_by_name.get(name_ja) or []:
            parsed = _load_ref_image(str(ref.get("path") or ""))
            if not parsed:
                continue
            score = _score_reference(query, parsed[0], parsed[1])
            key = _ref_key(name_ja, ref)
            if score > shape_scores.get(key, 0.0):
                shape_scores[key] = score

    results = sorted(
        [_to_result(k, v) for k, v in shape_scores.items() if v > 0.10],
        key=lambda x: x["score"],
        reverse=True,
    )
    if _logger.isEnabledFor(logging.DEBUG) and results:
        top5 = results[:5]
        lines = ", ".join(
            f"{r['name_ja']}({r['form'] or 'base'})={'shiny' if r['is_shiny'] else 'n'}:{r['score']:.3f}"
            for r in top5
        )
        _logger.debug("[shape_fallback] %s", lines)

    return results[:max(1, int(top_k))]
