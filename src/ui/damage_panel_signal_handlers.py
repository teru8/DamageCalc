"""Extracted methods from damage_panel.py."""
from __future__ import annotations


def _bootstrap() -> None:
    from src.ui import damage_panel as _dp
    globals().update(_dp.__dict__)

def _on_party_slot_context_menu(self, side: str, idx: int, global_pos) -> None:
    _bootstrap()
    from PyQt5.QtWidgets import QMenu, QAction

    party = self._my_party if side == "my" else self._opp_party

    menu = QMenu(self)

    if idx < len(party) and party[idx] is not None:
        act_change = QAction("変更", menu)
        act_change.triggered.connect(lambda: self._edit_party_slot(side, idx))
        menu.addAction(act_change)

        act_save = QAction("保存", menu)
        act_save.triggered.connect(lambda: self._save_party_slot_to_db(side, idx))
        menu.addAction(act_save)
    else:
        act_add = QAction("新規登録", menu)
        act_add.triggered.connect(lambda: self._add_party_slot(side, idx))
        menu.addAction(act_add)

    menu.exec_(global_pos)


def _edit_party_slot(self, side: str, idx: int) -> None:
    _bootstrap()
    party = self._my_party if side == "my" else self._opp_party
    if idx >= len(party) or party[idx] is None:
        return

    dlg = open_pokemon_edit_dialog(None, self, save_to_db=False)
    if not dlg.exec_():
        if dlg.box_select_requested():
            QTimer.singleShot(0, lambda: self._box_select_into_slot(side, idx))
        return

    updated = dlg.get_pokemon()
    if not updated:
        return

    party[idx] = copy.deepcopy(updated)

    # , atk/def (_persist_party_member_edits )
    if self._party_source == side:
        self._atk_party_side = side
        self._atk_party_idx = idx
        self._atk = copy.deepcopy(updated)
        self._atk_panel.set_pokemon(self._atk)
        self.attacker_changed.emit(self._atk)
    else:
        self._def_party_side = side
        self._def_party_idx = idx
        self._def_custom = copy.deepcopy(updated)
        self._def_species_name = self._def_custom.name_ja or ""
        self._def_panel.set_pokemon(self._def_custom)
        self.defender_changed.emit(self._def_custom)

    self.registry_maybe_changed.emit()
    self._refresh_party_slots()
    self._refresh_defender_card()
    self.recalculate()


def _save_party_slot_to_db(self, side: str, idx: int) -> None:
    _bootstrap()
    from src.data import database as db

    party = self._my_party if side == "my" else self._opp_party
    if idx >= len(party) or party[idx] is None:
        return

    pokemon = party[idx]
    pokemon.db_id = db.save_pokemon(pokemon)
    self.registry_maybe_changed.emit()


def _add_party_slot(self, side: str, idx: int) -> None:
    _bootstrap()
    dlg = open_pokemon_edit_dialog(None, self, save_to_db=False)
    if not dlg.exec_():
        if dlg.box_select_requested():
            QTimer.singleShot(0, lambda: self._box_select_into_slot(side, idx))
        return
    new_pokemon = dlg.get_pokemon()
    if not new_pokemon:
        return

    party = self._my_party if side == "my" else self._opp_party
    while len(party) <= idx:
        party.append(None)
    party[idx] = copy.deepcopy(new_pokemon)
    if side == "my":
        self._on_my_party_slot_clicked(idx)
    else:
        self._on_opp_party_slot_clicked(idx)


def _on_atk_panel_changed(self) -> None:
    _bootstrap()
    self._persist_party_member_edits()
    self._refresh_party_slots()
    self.recalculate()


def _on_def_panel_changed(self) -> None:
    _bootstrap()
    self._persist_party_member_edits()
    self._refresh_party_slots()
    self.recalculate()


