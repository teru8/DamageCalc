from __future__ import annotations

from dataclasses import dataclass

from src.calc.calc_inputs import DamageCalcInputs
from src.models import MoveInfo, PokemonInstance


@dataclass(frozen=True)
class DamageRuntimeContext:
    atk_weather: str
    opp_weather: str
    terrain: str
    is_crit: bool
    helping: bool
    steel_spirit: bool
    charged: bool
    opp_helping: bool
    opp_steel_spirit: bool
    opp_charged: bool
    reflect: bool
    lightscreen: bool
    fairy_aura: bool
    dark_aura: bool
    self_reflect: bool
    self_lightscreen: bool
    friend_guard: bool
    self_friend_guard: bool
    tailwind: bool
    self_tailwind: bool
    gravity: bool
    def_ac_rank: int
    def_bd_rank: int
    def_rank: int
    hp_percent: float
    def_use_sp: bool
    def_ev_pts_h: int
    def_ev_pts_a: int
    def_ev_pts_b: int
    def_ev_pts_c: int
    def_ev_pts_d: int
    def_ev_pts_s: int
    def_nature: str
    is_double: bool
    stakeout_active: bool
    flash_fire_active: bool
    protosynthesis_active: bool
    quark_drive_active: bool
    analytic_active: bool
    ability_on: bool
    allies_fainted: int
    rivalry_state: str
    attacker_gender: str
    defender_gender: str


