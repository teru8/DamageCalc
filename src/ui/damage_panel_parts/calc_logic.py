"""Extracted methods from damage_panel.py."""
from __future__ import annotations

import copy
import dataclasses
import math

from src.calc.calc_inputs import (
    AttackerCalcConfig,
    DefenderCalcConfig,
    DamageCalcInputs,
    FieldCalcConfig,
)
from src.models import MoveInfo, PokemonInstance
from src.ui.damage_panel_math import nature_mult_from_name as _nature_mult_from_name

def recalculate(self) -> None:
    if not hasattr(self, "_move_sections"):
        return
    self._sync_attacker_ability_support_buttons()
    self._sync_defender_ability_support_buttons()
    if self._atk is None:
        for sec in self._move_sections:
            sec.setup_move(None)
        self._refresh_defender_card()
        self._show_opp_moves_only()
        return
    self._refresh_defender_card()
    self._calc_moves()


def collect_calc_inputs(self) -> DamageCalcInputs:
    """Read all widget states and return a UI-agnostic DamageCalcInputs.

    This is the only function in the calc pipeline that touches PyQt5 widgets.
    Everything downstream can work purely from the returned dataclass.
    """
    from src.calc.calc_utils import is_grounded

    def _btn(name: str, default: bool = False) -> bool:
        btn = getattr(self, name, None)
        if btn is None:
            return default
        return bool(btn.isVisible() and btn.isChecked())

    atk = self._atk

    # ── attacker ─────────────────────────────────────────────────────────
    atk_config = AttackerCalcConfig(
        pokemon=atk,
        ev_hp=self._atk_panel.ev_hp_pts(),
        ev_attack=self._atk_panel.ev_attack_pts(),
        ev_defense=self._atk_panel.ev_defense_pts(),
        ev_sp_attack=self._atk_panel.ev_sp_attack_pts(),
        ev_sp_defense=self._atk_panel.ev_sp_defense_pts(),
        ev_speed=self._atk_panel.ev_speed_pts(),
        nature=self._atk_panel.panel_nature(),
        ac_rank=self._atk_panel.ac_rank(),
        bd_rank=self._atk_panel.bd_rank(),
        tera=self._atk_panel.terastal_type(),
        is_burned=self._burn_btn.isChecked(),
        is_toxic_boosted=_btn("_toxic_boost_btn"),
        is_pinch=any(_btn(n) for n in (
            "_overgrow_btn", "_blaze_btn", "_torrent_btn", "_swarm_btn"
        )),
        flare_boost_active=_btn("_flare_boost_btn"),
        guts_active=_btn("_guts_btn"),
        ability_on=(
            _btn("_stakeout_btn") or
            _btn("_flash_fire_boost_btn") or
            _btn("_analytic_btn")
        ),
        stakeout_active=_btn("_stakeout_btn"),
        flash_fire_active=_btn("_flash_fire_boost_btn"),
        protosynthesis_active=_btn("_protosynthesis_btn"),
        quark_drive_active=_btn("_quark_drive_btn"),
        analytic_active=_btn("_analytic_btn"),
        allies_fainted=int(self._supreme_combo.currentData() or 0)
            if self._supreme_combo.isVisible() else 0,
        rivalry_state=str(self._rivalry_combo.currentData() or "none")
            if self._rivalry_combo.isVisible() else "none",
        multiscale_intact=_btn("_atk_multiscale_btn", default=True),
        shadow_shield_intact=_btn("_atk_shadow_shield_btn", default=True),
        tera_shell_intact=_btn("_atk_tera_shell_btn", default=True),
    )

    # ── defender ─────────────────────────────────────────────────────────
    has_def = hasattr(self, "_def_panel")
    def_config = DefenderCalcConfig(
        pokemon=self._def_custom,
        species_name=self._def_species_name or "",
        ev_hp=self._def_panel.ev_hp_pts() if has_def else 0,
        ev_attack=self._def_panel.ev_attack_pts() if has_def else 0,
        ev_defense=self._def_panel.ev_defense_pts() if has_def else 0,
        ev_sp_attack=self._def_panel.ev_sp_attack_pts() if has_def else 0,
        ev_sp_defense=self._def_panel.ev_sp_defense_pts() if has_def else 0,
        ev_speed=self._def_panel.ev_speed_pts() if has_def else 0,
        nature=self._def_panel.panel_nature() if has_def else "まじめ",
        ac_rank=self._def_panel.ac_rank() if has_def else 0,
        bd_rank=self._def_panel.bd_rank() if has_def else 0,
        hp_percent=self._def_panel.current_hp_percent() if has_def else 100.0,
        use_sp_defense=self._def_panel.use_sp_defense() if has_def else False,
        tera=self._def_panel.terastal_type() if has_def else "",
        multiscale_intact=_btn("_opp_multiscale_btn", default=True),
        shadow_shield_intact=_btn("_opp_shadow_shield_btn", default=True),
        tera_shell_intact=_btn("_opp_tera_shell_btn", default=True),
        disguise_intact=(
            has_def and self._def_panel.disguise_intact()
        ),
    )

    # ── field ─────────────────────────────────────────────────────────────
    field_config = FieldCalcConfig(
        weather=self._weather_key(),
        terrain=self._terrain_key(),
        is_double=getattr(self, "_battle_format", "single") == "double",
        is_crit=self._crit_btn.isChecked(),
        has_reflect=self._reflect_btn.isChecked(),
        has_light_screen=self._lightscreen_btn.isChecked(),
        helping=self._helping_btn.isChecked(),
        steel_spirit=self._steel_spirit_btn.isChecked(),
        charged=self._charge_btn.isChecked(),
        friend_guard=self._friend_guard_btn.isChecked(),
        tailwind=self._tailwind_btn.isChecked(),
        fairy_aura=(
            self._fairy_aura_btn.isChecked() or
            self._opp_fairy_aura_btn.isChecked()
        ),
        dark_aura=(
            self._dark_aura_btn.isChecked() or
            self._opp_dark_aura_btn.isChecked()
        ),
        gravity=self._gravity_btn.isChecked(),
        opp_helping=self._opp_helping_btn.isChecked(),
        opp_steel_spirit=self._opp_steel_spirit_btn.isChecked(),
        opp_charged=self._opp_charge_btn.isChecked(),
        self_reflect=self._self_reflect_btn.isChecked(),
        self_light_screen=self._self_lightscreen_btn.isChecked(),
        self_friend_guard=self._self_friend_guard_btn.isChecked(),
        self_tailwind=self._self_tailwind_btn.isChecked(),
    )

    return DamageCalcInputs(
        attacker=atk_config,
        defender=def_config,
        field=field_config,
        show_bulk_rows=self._show_bulk_rows,
    )


