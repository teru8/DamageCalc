from __future__ import annotations

import re
import requests
import logging

from main import APP_USER_AGENT
from src.constants import POKEAPI_BASE
from src.models import PokemonInstance, SpeciesInfo

_POKEAPI_SPECIES_CACHE_BY_NAME_EN: dict[str, SpeciesInfo | None] = {}
_POKEAPI_SESSION = requests.Session()
_POKEAPI_SESSION.headers["User-Agent"] = APP_USER_AGENT


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
        logging.warning("species lookup failed (name_en=%r name_ja=%r): %s", key, name_ja, exc, exc_info=True)
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


def _resolve_by_name_en(pokemon: PokemonInstance, current: SpeciesInfo | None) -> SpeciesInfo | None:
    """Try to resolve species from pokemon.name_en, including mega name variants."""
    if not pokemon.name_en:
        return None

    if current is None or (current.name_en and current.name_en != pokemon.name_en):
        result = species_from_name_en(pokemon.name_en, pokemon.species_id, pokemon.name_ja)
        if result is not None:
            return result

    if current is not None:
        return None

    normalized = pokemon.name_en.lower()
    candidates: list[str] = []
    if normalized.startswith("mega-"):
        candidates.append(normalized[5:])
    if "-mega-" in normalized:
        candidates.append(normalized.split("-mega-")[0])
    if normalized.endswith("-mega"):
        candidates.append(normalized[:-5])
    for cand in candidates:
        if not cand:
            continue
        result = species_from_name_en(cand, pokemon.species_id, pokemon.name_ja)
        if result is not None:
            return result
    return None


def _resolve_mega_by_name_ja(name_ja: str) -> SpeciesInfo | None:
    """Resolve メガ evolution species from Japanese name."""
    if not name_ja.startswith("メガ"):
        return None
    from src.data.database import get_species_by_name_ja
    from src.calc.smogon_bridge import smogon_mega_species as _smogon_mega
    from src.ui.damage_panel_form_data import FORM_MISSING_MEGA_STATS

    base_name = name_ja[2:]
    base_species = get_species_by_name_ja(base_name)
    if base_species is None and base_name.endswith(("X", "Y", "Ｘ", "Ｙ")):
        base_species = get_species_by_name_ja(base_name[:-1])
    if base_species is None:
        return None

    smogon_name = _smogon_mega(base_species.name_en or "", name_ja)
    fb = FORM_MISSING_MEGA_STATS.get(smogon_name)
    if fb:
        fb_en, fb_t1, fb_t2, fb_hp, fb_atk, fb_def, fb_spa, fb_spd, fb_spe, fb_wt = fb
        return SpeciesInfo(
            species_id=base_species.species_id,
            name_ja=name_ja, name_en=fb_en,
            type1=fb_t1, type2=fb_t2,
            base_hp=fb_hp, base_attack=fb_atk, base_defense=fb_def,
            base_sp_attack=fb_spa, base_sp_defense=fb_spd, base_speed=fb_spe,
            weight_kg=fb_wt,
        )
    return base_species


_FLOETTE_ALIASES = frozenset((
    "フラエッテ(えいえん)", "フラエッテ (えいえん)",
    "フラエッテ(えいえんのはな)", "フラエッテ (えいえんのはな)",
))


def resolve_species(
    pokemon: PokemonInstance | None,
    fallback_name_ja: str = "",
) -> SpeciesInfo | None:
    """Resolve SpeciesInfo for a PokemonInstance using multiple fallback strategies."""
    from src.data.database import get_species_by_id, get_species_by_name_ja

    name_ja = (pokemon.name_ja if pokemon and pokemon.name_ja else "") or fallback_name_ja

    species: SpeciesInfo | None = get_species_by_name_ja(name_ja) if name_ja else None

    if species is None and pokemon and pokemon.species_id:
        species = get_species_by_id(pokemon.species_id)

    if pokemon and pokemon.name_en:
        by_en = _resolve_by_name_en(pokemon, species)
        if by_en is not None:
            species = by_en

    if species is None:
        species = _resolve_mega_by_name_ja(name_ja)

    if species is None and name_ja in _FLOETTE_ALIASES:
        species = get_species_by_name_ja("フラエッテ (えいえんのはな)") or get_species_by_name_ja("フラエッテ")

    if species is None and name_ja:
        base = re.sub(r"\s*[（(].*?[)）]", "", name_ja).strip()
        if base and base != name_ja:
            species = get_species_by_name_ja(base)

    return species