class DamageCalculator:
    """Pure service that derives calculation context from DamageCalcInputs."""

    def __init__(self, inputs: DamageCalcInputs) -> None:
        self._inputs = inputs

    @staticmethod
    def _weather_for_attacker(weather_key: str, ability_name: str) -> str:
        ability = (ability_name or "").strip()
        if ability in ("メガソーラー", "Mega Sol"):
            return "sun"
        if weather_key == "none" and ability in ("ひひいろのこどう", "Orichalcum Pulse"):
            return "sun"
        return weather_key

    def build_runtime_context(
        self,
        *,
        attacker_ability: str,
        defender_ability: str,
    ) -> DamageRuntimeContext:
        attacker = self._inputs.attacker
        defender = self._inputs.defender
        field = self._inputs.field

        atk_weather = self._weather_for_attacker(field.weather, attacker_ability)
        opp_weather = self._weather_for_attacker(field.weather, defender_ability)
        terrain = field.terrain
        if terrain == "none" and attacker_ability in ("ハドロンエンジン", "Hadron Engine"):
            terrain = "electric"

        ability_on = (
            (attacker_ability in ("はりこみ", "Stakeout") and attacker.stakeout_active)
            or (attacker_ability in ("もらいび", "Flash Fire") and attacker.flash_fire_active)
            or (attacker_ability in ("アナライズ", "Analytic") and attacker.analytic_active)
        )

        rivalry_state = attacker.rivalry_state
        attacker_gender = ""
        defender_gender = ""
        if rivalry_state == "same":
            attacker_gender = "M"
            defender_gender = "M"
        elif rivalry_state == "opposite":
            attacker_gender = "M"
            defender_gender = "F"
        elif rivalry_state != "none":
            attacker_gender = "N"
            defender_gender = "N"

        return DamageRuntimeContext(
            atk_weather=atk_weather,
            opp_weather=opp_weather,
            terrain=terrain,
            is_crit=field.is_crit,
            helping=field.helping,
            steel_spirit=field.steel_spirit,
            charged=field.charged,
            opp_helping=field.opp_helping,
            opp_steel_spirit=field.opp_steel_spirit,
            opp_charged=field.opp_charged,
            reflect=field.has_reflect,
            lightscreen=field.has_light_screen,
            fairy_aura=field.fairy_aura,
            dark_aura=field.dark_aura,
            self_reflect=field.self_reflect,
            self_lightscreen=field.self_light_screen,
            friend_guard=field.friend_guard,
            self_friend_guard=field.self_friend_guard,
            tailwind=field.tailwind,
            self_tailwind=field.self_tailwind,
            gravity=field.gravity,
            def_ac_rank=defender.ac_rank,
            def_bd_rank=defender.bd_rank,
            def_rank=defender.bd_rank,
            hp_percent=defender.hp_percent,
            def_use_sp=defender.use_sp_defense,
            def_ev_pts_h=defender.ev_hp,
            def_ev_pts_a=defender.ev_attack,
            def_ev_pts_b=defender.ev_defense,
            def_ev_pts_c=defender.ev_sp_attack,
            def_ev_pts_d=defender.ev_sp_defense,
            def_ev_pts_s=defender.ev_speed,
            def_nature=defender.nature,
            is_double=field.is_double,
            stakeout_active=attacker.stakeout_active,
            flash_fire_active=attacker.flash_fire_active,
            protosynthesis_active=attacker.protosynthesis_active,
            quark_drive_active=attacker.quark_drive_active,
            analytic_active=attacker.analytic_active,
            ability_on=ability_on,
            allies_fainted=attacker.allies_fainted,
            rivalry_state=rivalry_state,
            attacker_gender=attacker_gender,
            defender_gender=defender_gender,
        )

    def build_attacker_dict(
        self,
        atk: PokemonInstance,
        runtime: DamageRuntimeContext,
    ) -> dict:
        """Build smogon attacker dict from PokemonInstance + runtime context."""
        from src.calc.smogon_bridge import (
            pokemon_to_attacker_dict,
            ABILITY_JA_TO_EN,
        )
        from src.constants import nature_ja_to_en

        attacker = self._inputs.attacker
        ev_override = {
            "hp": attacker.ev_hp * 8,
            "atk": attacker.ev_attack * 8,
            "def": attacker.ev_defense * 8,
            "spa": attacker.ev_sp_attack * 8,
            "spd": attacker.ev_sp_defense * 8,
            "spe": attacker.ev_speed * 8,
        }
        d = pokemon_to_attacker_dict(
            atk,
            ev_override=ev_override,
            atk_rank=attacker.ac_rank,
            terastal_type=attacker.tera,
            allies_fainted=runtime.allies_fainted,
            gender=runtime.attacker_gender,
            ability_on=runtime.ability_on,
            apply_both=True,
        )
        d["nature"] = nature_ja_to_en(attacker.nature)
        boosts = d.setdefault("boosts", {})
        if attacker.bd_rank != 0:
            boosts["def"] = attacker.bd_rank
            boosts["spd"] = attacker.bd_rank
        if (
            atk.ability in ("こだいかっせい", "Protosynthesis")
            and runtime.protosynthesis_active
            and runtime.atk_weather != "sun"
        ) or (
            atk.ability in ("クォークチャージ", "Quark Drive")
            and runtime.quark_drive_active
            and runtime.terrain != "electric"
        ):
            stat_pairs = [
                ("atk", int(atk.attack or 0)),
                ("def", int(atk.defense or 0)),
                ("spa", int(atk.sp_attack or 0)),
                ("spd", int(atk.sp_defense or 0)),
                ("spe", int(atk.speed or 0)),
            ]
            best = max(stat_pairs, key=lambda kv: kv[1])[0]
            d["boostedStat"] = best
        if atk.ability == "おやこあい" and ABILITY_JA_TO_EN.get(atk.ability, "") != "Parental Bond":
            d["ability"] = "Parental Bond"
        return d

    def build_field_dicts(
        self,
        runtime: DamageRuntimeContext,
    ) -> tuple[dict, dict]:
        """Return (atk→def field dict, def→atk field dict)."""
        from src.calc.smogon_bridge import field_to_dict

        field_d = field_to_dict(
            runtime.atk_weather,
            runtime.terrain,
            runtime.reflect,
            runtime.lightscreen,
            runtime.helping,
            runtime.fairy_aura,
            runtime.dark_aura,
            friend_guard=runtime.friend_guard,
            tailwind=runtime.tailwind,
            gravity=runtime.gravity,
        )
        field_d_rev = field_to_dict(
            runtime.opp_weather,
            runtime.terrain,
            runtime.self_reflect,
            runtime.self_lightscreen,
            runtime.opp_helping,
            runtime.fairy_aura,
            runtime.dark_aura,
            friend_guard=runtime.self_friend_guard,
            tailwind=runtime.self_tailwind,
            gravity=runtime.gravity,
        )
        return field_d, field_d_rev

    @staticmethod
    def build_move_dict(
        effective_move: MoveInfo,
        atk: PokemonInstance,
        pre_resolve_type: str,
        resolved_type: str,
        is_crit: bool,
        hits: int,
        pow_override: int,
        charged: bool,
    ) -> dict:
        """Build smogon move dict, handling WeatherBall and skin-type abilities."""
        from src.calc.smogon_bridge import move_to_dict, TYPE_TO_SMOGON
        from src.calc.calc_utils import normalize_move_name

        weather_ball_active_type = (
            resolved_type
            if normalize_move_name(effective_move.name_ja) == normalize_move_name("ウェザーボール")
            and resolved_type != "normal"
            else ""
        )
        if weather_ball_active_type:
            smogon_type = TYPE_TO_SMOGON.get(weather_ball_active_type, "Normal")
            return {
                "name": "Tackle",
                "isCrit": is_crit,
                "overrides": {"basePower": 100, "type": smogon_type, "category": "Special"},
            }

        bridge_forced_type = ""
        bridge_bp_multiplier = 1.0
        if (
            atk.ability in ("ドラゴンスキン", "Dragonize")
            and pre_resolve_type == "normal"
            and resolved_type == "dragon"
        ):
            bridge_forced_type = "dragon"
            bridge_bp_multiplier = 1.2

        return move_to_dict(
            effective_move,
            is_crit=is_crit,
            hits=hits if hits > 1 else 0,
            bp_override=pow_override,
            charged=charged,
            forced_type=bridge_forced_type,
            bp_multiplier=bridge_bp_multiplier,
        )

    @staticmethod
    def adjust_attacker_dict_for_move(
        atk_d: dict,
        effective_move: MoveInfo,
        pow_override: int,
    ) -> dict:
        """Apply per-move attacker dict overrides (e.g. Facade status clear)."""
        from src.calc.calc_utils import normalize_move_name

        if normalize_move_name(effective_move.name_ja) == normalize_move_name("からげんき") and pow_override > 0:
            atk_d = dict(atk_d)
            atk_d["status"] = ""
        return atk_d