def _edit_attacker(self) -> None:
    _bootstrap()
    dlg = open_pokemon_edit_dialog(self._atk, self, save_to_db=False)
    if dlg.exec_():
        updated = dlg.get_pokemon()
        if updated:
            self._atk = copy.deepcopy(updated)
            if self._atk_party_side is not None and self._atk_party_idx is not None:
                party = self._my_party if self._atk_party_side == "my" else self._opp_party
                if 0 <= self._atk_party_idx < len(party):
                    party[self._atk_party_idx] = copy.deepcopy(updated)
            self._atk_panel.set_pokemon(self._atk)
            self.registry_maybe_changed.emit()
            self._refresh_party_slots()
            self.attacker_changed.emit(self._atk)
            self.recalculate()
    elif dlg.box_select_requested():
        QTimer.singleShot(0, self._change_attacker)


def _new_attacker(self) -> None:
    _bootstrap()
    dlg = open_pokemon_edit_dialog(None, self, save_to_db=False)
    if dlg.exec_():
        updated = dlg.get_pokemon()
        if updated:
            self._atk = copy.deepcopy(updated)
            self._atk_party_side = None
            self._atk_party_idx = None
            self._atk_panel.set_pokemon(self._atk)
            self.registry_maybe_changed.emit()
            self._refresh_party_slots()
            self.attacker_changed.emit(self._atk)
            self.recalculate()


def _clear_attacker(self) -> None:
    _bootstrap()
    self._atk = None
    self._atk_party_side = None
    self._atk_party_idx = None
    self._atk_panel.set_pokemon(None)
    self._refresh_party_slots()
    self.attacker_changed.emit(None)
    self.recalculate()


def _change_attacker(self) -> None:
    _bootstrap()
    from src.ui.pokemon_edit_dialog import MyBoxSelectDialog
    dlg = MyBoxSelectDialog("攻撃側PT", self)
    if not dlg.exec_():
        return
    selected_pokemon = dlg.selected_pokemon()
    if selected_pokemon:
        self._atk = copy.deepcopy(selected_pokemon)
        self._atk_party_side = None
        self._atk_party_idx = None
        self._atk_panel.set_pokemon(self._atk)
        self._refresh_party_slots()
        self.attacker_changed.emit(self._atk)
        self.recalculate()


def _edit_defender(self) -> None:
    _bootstrap()
    dlg = open_pokemon_edit_dialog(self._def_custom, self, save_to_db=False)
    if dlg.exec_():
        updated = dlg.get_pokemon()
        if updated:
            self._def_custom = copy.deepcopy(updated)
            self._def_species_name = updated.name_ja or ""
            if self._def_party_side is not None and self._def_party_idx is not None:
                party = self._my_party if self._def_party_side == "my" else self._opp_party
                while len(party) <= self._def_party_idx:
                    party.append(None)
                party[self._def_party_idx] = copy.deepcopy(self._def_custom)
            else:
                if self._opp_party:
                    self._opp_party[0] = copy.deepcopy(self._def_custom)
                else:
                    self._opp_party = [copy.deepcopy(self._def_custom)]
                self._def_party_side = "opp"
                self._def_party_idx = 0
            self._def_panel.set_pokemon(self._def_custom)
            self.registry_maybe_changed.emit()
            self._refresh_party_slots()
            self.defender_changed.emit(self._def_custom)
            self.recalculate()
    elif dlg.box_select_requested():
        QTimer.singleShot(0, self._change_defender)


def _new_defender(self) -> None:
    _bootstrap()
    dlg = open_pokemon_edit_dialog(None, self, save_to_db=False)
    if dlg.exec_():
        updated = dlg.get_pokemon()
        if updated:
            self._def_custom = copy.deepcopy(updated)
            self._def_species_name = updated.name_ja or ""
            if self._opp_party:
                self._opp_party[0] = copy.deepcopy(self._def_custom)
            else:
                self._opp_party = [copy.deepcopy(self._def_custom)]
            self._def_party_side = "opp"
            self._def_party_idx = 0
            self._def_panel.set_pokemon(self._def_custom)
            self.registry_maybe_changed.emit()
            self._refresh_party_slots()
            self.defender_changed.emit(self._def_custom)
            self.recalculate()


