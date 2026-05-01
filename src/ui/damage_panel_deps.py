"""Shared dependencies for extracted damage_panel_* modules.

This module intentionally centralizes symbols used by extracted modules so they
do not depend on `src.ui.damage_panel` module globals.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import math
from typing import Optional

from PyQt5.QtCore import QPointF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGroupBox, QScrollArea, QPushButton, QSizePolicy,
    QSpinBox, QComboBox, QCheckBox, QSplitter, QDialog,
    QSlider,
)

from src.models import PokemonInstance, MoveInfo, SpeciesInfo
from src.data import zukan_client
from src.ui.damage_panel_cards import AttackerCard as _AttackerCard
from src.ui.damage_panel_cards import DefenderCard as _DefenderCard
from src.ui.damage_panel_forms import FORM_NAME_TO_GROUP as _FORM_NAME_TO_GROUP
from src.ui.damage_panel_form_apply import apply_form as _apply_form_impl
from src.ui.damage_panel_math import nature_mult_from_name as _nature_mult_from_name
from src.ui.damage_panel_math import rank_mult as _rank_mult
from src.ui.damage_panel_move_section import MoveSection as _MoveSection
from src.ui.damage_panel_panels import _AttackerPanel, _DefenderPanel
from src.ui.damage_panel_party import PartySlot as _PartySlot
from src.ui.damage_panel_species import species_from_name_en as _species_from_name_en
from src.ui.damage_panel_ui_helpers import row_label as _row_label
from src.ui.damage_panel_ui_helpers import sep as _sep
from src.ui.damage_panel_widgets import RadioGroup as _RadioGroup
from src.ui.damage_panel_widgets import ToggleBtn as _ToggleBtn
from src.ui.ui_utils import open_pokemon_edit_dialog
from src.ui.damage_panel_form_data import (
    FORM_ABILITY_JA as _FORM_ABILITY_JA,
    FORM_MISSING_MEGA_STATS as _FORM_MISSING_MEGA_STATS,
    FORM_POKEAPI_EN as _FORM_POKEAPI_EN,
)


def _normalize_form_name(name_ja: str) -> str:
    from src.ui.damage_panel_forms import normalize_form_name

    return normalize_form_name(name_ja, _FORM_NAME_TO_GROUP)


def _form_group(name_ja: str) -> list[str]:
    from src.ui.damage_panel_forms import form_group

    return form_group(name_ja, _FORM_NAME_TO_GROUP)


def _next_form_name(name_ja: str) -> Optional[str]:
    from src.ui.damage_panel_forms import next_form_name

    return next_form_name(name_ja, _FORM_NAME_TO_GROUP)


def _apply_form(p: PokemonInstance, form_name: str, original_ability: str = "") -> PokemonInstance:
    return _apply_form_impl(
        pokemon=p,
        form_name=form_name,
        original_ability=original_ability,
        form_name_to_group=_FORM_NAME_TO_GROUP,
        form_pokeapi_en=_FORM_POKEAPI_EN,
        form_missing_mega_stats=_FORM_MISSING_MEGA_STATS,
        form_ability_ja=_FORM_ABILITY_JA,
    )
