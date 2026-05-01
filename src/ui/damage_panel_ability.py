from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models import PokemonInstance


def sanitize_form_ability(
    pokemon: "PokemonInstance",
    form_name: str,
    form_ability_ja: dict[str, str],
    original_ability: str = "",
) -> None:
    """Ensure ability remains valid after form change.

    This path intentionally avoids network access so form changes stay responsive.
    """
    from src.data import database as db
    from src.ui.pokemon_edit_dialog import _unique

    forced_ability = form_ability_ja.get(form_name, "")
    if forced_ability:
        pokemon.ability = forced_ability
        return

    usage_name = (pokemon.usage_name or pokemon.name_ja or "").strip()
    ranked = _unique(db.get_abilities_by_usage(usage_name) if usage_name else [])
    if pokemon.ability and pokemon.ability in ranked:
        return
    if original_ability and original_ability in ranked:
        pokemon.ability = original_ability
        return
    if ranked:
        pokemon.ability = ranked[0]
        return
    if original_ability:
        pokemon.ability = original_ability