def _clear_defender(self) -> None:
    _bootstrap()
    self._def_custom = None
    self._def_species_name = ""
    self._def_party_side = None
    self._def_party_idx = None
    self._def_panel.set_pokemon(None)
    self._refresh_party_slots()
    self.defender_changed.emit(None)
    self.recalculate()


def _change_defender(self) -> None:
    _bootstrap()
    from src.ui.pokemon_edit_dialog import MyBoxSelectDialog
    dlg = MyBoxSelectDialog("防御側PT", self)
    if not dlg.exec_():
        return
    p = dlg.selected_pokemon()
    if p:
        self._def_custom = copy.deepcopy(p)
        self._def_species_name = self._def_custom.name_ja or ""
        if self._opp_party:
            self._opp_party[0] = copy.deepcopy(self._def_custom)
        else:
            self._opp_party = [copy.deepcopy(self._def_custom)]
        self._def_party_side = "opp"
        self._def_party_idx = 0
        self._def_panel.set_pokemon(self._def_custom)
        self._refresh_party_slots()
        self.defender_changed.emit(self._def_custom)
        self.recalculate()


def _box_select_into_slot(self, side: str, idx: int) -> None:
    _bootstrap()
    from src.ui.pokemon_edit_dialog import MyBoxSelectDialog
    dlg = MyBoxSelectDialog("自分PT{}番".format(idx + 1), self.window())
    if not dlg.exec_():
        return
    p = dlg.selected_pokemon()
    if not p:
        return
    party = self._my_party if side == "my" else self._opp_party
    while len(party) <= idx:
        party.append(None)
    party[idx] = copy.deepcopy(p)

    if side == "my":
        self._on_my_party_slot_clicked(idx)
    else:
        self._on_opp_party_slot_clicked(idx)


def _change_move(self, slot: int) -> None:
    _bootstrap()
    if self._atk is None:
        return
    from src.ui.pokemon_edit_dialog import MoveSelectDialog
    from src.data.database import get_species_by_id, get_species_by_name_ja
    species = get_species_by_id(self._atk.species_id) if self._atk.species_id else None
    if species is None and self._atk.name_ja:
        species = get_species_by_name_ja(self._atk.name_ja)
    current_moves = (self._atk.moves + ["", "", "", ""])[:4]
    original_move = current_moves[slot]
    current_moves[slot] = ""
    dlg = MoveSelectDialog(
        species.species_id if species else None,
        self._atk.name_ja or "",
        original_move,
        self,
        usage_name=self._atk.usage_name or self._atk.name_ja or "",
        current_moves=current_moves,
    )
    if dlg.exec_():
        self._atk.moves = dlg.selected_moves()
        self._persist_party_member_edits()
        self.attacker_changed.emit(self._atk)
        self.recalculate()


def _change_opp_move(self, slot: int) -> None:
    _bootstrap()
    if self._def_custom is None:
        return
    from src.ui.pokemon_edit_dialog import MoveSelectDialog
    from src.data.database import get_species_by_id, get_species_by_name_ja
    species = get_species_by_id(self._def_custom.species_id) if self._def_custom.species_id else None
    if species is None and self._def_custom.name_ja:
        species = get_species_by_name_ja(self._def_custom.name_ja)
    current_moves = (self._def_custom.moves + ["", "", "", ""])[:4]
    original_move = current_moves[slot]
    current_moves[slot] = ""
    dlg = MoveSelectDialog(
        species.species_id if species else None,
        self._def_custom.name_ja or "",
        original_move,
        self,
        usage_name=self._def_custom.usage_name or self._def_custom.name_ja or "",
        current_moves=current_moves,
    )
    if dlg.exec_():
        self._def_custom.moves = dlg.selected_moves()
        self._persist_party_member_edits()
        self.defender_changed.emit(self._def_custom)
        self.recalculate()


