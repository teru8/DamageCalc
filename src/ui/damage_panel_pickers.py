from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtWidgets import QDialogButtonBox, QVBoxLayout, QWidget
from src.ui.ui_utils import make_dialog

if TYPE_CHECKING:
    from src.models import PokemonInstance


def show_pick_dialog(
    title: str,
    items: list,
    separator_after: int | None,
    current: str,
    parent: QWidget,
    completer_items: list[str] | None = None,
) -> str | None:
    from src.ui.pokemon_edit_dialog import SuggestComboBox

    dlg = make_dialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(320)
    lay = QVBoxLayout(dlg)
    combo = SuggestComboBox(parent=dlg)
    combo.set_items(items, preserve_text=False, separator_after=separator_after, completer_items=completer_items)
    combo.set_text(current)
    lay.addWidget(combo)
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)
    if dlg.exec_():
        return combo.current_text_stripped()
    return None


def pick_ability(pokemon: "PokemonInstance", parent: QWidget) -> str | None:
    from src.constants import ABILITIES_JA
    from src.data import database as db
    from src.ui.damage_panel_ability import _pokeapi_ability_names_for_pokemon
    from src.ui.pokemon_edit_dialog import _build_ranked_options, _unique

    all_abilities = sorted(_unique(list(ABILITIES_JA)))
    usage_name = pokemon.usage_name or pokemon.name_ja
    species_abilities = _pokeapi_ability_names_for_pokemon(pokemon.name_en) if pokemon.name_en else []
    usage_abilities = db.get_abilities_by_usage(usage_name) if usage_name else []
    if not usage_abilities and pokemon.species_id:
        base = db.get_species_by_id(pokemon.species_id)
        if base and base.name_ja != usage_name:
            usage_abilities = db.get_abilities_by_usage(base.name_ja)
    ranked = _unique(species_abilities + usage_abilities)
    items, sep = _build_ranked_options(ranked, all_abilities)
    return show_pick_dialog("特性を選択", items, sep, pokemon.ability or "", parent)


def pick_item(pokemon: "PokemonInstance", parent: QWidget) -> str | None:
    from src.data.item_dictionary import ITEMS_JA
    from src.data import database as db
    from src.data.item_catalog import get_item_names
    from src.ui.pokemon_edit_dialog import _build_ranked_options, _unique

    list_items = sorted(_unique(list(ITEMS_JA)))
    completer_items = sorted(_unique(list(ITEMS_JA) + get_item_names()))
    usage_name = pokemon.usage_name or pokemon.name_ja
    ranked = _unique(db.get_items_by_usage(usage_name) if usage_name else [])
    if not ranked and pokemon.species_id:
        base = db.get_species_by_id(pokemon.species_id)
        if base and base.name_ja != usage_name:
            ranked = _unique(db.get_items_by_usage(base.name_ja))
    items, sep = _build_ranked_options(ranked, list_items)
    return show_pick_dialog("持ち物を選択", items, sep, pokemon.item or "", parent, completer_items=completer_items)
