from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.constants import NATURES_JA
from src.models import PokemonInstance, SpeciesInfo
from src.ui.ui_utils import sprite_pixmap_or_zukan

_SPEED_RANK_MULT: dict[int, float] = {
    -6: 2 / 8,
    -5: 2 / 7,
    -4: 2 / 6,
    -3: 2 / 5,
    -2: 2 / 4,
    -1: 2 / 3,
    0: 1.0,
    1: 3 / 2,
    2: 4 / 2,
    3: 5 / 2,
    4: 6 / 2,
    5: 7 / 2,
    6: 8 / 2,
}

_SPEED_ABILITY_MULT: dict[str, float] = {
    "すいすい": 2.0,
    "Swift Swim": 2.0,
    "ようりょくそ": 2.0,
    "Chlorophyll": 2.0,
    "すなかき": 2.0,
    "Sand Rush": 2.0,
    "ゆきかき": 2.0,
    "Slush Rush": 2.0,
    "かるわざ": 2.0,
    "Unburden": 2.0,
    "サーフテール": 2.0,
    "Surge Surfer": 2.0,
    "はやあし": 1.5,
    "Quick Feet": 1.5,
    "こだいかっせい": 1.5,
    "Protosynthesis": 1.5,
    "クォークチャージ": 1.5,
    "Quark Drive": 1.5,
}

_SCARF_ITEMS = {"こだわりスカーフ", "Choice Scarf"}
_MAX_SPEED_EV = 32


@dataclass(frozen=True)
class _SpeedState:
    scarf_on: bool = False
    rank: int = 0
    ability_on: bool = False
    profile_override: str = ""
    signature: tuple[str, str, str] = ("", "", "")


@dataclass(frozen=True)
class _SpeedEntry:
    side: str
    index: int
    pokemon: PokemonInstance | None
    value: int
    state: _SpeedState
    ability_mult: float