def _swap_atk_def(self) -> None:
    _bootstrap()
    if self._def_custom is None:
        return
    old_atk = self._atk
    self._atk = copy.deepcopy(self._def_custom)
    self._def_custom = copy.deepcopy(old_atk) if old_atk else None
    self._def_species_name = (self._def_custom.name_ja or "") if self._def_custom else ""
    self._party_source = "opp" if self._party_source == "my" else "my"
    self._refresh_bulk_rows_visibility()
    self._atk_panel.set_pokemon(self._atk)
    self._def_panel.set_pokemon(self._def_custom)
    self._refresh_party_selector_labels()
    self._refresh_party_slots()
    self.attacker_changed.emit(self._atk)
    if self._def_custom:
        self.defender_changed.emit(self._def_custom)
    self.recalculate()


def _reset_conditions(self) -> None:
    _bootstrap()
    self._weather_grp.set_value("none")
    self._terrain_grp.set_value("none")
    for btn in (self._burn_btn, self._crit_btn, self._fairy_aura_btn,
                self._dark_aura_btn, self._charge_btn, self._helping_btn, self._steel_spirit_btn,
                self._overgrow_btn, self._blaze_btn, self._torrent_btn,
                self._swarm_btn, self._toxic_boost_btn,
                self._stakeout_btn, self._flash_fire_boost_btn,
                self._protosynthesis_btn, self._quark_drive_btn,
                self._analytic_btn, self._flare_boost_btn,
                self._guts_btn,
                self._self_reflect_btn, self._self_lightscreen_btn, self._self_friend_guard_btn,
                self._self_tailwind_btn,
                self._reflect_btn, self._lightscreen_btn, self._friend_guard_btn, self._tailwind_btn,
                self._opp_burn_btn, self._opp_crit_btn,
                self._opp_fairy_aura_btn, self._opp_dark_aura_btn,
                self._opp_charge_btn, self._opp_helping_btn, self._opp_steel_spirit_btn,
                self._opp_overgrow_btn, self._opp_blaze_btn, self._opp_torrent_btn,
                self._opp_swarm_btn, self._opp_toxic_boost_btn,
                self._opp_stakeout_btn, self._opp_flash_fire_btn,
                self._opp_protosynthesis_btn, self._opp_quark_drive_btn,
                self._opp_analytic_btn, self._opp_flare_boost_btn, self._opp_guts_btn,
                self._gravity_btn):
        btn.setChecked(False)
    if hasattr(self, "_supreme_combo"):
        self._supreme_combo.setCurrentIndex(0)
    if hasattr(self, "_opp_supreme_combo"):
        self._opp_supreme_combo.setCurrentIndex(0)
    if hasattr(self, "_rivalry_combo"):
        self._rivalry_combo.setCurrentIndex(0)
    for btn_name in (
        "_atk_multiscale_btn",
        "_atk_shadow_shield_btn",
        "_atk_tera_shell_btn",
        "_opp_multiscale_btn",
        "_opp_shadow_shield_btn",
        "_opp_tera_shell_btn",
    ):
        if hasattr(self, btn_name):
            btn = getattr(self, btn_name)
            btn.setChecked(True)
    self._atk_panel.reset_to_base()
    self._def_panel.reset_to_base()
    self.recalculate()


def _set_attacker_from_party(self, pokemon: PokemonInstance, source: str) -> None:
    _bootstrap()
    self._atk = copy.deepcopy(pokemon)
    self._party_source = source
    self._refresh_bulk_rows_visibility()
    self._atk_panel.set_pokemon(self._atk)
    self._refresh_party_selector_labels()
    self.attacker_changed.emit(self._atk)