def _calc_moves(self) -> None:
    from src.calc.calc_utils import (
        calc_stat, get_nature_mult,
        get_damage_modifier_notes, move_type_effectiveness,
        resolve_effective_move_category, resolve_effective_move_type,
        is_grounded, normalize_move_name,
    )
    from src.calc.smogon_bridge import (
        SmogonBridge, pokemon_to_attacker_dict, defender_scenario_dict, attacker_scenario_dict,
        pokemon_to_defender_dict,
        move_to_dict as smogon_move_to_dict,
        TYPE_TO_SMOGON,
        smogon_mega_species,
        _ability_name_to_en,
    )
    from src.data.item_catalog import get_item_name_en
    from src.data.item_dictionary import ITEM_FALLBACK_JA_TO_EN
    from src.data.database import get_move_by_name_ja
    from src.constants import BEST_DEF_NATURE_FOR, nature_ja_to_en
    from src.calc.damage_calculator import DamageCalculator

    inputs = self.collect_calc_inputs()
    atk = copy.copy(self._atk)

    # Apply attacker EV overrides for all stats
    ev_pts_h_atk = inputs.attacker.ev_hp
    ev_pts_a = inputs.attacker.ev_attack
    ev_pts_b_atk = inputs.attacker.ev_defense
    ev_pts_c = inputs.attacker.ev_sp_attack
    ev_pts_d_atk = inputs.attacker.ev_sp_defense
    ev_pts_s_atk = inputs.attacker.ev_speed
    atk_nature = inputs.attacker.nature
    atk_ac_rank = inputs.attacker.ac_rank
    atk_bd_rank = inputs.attacker.bd_rank
    rank = atk_ac_rank
    tera = inputs.attacker.tera

    # Re-calc all stats from species if available
    species = self._resolve_species_info(atk, atk.name_ja)
    if species:
        hp_iv = atk.iv_hp if atk.iv_hp > 0 else 31
        atk.hp = calc_stat(species.base_hp, hp_iv, ev_pts_h_atk * 8, is_hp=True)
        atk.max_hp = atk.hp
        atk.attack = calc_stat(species.base_attack, 31, ev_pts_a * 8,
                               nature_mult=_nature_mult_from_name(atk_nature, "attack"))
        atk.defense = calc_stat(species.base_defense, 31, ev_pts_b_atk * 8,
                                nature_mult=_nature_mult_from_name(atk_nature, "defense"))
        atk.sp_attack = calc_stat(species.base_sp_attack, 31, ev_pts_c * 8,
                                  nature_mult=_nature_mult_from_name(atk_nature, "sp_attack"))
        atk.sp_defense = calc_stat(species.base_sp_defense, 31, ev_pts_d_atk * 8,
                                   nature_mult=_nature_mult_from_name(atk_nature, "sp_defense"))
        atk.speed = calc_stat(species.base_speed, 31, ev_pts_s_atk * 8,
                              nature_mult=_nature_mult_from_name(atk_nature, "speed"))
        if atk.weight_kg <= 0:
            atk.weight_kg = species.weight_kg
        if atk.hp <= 0 and atk.max_hp > 0:
            atk.hp = atk.max_hp
    self._atk_panel.update_stat_display(atk)

    if inputs.attacker.is_burned:
        atk.status = "burn"
    if inputs.attacker.is_toxic_boosted:
        atk.status = "poison"

    pinch_trigger = inputs.attacker.is_pinch
    if pinch_trigger:
        hp_max = atk.max_hp if atk.max_hp > 0 else atk.hp
        if hp_max > 0:
            atk.max_hp = hp_max
            pinch_hp = max(1, hp_max // 3)
            if atk.current_hp > 0:
                atk.current_hp = min(atk.current_hp, pinch_hp)
            else:
                atk.current_hp = pinch_hp

    atk.terastal_type = tera

    # Defender scenarios
    def_types_override: list[str] = []
    def_tera = inputs.defender.tera
    if def_tera:
        def_types_override = [def_tera]

    _calc = DamageCalculator(inputs)
    runtime = _calc.build_runtime_context(
        attacker_ability=atk.ability,
        defender_ability=self._def_custom.ability if self._def_custom else "",
    )
    atk_weather = runtime.atk_weather
    opp_weather = runtime.opp_weather
    terrain = runtime.terrain
    is_crit = runtime.is_crit
    helping = runtime.helping
    steel_spirit = runtime.steel_spirit
    charged = runtime.charged
    opp_helping = runtime.opp_helping
    opp_steel_spirit = runtime.opp_steel_spirit
    opp_charged = runtime.opp_charged
    reflect = runtime.reflect
    lightscreen = runtime.lightscreen
    fairy_aura = runtime.fairy_aura
    dark_aura = runtime.dark_aura
    self_reflect = runtime.self_reflect
    self_lightscreen = runtime.self_lightscreen
    friend_guard = runtime.friend_guard
    self_friend_guard = runtime.self_friend_guard
    tailwind = runtime.tailwind
    self_tailwind = runtime.self_tailwind
    gravity = runtime.gravity
    def_ac_rank = runtime.def_ac_rank
    def_bd_rank = runtime.def_bd_rank
    def_rank = runtime.def_rank
    hp_percent = runtime.hp_percent
    def_use_sp = runtime.def_use_sp
    def_ev_pts_h = runtime.def_ev_pts_h
    def_ev_pts_a = runtime.def_ev_pts_a
    def_ev_pts_b = runtime.def_ev_pts_b
    def_ev_pts_c = runtime.def_ev_pts_c
    def_ev_pts_d = runtime.def_ev_pts_d
    def_ev_pts_s = runtime.def_ev_pts_s
    def_nature = runtime.def_nature
    is_double = runtime.is_double
    stakeout_active = runtime.stakeout_active
    flash_fire_active = runtime.flash_fire_active
    protosynthesis_active = runtime.protosynthesis_active
    quark_drive_active = runtime.quark_drive_active
    analytic_active = runtime.analytic_active
    flare_boost_active = inputs.attacker.flare_boost_active
    guts_active = inputs.attacker.guts_active
    if flare_boost_active:
        atk.status = "burn"
    if guts_active and not atk.status:
        atk.status = "par"
    ability_on = runtime.ability_on
    allies_fainted = runtime.allies_fainted
    rivalry_state = runtime.rivalry_state
    attacker_gender = runtime.attacker_gender
    defender_gender = runtime.defender_gender

    shared = dict(
        weather=atk_weather, terrain=terrain, is_critical=is_crit,
        has_reflect=reflect, has_light_screen=lightscreen,
        helping_hand=helping, steel_spirit=steel_spirit, charged=charged,
        fairy_aura=fairy_aura, dark_aura=dark_aura,
        terastal_type=tera,
        atk_rank=atk_ac_rank,
        def_rank=atk_bd_rank,
        attacker_def_rank=atk_bd_rank,
        defender_atk_rank=def_ac_rank,
        is_double_battle=is_double,
        allies_fainted=allies_fainted,
        rivalry_state=rivalry_state,
        stakeout_active=stakeout_active,
        flash_fire_active=flash_fire_active,
        protosynthesis_active=protosynthesis_active,
        quark_drive_active=quark_drive_active,
        attacker_moves_after_target=True if analytic_active else None,
        friend_guard=friend_guard,
        gravity=gravity,
        is_grounded=is_grounded(atk),
    )

    # ── smogon bridge: build attacker dict and field dict once ────────
    _bridge = SmogonBridge.get()
    _atk_d = _calc.build_attacker_dict(atk, runtime)
    _field_d, _field_d_rev = _calc.build_field_dicts(runtime)

    slot_to_move: dict[int, tuple[str, MoveInfo | None]] = {}
    for slot in range(4):
        move_name = atk.moves[slot] if slot < len(atk.moves) else ""
        move_info: MoveInfo | None = None
        if move_name:
            move_info = self._move_cache.get(move_name) or get_move_by_name_ja(move_name)
            if move_info:
                self._move_cache[move_name] = move_info
        slot_to_move[slot] = (move_name, move_info)

    self._display_to_move_slot = [0, 1, 2, 3]
    self._refresh_defender_card(atk)

    for disp_slot, sec in enumerate(self._move_sections):
        src_slot = self._display_to_move_slot[disp_slot] if disp_slot < len(self._display_to_move_slot) else disp_slot
        move_name, move = slot_to_move.get(src_slot, ("", None))
        effective_move: MoveInfo | None = None
        if not move_name or not move:
            sec.setup_move(None)
        else:
            # Apply type override to the move
            effective_move = move
            pre_resolve_type = effective_move.type_name
            resolved_type = resolve_effective_move_type(atk, effective_move, tera, atk_weather)
            resolved_power = effective_move.power
            if normalize_move_name(effective_move.name_ja) == normalize_move_name("ウェザーボール") and resolved_type != "normal":
                resolved_power = 100
            resolved_category = resolve_effective_move_category(
                atk, effective_move, atk_rank=rank, terastal_type=tera,
            )
            if (resolved_type != effective_move.type_name
                    or resolved_category != effective_move.category
                    or resolved_power != effective_move.power):
                effective_move = dataclasses.replace(
                    effective_move, type_name=resolved_type,
                    category=resolved_category, power=resolved_power,
                )
            sec.setup_move(effective_move)

        if effective_move is None:
            continue

        if effective_move.category == "status":
            sec.set_modifier_notes([])
            sec.update_results(None, (0, 0, 1), (0, 0, 1), show_bulk_rows=self._show_bulk_rows)
            continue

        pow_override = sec.power_override()
        move_shared = dict(**shared, power_override=pow_override)

        is_phys = effective_move.category == "physical" or effective_move.name_ja in (
            "サイコショック", "サイコブレイク", "しんぴのつるぎ"
        )
        best_nat = BEST_DEF_NATURE_FOR["defense" if is_phys else "sp_defense"]
        opp_species = self._resolve_species_info(self._def_custom, self._def_species_name)

        def _build_def(hp_ev: int, bd_ev: int, nat: str) -> PokemonInstance:
            d = copy.copy(self._def_custom) if self._def_custom else PokemonInstance()
            d.ability = (self._def_custom.ability if self._def_custom else "")
            if opp_species:
                d.hp = calc_stat(opp_species.base_hp, 31, hp_ev, is_hp=True)
                if d.attack <= 0:
                    d.attack = calc_stat(
                        opp_species.base_attack, 31, 0,
                        nature_mult=get_nature_mult("まじめ", "attack")
                    )
                if d.sp_attack <= 0:
                    d.sp_attack = calc_stat(
                        opp_species.base_sp_attack, 31, 0,
                        nature_mult=get_nature_mult("まじめ", "sp_attack")
                    )
                d.defense = calc_stat(opp_species.base_defense, 31,
                                     bd_ev if is_phys else 0,
                                     nature_mult=get_nature_mult(nat, "defense"))
                d.sp_defense = calc_stat(opp_species.base_sp_defense, 31,
                                         bd_ev if not is_phys else 0,
                                         nature_mult=get_nature_mult(nat, "sp_defense"))
                if d.speed <= 0:
                    d.speed = calc_stat(
                        opp_species.base_speed, 31, 0,
                        nature_mult=get_nature_mult("まじめ", "speed")
                    )
                d.max_hp = d.hp
                if d.weight_kg <= 0:
                    d.weight_kg = opp_species.weight_kg
            d.types = def_types_override or (d.types or ["normal"])
            return d

        hbd0 = _build_def(0, 0, "まじめ")
        hbd252 = _build_def(252, 252, best_nat)

        # ── smogon bridge: build move dict ────────────────────────────
        hits = sec.hit_count()
        _mv_d = _calc.build_move_dict(
            effective_move, atk, pre_resolve_type, resolved_type,
            is_crit, hits, pow_override, charged,
        )
        _atk_d_for_move = _calc.adjust_attacker_dict_for_move(_atk_d, effective_move, pow_override)

        # ── defender meta for smogon dicts ───────────────────────────
        _raw_species_en = (opp_species.name_en if opp_species
                           else (self._def_custom.name_en if self._def_custom else ""))
        _def_name_ja = (self._def_custom.name_ja if self._def_custom else "") or ""
        species_en = smogon_mega_species(_raw_species_en, _def_name_ja)
        def_ability_ja = self._def_custom.ability if self._def_custom else ""
        def_terastal_active = bool(def_tera)
        def_ability_en = _ability_name_to_en(def_ability_ja, _def_name_ja, def_terastal_active)
        def_item_en = ITEM_FALLBACK_JA_TO_EN.get(
            self._def_custom.item if self._def_custom else "", ""
        )
        if not def_item_en:
            def_item_en = get_item_name_en(self._def_custom.item if self._def_custom else "")
        best_nat_en = nature_ja_to_en(best_nat)

        _def0_d = defender_scenario_dict(
            species_en, ev_hp=0, ev_def=0, ev_spd=0,
            nature_en="Hardy",
            ability_en=def_ability_en, item_en=def_item_en,
            terastal_type=def_tera, def_rank=def_bd_rank, is_physical=is_phys,
            gender=defender_gender,
            apply_both=True,
        )
        _def252_d = defender_scenario_dict(
            species_en, ev_hp=252,
            ev_def=252 if is_phys else 0,
            ev_spd=0 if is_phys else 252,
            nature_en=best_nat_en,
            ability_en=def_ability_en, item_en=def_item_en,
            terastal_type=def_tera, def_rank=def_bd_rank, is_physical=is_phys,
            gender=defender_gender,
            apply_both=True,
        )

        # ── type effectiveness (for berry check + display) ────────────
        disp_types = def_types_override or (
            (self._def_custom.types or ["normal"]) if self._def_custom else ["normal"]
        )
        disp_ability = self._def_custom.ability if self._def_custom else ""
        type_eff = move_type_effectiveness(
            effective_move, effective_move.type_name, disp_types, disp_ability
        )
        sec.set_effectiveness(type_eff)

        # ── bridge call helper ────────────────────────────────────────
        def _is_opp_full_hp_guard_intact(ability_en: str) -> bool:
            guard_map = {
                "Multiscale": "_opp_multiscale_btn",
                "Shadow Shield": "_opp_shadow_shield_btn",
                "Tera Shell": "_opp_tera_shell_btn",
            }
            btn_name = guard_map.get((ability_en or "").strip(), "")
            if not btn_name or not hasattr(self, btn_name):
                return True
            btn = getattr(self, btn_name)
            if not btn.isVisible():
                return True
            return bool(btn.isChecked())

        def _is_my_full_hp_guard_intact(ability_en: str) -> bool:
            guard_map = {
                "Multiscale": "_atk_multiscale_btn",
                "Shadow Shield": "_atk_shadow_shield_btn",
                "Tera Shell": "_atk_tera_shell_btn",
            }
            btn_name = guard_map.get((ability_en or "").strip(), "")
            if not btn_name or not hasattr(self, btn_name):
                return True
            btn = getattr(self, btn_name)
            if not btn.isVisible():
                return True
            return bool(btn.isChecked())

        def _call_bridge(def_d: dict, hp: int) -> tuple[int, int, int, bool]:
            if hp <= 0:
                return (0, 0, 1, False)
            cur_hp = max(1, math.floor(hp * hp_percent / 100.0))
            def_ability_en = str(def_d.get("ability") or "").strip()
            if (
                def_ability_en in ("Multiscale", "Shadow Shield", "Tera Shell")
                and not _is_opp_full_hp_guard_intact(def_ability_en)
                and cur_hp >= hp
            ):
                cur_hp = max(1, hp - 1)
            disguise = bool(
                def_d.get("ability") == "Disguise" and
                hasattr(self, "_def_panel") and
                self._def_panel.disguise_intact() and
                cur_hp >= hp
            )
            if disguise:
                return (0, 0, hp, False)
            d_copy = dict(def_d)
            if cur_hp < hp:
                d_copy["curHP"] = cur_hp
            try:
                self.bridge_payload_logged.emit(
                    "[SmogonReq] {}".format(
                        json.dumps(
                            {
                                "dir": "atk->def",
                                "attacker": _atk_d_for_move,
                                "defender": d_copy,
                                "move": _mv_d,
                                "field": _field_d,
                            },
                            ensure_ascii=False,
                        )
                    )
                )
            except (AttributeError, TypeError, ValueError) as exc:
                import logging
                logging.warning(
                    "bridge payload emit failed (atk->def atk=%r def=%r move=%r): %s",
                    _atk_d_for_move.get("name"), d_copy.get("name"), _mv_d.get("name"),
                    exc, exc_info=True,
                )
            mn, mx, is_error = _bridge.calc(_atk_d_for_move, d_copy, _mv_d, _field_d)
            return (mn, mx, hp or 1, is_error)

        # ── modifier notes (Python calc still used for notes) ─────────
        def _modifier_notes_for(d: PokemonInstance) -> list[str]:
            if d.hp <= 0:
                return []
            cur_hp = max(1, math.floor(d.hp * hp_percent / 100.0))
            disguise = bool(
                d.ability == "ばけのかわ" and
                hasattr(self, "_def_panel") and
                self._def_panel.disguise_intact() and
                cur_hp >= d.hp
            )
            return get_damage_modifier_notes(
                atk, effective_move, d,
                **move_shared,
                defender_is_grounded=is_grounded(d),
            )

        # ── custom defender ───────────────────────────────────────────
        custom_result: tuple[int, int, int, bool] | None = None
        mod_target = hbd0
        if self._def_custom and self._def_custom.hp > 0:
            cd = copy.copy(self._def_custom)
            if opp_species:
                cd.attack = calc_stat(
                    opp_species.base_attack, 31, def_ev_pts_a * 8,
                    nature_mult=_nature_mult_from_name(def_nature, "attack")
                )
                cd.defense = calc_stat(
                    opp_species.base_defense, 31, def_ev_pts_b * 8,
                    nature_mult=_nature_mult_from_name(def_nature, "defense")
                )
                cd.sp_attack = calc_stat(
                    opp_species.base_sp_attack, 31, def_ev_pts_c * 8,
                    nature_mult=_nature_mult_from_name(def_nature, "sp_attack")
                )
                cd.sp_defense = calc_stat(
                    opp_species.base_sp_defense, 31, def_ev_pts_d * 8,
                    nature_mult=_nature_mult_from_name(def_nature, "sp_defense")
                )
                cd.hp = calc_stat(
                    opp_species.base_hp, 31, def_ev_pts_h * 8, is_hp=True
                )
                cd.max_hp = cd.hp
                cd.speed = calc_stat(
                    opp_species.base_speed, 31, def_ev_pts_s * 8,
                    nature_mult=_nature_mult_from_name(def_nature, "speed")
                )
                if cd.weight_kg <= 0:
                    cd.weight_kg = opp_species.weight_kg
            cd.types = def_types_override or (cd.types or ["normal"])
            self._def_panel.update_stat_display(cd)

            # Build smogon dict for custom defender with panel EV/nature override
            _custom_nat = nature_ja_to_en(def_nature)
            _custom_d = pokemon_to_defender_dict(cd, def_bd_rank, is_phys, gender=defender_gender, apply_both=True)
            _custom_d["nature"] = _custom_nat
            _custom_d["evs"]["hp"] = def_ev_pts_h * 8
            _custom_d["evs"]["atk"] = def_ev_pts_a * 8
            _custom_d["evs"]["def"] = def_ev_pts_b * 8
            _custom_d["evs"]["spa"] = def_ev_pts_c * 8
            _custom_d["evs"]["spd"] = def_ev_pts_d * 8
            _custom_d["evs"]["spe"] = def_ev_pts_s * 8
            # Always align tera payload with panel toggle state.
            # When the tera checkbox is OFF, force empty teraType.
            _custom_d["teraType"] = TYPE_TO_SMOGON.get(def_tera, "") if def_tera else ""

            custom_result = _call_bridge(_custom_d, cd.hp)
            mod_target = cd

        sec.set_modifier_notes(_modifier_notes_for(mod_target))

        sec.update_results(
            custom_result,
            _call_bridge(_def0_d, hbd0.hp),
            _call_bridge(_def252_d, hbd252.hp),
            show_bulk_rows=self._show_bulk_rows,
        )

    opp_moves = self._def_custom.moves if self._def_custom else []
    for slot, opp_sec in enumerate(self._opp_move_sections):
        opp_custom_result: tuple[int, int, int, bool] | None = None
        opp_ac0_result: tuple[int, int, int, bool] | None = None
        opp_ac32_result: tuple[int, int, int, bool] | None = None
        opp_move_info: MoveInfo | None = None
        opp_effective_move: MoveInfo | None = None

        opp_move_name = opp_moves[slot] if slot < len(opp_moves) else ""
        if opp_move_name:
            opp_move_info = self._move_cache.get(opp_move_name) or get_move_by_name_ja(opp_move_name)
            if opp_move_info:
                self._move_cache[opp_move_name] = opp_move_info
                opp_effective_move = opp_move_info
                _opp_def_ac_rank_preview = self._def_panel.ac_rank() if hasattr(self, "_def_panel") else 0
                _opp_resolved_type = resolve_effective_move_type(
                    self._def_custom if self._def_custom else PokemonInstance(),
                    opp_move_info,
                    def_tera,
                    opp_weather,
                )
                _opp_resolved_category = resolve_effective_move_category(
                    self._def_custom if self._def_custom else PokemonInstance(),
                    opp_move_info,
                    atk_rank=_opp_def_ac_rank_preview,
                    terastal_type=def_tera,
                )
                _opp_resolved_power = opp_move_info.power
                if (
                    normalize_move_name(opp_move_info.name_ja) == normalize_move_name("ウェザーボール")
                    and _opp_resolved_type != "normal"
                ):
                    _opp_resolved_power = 100
                if (
                    _opp_resolved_type != opp_move_info.type_name
                    or _opp_resolved_category != opp_move_info.category
                    or _opp_resolved_power != opp_move_info.power
                ):
                    opp_effective_move = dataclasses.replace(
                        opp_move_info,
                        type_name=_opp_resolved_type,
                        category=_opp_resolved_category,
                        power=_opp_resolved_power,
                    )

        if self._def_custom and atk.hp > 0 and opp_effective_move and opp_effective_move.category != "status":
            _opp_species = self._resolve_species_info(self._def_custom, self._def_species_name)
            _opp_atk_en = _ability_name_to_en(
                self._def_custom.ability if self._def_custom else "",
                self._def_custom.name_ja if self._def_custom else "",
                bool(def_tera),
            ) or "No Ability"
            _opp_item_en = ITEM_FALLBACK_JA_TO_EN.get(self._def_custom.item or "", "")
            if not _opp_item_en:
                _opp_item_en = get_item_name_en(self._def_custom.item or "")
            _opp_species_en = ""
            if _opp_species:
                _opp_species_en = _opp_species.name_en or ""
            _opp_species_en = smogon_mega_species(
                _opp_species_en or (self._def_custom.name_en or ""),
                self._def_custom.name_ja or "",
            )
            _is_opp_phys = opp_effective_move.category == "physical" or opp_effective_move.name_ja in (
                "サイコショック", "サイコブレイク", "しんぴのつるぎ"
            )
            _opp_best_nat_en = "Adamant" if _is_opp_phys else "Modest"

            # Build self (atk) as defender dict for reverse calc
            _self_def_d = pokemon_to_defender_dict(atk, atk_bd_rank, _is_opp_phys, apply_both=True)

            # Build move dict for opponent's move
            _opp_is_crit = self._opp_crit_btn.isChecked()
            _opp_burn = self._opp_burn_btn.isChecked()
            _opp_pow_override = opp_sec.power_override()
            _opp_hits = opp_sec.hit_count()

            _opp_ability_for_skin = self._def_custom.ability if self._def_custom else ""
            _opp_defender_name_ja = self._def_custom.name_ja if self._def_custom else ""
            _mv_d_opp = _calc.build_opponent_move_dict(
                opp_effective_move,
                opp_move_info,
                _opp_ability_for_skin,
                _opp_defender_name_ja,
                _opp_is_crit,
                _opp_hits,
                _opp_pow_override,
            )

            _self_types = atk.types or ["normal"]
            _self_ability = atk.ability or ""
            _opp_effective_type = opp_effective_move.type_name
            _opp_type_eff = move_type_effectiveness(
                opp_effective_move, _opp_effective_type, _self_types, _self_ability
            )

            def _call_bridge_rev(opp_atk_d: dict) -> tuple[int, int, int, bool]:
                self_hp = atk.hp if atk.hp > 0 else 1
                defender_ability_en = str(_self_def_d.get("ability") or "").strip()
                def_payload = dict(_self_def_d)
                if (
                    defender_ability_en in ("Multiscale", "Shadow Shield", "Tera Shell")
                    and not _is_my_full_hp_guard_intact(defender_ability_en)
                    and self_hp > 1
                ):
                    def_payload["curHP"] = self_hp - 1
                try:
                    self.bridge_payload_logged.emit(
                        "[SmogonReq] {}".format(
                            json.dumps(
                                {
                                    "dir": "def->atk",
                                    "attacker": opp_atk_d,
                                    "defender": def_payload,
                                    "move": _mv_d_opp,
                                    "field": _field_d_rev,
                                },
                                ensure_ascii=False,
                            )
                        )
                    )
                except (AttributeError, TypeError, ValueError) as exc:
                    import logging
                    logging.warning(
                        "bridge payload emit failed (def->atk atk=%r def=%r move=%r): %s",
                        opp_atk_d.get("name"), def_payload.get("name"), _mv_d_opp.get("name"),
                        exc, exc_info=True,
                    )
                mn, mx, is_error = _bridge.calc(opp_atk_d, def_payload, _mv_d_opp, _field_d_rev)
                return (mn, mx, self_hp, is_error)

            _opp_def_ac_rank = self._def_panel.ac_rank() if hasattr(self, "_def_panel") else 0
            _opp_ability_on = any(
                btn.isVisible() and btn.isChecked()
                for btn in list(
                    (self._defender_ability_cond_btns or {}).values()
                ) + list(
                    (self._defender_trigger_cond_btns or {}).values()
                )
            )
            _opp_allies_fainted = int(self._opp_supreme_combo.currentData() or 0) if hasattr(self, "_opp_supreme_combo") and self._opp_supreme_combo.isVisible() else 0
            _opp_stakeout_active = hasattr(self, "_opp_stakeout_btn") and self._opp_stakeout_btn.isVisible() and self._opp_stakeout_btn.isChecked()
            _opp_flash_fire_active = hasattr(self, "_opp_flash_fire_btn") and self._opp_flash_fire_btn.isVisible() and self._opp_flash_fire_btn.isChecked()
            _opp_protosynthesis_active = hasattr(self, "_opp_protosynthesis_btn") and self._opp_protosynthesis_btn.isVisible() and self._opp_protosynthesis_btn.isChecked()
            _opp_quark_drive_active = hasattr(self, "_opp_quark_drive_btn") and self._opp_quark_drive_btn.isVisible() and self._opp_quark_drive_btn.isChecked()
            _opp_analytic_active = hasattr(self, "_opp_analytic_btn") and self._opp_analytic_btn.isVisible() and self._opp_analytic_btn.isChecked()
            _opp_guts_active = hasattr(self, "_opp_guts_btn") and self._opp_guts_btn.isVisible() and self._opp_guts_btn.isChecked()

            # pinch()HP
            _opp_atk_instance = copy.copy(self._def_custom)
            _opp_pinch_trigger = any(
                btn.isVisible() and btn.isChecked()
                for btn in (
                    self._opp_overgrow_btn, self._opp_blaze_btn,
                    self._opp_torrent_btn, self._opp_swarm_btn,
                )
            )
            if _opp_pinch_trigger:
                _opp_hp_max = _opp_atk_instance.max_hp if _opp_atk_instance.max_hp > 0 else _opp_atk_instance.hp
                if _opp_hp_max > 0:
                    _opp_atk_instance.max_hp = _opp_hp_max
                    _opp_pinch_hp = max(1, _opp_hp_max // 3)
                    if _opp_atk_instance.current_hp > 0:
                        _opp_atk_instance.current_hp = min(_opp_atk_instance.current_hp, _opp_pinch_hp)
                    else:
                        _opp_atk_instance.current_hp = _opp_pinch_hp
            _opp_toxic_boost_active = (
                hasattr(self, "_opp_toxic_boost_btn") and
                self._opp_toxic_boost_btn.isVisible() and
                self._opp_toxic_boost_btn.isChecked()
            )
            if _opp_burn:
                _opp_atk_instance.status = "brn"
            elif _opp_guts_active:
                _opp_atk_instance.status = "par"
            elif _opp_toxic_boost_active:
                _opp_atk_instance.status = "psn"

            _opp_custom_atk_d = pokemon_to_attacker_dict(
                _opp_atk_instance,
                atk_rank=_opp_def_ac_rank,
                terastal_type=def_tera,
                ability_on=_opp_ability_on,
                allies_fainted=_opp_allies_fainted,
                apply_both=True,
            )
            if opp_charged:
                _opp_custom_atk_d["volatileStatus"] = "charge"
            opp_custom_result = _call_bridge_rev(_opp_custom_atk_d)

            # AC 0: / EV=0,
            _opp_ac0_atk_d = attacker_scenario_dict(
                _opp_species_en or self._def_custom.name_ja or "Bulbasaur",
                ev_hp=int(_opp_atk_instance.ev_hp or 0),
                ev_atk=0,
                ev_spa=0,
                nature_en="Hardy",
                ability_en=_opp_atk_en,
                item_en=_opp_item_en,
                atk_rank=_opp_def_ac_rank,
                is_physical=_is_opp_phys,
                terastal_type=def_tera,
                allies_fainted=_opp_allies_fainted,
                ability_on=_opp_ability_on,
                gender=defender_gender,
                apply_both=True,
            )
            _opp_ac0_atk_d["status"] = _opp_atk_instance.status or ""
            if _opp_atk_instance.current_hp > 0:
                _opp_ac0_atk_d["curHP"] = int(_opp_atk_instance.current_hp)
            opp_ac0_result = _call_bridge_rev(_opp_ac0_atk_d)

            # AC 32: / EV=252,
            _opp_ac32_atk_d = attacker_scenario_dict(
                _opp_species_en or self._def_custom.name_ja or "Bulbasaur",
                ev_hp=int(_opp_atk_instance.ev_hp or 0),
                ev_atk=252 if _is_opp_phys else 0,
                ev_spa=0 if _is_opp_phys else 252,
                nature_en=_opp_best_nat_en,
                ability_en=_opp_atk_en,
                item_en=_opp_item_en,
                atk_rank=_opp_def_ac_rank,
                is_physical=_is_opp_phys,
                terastal_type=def_tera,
                allies_fainted=_opp_allies_fainted,
                ability_on=_opp_ability_on,
                gender=defender_gender,
                apply_both=True,
            )
            _opp_ac32_atk_d["status"] = _opp_atk_instance.status or ""
            if _opp_atk_instance.current_hp > 0:
                _opp_ac32_atk_d["curHP"] = int(_opp_atk_instance.current_hp)
            opp_ac32_result = _call_bridge_rev(_opp_ac32_atk_d)

        opp_sec.setup_move(opp_effective_move)
        if opp_effective_move is not None:
            _atk_types = atk.types or ["normal"]
            _atk_ability = atk.ability or ""
            _opp_eff = move_type_effectiveness(opp_effective_move, opp_effective_move.type_name, _atk_types, _atk_ability)
            opp_sec.set_effectiveness(_opp_eff)
            if opp_effective_move.category != "status" and self._def_custom and atk.hp > 0:
                _opp_move_shared = dict(
                    weather=opp_weather, terrain=terrain,
                    is_critical=self._opp_crit_btn.isChecked(),
                    has_reflect=self_reflect, has_light_screen=self_lightscreen,
                    helping_hand=opp_helping, steel_spirit=opp_steel_spirit, charged=opp_charged,
                    fairy_aura=fairy_aura, dark_aura=dark_aura,
                    terastal_type=def_tera,
                    atk_rank=self._def_panel.ac_rank() if hasattr(self, "_def_panel") else 0,
                    def_rank=def_bd_rank,
                    defender_def_rank=def_bd_rank,
                    defender_atk_rank=atk_ac_rank,
                    is_double_battle=is_double,
                    defender_speed=atk.speed,
                    defender_weight_kg=atk.weight_kg,
                    allies_fainted=_opp_allies_fainted,
                    stakeout_active=_opp_stakeout_active,
                    flash_fire_active=_opp_flash_fire_active,
                    protosynthesis_active=_opp_protosynthesis_active,
                    quark_drive_active=_opp_quark_drive_active,
                    attacker_moves_after_target=True if _opp_analytic_active else None,
                    friend_guard=self_friend_guard,
                    gravity=gravity,
                    is_grounded=is_grounded(_opp_atk_instance),
                )
                _opp_notes = get_damage_modifier_notes(
                    _opp_atk_instance, opp_effective_move, atk,
                    **_opp_move_shared,
                    defender_is_grounded=is_grounded(atk),
                )
                opp_sec.set_modifier_notes(_opp_notes)
            else:
                opp_sec.set_modifier_notes([])
        else:
            opp_sec.set_modifier_notes([])
        opp_sec.update_results(
            opp_custom_result,
            opp_ac0_result,
            opp_ac32_result,
            show_bulk_rows=self._show_bulk_rows,
        )


