"""Dataclasses representing the pure inputs to a damage calculation.

These are intentionally UI-agnostic so that tests can construct them
without instantiating any PyQt5 widgets.
"""
from __future__ import annotations

import dataclasses

from src.models import PokemonInstance


@dataclasses.dataclass(frozen=True)
class AttackerCalcConfig:
    """All per-attacker inputs resolved from widget states."""

    pokemon: PokemonInstance
    ev_hp: int = 0
    ev_attack: int = 0
    ev_defense: int = 0
    ev_sp_attack: int = 0
    ev_sp_defense: int = 0
    ev_speed: int = 0
    nature: str = "まじめ"
    ac_rank: int = 0
    bd_rank: int = 0
    tera: str = ""
    # Status / condition flags (resolved from buttons)
    is_burned: bool = False
    is_toxic_boosted: bool = False
    is_pinch: bool = False
    flare_boost_active: bool = False
    guts_active: bool = False
    ability_on: bool = False
    allies_fainted: int = 0
    rivalry_state: str = "none"
    # HP-guard ability intact state
    multiscale_intact: bool = True
    shadow_shield_intact: bool = True
    tera_shell_intact: bool = True


@dataclasses.dataclass(frozen=True)
class DefenderCalcConfig:
    """All per-defender inputs resolved from widget states."""

    pokemon: PokemonInstance | None
    species_name: str = ""
    ev_hp: int = 0
    ev_attack: int = 0
    ev_defense: int = 0
    ev_sp_attack: int = 0
    ev_sp_defense: int = 0
    ev_speed: int = 0
    nature: str = "まじめ"
    ac_rank: int = 0
    bd_rank: int = 0
    hp_percent: float = 100.0
    use_sp_defense: bool = False
    tera: str = ""
    multiscale_intact: bool = True
    shadow_shield_intact: bool = True
    tera_shell_intact: bool = True
    disguise_intact: bool = True


@dataclasses.dataclass(frozen=True)
class FieldCalcConfig:
    """Field / environment conditions."""

    weather: str = "none"
    terrain: str = "none"
    is_double: bool = False
    # Attacker-side screens / boosts
    has_reflect: bool = False
    has_light_screen: bool = False
    helping: bool = False
    steel_spirit: bool = False
    charged: bool = False
    friend_guard: bool = False
    tailwind: bool = False
    fairy_aura: bool = False
    dark_aura: bool = False
    gravity: bool = False
    # Defender-side counters
    opp_helping: bool = False
    opp_steel_spirit: bool = False
    opp_charged: bool = False
    self_reflect: bool = False
    self_light_screen: bool = False
    self_friend_guard: bool = False
    self_tailwind: bool = False


@dataclasses.dataclass(frozen=True)
class DamageCalcInputs:
    """Top-level container for all damage calculation inputs.

    Construct this via ``collect_calc_inputs(panel)`` in UI code,
    or build it directly in tests without any widget dependency.
    """

    attacker: AttackerCalcConfig
    defender: DefenderCalcConfig
    field: FieldCalcConfig
    show_bulk_rows: bool = True
