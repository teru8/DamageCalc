"""Damage calculation panel – complete redesign."""
from __future__ import annotations

import copy
from functools import partial
from itertools import zip_longest

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGroupBox, QSpinBox, QComboBox, QCheckBox,
)

from src.models import PokemonInstance, SpeciesInfo
from src.ui.damage_panel_forms import (
    FORM_NAME_TO_GROUP as _FORM_NAME_TO_GROUP,
    form_group as _form_group_fn,
    next_form_name as _next_form_name_fn,
    normalize_form_name as _normalize_form_name_fn,
)
from src.ui.damage_panel_form_apply import apply_form as _apply_form_fn


# ── Helpers ───────────────────────────────────────────────────────────────


def _category_icon(category: str, width: int = 66, height: int = 22) -> QPixmap:
    from src.ui.damage_panel_icons import category_icon

    return category_icon(category, width, height)


# ── Form change data ─────────────────────────────────────────────────────
# Form groups moved to src/ui/damage_panel_forms.py

# PokeAPI english names for non-base forms
from src.ui.damage_panel_form_data import (
    FORM_ABILITY_JA as _FORM_ABILITY_JA,
    FORM_MISSING_MEGA_STATS as _FORM_MISSING_MEGA_STATS,
    FORM_POKEAPI_EN as _FORM_POKEAPI_EN,
)

_normalize_form_name = partial(_normalize_form_name_fn, form_name_to_group=_FORM_NAME_TO_GROUP)
_form_group = partial(_form_group_fn, form_name_to_group=_FORM_NAME_TO_GROUP)
_next_form_name = partial(_next_form_name_fn, form_name_to_group=_FORM_NAME_TO_GROUP)


def _apply_form(p: PokemonInstance, form_name: str, original_ability: str = "") -> PokemonInstance:
    return _apply_form_fn(
        pokemon=p,
        form_name=form_name,
        original_ability=original_ability,
        form_name_to_group=_FORM_NAME_TO_GROUP,
        form_pokeapi_en=_FORM_POKEAPI_EN,
        form_missing_mega_stats=_FORM_MISSING_MEGA_STATS,
        form_ability_ja=_FORM_ABILITY_JA,
    )


# ── Simple toggle button ──────────────────────────────────────────────────

# ── Ability / Item quick-pick helpers ────────────────────────────────────

def _pick_ability(pokemon: PokemonInstance, parent: QWidget) -> str | None:
    from src.ui.damage_panel_pickers import pick_ability

    return pick_ability(pokemon, parent)


def _pick_item(pokemon: PokemonInstance, parent: QWidget) -> str | None:
    from src.ui.damage_panel_pickers import pick_item

    return pick_item(pokemon, parent)


def _show_pick_dialog(
    title: str,
    items: list,
    separator_after: int | None,
    current: str,
    parent: QWidget,
) -> str | None:
    from src.ui.damage_panel_pickers import show_pick_dialog

    return show_pick_dialog(title, items, separator_after, current, parent)


# ── Main DamagePanel ──────────────────────────────────────────────────────

