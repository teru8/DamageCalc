from __future__ import annotations

import copy

from src.models import PokemonInstance, SpeciesInfo
from src.ui.damage_panel_ability import sanitize_form_ability
from src.ui.damage_panel_math import nature_mult_from_name
from src.ui.damage_panel_species import species_from_name_en


def apply_form(
    pokemon: PokemonInstance,
    form_name: str,
    original_ability: str,
    form_name_to_group: dict[str, list[str]],
    form_pokeapi_en: dict[str, str],
    form_missing_mega_stats: dict[str, tuple],
    form_ability_ja: dict[str, str],
) -> PokemonInstance:
    """Return a new PokemonInstance with form stats/types/ability applied."""
    from src.calc.damage_calc import calc_stat
    from src.calc.smogon_bridge import smogon_mega_species
    from src.data.database import get_species_by_name_ja

    new_p = copy.deepcopy(pokemon)
    new_p.name_ja = form_name
    group = form_name_to_group.get(form_name)
    new_p.usage_name = group[0] if group else (pokemon.usage_name or pokemon.name_ja)

    en = form_pokeapi_en.get(form_name, "")
    if en:
        species = species_from_name_en(en, name_ja=form_name)
        if species is None and form_name.startswith("メガ"):
            smogon_name = smogon_mega_species(en, form_name)
            fb = form_missing_mega_stats.get(smogon_name)
            if fb:
                fb_en, fb_t1, fb_t2, fb_hp, fb_atk, fb_def, fb_spa, fb_spd, fb_spe, fb_wt = fb
                species = SpeciesInfo(
                    species_id=pokemon.species_id if hasattr(pokemon, "species_id") else 0,
                    name_ja=form_name,
                    name_en=fb_en,
                    type1=fb_t1,
                    type2=fb_t2,
                    base_hp=fb_hp,
                    base_attack=fb_atk,
                    base_defense=fb_def,
                    base_sp_attack=fb_spa,
                    base_sp_defense=fb_spd,
                    base_speed=fb_spe,
                    weight_kg=fb_wt,
                )
    else:
        species = get_species_by_name_ja(form_name)
        if species is None and form_name.startswith("メガ"):
            base_ja = form_name[2:]
            base_species = get_species_by_name_ja(base_ja)
            smogon_name = smogon_mega_species(base_species.name_en or "" if base_species else "", form_name)
            fb = form_missing_mega_stats.get(smogon_name)
            if fb:
                fb_en, fb_t1, fb_t2, fb_hp, fb_atk, fb_def, fb_spa, fb_spd, fb_spe, fb_wt = fb
                species = SpeciesInfo(
                    species_id=pokemon.species_id if hasattr(pokemon, "species_id") else 0,
                    name_ja=form_name,
                    name_en=fb_en,
                    type1=fb_t1,
                    type2=fb_t2,
                    base_hp=fb_hp,
                    base_attack=fb_atk,
                    base_defense=fb_def,
                    base_sp_attack=fb_spa,
                    base_sp_defense=fb_spd,
                    base_speed=fb_spe,
                    weight_kg=fb_wt,
                )

    if species:
        new_p.name_en = species.name_en or new_p.name_en
        new_p.types = [t for t in [species.type1, species.type2] if t]
        new_p.weight_kg = species.weight_kg
        lv = new_p.level or 50
        nat = new_p.nature or ""
        new_p.hp = calc_stat(species.base_hp, 31, new_p.ev_hp or 0, level=lv, is_hp=True)
        new_p.attack = calc_stat(
            species.base_attack, 31, new_p.ev_attack or 0, level=lv,
            nature_mult=nature_mult_from_name(nat, "attack"),
        )
        new_p.defense = calc_stat(
            species.base_defense, 31, new_p.ev_defense or 0, level=lv,
            nature_mult=nature_mult_from_name(nat, "defense"),
        )
        new_p.sp_attack = calc_stat(
            species.base_sp_attack, 31, new_p.ev_sp_attack or 0, level=lv,
            nature_mult=nature_mult_from_name(nat, "sp_attack"),
        )
        new_p.sp_defense = calc_stat(
            species.base_sp_defense, 31, new_p.ev_sp_defense or 0, level=lv,
            nature_mult=nature_mult_from_name(nat, "sp_defense"),
        )
        new_p.speed = calc_stat(
            species.base_speed, 31, new_p.ev_speed or 0, level=lv,
            nature_mult=nature_mult_from_name(nat, "speed"),
        )
        new_p.max_hp = new_p.hp
        new_p.current_hp = new_p.hp

    sanitize_form_ability(
        new_p,
        form_name,
        form_ability_ja,
        original_ability=original_ability,
    )
    return new_p
