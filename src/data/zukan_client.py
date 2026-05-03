from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

_BASE_URL = "https://zukan.pokemon.co.jp"
_SEARCH_API_URL = _BASE_URL + "/zukan-api/api/search/?limit=2000&page=1"
_MASTERS_API_URL = _BASE_URL + "/zukan-api/api/masters/"
_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
_TIMEOUT = (5, 15)


@dataclass(frozen=True)
class ZukanPokemonEntry:
    dex_no: str
    base_no: str
    sub_index: int
    name_ja: str
    sub_name: str
    type1_id: int
    type2_id: int
    image_small_url: str
    image_medium_url: str


def _cache_root() -> Path:
    root = Path.home() / ".pokemon_damage_calc" / "zukan_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _index_path() -> Path:
    return _cache_root() / "pokemon_index.json"


def _asset_dir() -> Path:
    path = _cache_root() / "assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _detail_dir() -> Path:
    path = _cache_root() / "detail"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _detail_path(dex_no: str) -> Path:
    safe = (dex_no or "").strip().replace("/", "_").replace("\\", "_")
    return _detail_dir() / "{}.json".format(safe or "unknown")


def _masters_path() -> Path:
    return _cache_root() / "masters.json"


def _load_cached_index() -> dict[str, Any] | None:
    path = _index_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _save_index(payload: dict[str, Any]) -> None:
    _index_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_cached_masters() -> dict[str, Any] | None:
    path = _masters_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _save_masters(payload: dict[str, Any]) -> None:
    _masters_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _parse_index(payload: dict[str, Any] | None) -> list[ZukanPokemonEntry]:
    if not payload:
        return []
    results = payload.get("results") or []
    parsed: list[ZukanPokemonEntry] = []
    for row in results:
        parsed.append(
            ZukanPokemonEntry(
                dex_no=str(row.get("zukan_no") or row.get("no") or ""),
                base_no=str(row.get("no") or "").strip(),
                sub_index=int(row.get("sub") or 0),
                name_ja=str(row.get("name") or "").strip(),
                sub_name=str(row.get("sub_name") or "").strip(),
                type1_id=int(row.get("type_1") or 0),
                type2_id=int(row.get("type_2") or 0),
                image_small_url=str(row.get("image_s") or "").strip(),
                image_medium_url=str(row.get("image_m") or "").strip(),
            )
        )
    return parsed


def get_pokemon_index(force_refresh: bool = False) -> list[ZukanPokemonEntry]:
    cached = _load_cached_index()
    if not force_refresh and cached:
        fetched_at = float(cached.get("fetched_at") or 0)
        if time.time() - fetched_at < _CACHE_TTL_SECONDS:
            return _parse_index(cached)

    try:
        response = requests.get(
            _SEARCH_API_URL,
            timeout=_TIMEOUT,
            headers={"User-Agent": "PokeDamageCalc/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
        payload["fetched_at"] = time.time()
        _save_index(payload)
        return _parse_index(payload)
    except (requests.RequestException, ValueError, TypeError, OSError) as exc:
        logging.debug("get_pokemon_index fallback to cache: %s", exc)
        return _parse_index(cached)


def get_masters(force_refresh: bool = False) -> dict[str, Any]:
    cached = _load_cached_masters()
    if not force_refresh and cached:
        fetched_at = float(cached.get("fetched_at") or 0)
        if time.time() - fetched_at < _CACHE_TTL_SECONDS:
            return cached.get("payload", {}) or {}

    try:
        response = requests.get(
            _MASTERS_API_URL,
            timeout=_TIMEOUT,
            headers={"User-Agent": "PokeDamageCalc/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
        wrapped = {
            "fetched_at": time.time(),
            "payload": payload,
        }
        _save_masters(wrapped)
        return payload
    except (requests.RequestException, ValueError, TypeError, OSError) as exc:
        logging.debug("get_masters fallback to cache: %s", exc)
        return (cached or {}).get("payload", {}) or {}


def get_ability_name_by_id(ability_id: int | str) -> str:
    try:
        key = str(int(ability_id))
    except (TypeError, ValueError):
        return ""

    masters = get_masters()
    tokusei = masters.get("tokusei")
    if isinstance(tokusei, dict):
        value = tokusei.get(key)
        if isinstance(value, str):
            return value.strip()
    return ""


def get_cached_asset_bytes(url: str) -> bytes | None:
    url = (url or "").strip()
    if not url:
        return None

    suffix = Path(url.split("?", 1)[0]).suffix or ".bin"
    cache_name = "{}{}".format(
        hashlib.sha1(url.encode("utf-8")).hexdigest(),
        suffix,
    )
    cache_path = _asset_dir() / cache_name
    if cache_path.exists():
        try:
            return cache_path.read_bytes()
        except OSError:
            pass

    try:
        response = requests.get(
            url,
            timeout=_TIMEOUT,
            headers={"User-Agent": "PokeDamageCalc/1.0"},
        )
        response.raise_for_status()
        data = response.content
        cache_path.write_bytes(data)
        return data
    except (requests.RequestException, OSError) as exc:
        logging.debug("get_cached_asset_bytes failed: %s", exc)
        if cache_path.exists():
            try:
                return cache_path.read_bytes()
            except OSError:
                return None
        return None


def get_pokemon_detail(dex_no: str, force_refresh: bool = False) -> dict[str, Any]:
    dex_no = (dex_no or "").strip()
    if not dex_no:
        return {}

    path = _detail_path(dex_no)
    if not force_refresh and path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = float(cached.get("fetched_at") or 0)
            if time.time() - fetched_at < _CACHE_TTL_SECONDS:
                return cached.get("pokemon", {}) or {}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    url = _BASE_URL + "/zukan-api/api/detail/{}".format(dex_no)
    try:
        response = requests.get(
            url,
            timeout=_TIMEOUT,
            headers={"User-Agent": "PokeDamageCalc/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
        wrapped = {
            "fetched_at": time.time(),
            "pokemon": payload.get("pokemon", {}) or {},
        }
        path.write_text(json.dumps(wrapped, ensure_ascii=False), encoding="utf-8")
        return wrapped["pokemon"]
    except (requests.RequestException, ValueError, TypeError, OSError) as exc:
        logging.debug("get_pokemon_detail fallback to cache: %s", exc)
        if path.exists():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                return cached.get("pokemon", {}) or {}
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                return {}
        return {}
