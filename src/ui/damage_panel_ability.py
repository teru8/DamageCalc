from __future__ import annotations

from typing import TYPE_CHECKING

import requests

from src.constants import POKEAPI_BASE

if TYPE_CHECKING:
    from src.models import PokemonInstance

_POKEAPI_ABILITY_NAMES_BY_POKEMON_EN: dict[str, list[str]] = {}
_POKEAPI_ABILITY_JA_BY_EN: dict[str, str] = {}
_POKEAPI_SESSION = requests.Session()
_POKEAPI_SESSION.headers["User-Agent"] = "DamageCalc/0.1.0-alpha"


def _ability_name_ja_from_name_en(ability_name_en: str) -> str:
    key = (ability_name_en or "").strip().lower()
    if not key:
        return ""
    if key in _POKEAPI_ABILITY_JA_BY_EN:
        return _POKEAPI_ABILITY_JA_BY_EN[key]
    try:
        response = _POKEAPI_SESSION.get("{}/ability/{}".format(POKEAPI_BASE, key), timeout=15)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        _POKEAPI_ABILITY_JA_BY_EN[key] = ""
        return ""

    names = payload.get("names") if isinstance(payload, dict) else []
    ja_name = ""
    if isinstance(names, list):
        for row in names:
            lang = str(((row or {}).get("language") or {}).get("name") or "").strip()
            if lang in ("ja-Hrkt", "ja"):
                ja_name = str((row or {}).get("name") or "").strip()
                break
    _POKEAPI_ABILITY_JA_BY_EN[key] = ja_name
    return ja_name


def _pokeapi_ability_names_for_pokemon(name_en: str) -> list[str]:
    key = (name_en or "").strip().lower()
    if not key:
        return []
    if key in _POKEAPI_ABILITY_NAMES_BY_POKEMON_EN:
        return list(_POKEAPI_ABILITY_NAMES_BY_POKEMON_EN[key])
    try:
        response = _POKEAPI_SESSION.get("{}/pokemon/{}".format(POKEAPI_BASE, key), timeout=15)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        _POKEAPI_ABILITY_NAMES_BY_POKEMON_EN[key] = []
        return []

    names_ja: list[str] = []
    abilities = payload.get("abilities") if isinstance(payload, dict) else []
    if isinstance(abilities, list):
        for row in abilities:
            ability_name_en = str(((row or {}).get("ability") or {}).get("name") or "").strip().lower()
            if not ability_name_en:
                continue
            ja = _ability_name_ja_from_name_en(ability_name_en)
            if ja:
                names_ja.append(ja)

    deduped: list[str] = []
    seen: set[str] = set()
    for name in names_ja:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    _POKEAPI_ABILITY_NAMES_BY_POKEMON_EN[key] = deduped
    return list(deduped)


def sanitize_form_ability(
    pokemon: "PokemonInstance",
    form_name: str,
    form_ability_ja: dict[str, str],
    original_ability: str = "",
) -> None:
    """Ensure ability remains valid after form change."""
    from src.data import database as db
    from src.ui.pokemon_edit_dialog import _unique

    forced_ability = form_ability_ja.get(form_name, "")
    if forced_ability:
        pokemon.ability = forced_ability
        return

    candidates = _unique(_pokeapi_ability_names_for_pokemon(pokemon.name_en or ""))
    if not candidates:
        if original_ability:
            pokemon.ability = original_ability
        return

    if pokemon.ability in candidates:
        return
    if original_ability and original_ability in candidates:
        pokemon.ability = original_ability
        return

    usage_name = (pokemon.usage_name or pokemon.name_ja or "").strip()
    ranked = _unique(db.get_abilities_by_usage(usage_name) if usage_name else [])
    for ability in ranked:
        if ability in candidates:
            pokemon.ability = ability
            return
    pokemon.ability = candidates[0]
