from __future__ import annotations

import requests
import logging

from src.constants import POKEAPI_BASE
from src.models import SpeciesInfo

_POKEAPI_SPECIES_CACHE_BY_NAME_EN: dict[str, SpeciesInfo | None] = {}
_POKEAPI_SESSION = requests.Session()
_POKEAPI_SESSION.headers["User-Agent"] = "DamageCalc/0.1.1-alpha"


def species_from_name_en(name_en: str, species_id: int = 0, name_ja: str = "") -> SpeciesInfo | None:
    key = (name_en or "").strip().lower()
    if not key:
        return None
    if key in _POKEAPI_SPECIES_CACHE_BY_NAME_EN:
        return _POKEAPI_SPECIES_CACHE_BY_NAME_EN[key]
    try:
        response = _POKEAPI_SESSION.get("{}/pokemon/{}".format(POKEAPI_BASE, key), timeout=15)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            _POKEAPI_SPECIES_CACHE_BY_NAME_EN[key] = None
            return None
    except (requests.RequestException, TypeError, ValueError) as exc:
        logging.warning("species lookup failed: %s", exc, exc_info=True)
        _POKEAPI_SPECIES_CACHE_BY_NAME_EN[key] = None
        return None

    type_rows = payload.get("types")
    type_names: list[str] = []
    if isinstance(type_rows, list):
        for row in sorted(type_rows, key=lambda x: int((x or {}).get("slot") or 99)):
            type_name = str(((row or {}).get("type") or {}).get("name") or "").strip()
            if type_name:
                type_names.append(type_name)

    stats_map: dict[str, int] = {}
    for row in payload.get("stats") or []:
        stat_name = str(((row or {}).get("stat") or {}).get("name") or "").strip()
        if not stat_name:
            continue
        try:
            stats_map[stat_name] = int(row.get("base_stat") or 0)
        except (TypeError, ValueError):
            stats_map[stat_name] = 0

    resolved = SpeciesInfo(
        species_id=species_id or 0,
        name_ja=name_ja or key,
        name_en=key,
        type1=type_names[0] if len(type_names) >= 1 else "normal",
        type2=type_names[1] if len(type_names) >= 2 else "",
        base_hp=stats_map.get("hp", 0),
        base_attack=stats_map.get("attack", 0),
        base_defense=stats_map.get("defense", 0),
        base_sp_attack=stats_map.get("special-attack", 0),
        base_sp_defense=stats_map.get("special-defense", 0),
        base_speed=stats_map.get("speed", 0),
        weight_kg=float(payload.get("weight") or 0) / 10.0,
    )
    _POKEAPI_SPECIES_CACHE_BY_NAME_EN[key] = resolved
    return resolved