def _set_defender_from_party(self, pokemon: PokemonInstance) -> None:
    _bootstrap()
    self._def_custom = copy.deepcopy(pokemon)
    self._def_species_name = (self._def_custom.name_ja or "") if self._def_custom else ""
    self._def_panel.set_pokemon(self._def_custom)
    self.defender_changed.emit(self._def_custom)


def _change_atk_ability(self) -> None:
    _bootstrap()
    if not self._atk:
        return
    new_val = _pick_ability(self._atk, self)
    if new_val is not None:
        self._atk.ability = new_val
        self._persist_party_member_edits()
        self._atk_panel.set_pokemon(self._atk)
        self._atk_card.set_pokemon(self._atk)
        self._refresh_party_slots()
        self.attacker_changed.emit(self._atk)
        self.recalculate()


def _change_atk_item(self) -> None:
    _bootstrap()
    if not self._atk:
        return
    new_val = _pick_item(self._atk, self)
    if new_val is not None:
        self._atk.item = new_val
        self._persist_party_member_edits()
        self._atk_panel.set_pokemon(self._atk)
        self._atk_card.set_pokemon(self._atk)
        self._refresh_party_slots()
        self.attacker_changed.emit(self._atk)
        self.recalculate()


def _change_def_ability(self) -> None:
    _bootstrap()
    if not self._def_custom:
        return
    new_val = _pick_ability(self._def_custom, self)
    if new_val is not None:
        self._def_custom.ability = new_val
        self._persist_party_member_edits()
        self._def_panel.set_pokemon(self._def_custom)
        self._refresh_defender_card()
        self._refresh_party_slots()
        self.defender_changed.emit(self._def_custom)
        self.recalculate()


def _change_def_item(self) -> None:
    _bootstrap()
    if not self._def_custom:
        return
    new_val = _pick_item(self._def_custom, self)
    if new_val is not None:
        self._def_custom.item = new_val
        self._persist_party_member_edits()
        self._def_panel.set_pokemon(self._def_custom)
        self._refresh_defender_card()
        self._refresh_party_slots()
        self.defender_changed.emit(self._def_custom)
        self.recalculate()


def _on_form_change_atk(self) -> None:
    _bootstrap()
    from src.data.database import get_abilities_by_usage, get_species_by_name_ja
    from src.ui.damage_panel_ability import _pokeapi_ability_names_for_pokemon

    def _fallback_original_ability(current_ability: str, canon_name: str) -> str:
        species = get_species_by_name_ja(canon_name)
        candidates: list[str] = []
        if species and species.name_en:
            candidates = _pokeapi_ability_names_for_pokemon(species.name_en or "")
        if current_ability and current_ability in candidates:
            return current_ability
        ranked = get_abilities_by_usage(canon_name)
        if candidates:
            for ability in ranked:
                if ability in candidates:
                    return ability
            return candidates[0]
        return ranked[0] if ranked else ""

    if not self._atk:
        return
    key = _normalize_form_name(self._atk.name_ja)
    group = _FORM_NAME_TO_GROUP.get(key)
    if not group or len(group) < 2:
        return
    canon = group[0]
    cur_idx = group.index(key) if key in group else 0
    next_name = group[(cur_idx + 1) % len(group)]
    if next_name == canon:
        cached = self._atk_form_cache.pop(canon, None)
        original_ability = cached[1] if isinstance(cached, tuple) else ""
        if not original_ability:
            # PT
            original_ability = _fallback_original_ability(self._atk.ability, canon)
        new_p = _apply_form(self._atk, next_name, original_ability=original_ability)
    else:
        existing = self._atk_form_cache.get(canon)
        original_ability = existing[1] if isinstance(existing, tuple) else self._atk.ability
        self._atk_form_cache[canon] = (next_name, original_ability)
        new_p = _apply_form(self._atk, next_name)
    self._atk = new_p
    self._persist_party_member_edits()
    self._atk_panel.set_pokemon(self._atk)
    self.attacker_changed.emit(self._atk)
    self._refresh_defender_card()
    self._refresh_party_slots()
    self.recalculate()


