from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from src.models import PokemonInstance


def show_pick_dialog(
    title: str,
    items: list,
    separator_after: int | None,
    current: str,
    parent: QWidget,
) -> str | None:
    from src.ui.pokemon_edit_dialog import SuggestComboBox

    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(320)
    lay = QVBoxLayout(dlg)
    combo = SuggestComboBox(parent=dlg)
    combo.set_items(items, preserve_text=False, separator_after=separator_after)
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
    from src.ui.pokemon_edit_dialog import _build_ranked_options, _unique

    all_abilities = sorted(_unique(list(ABILITIES_JA)))
    usage_name = pokemon.usage_name or pokemon.name_ja
    ranked = _unique(db.get_abilities_by_usage(usage_name) if usage_name else [])
    items, sep = _build_ranked_options(ranked, all_abilities)
    return show_pick_dialog("特性を選択", items, sep, pokemon.ability or "", parent)


def pick_item(pokemon: "PokemonInstance", parent: QWidget) -> str | None:
    from src.data.item_dictionary import ITEMS_JA
    from src.data import database as db
    from src.data.item_catalog import get_item_names
    from src.ui.pokemon_edit_dialog import _build_ranked_options, _unique

    all_items = sorted(_unique(list(ITEMS_JA) + get_item_names()))
    usage_name = pokemon.usage_name or pokemon.name_ja
    ranked = _unique(db.get_items_by_usage(usage_name) if usage_name else [])
    items, sep = _build_ranked_options(ranked, all_items)
    return show_pick_dialog("持ち物を選択", items, sep, pokemon.item or "", parent)
