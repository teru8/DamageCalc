from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

from main import APP_USER_AGENT
from src.data.item_dictionary import ITEM_FALLBACK_JA_TO_EN

_POKEAPI_BASE = "https://pokeapi.co/api/v2"
_HOLDABLE_ITEM_CATEGORIES = (
    "in-a-pinch",
    "picky-healing",
    "type-protection",
    "held-items",
    "choice",
    "bad-held-items",
    "plates",
    "species-specific",
    "type-enhancement",
    "scarves",
    "jewels",
    "mega-stones",
    "memories",
    "z-crystals",
)
_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
_REQUEST_TIMEOUT = (5, 15)
_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = APP_USER_AGENT

_ITEM_MAP_CACHE: dict[str, str] | None = None


def _cache_path() -> Path:
    root = Path.home() / ".pokemon_damage_calc"
    root.mkdir(parents=True, exist_ok=True)
    return root / "item_catalog.json"


def _load_cached_map() -> dict[str, str] | None:
    path = _cache_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logging.warning("item_catalog cache load failed: %s", exc, exc_info=True)
        return None

    fetched_at = float(payload.get("fetched_at") or 0)
    if time.time() - fetched_at >= _CACHE_TTL_SECONDS:
        return None

    item_map = payload.get("item_map")
    if isinstance(item_map, dict):
        result: dict[str, str] = {}
        for ja_name, en_name in item_map.items():
            ja = str(ja_name or "").strip()
            en = _normalize_item_name_en(str(en_name or ""))
            if ja and en:
                result[ja] = en
        return result
    return None


def _save_cached_map(item_map: dict[str, str]) -> None:
    payload = {
        "fetched_at": time.time(),
        "item_map": item_map,
    }
    _cache_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _get_json(url: str) -> dict:
    try:
        response = _SESSION.get(url, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}
    except (requests.RequestException, ValueError, TypeError) as exc:
        logging.warning("item_catalog request failed: url=%s error=%s", url, exc, exc_info=True)
        return {}


def _normalize_item_name_en(name: str) -> str:
    value = (name or "").strip()
    if not value:
        return ""
    return (
        value
        .replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
    )


def _fallback_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for ja_name, en_name in ITEM_FALLBACK_JA_TO_EN.items():
        ja = str(ja_name or "").strip()
        en = _normalize_item_name_en(str(en_name or ""))
        if ja and en:
            result[ja] = en
    return result


def _build_item_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for category_name in _HOLDABLE_ITEM_CATEGORIES:
        category_data = _get_json("{}/item-category/{}".format(_POKEAPI_BASE, category_name))
        items = category_data.get("items")
        if not isinstance(items, list):
            continue
        for item_entry in items:
            if not isinstance(item_entry, dict):
                continue
            detail_url = str(item_entry.get("url") or "").strip()
            if not detail_url:
                continue
            detail = _get_json(detail_url)
            names = detail.get("names")
            if not isinstance(names, list):
                continue
            ja_name = ""
            en_name = ""
            for name_entry in names:
                if not isinstance(name_entry, dict):
                    continue
                text = str(name_entry.get("name") or "").strip()
                lang = str((name_entry.get("language") or {}).get("name") or "").strip()
                if lang == "ja":
                    ja_name = text
                elif lang == "en":
                    en_name = _normalize_item_name_en(text)
            if ja_name and en_name:
                result[ja_name] = en_name
    return dict(sorted(result.items(), key=lambda row: row[0]))


def get_item_name_map(force_refresh: bool = False) -> dict[str, str]:
    global _ITEM_MAP_CACHE

    if _ITEM_MAP_CACHE is not None and not force_refresh:
        return _ITEM_MAP_CACHE

    base_map = _fallback_map()
    cached = _load_cached_map()
    if cached:
        base_map.update(cached)
    if not force_refresh:
        _ITEM_MAP_CACHE = dict(sorted(base_map.items(), key=lambda row: row[0]))
        return _ITEM_MAP_CACHE

    built = _build_item_map()
    if built:
        base_map.update(built)
        _ITEM_MAP_CACHE = dict(sorted(base_map.items(), key=lambda row: row[0]))
        _save_cached_map(_ITEM_MAP_CACHE)
        return _ITEM_MAP_CACHE

    _ITEM_MAP_CACHE = dict(sorted(base_map.items(), key=lambda row: row[0]))
    return _ITEM_MAP_CACHE


def get_item_names(force_refresh: bool = False) -> list[str]:
    return sorted(get_item_name_map(force_refresh=force_refresh).keys())


def get_item_name_en(item_name_ja: str) -> str:
    name = (item_name_ja or "").strip()
    if not name:
        return ""
    return get_item_name_map().get(name, "")