def _on_form_change_def(self) -> None:
    _bootstrap()
    from src.data.database import get_abilities_by_usage, get_species_by_name_ja
    from src.ui.damage_panel_ability import _pokeapi_ability_names_for_pokemon

    def _fallback_original_ability(current_ability: str, canon_name: str) -> str:
        species = get_species_by_name_ja(canon_name)
        candidates: list[str] = []
        if species and species.name_en:
            candidates = _pokeapi_ability_names_for_pokemon(species.name_en or "")
        if current_ability and current_ability in candidates:
            return current_ability
        ranked = get_abilities_by_usage(canon_name)
        if candidates:
            for ability in ranked:
                if ability in candidates:
                    return ability
            return candidates[0]
        return ranked[0] if ranked else ""

    if not self._def_custom:
        return
    key = _normalize_form_name(self._def_custom.name_ja)
    group = _FORM_NAME_TO_GROUP.get(key)
    if not group or len(group) < 2:
        return
    canon = group[0]
    cur_idx = group.index(key) if key in group else 0
    next_name = group[(cur_idx + 1) % len(group)]
    if next_name == canon:
        cached = self._def_form_cache.pop(canon, None)
        original_ability = cached[1] if isinstance(cached, tuple) else ""
        if not original_ability:
            original_ability = _fallback_original_ability(self._def_custom.ability, canon)
        new_p = _apply_form(self._def_custom, next_name, original_ability=original_ability)
    else:
        existing = self._def_form_cache.get(canon)
        original_ability = existing[1] if isinstance(existing, tuple) else self._def_custom.ability
        self._def_form_cache[canon] = (next_name, original_ability)
        new_p = _apply_form(self._def_custom, next_name)
    self._def_custom = new_p
    self._def_species_name = new_p.name_ja or ""
    self._persist_party_member_edits()
    self._def_panel.set_pokemon(self._def_custom)
    self.defender_changed.emit(self._def_custom)
    self._refresh_defender_card()
    self._refresh_party_slots()
    self.recalculate()


def _on_my_party_slot_clicked(self, idx: int) -> None:
    _bootstrap()
    if idx >= len(self._my_party) or self._my_party[idx] is None:
        self._add_party_slot("my", idx)
        return
    party_member = self._my_party[idx]
    if self._party_source == "my":
        self._atk_party_side = "my"
        self._atk_party_idx = idx
        self._set_attacker_from_party(party_member, source="my")
        norm = _normalize_form_name(party_member.name_ja)
        canon = (_FORM_NAME_TO_GROUP.get(norm) or [norm])[0]
        cached = self._atk_form_cache.get(canon)
        if cached:
            form_name = cached[0] if isinstance(cached, tuple) else cached
            self._atk = _apply_form(self._atk, form_name)
            self._atk_panel.set_pokemon(self._atk)
            self.attacker_changed.emit(self._atk)
    else:
        self._def_party_side = "my"
        self._def_party_idx = idx
        self._set_defender_from_party(party_member)
        norm = _normalize_form_name(party_member.name_ja)
        canon = (_FORM_NAME_TO_GROUP.get(norm) or [norm])[0]
        cached = self._def_form_cache.get(canon)
        if cached:
            form_name = cached[0] if isinstance(cached, tuple) else cached
            self._def_custom = _apply_form(self._def_custom, form_name)
            self._def_species_name = self._def_custom.name_ja or ""
            self._def_panel.set_pokemon(self._def_custom)
            self.defender_changed.emit(self._def_custom)
    self._refresh_party_slots()
    self.recalculate()