class DamagePanel(QWidget):
    attacker_changed = pyqtSignal(object)   # emitted when attacker pokemon changes
    defender_changed = pyqtSignal(object)   # emitted when defender pokemon changes
    registry_maybe_changed = pyqtSignal()
    bridge_payload_logged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._atk: PokemonInstance | None = None
        self._def_custom: PokemonInstance | None = None   # registered / edited defender
        self._def_species_name: str = ""
        self._my_party: list[PokemonInstance | None] = []
        self._opp_party: list[PokemonInstance | None] = []
        self._party_source = "my"
        self._atk_party_side: str | None = None
        self._atk_party_idx: int | None = None
        self._def_party_side: str | None = None
        self._def_party_idx: int | None = None
        self._show_bulk_rows = True
        self._is_recalculating = False
        self._move_cache: dict[str, MoveInfo] = {}
        self._display_to_move_slot = [0, 1, 2, 3]
        self._atk_form_cache: dict[str, str] = {}
        self._def_form_cache: dict[str, str] = {}
        self.setStyleSheet(
            "QPushButton{font-size:14px;}"
            "QLabel{font-size:14px;}"
            "QCheckBox{font-size:14px;}"
            "QComboBox{font-size:14px;}"
            "QSpinBox{font-size:14px;}"
        )
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        from src.ui.damage_panel_parts.ui_builders import _build_ui as build_ui_fn
        return build_ui_fn(self)

    @property
    def side_panel(self) -> QWidget:
        """Attacker/defender controls + battle settings widget (hosted in cam panel)."""
        return self._side_panel

    def _build_side_panel(self) -> None:
        from src.ui.damage_panel_parts.ui_builders import _build_side_panel as build_side_panel_fn
        return build_side_panel_fn(self)

    def _build_content(self) -> None:
        from src.ui.damage_panel_parts.ui_builders import _build_content as build_content_fn
        return build_content_fn(self)

    def set_my_pokemon(self, pokemon: PokemonInstance) -> None:
        self._atk = copy.deepcopy(pokemon)
        self._party_source = "my"
        self._atk_party_side = None
        self._atk_party_idx = None
        self._refresh_bulk_rows_visibility()
        self._atk_panel.set_pokemon(self._atk)
        self._refresh_party_selector_labels()
        self._refresh_party_slots()
        self.recalculate()

    def set_opp_party_action_widget(self, widget: QWidget | None) -> None:
        if not hasattr(self, "_opp_party_action_layout"):
            return
        layout = self._opp_party_action_layout
        while layout.count():
            item = layout.takeAt(0)
            child = item.widget()
            if child is not None:
                child.setParent(None)
        if widget is not None:
            layout.addStretch()
            layout.addWidget(widget, 0, Qt.AlignRight | Qt.AlignBottom)

    def _on_party_slot_context_menu(self, side: str, idx: int, global_pos) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _on_party_slot_context_menu as on_party_slot_context_menu_fn
        return on_party_slot_context_menu_fn(self, side, idx, global_pos)

    def _edit_party_slot(self, side: str, idx: int) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _edit_party_slot as edit_party_slot_fn
        return edit_party_slot_fn(self, side, idx)

    def _save_party_slot_to_db(self, side: str, idx: int) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _save_party_slot_to_db as save_party_slot_to_db_fn
        return save_party_slot_to_db_fn(self, side, idx)

    def _add_party_slot(self, side: str, idx: int) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _add_party_slot as add_party_slot_fn
        return add_party_slot_fn(self, side, idx)

    def set_my_party(self, party: list[PokemonInstance | None]) -> None:
        self._my_party = [copy.deepcopy(member) if member else None for member in party]
        self._refresh_party_slots()

    def set_opponent_options(
        self,
        party: list[PokemonInstance | None],
        active: PokemonInstance | None = None,
    ) -> None:
        if not any(member for member in party):
            return
        self._opp_party = [(copy.deepcopy(member) if member else None) for member in (list(party) + [None] * 6)[:6]]
        defender = active or next((member for member in self._opp_party if member), None)
        if not defender:
            return
        self._def_custom = copy.deepcopy(defender)
        self._def_species_name = defender.name_ja or ""
        self._def_party_side = "opp"
        self._def_party_idx = next(
            (index for index, member in enumerate(self._opp_party) if member and member.name_ja == defender.name_ja),
            None,
        )
        self._def_panel.set_pokemon(self._def_custom)
        self.defender_changed.emit(self._def_custom)
        self._refresh_party_slots()
        self._refresh_defender_card()
        self.recalculate()

    def set_opponent_pokemon(self, pokemon: PokemonInstance) -> None:
        if self._opp_party:
            self._opp_party[0] = copy.deepcopy(pokemon)
        else:
            self._opp_party = [copy.deepcopy(pokemon)]
        self._def_custom = copy.deepcopy(pokemon)
        self._def_species_name = pokemon.name_ja or ""
        self._def_party_side = "opp"
        self._def_party_idx = 0
        self._def_panel.set_pokemon(self._def_custom)
        self.defender_changed.emit(self._def_custom)
        self._refresh_party_slots()
        self._refresh_defender_card()
        self.recalculate()

    def get_my_party_snapshot(self) -> list[PokemonInstance | None]:
        return [copy.deepcopy(member) if member else None for member in self._my_party]

    def get_opp_party_snapshot(self) -> list[PokemonInstance | None]:
        return [copy.deepcopy(member) if member else None for member in self._opp_party]

    def set_weather(self, weather: str) -> None:
        _map = {"sun": "はれ", "rain": "あめ", "sand": "すな", "hail": "ゆき"}
        self._weather_grp.set_value(_map.get(weather, "none"))
        self.recalculate()

    def set_terrain(self, terrain: str) -> None:
        _map = {"electric": "エレキ", "grassy": "グラス",
                "misty": "ミスト", "psychic": "サイコ"}
        self._terrain_grp.set_value(_map.get(terrain, "none"))
        self.recalculate()

    def set_terastal_controls_visible(self, visible: bool) -> None:
        if hasattr(self, "_atk_panel"):
            self._atk_panel.set_tera_visible(visible)
        if hasattr(self, "_def_panel"):
            self._def_panel.set_tera_visible(visible)
        if hasattr(self, "_move_sections"):
            self.recalculate()

    def attacker_side(self) -> str:
        return "opp" if self._party_source == "opp" else "my"

    def defender_side(self) -> str:
        return "my" if self._party_source == "opp" else "opp"

    # ── Ability combo shared style constants ─────────────────────────────
    _ABILITY_COMBO_STYLE_ACTIVE = (
        "QComboBox{background:#f9e2af;color:#3a3218;border:1px solid #a87d3a;"
        "border-radius:4px;padding:4px 8px;font-size:14px;font-weight:bold;}"
        "QComboBox::drop-down{border:none;}"
        "QComboBox::down-arrow{image:none;width:0;height:0;}"
        "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;"
        "selection-background-color:#f9e2af;selection-color:#3a3218;}"
    )
    _ABILITY_COMBO_STYLE_INACTIVE = (
        "QComboBox{background:#3a3218;color:#f9e2af;border:1px solid #a87d3a;"
        "border-radius:4px;padding:4px 8px;font-size:14px;}"
        "QComboBox::drop-down{border:none;}"
        "QComboBox::down-arrow{image:none;width:0;height:0;}"
        "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;"
        "selection-background-color:#f9e2af;selection-color:#3a3218;}"
    )

    def _refresh_ability_combo(self, combo: QComboBox) -> None:
        """コンボボックスのスタイルを選択状態に合わせて更新し、再計算を実行する。"""
        self.recalculate()
        style = (
            self._ABILITY_COMBO_STYLE_ACTIVE
            if combo.currentIndex() > 0
            else self._ABILITY_COMBO_STYLE_INACTIVE
        )
        combo.setStyleSheet(style)

    def _refresh_supreme_combo(self) -> None:
        self._refresh_ability_combo(self._supreme_combo)

    def _refresh_rivalry_combo(self) -> None:
        self._refresh_ability_combo(self._rivalry_combo)

    def _refresh_opp_rivalry_combo(self) -> None:
        self._refresh_ability_combo(self._opp_rivalry_combo)

    def _refresh_opp_supreme_combo(self) -> None:
        self._refresh_ability_combo(self._opp_supreme_combo)

    def _update_cond_btn_visibility(
        self,
        btns: dict,
        show_map: dict[str, bool],
        *,
        auto_check_on_show: bool = False,
    ) -> None:
        """能力条件ボタン群の表示/非表示と選択状態をまとめて更新する。

        auto_check_on_show=True の場合、非表示→表示に変わったボタンを自動でオンにする（守備側のフルHP特性用）。
        False の場合、非表示になるボタンはオフにする（攻撃/守備の通常ボタン用）。
        """
        for key, btn in btns.items():
            show = show_map.get(key, False)
            if auto_check_on_show:
                was_visible = btn.isVisible()
                btn.setVisible(show)
                if show and not was_visible:
                    btn.blockSignals(True)
                    btn.setChecked(True)
                    btn.blockSignals(False)
                    btn._refresh()
            else:
                if not show and btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
                    btn._refresh()
                btn.setVisible(show)

    def _sync_attacker_ability_support_buttons(self) -> None:
        if not hasattr(self, "_attacker_ability_cond_btns"):
            return
        self._sync_ability_support_buttons(is_attacker=True)

    def _sync_defender_ability_support_buttons(self) -> None:
        if not hasattr(self, "_defender_ability_cond_btns"):
            return
        self._sync_ability_support_buttons(is_attacker=False)

    def _sync_ability_support_buttons(self, is_attacker: bool) -> None:
        """攻撃側/守備側の能力条件ボタン表示を ability に合わせて一括更新する。"""
        if is_attacker:
            ability = (self._atk.ability if self._atk else "").strip()
            cond_btns_attr = "_attacker_ability_cond_btns"
            trigger_btns_attr = "_attacker_trigger_cond_btns"
            full_hp_btns_attr = "_attacker_full_hp_guard_btns"
        else:
            ability = (self._def_custom.ability if self._def_custom else "").strip()
            cond_btns_attr = "_defender_ability_cond_btns"
            trigger_btns_attr = "_defender_trigger_cond_btns"
            full_hp_btns_attr = "_defender_full_hp_guard_btns"

        cond_show_map = {
            "しんりょく": ability in ("しんりょく", "Overgrow"),
            "もうか": ability in ("もうか", "Blaze"),
            "げきりゅう": ability in ("げきりゅう", "Torrent"),
            "むしのしらせ": ability in ("むしのしらせ", "Swarm"),
            "どくぼうそう": ability in ("どくぼうそう", "Toxic Boost"),
        }
        self._update_cond_btn_visibility(getattr(self, cond_btns_attr), cond_show_map)

        trigger_show_map = {
            "はりこみ": ability in ("はりこみ", "Stakeout"),
            "もらいび": ability in ("もらいび", "Flash Fire"),
            "こだいかっせい": ability in ("こだいかっせい", "Protosynthesis"),
            "クォークチャージ": ability in ("クォークチャージ", "Quark Drive"),
            "アナライズ": ability in ("アナライズ", "Analytic"),
            "ねつぼうそう": ability in ("ねつぼうそう", "Flare Boost"),
            "こんじょう": ability in ("こんじょう", "Guts"),
        }
        if hasattr(self, trigger_btns_attr):
            self._update_cond_btn_visibility(getattr(self, trigger_btns_attr), trigger_show_map)

        full_hp_show_map = {
            "マルチスケイル": ability in ("マルチスケイル", "Multiscale"),
            "ファントムガード": ability in ("ファントムガード", "Shadow Shield"),
            "テラスシェル": ability in ("テラスシェル", "Tera Shell"),
        }
        if hasattr(self, full_hp_btns_attr):
            self._update_cond_btn_visibility(
                getattr(self, full_hp_btns_attr), full_hp_show_map, auto_check_on_show=True
            )

        if is_attacker:
            show_supreme = ability in ("そうだいしょう", "Supreme Overlord")
            self._supreme_combo.setVisible(show_supreme)
            if not show_supreme:
                self._supreme_combo.blockSignals(True)
                self._supreme_combo.setCurrentIndex(0)
                self._supreme_combo.blockSignals(False)

            show_rivalry = ability in ("とうそうしん", "Rivalry")
            self._rivalry_combo.setVisible(show_rivalry)
            if not show_rivalry:
                self._rivalry_combo.blockSignals(True)
                self._rivalry_combo.setCurrentIndex(0)
                self._rivalry_combo.blockSignals(False)
        else:
            if hasattr(self, "_opp_supreme_combo"):
                show_opp_supreme = ability in ("そうだいしょう", "Supreme Overlord")
                self._opp_supreme_combo.setVisible(show_opp_supreme)
                if not show_opp_supreme:
                    self._opp_supreme_combo.blockSignals(True)
                    self._opp_supreme_combo.setCurrentIndex(0)
                    self._opp_supreme_combo.blockSignals(False)

    # ── Recalculation ─────────────────────────────────────────────────

    def recalculate(self) -> None:
        if self._is_recalculating:
            return
        self._is_recalculating = True
        try:
            from src.ui.damage_panel_parts.calc_logic import recalculate as recalculate_fn
            recalculate_fn(self)
        finally:
            self._is_recalculating = False

    def _show_opp_moves_only(self) -> None:
        """自分未設定・相手のみ設定時に相手のわざ名だけ右側に表示する。"""
        from src.data.database import get_move_by_name_ja

        if not self._def_custom:
            for sec in self._opp_move_sections:
                sec.setup_move(None)
            return

        opp_moves = self._def_custom.moves or []
        for opp_sec, opp_move_name in zip_longest(self._opp_move_sections, opp_moves, fillvalue=None):
            if opp_sec is None:
                continue
            if opp_move_name:
                opp_move_info = self._move_cache.get(opp_move_name) or get_move_by_name_ja(opp_move_name)
                if opp_move_info:
                    self._move_cache[opp_move_name] = opp_move_info
                opp_sec.setup_move(opp_move_info)
            else:
                opp_sec.setup_move(None)

    def _resolve_species_info(
        self,
        pokemon: PokemonInstance | None,
        fallback_name_ja: str = "",
    ) -> SpeciesInfo | None:
        from src.ui.damage_panel_species import resolve_species
        return resolve_species(pokemon, fallback_name_ja)

    def collect_calc_inputs(self):
        from src.ui.damage_panel_parts.calc_logic import collect_calc_inputs as collect_calc_inputs_fn
        return collect_calc_inputs_fn(self)

    def _calc_moves(self) -> None:
        from src.ui.damage_panel_parts.calc_logic import _calc_moves as _calc_moves_fn
        return _calc_moves_fn(self)

    def _refresh_defender_card(self, atk_view: PokemonInstance | None = None) -> None:
        self._atk_card.set_pokemon(atk_view if atk_view is not None else self._atk)
        self._def_card.set_pokemon(self._def_custom)

    def _persist_party_member_edits(self) -> None:
        if self._atk:
            self._atk.ev_hp = self._atk_panel.ev_hp_pts() * 8
            self._atk.ev_attack = self._atk_panel.ev_attack_pts() * 8
            self._atk.ev_defense = self._atk_panel.ev_defense_pts() * 8
            self._atk.ev_sp_attack = self._atk_panel.ev_sp_attack_pts() * 8
            self._atk.ev_sp_defense = self._atk_panel.ev_sp_defense_pts() * 8
            self._atk.ev_speed = self._atk_panel.ev_speed_pts() * 8
            self._atk.nature = self._atk_panel.panel_nature()

        if self._def_custom:
            self._def_custom.ev_hp = self._def_panel.ev_hp_pts() * 8
            self._def_custom.ev_attack = self._def_panel.ev_attack_pts() * 8
            self._def_custom.ev_defense = self._def_panel.ev_defense_pts() * 8
            self._def_custom.ev_sp_attack = self._def_panel.ev_sp_attack_pts() * 8
            self._def_custom.ev_sp_defense = self._def_panel.ev_sp_defense_pts() * 8
            self._def_custom.ev_speed = self._def_panel.ev_speed_pts() * 8
            self._def_custom.nature = self._def_panel.panel_nature()

        if self._atk and self._atk_party_side in ("my", "opp") and self._atk_party_idx is not None:
            party = self._my_party if self._atk_party_side == "my" else self._opp_party
            if 0 <= self._atk_party_idx < len(party):
                party[self._atk_party_idx] = copy.deepcopy(self._atk)
        if self._def_custom and self._def_party_side in ("my", "opp") and self._def_party_idx is not None:
            party = self._my_party if self._def_party_side == "my" else self._opp_party
            if 0 <= self._def_party_idx < len(party):
                party[self._def_party_idx] = copy.deepcopy(self._def_custom)

    def _on_atk_panel_changed(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _on_atk_panel_changed as _on_atk_panel_changed_fn
        return _on_atk_panel_changed_fn(self)

    def _on_def_panel_changed(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _on_def_panel_changed as _on_def_panel_changed_fn
        return _on_def_panel_changed_fn(self)

    def _effective_def_types(self) -> list[str]:
        tera = self._def_panel.terastal_type() if hasattr(self, "_def_panel") else ""
        if tera:
            return [tera]
        if self._def_custom:
            return self._def_custom.types or ["normal"]
        return ["normal"]

    def _active_party(self) -> list[PokemonInstance | None]:
        return self._opp_party if self._party_source == "opp" else self._my_party

    def _refresh_party_selector_labels(self) -> None:
        if not hasattr(self, "_my_party_row_label"):
            return
        self._my_party_row_label.setText("自分PT")
        self._opp_party_row_label.setText("相手PT")

    def _refresh_party_slots(self) -> None:
        if not hasattr(self, "_my_party_slots"):
            return
        my_is_attacker = (self._party_source == "my")
        atk_name = (self._atk.name_ja or "") if self._atk else ""
        def_name = (self._def_custom.name_ja or "") if self._def_custom else ""
        atk_canon = (_FORM_NAME_TO_GROUP.get(atk_name) or [atk_name])[0] if atk_name else ""
        def_canon = (_FORM_NAME_TO_GROUP.get(def_name) or [def_name])[0] if def_name else ""
        atk_current = atk_name
        def_current = def_name
        atk_idx_known = self._atk_party_side is not None and self._atk_party_idx is not None
        def_idx_known = self._def_party_side is not None and self._def_party_idx is not None
        my_cache = self._atk_form_cache if my_is_attacker else self._def_form_cache
        opp_cache = self._def_form_cache if my_is_attacker else self._atk_form_cache
        for i, slot in enumerate(self._my_party_slots):
            if i < len(self._my_party) and self._my_party[i]:
                name = self._my_party[i].name_ja or ""
                name_canon = (_FORM_NAME_TO_GROUP.get(name) or [name])[0]
                if atk_idx_known:
                    is_atk = my_is_attacker and self._atk_party_side == "my" and self._atk_party_idx == i
                else:
                    is_atk = my_is_attacker and name_canon == atk_canon
                if def_idx_known:
                    is_def = not my_is_attacker and self._def_party_side == "my" and self._def_party_idx == i
                else:
                    is_def = not my_is_attacker and name_canon == def_canon
                if not is_atk and not is_def:
                    cached = my_cache.get(name_canon)
                    cached_form = (cached[0] if isinstance(cached, tuple) else cached) if cached else None
                else:
                    cached_form = None
                sprite = (atk_current if is_atk else def_current if is_def else cached_form or "") or name
                slot.set_name(name, attack_active=is_atk, defense_active=is_def, sprite_name=sprite)
            else:
                slot.set_name("")
        for i, slot in enumerate(self._opp_party_slots):
            if i < len(self._opp_party) and self._opp_party[i]:
                name = self._opp_party[i].name_ja or ""
                name_canon = (_FORM_NAME_TO_GROUP.get(name) or [name])[0]
                if atk_idx_known:
                    is_atk = not my_is_attacker and self._atk_party_side == "opp" and self._atk_party_idx == i
                else:
                    is_atk = not my_is_attacker and name_canon == atk_canon
                if def_idx_known:
                    is_def = my_is_attacker and self._def_party_side == "opp" and self._def_party_idx == i
                else:
                    is_def = my_is_attacker and name_canon == def_canon
                if not is_atk and not is_def:
                    cached = opp_cache.get(name_canon)
                    cached_form = (cached[0] if isinstance(cached, tuple) else cached) if cached else None
                else:
                    cached_form = None
                sprite = (atk_current if is_atk else def_current if is_def else cached_form or "") or name
                slot.set_name(name, attack_active=is_atk, defense_active=is_def, sprite_name=sprite)
            else:
                slot.set_name("")

    # ── Event handlers ────────────────────────────────────────────────

    def _edit_attacker(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _edit_attacker as _edit_attacker_fn
        return _edit_attacker_fn(self)

    def _new_attacker(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _new_attacker as _new_attacker_fn
        return _new_attacker_fn(self)

    def _clear_attacker(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _clear_attacker as _clear_attacker_fn
        return _clear_attacker_fn(self)

    def _change_attacker(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _change_attacker as _change_attacker_fn
        return _change_attacker_fn(self)

    def _edit_defender(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _edit_defender as _edit_defender_fn
        return _edit_defender_fn(self)

    def _new_defender(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _new_defender as _new_defender_fn
        return _new_defender_fn(self)

    def _clear_defender(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _clear_defender as _clear_defender_fn
        return _clear_defender_fn(self)

    def _change_defender(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _change_defender as _change_defender_fn
        return _change_defender_fn(self)

    def _box_select_into_slot(self, side: str, idx: int) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _box_select_into_slot as _box_select_into_slot_fn
        return _box_select_into_slot_fn(self, side, idx)

    def _change_move(self, slot: int) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _change_move as _change_move_fn
        return _change_move_fn(self, slot)

    def _change_opp_move(self, slot: int) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _change_opp_move as _change_opp_move_fn
        return _change_opp_move_fn(self, slot)

    def _swap_atk_def(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _swap_atk_def as _swap_atk_def_fn
        return _swap_atk_def_fn(self)

    def _reset_conditions(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _reset_conditions as _reset_conditions_fn
        return _reset_conditions_fn(self)

    def _set_attacker_from_party(self, pokemon: PokemonInstance, source: str) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _set_attacker_from_party as _set_attacker_from_party_fn
        return _set_attacker_from_party_fn(self, pokemon, source)

    def _set_defender_from_party(self, pokemon: PokemonInstance) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _set_defender_from_party as _set_defender_from_party_fn
        return _set_defender_from_party_fn(self, pokemon)

    def _change_atk_ability(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _change_atk_ability as _change_atk_ability_fn
        return _change_atk_ability_fn(self)

    def _change_atk_item(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _change_atk_item as _change_atk_item_fn
        return _change_atk_item_fn(self)

    def _change_def_ability(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _change_def_ability as _change_def_ability_fn
        return _change_def_ability_fn(self)

    def _change_def_item(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _change_def_item as _change_def_item_fn
        return _change_def_item_fn(self)

    def _on_form_change_atk(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _on_form_change_atk as _on_form_change_atk_fn
        return _on_form_change_atk_fn(self)

    def _on_form_change_def(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _on_form_change_def as _on_form_change_def_fn
        return _on_form_change_def_fn(self)

    def _on_my_party_slot_clicked(self, idx: int) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _on_my_party_slot_clicked as _on_my_party_slot_clicked_fn
        return _on_my_party_slot_clicked_fn(self, idx)

    def _on_opp_party_slot_clicked(self, idx: int) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _on_opp_party_slot_clicked as _on_opp_party_slot_clicked_fn
        return _on_opp_party_slot_clicked_fn(self, idx)

    def _open_copy_dialog(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _open_copy_dialog as _open_copy_dialog_fn
        return _open_copy_dialog_fn(self)

    def _set_battle_format(self, mode: str) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _set_battle_format as _set_battle_format_fn
        return _set_battle_format_fn(self, mode)

    def _toggle_details(self, checked: bool) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _toggle_details as _toggle_details_fn
        return _toggle_details_fn(self, checked)

    def _apply_bulk_rows_default(self) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _apply_bulk_rows_default as _apply_bulk_rows_default_fn
        return _apply_bulk_rows_default_fn(self)

    def _set_bulk_rows_visible(self, visible: bool, refresh: bool = True) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _set_bulk_rows_visible as _set_bulk_rows_visible_fn
        return _set_bulk_rows_visible_fn(self, visible, refresh)

    def _on_bulk_toggle_clicked(self, checked: bool) -> None:
        from src.ui.damage_panel_parts.signal_handlers import _on_bulk_toggle_clicked as _on_bulk_toggle_clicked_fn
        return _on_bulk_toggle_clicked_fn(self, checked)

    def _refresh_bulk_rows_visibility(self) -> None:
        pass

    def _weather_key(self) -> str:
        return {"はれ": "sun", "あめ": "rain", "すな": "sand", "ゆき": "hail"}.get(
            self._weather_grp.value(), "none")

    def _terrain_key(self) -> str:
        return {"エレキ": "electric", "グラス": "grassy",
                "ミスト": "misty", "サイコ": "psychic"}.get(
            self._terrain_grp.value(), "none")