class _SpeedRow(QFrame):
    rank_changed = pyqtSignal(str, int, int)
    profile_changed = pyqtSignal(str, int, str)
    toggled = pyqtSignal()
    _SPRITE_SIZE = 44

    def __init__(self, parent=None):
        super().__init__(parent)
        self._side = ""
        self._index = -1
        self._SPRITE_SIZE = 52
        self.setFixedHeight(86)
        self.setStyleSheet(
            "QFrame{background:#181825;border:1px solid #313244;border-radius:6px;}"
        )
        root = QHBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        self._sprite_lbl = QLabel()
        self._sprite_lbl.setFixedSize(self._SPRITE_SIZE, self._SPRITE_SIZE)
        self._sprite_lbl.setAlignment(Qt.AlignCenter)
        sprite_col = QVBoxLayout()
        sprite_col.setContentsMargins(0, 0, 0, 0)
        sprite_col.setSpacing(1)
        sprite_col.addWidget(self._sprite_lbl, 0, Qt.AlignCenter)
        self._base_speed_lbl = QLabel("---")
        self._base_speed_lbl.setAlignment(Qt.AlignCenter)
        self._base_speed_lbl.setFixedSize(52, 24)
        self._base_speed_lbl.setStyleSheet(
            "font-size:12px;font-weight:bold;color:#cdd6f4;"
            "background:#111827;border-radius:9px;padding:1px 4px;"
        )
        sprite_col.addWidget(self._base_speed_lbl)
        root.addLayout(sprite_col, 0)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(3)
        root.addLayout(body, 1)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(4)
        self._name_lbl = QLabel("---")
        self._name_lbl.setStyleSheet("font-size:12px;color:#a6adc8;font-weight:bold;")
        self._name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top.addWidget(self._name_lbl, 1)
        self._value_lbl = QLabel("---")
        self._value_lbl.setAlignment(Qt.AlignCenter)
        self._value_lbl.setFixedSize(44, 24)
        self._value_lbl.setStyleSheet(
            "font-size:18px;font-weight:bold;color:#f8f8ff;"
            "background:#111827;border-radius:10px;padding:1px 5px;"
        )
        top.addWidget(self._value_lbl)
        body.addLayout(top)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(2)
        self._scarf_btn = self._make_toggle("スカーフ")
        self._scarf_btn.toggled.connect(self.toggled.emit)
        controls.addWidget(self._scarf_btn)
        self._minus_btn = self._make_rank_button("-")
        self._minus_btn.clicked.connect(lambda: self._emit_rank(-1))
        controls.addWidget(self._minus_btn)
        self._rank_lbl = QLabel("0")
        self._rank_lbl.setFixedSize(28, 24)
        self._rank_lbl.setAlignment(Qt.AlignCenter)
        self._rank_lbl.setStyleSheet(
            "font-size:12px;font-weight:bold;color:#cdd6f4;background:#111827;"
            "border:1px solid #45475a;border-radius:4px;"
        )
        controls.addWidget(self._rank_lbl)
        self._plus_btn = self._make_rank_button("+")
        self._plus_btn.clicked.connect(lambda: self._emit_rank(1))
        controls.addWidget(self._plus_btn)
        self._ability_btn = self._make_toggle("特性")
        self._ability_btn.toggled.connect(self.toggled.emit)
        controls.addWidget(self._ability_btn)
        controls.addStretch()
        body.addLayout(controls)

        profiles = QHBoxLayout()
        profiles.setContentsMargins(0, 0, 0, 0)
        profiles.setSpacing(3)
        self._profile_btns: dict[str, QToolButton] = {}
        for code, text in (
            ("fastest", "最速"),
            ("junsoku", "準速"),
            ("none", "無振り"),
        ):
            btn = self._make_toggle(text)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda checked, c=code: self._emit_profile(c, checked))
            self._profile_btns[code] = btn
            profiles.addWidget(btn)
        profiles.addStretch()
        body.addLayout(profiles)

    def set_entry(self, entry: _SpeedEntry | None) -> None:
        if entry is None or entry.pokemon is None:
            self._side = ""
            self._index = -1
            self._sprite_lbl.setPixmap(QPixmap())
            self._base_speed_lbl.setText("---")
            self._name_lbl.setText("---")
            self._value_lbl.setText("---")
            for widget in (
                self._scarf_btn,
                self._minus_btn,
                self._rank_lbl,
                self._plus_btn,
                self._ability_btn,
                *self._profile_btns.values(),
            ):
                widget.setEnabled(False)
            self._set_toggle_checked(self._scarf_btn, False)
            self._set_toggle_checked(self._ability_btn, False)
            self._ability_btn.setVisible(False)
            self._rank_lbl.setText("0")
            for btn in self._profile_btns.values():
                self._set_toggle_checked(btn, False)
            return

        self._side = entry.side
        self._index = entry.index
        pokemon = entry.pokemon
        pm = sprite_pixmap_or_zukan(
            pokemon.name_ja or "",
            self._SPRITE_SIZE,
            self._SPRITE_SIZE,
            name_en=pokemon.name_en or "",
        )
        self._sprite_lbl.setPixmap(pm if pm else QPixmap())
        self._base_speed_lbl.setText("S{}".format(_base_speed(pokemon) or "---"))
        display_name = pokemon.name_ja or pokemon.name_en or "---"
        self._name_lbl.setText(display_name)
        self._name_lbl.setToolTip(display_name)
        self._value_lbl.setText(str(entry.value))
        self._rank_lbl.setText(_format_rank(entry.state.rank))
        for widget in (
            self._scarf_btn,
            self._minus_btn,
            self._rank_lbl,
            self._plus_btn,
            self._ability_btn,
            *self._profile_btns.values(),
        ):
            widget.setEnabled(True)
        self._set_toggle_checked(self._scarf_btn, entry.state.scarf_on)
        self._ability_btn.setVisible(entry.ability_mult != 1.0)
        self._ability_btn.setText(_ability_label(pokemon.ability))
        self._set_toggle_checked(self._ability_btn, entry.state.ability_on)
        active_profile = entry.state.profile_override or _speed_profile_code(pokemon)
        for code, btn in self._profile_btns.items():
            self._set_toggle_checked(btn, active_profile == code)

    def scarf_checked(self) -> bool:
        return self._scarf_btn.isChecked()

    def ability_checked(self) -> bool:
        return self._ability_btn.isChecked()

    def _emit_rank(self, delta: int) -> None:
        if not self._side or self._index < 0:
            return
        current = _parse_rank(self._rank_lbl.text())
        self.rank_changed.emit(self._side, self._index, max(-6, min(6, current + delta)))

    def _emit_profile(self, code: str, checked: bool) -> None:
        if not self._side or self._index < 0:
            return
        self.profile_changed.emit(self._side, self._index, code if checked else "")

    @staticmethod
    def _make_toggle(text: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setCheckable(True)
        btn.setFixedHeight(24)
        btn.setStyleSheet(
            "QToolButton{background:#313244;border:1px solid #45475a;border-radius:4px;"
            "font-size:11px;color:#cdd6f4;padding:1px 4px;}"
            "QToolButton:checked{background:#1f3d32;border-color:#a6e3a1;color:#a6e3a1;"
            "font-weight:bold;}"
            "QToolButton:hover{border-color:#89b4fa;}"
        )
        return btn

    @staticmethod
    def _make_rank_button(text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(22, 22)
        color = "#f38ba8" if text == "-" else "#a6e3a1"
        btn.setStyleSheet(
            "QPushButton{{background:#313244;border:1px solid {0};color:{0};"
            "border-radius:4px;font-size:12px;font-weight:bold;padding:0px;margin:0px;"
            "min-height:22px;max-height:22px;min-width:22px;max-width:22px;}}"
            "QPushButton:hover{{background:#45475a;}}".format(color)
        )
        return btn

    @staticmethod
    def _set_toggle_checked(btn: QToolButton, checked: bool) -> None:
        btn.blockSignals(True)
        btn.setChecked(checked)
        btn.blockSignals(False)


class SpeedCompareWidget(QWidget):
    def __init__(
        self,
        rank_changed: Callable[[str, int, int], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._rank_changed_cb = rank_changed
        self._states: dict[tuple[str, int], _SpeedState] = {}
        self._rows: dict[tuple[str, int], _SpeedRow] = {}
        self._parties: dict[str, list[PokemonInstance | None]] = {"my": [], "opp": []}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self._toggle_btn = QPushButton("▷ すばやさ比較")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(False)
        self._toggle_btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#89b4fa;"
            "font-size:15px;font-weight:bold;text-align:left;padding:0 0 0 6px;}"
            "QPushButton:hover{color:#cdd6f4;}"
        )
        self._toggle_btn.toggled.connect(self._set_open)
        root.addWidget(self._toggle_btn)

        self._content = QFrame()
        self._content.setStyleSheet(
            "QFrame{background:#111827;border:1px solid #313244;border-radius:8px;}"
        )
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(6, 6, 6, 6)
        content_layout.setSpacing(5)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        for text, color in (("自分", "#89b4fa"), ("相手", "#f9e2af")):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                "font-size:12px;font-weight:bold;color:{};background:#181825;"
                "border-radius:8px;padding:2px;".format(color)
            )
            header.addWidget(lbl, 1)
        content_layout.addLayout(header)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        for col, side in enumerate(("my", "opp")):
            for row_index in range(6):
                row = _SpeedRow()
                row.rank_changed.connect(self._set_rank)
                row.profile_changed.connect(self._set_profile)
                row.toggled.connect(self._on_row_toggled)
                grid.addWidget(row, row_index, col)
                self._rows[(side, row_index)] = row
        content_layout.addLayout(grid)
        self._content.setVisible(False)
        root.addWidget(self._content)

    def set_parties(
        self,
        my_party: list[PokemonInstance | None],
        opp_party: list[PokemonInstance | None],
    ) -> None:
        self._parties = {
            "my": (list(my_party) + [None] * 6)[:6],
            "opp": (list(opp_party) + [None] * 6)[:6],
        }
        self._ensure_states()
        self.refresh()

    def set_active_rank(self, side: str | None, index: int | None, rank: int) -> None:
        if side not in ("my", "opp") or index is None or not 0 <= index < 6:
            return
        key = (side, index)
        state = self._states.get(key)
        if state is None:
            return
        self._states[key] = _SpeedState(
            scarf_on=state.scarf_on,
            rank=max(-6, min(6, int(rank))),
            ability_on=state.ability_on,
            profile_override=state.profile_override,
            signature=state.signature,
        )

    def refresh(self) -> None:
        for side in ("my", "opp"):
            entries = [self._entry_for(side, idx) for idx in range(6)]
            entries.sort(key=lambda entry: (entry.pokemon is not None, entry.value), reverse=True)
            for row_index, entry in enumerate(entries):
                row_entry = entry if entry.pokemon is not None else None
                self._rows[(side, row_index)].set_entry(row_entry)

    def _set_open(self, checked: bool) -> None:
        self._content.setVisible(checked)
        self._toggle_btn.setText("▽ すばやさ比較" if checked else "▷ すばやさ比較")

    def _ensure_states(self) -> None:
        live_keys: set[tuple[str, int]] = set()
        for side, party in self._parties.items():
            for idx, pokemon in enumerate((party + [None] * 6)[:6]):
                key = (side, idx)
                live_keys.add(key)
                signature = _signature(pokemon)
                state = self._states.get(key)
                if state is None or state.signature != signature:
                    self._states[key] = _SpeedState(
                        scarf_on=_has_scarf(pokemon),
                        rank=0,
                        ability_on=False,
                        profile_override="",
                        signature=signature,
                    )
        for key in list(self._states):
            if key not in live_keys:
                del self._states[key]

    def _entry_for(self, side: str, index: int) -> _SpeedEntry:
        party = self._parties.get(side, [])
        pokemon = party[index] if index < len(party) else None
        state = self._states.get((side, index), _SpeedState())
        ability_mult = _speed_ability_mult(pokemon)
        value = _effective_speed(pokemon, state, ability_mult)
        return _SpeedEntry(side, index, pokemon, value, state, ability_mult)

    def _set_rank(self, side: str, index: int, rank: int) -> None:
        key = (side, index)
        state = self._states.get(key)
        if state is None:
            return
        self._states[key] = _SpeedState(
            scarf_on=state.scarf_on,
            rank=rank,
            ability_on=state.ability_on,
            profile_override=state.profile_override,
            signature=state.signature,
        )
        if self._rank_changed_cb is not None:
            self._rank_changed_cb(side, index, rank)
        self.refresh()

    def _set_profile(self, side: str, index: int, profile: str) -> None:
        key = (side, index)
        state = self._states.get(key)
        if state is None:
            return
        self._states[key] = _SpeedState(
            scarf_on=state.scarf_on,
            rank=state.rank,
            ability_on=state.ability_on,
            profile_override=profile,
            signature=state.signature,
        )
        self.refresh()

    def _on_row_toggled(self) -> None:
        for row in self._rows.values():
            side = row._side
            index = row._index
            if not side or index < 0:
                continue
            key = (side, index)
            state = self._states.get(key)
            if state is None:
                continue
            self._states[key] = _SpeedState(
                scarf_on=row.scarf_checked(),
                rank=state.rank,
                ability_on=row.ability_checked(),
                profile_override=state.profile_override,
                signature=state.signature,
            )
        self.refresh()


def _signature(pokemon: PokemonInstance | None) -> tuple[str, str, str]:
    if pokemon is None:
        return ("", "", "")
    return (
        pokemon.name_ja or pokemon.name_en or "",
        pokemon.item or "",
        pokemon.ability or "",
    )


def _has_scarf(pokemon: PokemonInstance | None) -> bool:
    return ((pokemon.item if pokemon else "") or "").strip() in _SCARF_ITEMS


def _speed_ability_mult(pokemon: PokemonInstance | None) -> float:
    if pokemon is None:
        return 1.0
    ability = (pokemon.ability or "").strip()
    if ability in ("こだいかっせい", "Protosynthesis", "クォークチャージ", "Quark Drive"):
        other_stats = (
            int(pokemon.attack or 0),
            int(pokemon.defense or 0),
            int(pokemon.sp_attack or 0),
            int(pokemon.sp_defense or 0),
        )
        if int(pokemon.speed or 0) <= max(other_stats):
            return 1.0
    return _SPEED_ABILITY_MULT.get(ability, 1.0)


def _base_speed(pokemon: PokemonInstance | None) -> int:
    species = _species_for(pokemon)
    return int(species.base_speed or 0) if species is not None else 0


def _species_for(pokemon: PokemonInstance | None) -> SpeciesInfo | None:
    if pokemon is None:
        return None
    try:
        from src.ui.damage_panel_species import resolve_species
    except ImportError:
        return None
    return resolve_species(pokemon, pokemon.name_ja)


def _effective_speed(
    pokemon: PokemonInstance | None,
    state: _SpeedState,
    ability_mult: float,
) -> int:
    if pokemon is None:
        return 0
    if state.profile_override:
        speed = _profile_speed(pokemon, state.profile_override)
    else:
        speed = _raw_speed(pokemon)
    mult = _SPEED_RANK_MULT.get(max(-6, min(6, state.rank)), 1.0)
    if state.scarf_on:
        mult *= 1.5
    if state.ability_on:
        mult *= ability_mult
    return int(speed * mult)


def _raw_speed(pokemon: PokemonInstance) -> int:
    try:
        from src.calc.calc_utils import calc_stat, get_nature_mult
    except ImportError:
        return _fallback_raw_speed(pokemon)

    species = _species_for(pokemon)
    if species is None:
        return _fallback_raw_speed(pokemon)
    iv = pokemon.iv_speed if pokemon.iv_speed > 0 else 31
    return calc_stat(
        species.base_speed,
        iv,
        pokemon.ev_speed or 0,
        level=pokemon.level or 50,
        nature_mult=get_nature_mult(pokemon.nature or "まじめ", "speed"),
    )


def _fallback_raw_speed(pokemon: PokemonInstance) -> int:
    speed = max(0, int(pokemon.speed or 0))
    if _has_scarf(pokemon) and speed > 0:
        return int(speed / 1.5)
    return speed


def _profile_speed(pokemon: PokemonInstance, profile: str) -> int:
    try:
        from src.calc.calc_utils import calc_stat, get_nature_mult
    except ImportError:
        return _fallback_raw_speed(pokemon)

    species = _species_for(pokemon)
    if species is None:
        return _fallback_raw_speed(pokemon)
    if profile == "fastest":
        ev = _MAX_SPEED_EV * 8
        nature_mult = 1.1
    elif profile == "junsoku":
        ev = _MAX_SPEED_EV * 8
        nature_mult = 1.0
    elif profile == "none":
        ev = 0
        nature_mult = 1.0
    else:
        return _raw_speed(pokemon)
    iv = pokemon.iv_speed if pokemon.iv_speed > 0 else 31
    return calc_stat(
        species.base_speed,
        iv,
        ev,
        level=pokemon.level or 50,
        nature_mult=nature_mult or get_nature_mult("まじめ", "speed"),
    )


def _format_rank(rank: int) -> str:
    if rank > 0:
        return "+{}".format(rank)
    return str(rank)


def _parse_rank(text: str) -> int:
    try:
        return int((text or "0").replace("+", ""))
    except ValueError:
        return 0


def _speed_profile_code(pokemon: PokemonInstance) -> str:
    ev_pts = max(0, int((pokemon.ev_speed or 0) / 8))
    boost, reduce = NATURES_JA.get((pokemon.nature or "").strip(), (None, None))
    if ev_pts == 0:
        return "none"
    if ev_pts >= _MAX_SPEED_EV and boost == "speed":
        return "fastest"
    if ev_pts >= _MAX_SPEED_EV and reduce != "speed" and boost != "speed":
        return "junsoku"
    return ""


def _ability_label(ability: str) -> str:
    ability = (ability or "").strip()
    if ability in ("こだいかっせい", "Protosynthesis"):
        return "古代"
    if ability in ("クォークチャージ", "Quark Drive"):
        return "クォーク"
    if len(ability) > 4:
        return "特性"
    return ability or "特性"