def _on_opp_party_slot_clicked(self, idx: int) -> None:
    _bootstrap()
    if idx >= len(self._opp_party) or self._opp_party[idx] is None:
        self._add_party_slot("opp", idx)
        return
    party_member = self._opp_party[idx]
    if self._party_source == "opp":
        self._atk_party_side = "opp"
        self._atk_party_idx = idx
        self._set_attacker_from_party(party_member, source="opp")
        norm = _normalize_form_name(party_member.name_ja)
        canon = (_FORM_NAME_TO_GROUP.get(norm) or [norm])[0]
        cached = self._atk_form_cache.get(canon)
        if cached:
            form_name = cached[0] if isinstance(cached, tuple) else cached
            self._atk = _apply_form(self._atk, form_name)
            self._atk_panel.set_pokemon(self._atk)
            self.attacker_changed.emit(self._atk)
    else:
        self._def_party_side = "opp"
        self._def_party_idx = idx
        self._set_defender_from_party(party_member)
        norm = _normalize_form_name(party_member.name_ja)
        canon = (_FORM_NAME_TO_GROUP.get(norm) or [norm])[0]
        cached = self._def_form_cache.get(canon)
        if cached:
            form_name = cached[0] if isinstance(cached, tuple) else cached
            self._def_custom = _apply_form(self._def_custom, form_name)
            self._def_species_name = self._def_custom.name_ja or ""
            self._def_panel.set_pokemon(self._def_custom)
            self.defender_changed.emit(self._def_custom)
    self._refresh_party_slots()
    self.recalculate()

# ── Key mapping helpers ───────────────────────────────────────────


def _open_copy_dialog(self) -> None:
    _bootstrap()
    from src.ui.damage_panel_copy_dialog import CopyDialog
    webhook_url = ""
    main_win = self.window()
    if hasattr(main_win, "_webhook_url_edit") and main_win._webhook_url_edit is not None:
        webhook_url = main_win._webhook_url_edit.text().strip()
    if not webhook_url and hasattr(main_win, "_load_settings"):
        settings = main_win._load_settings()
        webhook_url = settings.get("webhook_url", "")
    dlg = CopyDialog(self, webhook_url=webhook_url, parent=self)
    dlg.exec_()


def _set_battle_format(self, mode: str) -> None:
    _bootstrap()
    self._battle_format = mode
    is_double = mode == "double"
    if hasattr(self, "_helping_btn"):
        self._helping_btn.setVisible(is_double)
        self._opp_helping_btn.setVisible(is_double)
        self._steel_spirit_btn.setVisible(is_double)
        self._opp_steel_spirit_btn.setVisible(is_double)
        self._self_friend_guard_btn.setVisible(is_double)
        self._friend_guard_btn.setVisible(is_double)
        self._self_tailwind_btn.setVisible(is_double)
        self._tailwind_btn.setVisible(is_double)
    self.recalculate()


def _toggle_details(self, checked: bool) -> None:
    _bootstrap()
    self._detail_container.setVisible(checked)
    self._detail_toggle_btn.setText("詳細設定を隠す" if checked else "詳細設定を表示")
    if checked:
        self.recalculate()


def _apply_bulk_rows_default(self) -> None:
    _bootstrap()
    self._set_bulk_rows_visible(True, refresh=False)


def _set_bulk_rows_visible(self, visible: bool, refresh: bool = True) -> None:
    _bootstrap()
    self._show_bulk_rows = bool(visible)
    if hasattr(self, "_move_sections"):
        for sec in self._move_sections:
            sec.set_bulk_rows_visible(self._show_bulk_rows)
    if hasattr(self, "_opp_move_sections"):
        for sec in self._opp_move_sections:
            sec.set_bulk_rows_visible(self._show_bulk_rows)
    if refresh:
        self._refresh_defender_card()


def _on_bulk_toggle_clicked(self, checked: bool) -> None:
    _bootstrap()
    self._set_bulk_rows_visible(bool(checked), refresh=True)


