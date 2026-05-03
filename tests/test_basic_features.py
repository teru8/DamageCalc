"""
基本機能テスト

テスト対象:
  1. 相手PTのカメラ読込 → パネルへの個体反映
  2. PTパネル右クリック → PokemonEditDialog生成、使用率ランキングから選択 → パネル反映
  3. ①②によってSmogonからダメージ計算結果が返ること
"""
from __future__ import annotations

import dataclasses
import os
import copy
import json
from unittest.mock import MagicMock, patch, PropertyMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication

from src.models import BattleState, MoveInfo, PokemonInstance, SpeciesInfo
from src.calc.smogon_bridge import (
    SmogonBridge,
    field_to_dict,
    move_to_dict,
    pokemon_to_attacker_dict,
    pokemon_to_defender_dict,
)


# ─── fixture ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def pikachu_species() -> SpeciesInfo:
    return SpeciesInfo(
        species_id=25,
        name_ja="ピカチュウ",
        name_en="pikachu",
        type1="electric",
        type2="",
        base_hp=35,
        base_attack=55,
        base_defense=40,
        base_sp_attack=50,
        base_sp_defense=50,
        base_speed=90,
        weight_kg=6.0,
    )


@pytest.fixture
def pikachu(pikachu_species: SpeciesInfo) -> PokemonInstance:
    return PokemonInstance(
        species_id=pikachu_species.species_id,
        name_ja=pikachu_species.name_ja,
        name_en=pikachu_species.name_en,
        types=["electric"],
        level=50,
        nature="おくびょう",
        ability="せいでんき",
        item="でんきだま",
        ev_sp_attack=252,
        ev_speed=252,
        ev_hp=4,
        moves=["10まんボルト", "めざめるパワー", "でんじは", "なきごえ"],
    )


@pytest.fixture
def blissey() -> PokemonInstance:
    return PokemonInstance(
        species_id=242,
        name_ja="ハピナス",
        name_en="blissey",
        types=["normal"],
        level=50,
        nature="ずぶとい",
        ability="しぜんかいふく",
        item="たべのこし",
        ev_hp=252,
        ev_defense=252,
    )


@pytest.fixture
def thunderbolt() -> MoveInfo:
    return MoveInfo(
        name_ja="10まんボルト",
        name_en="thunderbolt",
        type_name="electric",
        category="special",
        power=90,
        accuracy=100,
        pp=15,
    )


# ─── ① 相手PTカメラ読込 → パネル反映 ────────────────────────────────────────────

class TestOpponentPartyDetectionToPanel:
    """
    テスト方針:
    - detect_opponent_party() の戻り値（スロット辞書リスト）を固定のモックで代替
    - _build_usage_template_pokemon() の内部DB呼び出しをモック
    - BattleState と DamagePanel.set_opponent_options の呼び出しを検証
    """

    @pytest.fixture
    def detection_slot_results(self) -> list[dict]:
        """detect_opponent_party() が返すスロット情報のサンプル"""
        return [
            {"slot_index": 0, "occupied": True,  "name_ja": "ピカチュウ", "types": ["electric"], "confidence": 0.92},
            {"slot_index": 1, "occupied": True,  "name_ja": "ハピナス",   "types": ["normal"],   "confidence": 0.87},
            {"slot_index": 2, "occupied": True,  "name_ja": "カビゴン",   "types": ["normal"],   "confidence": 0.80},
            {"slot_index": 3, "occupied": False, "name_ja": "",           "types": [],           "confidence": 0.0},
            {"slot_index": 4, "occupied": False, "name_ja": "",           "types": [],           "confidence": 0.0},
            {"slot_index": 5, "occupied": False, "name_ja": "",           "types": [],           "confidence": 0.0},
        ]

    def _make_species(self, species_id: int, name_ja: str, name_en: str,
                      type1: str, type2: str = "") -> SpeciesInfo:
        return SpeciesInfo(
            species_id=species_id, name_ja=name_ja, name_en=name_en,
            type1=type1, type2=type2,
            base_hp=80, base_attack=80, base_defense=80,
            base_sp_attack=80, base_sp_defense=80, base_speed=80,
            weight_kg=30.0,
        )

    def test_detect_result_structure(self, detection_slot_results: list[dict]) -> None:
        """detect_opponent_party の想定戻り値がパーサに必要なキーを持つことを確認"""
        for slot in detection_slot_results:
            assert "slot_index" in slot
            assert "occupied" in slot
            assert "name_ja" in slot
            assert "types" in slot

    def test_occupied_slot_parsed_to_pokemon(
        self, detection_slot_results: list[dict], pikachu_species: SpeciesInfo
    ) -> None:
        """
        occupied スロットの name_ja がテキストマッチャー経由でDBから種族取得され
        PokemonInstance に変換されること
        """
        with (
            patch("src.recognition.text_matcher.match_species_name", side_effect=lambda n: n),
            patch("src.data.database.get_species_by_name_ja", return_value=pikachu_species),
            patch("src.data.database.get_abilities_by_usage", return_value=["せいでんき"]),
            patch("src.data.database.get_items_by_usage", return_value=["でんきだま"]),
            patch("src.data.database.get_natures_by_usage", return_value=["おくびょう"]),
            patch("src.data.database.get_effort_spreads_by_usage", return_value=[]),
            patch("src.data.database.get_moves_by_usage", return_value=[]),
        ):
            from src.ui import main_window_handlers as mwh

            mock_self = MagicMock()
            mock_self._syncing_battle_state_to_panels = False

            result = mwh._build_usage_template_pokemon(mock_self, "ピカチュウ")

        assert result is not None, "occupied スロットから PokemonInstance が生成されること"
        assert result.name_ja == "ピカチュウ"
        assert result.ability == "せいでんき"
        assert result.item == "でんきだま"
        assert result.nature == "おくびょう"
        assert "electric" in result.types

    def test_empty_name_returns_none(self) -> None:
        """name_ja が空の場合は None を返すこと"""
        with patch("src.recognition.text_matcher.match_species_name", return_value=None):
            from src.ui import main_window_handlers as mwh

            mock_self = MagicMock()
            result = mwh._build_usage_template_pokemon(mock_self, "")

        assert result is None

    def test_unmatched_name_returns_none(self) -> None:
        """DBに存在しない種族名は None を返すこと"""
        with (
            patch("src.recognition.text_matcher.match_species_name", return_value="不明なポケモン"),
            patch("src.data.database.get_species_by_name_ja", return_value=None),
        ):
            from src.ui import main_window_handlers as mwh

            mock_self = MagicMock()
            result = mwh._build_usage_template_pokemon(mock_self, "不明なポケモン")

        assert result is None

    def test_detection_slots_build_correct_party(
        self, detection_slot_results: list[dict]
    ) -> None:
        """
        スロット結果からパーティ配列が構築され、
        - occupied=True スロットは PokemonInstance
        - occupied=False スロットは None
        となること
        """
        species_db = {
            "ピカチュウ": self._make_species(25,  "ピカチュウ", "pikachu",  "electric"),
            "ハピナス":   self._make_species(242, "ハピナス",   "blissey",  "normal"),
            "カビゴン":   self._make_species(143, "カビゴン",   "snorlax",  "normal"),
        }

        with (
            patch("src.recognition.text_matcher.match_species_name", side_effect=lambda n: n),
            patch("src.data.database.get_species_by_name_ja", side_effect=lambda n: species_db.get(n)),
            patch("src.data.database.get_abilities_by_usage", return_value=[]),
            patch("src.data.database.get_items_by_usage", return_value=[]),
            patch("src.data.database.get_natures_by_usage", return_value=[]),
            patch("src.data.database.get_effort_spreads_by_usage", return_value=[]),
            patch("src.data.database.get_moves_by_usage", return_value=[]),
        ):
            from src.ui import main_window_handlers as mwh

            mock_self = MagicMock()
            detected_party: list[PokemonInstance | None] = []
            for slot in detection_slot_results[:6]:
                if not slot.get("occupied"):
                    detected_party.append(None)
                    continue
                name = (slot.get("name_ja") or "").strip()
                pokemon = mwh._build_usage_template_pokemon(mock_self, name) if name else None
                detected_party.append(pokemon)

        party = (detected_party + [None] * 6)[:6]
        occupied = [p for p in party if p is not None]
        empty = [p for p in party if p is None]

        assert len(party) == 6, "パーティは常に6枠"
        assert len(occupied) == 3, "occupied スロット数が一致"
        assert len(empty) == 3, "空スロット数が一致"
        names = [p.name_ja for p in occupied]
        assert "ピカチュウ" in names
        assert "ハピナス" in names
        assert "カビゴン" in names

    def test_battle_state_updated_and_panel_synced(
        self, detection_slot_results: list[dict], pikachu_species: SpeciesInfo
    ) -> None:
        """
        _sync_battle_state_to_panels が呼ばれると
        DamagePanel.set_opponent_options に opponent_party が渡されること
        """
        from src.ui import main_window_handlers as mwh

        battle_state = BattleState()
        battle_state.opponent_party = [None] * 6

        mock_damage_panel = MagicMock()
        mock_self = MagicMock()
        mock_self._battle_state = battle_state
        mock_self._damage_panel = mock_damage_panel
        mock_self._syncing_battle_state_to_panels = False

        pikachu_instance = PokemonInstance(
            species_id=25, name_ja="ピカチュウ", name_en="pikachu",
            types=["electric"], ability="せいでんき",
        )
        battle_state.opponent_party = [pikachu_instance, None, None, None, None, None]
        battle_state.opponent_pokemon = pikachu_instance

        mwh._sync_battle_state_to_panels(mock_self)

        mock_damage_panel.set_opponent_options.assert_called_once()
        call_args = mock_damage_panel.set_opponent_options.call_args
        party_arg = call_args[0][0]
        assert any(p is not None and p.name_ja == "ピカチュウ" for p in party_arg)


# ─── ② EditDialog 生成 → 使用率選択 → パネル反映 ───────────────────────────────

class TestEditDialogUsageSelectionToPanel:
    """
    テスト方針:
    - PokemonEditDialog を offscreen Qt で起動（save_to_db=False）
    - ダイアログの _save() を呼び、get_pokemon() が正しい PokemonInstance を返すことを検証
    - DamagePanel への反映は BattleState 更新 + set_my_pokemon / set_opponent_options の呼び出しで確認
    """

    def test_edit_dialog_save_returns_pokemon_instance(
        self, qapp: QApplication, pikachu: PokemonInstance
    ) -> None:
        """
        PokemonEditDialog に PokemonInstance を渡して保存すると
        get_pokemon() が同名の PokemonInstance を返すこと
        """
        from src.ui.pokemon_edit_dialog_main import PokemonEditDialog

        dlg = PokemonEditDialog(pikachu, parent=None, save_to_db=False)
        try:
            dlg._save(save_to_db_override=False)
            result = dlg.get_pokemon()
        finally:
            dlg.close()
            dlg.deleteLater()

        assert result is not None, "保存後に PokemonInstance が返ること"
        assert result.name_ja == "ピカチュウ"

    def test_edit_dialog_new_entry_with_name(
        self, qapp: QApplication
    ) -> None:
        """
        新規作成で名前を設定して保存すると PokemonInstance が返ること
        """
        from src.ui.pokemon_edit_dialog_main import PokemonEditDialog

        dlg = PokemonEditDialog(None, parent=None, save_to_db=False)
        try:
            dlg.name_combo.set_text("ハピナス")
            dlg._on_name_changed("ハピナス")
            dlg._save(save_to_db_override=False)
            result = dlg.get_pokemon()
        finally:
            dlg.close()
            dlg.deleteLater()

        assert result is not None, "新規エントリでも保存後に PokemonInstance が返ること"

    def test_edit_dialog_reflects_ability_and_item(
        self, qapp: QApplication, pikachu: PokemonInstance
    ) -> None:
        """
        ダイアログに渡した特性・持ち物が保存後の PokemonInstance に反映されること
        """
        from src.ui.pokemon_edit_dialog_main import PokemonEditDialog

        dlg = PokemonEditDialog(pikachu, parent=None, save_to_db=False)
        try:
            dlg.ability_combo.set_text("ひらいしん")
            dlg.item_combo.set_text("こだわりめがね")
            dlg._save(save_to_db_override=False)
            result = dlg.get_pokemon()
        finally:
            dlg.close()
            dlg.deleteLater()

        assert result is not None
        assert result.ability == "ひらいしん"
        assert result.item == "こだわりめがね"

    def test_panel_set_my_pokemon_called_after_edit(self) -> None:
        """
        my_party 更新後に _sync_battle_state_to_panels を呼ぶと
        DamagePanel.set_my_pokemon が正しく呼ばれること
        """
        from src.ui import main_window_handlers as mwh

        pikachu_instance = PokemonInstance(
            species_id=25, name_ja="ピカチュウ", name_en="pikachu",
            types=["electric"],
        )
        battle_state = BattleState()
        battle_state.my_party = [pikachu_instance, None, None, None, None, None]
        battle_state.my_pokemon = pikachu_instance

        mock_damage_panel = MagicMock()
        mock_self = MagicMock()
        mock_self._battle_state = battle_state
        mock_self._damage_panel = mock_damage_panel
        mock_self._syncing_battle_state_to_panels = False

        mwh._sync_battle_state_to_panels(mock_self)

        mock_damage_panel.set_my_party.assert_called_once()
        mock_damage_panel.set_my_pokemon.assert_called_once()
        pokemon_arg = mock_damage_panel.set_my_pokemon.call_args[0][0]
        assert pokemon_arg.name_ja == "ピカチュウ"

    def test_panel_opponent_options_from_usage_selection(self) -> None:
        """
        使用率ランキングから選択したポケモンで opponent_party を組み、
        _sync_battle_state_to_panels → set_opponent_options が正しいパーティを受け取ること
        """
        from src.ui import main_window_handlers as mwh

        # 使用率1位を選択した想定
        selected = PokemonInstance(
            species_id=130, name_ja="ギャラドス", name_en="gyarados",
            types=["water", "flying"], ability="じしんかじょう",
        )
        battle_state = BattleState()
        battle_state.opponent_party = [selected] + [None] * 5
        battle_state.opponent_pokemon = selected

        mock_damage_panel = MagicMock()
        mock_self = MagicMock()
        mock_self._battle_state = battle_state
        mock_self._damage_panel = mock_damage_panel
        mock_self._syncing_battle_state_to_panels = False

        mwh._sync_battle_state_to_panels(mock_self)

        mock_damage_panel.set_opponent_options.assert_called_once()
        party_arg = mock_damage_panel.set_opponent_options.call_args[0][0]
        assert party_arg[0].name_ja == "ギャラドス"


# ─── ③ Smogon ダメージ計算結果 ──────────────────────────────────────────────────

class TestSmogonDamageCalc:
    """
    テスト方針:
    - pokemon_to_attacker_dict / defender_dict が必要キーを含む辞書を返すことを検証
    - SmogonBridge._send をモックして calc() の入出力変換を検証
    - エラー応答時のフォールバック (0, 0, True) を検証
    """

    def test_attacker_dict_has_required_keys(self, pikachu: PokemonInstance) -> None:
        """pokemon_to_attacker_dict が Smogon bridge に必要なキーを返すこと"""
        result = pokemon_to_attacker_dict(pikachu, apply_both=True)

        assert "species" in result, "species キーが必要"
        assert "level" in result
        assert "nature" in result
        assert "evs" in result
        assert result["species"] != "", "species が空でないこと"
        assert result["level"] == 50

    def test_defender_dict_has_required_keys(self, blissey: PokemonInstance) -> None:
        """pokemon_to_defender_dict が Smogon bridge に必要なキーを返すこと"""
        result = pokemon_to_defender_dict(blissey)

        assert "species" in result
        assert "level" in result
        assert "nature" in result
        assert "evs" in result

    def test_move_dict_has_required_keys(self, thunderbolt: MoveInfo) -> None:
        """move_to_dict が Smogon bridge に必要なキーを返すこと"""
        result = move_to_dict(thunderbolt)

        assert "name" in result
        assert result["name"] != ""

    def test_field_dict_default(self) -> None:
        """field_to_dict がデフォルトで有効な辞書を返すこと"""
        result = field_to_dict()
        assert isinstance(result, dict)

    def test_calc_returns_correct_damage(
        self, pikachu: PokemonInstance, blissey: PokemonInstance, thunderbolt: MoveInfo
    ) -> None:
        """
        SmogonBridge._send をモックして calc() が (min, max, is_error) を正しく返すこと
        """
        bridge = SmogonBridge.__new__(SmogonBridge)
        bridge._proc = None
        bridge._io_lock = __import__("threading").Lock()

        mock_response = {"min": 45, "max": 53}

        with patch.object(bridge, "_send", return_value=mock_response) as mock_send:
            attacker_d = pokemon_to_attacker_dict(pikachu, apply_both=True)
            defender_d = pokemon_to_defender_dict(blissey)
            move_d = move_to_dict(thunderbolt)
            field_d = field_to_dict()

            dmg_min, dmg_max, is_error = bridge.calc(attacker_d, defender_d, move_d, field_d)

        assert not is_error, "エラーなく計算できること"
        assert dmg_min == 45
        assert dmg_max == 53

        call_payload = mock_send.call_args[0][0]
        assert "attacker" in call_payload
        assert "defender" in call_payload
        assert "move" in call_payload
        assert "field" in call_payload

    def test_calc_returns_error_on_bridge_failure(
        self, pikachu: PokemonInstance, blissey: PokemonInstance, thunderbolt: MoveInfo
    ) -> None:
        """bridge が error レスポンスを返した場合は is_error=True で (0,0) を返すこと"""
        bridge = SmogonBridge.__new__(SmogonBridge)
        bridge._proc = None
        bridge._io_lock = __import__("threading").Lock()

        error_response = {"error": "Unknown move: unknown", "min": 0, "max": 0}

        with patch.object(bridge, "_send", return_value=error_response):
            attacker_d = pokemon_to_attacker_dict(pikachu, apply_both=True)
            defender_d = pokemon_to_defender_dict(blissey)
            move_d = move_to_dict(thunderbolt)
            field_d = field_to_dict()

            dmg_min, dmg_max, is_error = bridge.calc(attacker_d, defender_d, move_d, field_d)

        assert is_error, "エラーレスポンス時は is_error=True"
        assert dmg_min == 0
        assert dmg_max == 0

    def test_calc_handles_exception_gracefully(
        self, pikachu: PokemonInstance, blissey: PokemonInstance, thunderbolt: MoveInfo
    ) -> None:
        """_send が例外を投げた場合もクラッシュせず (0, 0, True) を返すこと"""
        bridge = SmogonBridge.__new__(SmogonBridge)
        bridge._proc = None
        bridge._io_lock = __import__("threading").Lock()

        with patch.object(bridge, "_send", side_effect=BrokenPipeError("プロセスが停止")):
            attacker_d = pokemon_to_attacker_dict(pikachu)
            defender_d = pokemon_to_defender_dict(blissey)
            move_d = move_to_dict(thunderbolt)
            field_d = field_to_dict()

            dmg_min, dmg_max, is_error = bridge.calc(attacker_d, defender_d, move_d, field_d)

        assert is_error
        assert dmg_min == 0
        assert dmg_max == 0

    def test_full_flow_opponent_party_to_calc_result(self) -> None:
        """
        統合テスト:
        カメラ読込で生成した PokemonInstance をそのまま Smogon bridge に渡して
        計算リクエストが正しく構成されること
        """
        pikachu_species = SpeciesInfo(
            species_id=25, name_ja="ピカチュウ", name_en="pikachu",
            type1="electric", type2="",
            base_hp=35, base_attack=55, base_defense=40,
            base_sp_attack=50, base_sp_defense=50, base_speed=90,
            weight_kg=6.0,
        )

        with (
            patch("src.recognition.text_matcher.match_species_name", return_value="ピカチュウ"),
            patch("src.data.database.get_species_by_name_ja", return_value=pikachu_species),
            patch("src.data.database.get_abilities_by_usage", return_value=["せいでんき"]),
            patch("src.data.database.get_items_by_usage", return_value=["でんきだま"]),
            patch("src.data.database.get_natures_by_usage", return_value=["おくびょう"]),
            patch("src.data.database.get_effort_spreads_by_usage", return_value=[]),
            patch("src.data.database.get_moves_by_usage", return_value=[]),
        ):
            from src.ui import main_window_handlers as mwh
            mock_self = MagicMock()
            opponent = mwh._build_usage_template_pokemon(mock_self, "ピカチュウ")

        assert opponent is not None

        attacker_d = pokemon_to_attacker_dict(opponent, apply_both=True)
        assert attacker_d["species"] != "", "カメラ読込から生成した個体が Smogon 計算できること"
        assert attacker_d["level"] == 50

        move = MoveInfo(
            name_ja="10まんボルト", name_en="thunderbolt",
            type_name="electric", category="special", power=90,
        )
        move_d = move_to_dict(move)
        assert move_d["name"] != ""


# ─── ④ DamageCalcInputs (UIレス入力モデル) ──────────────────────────────────────

class TestDamageCalcInputs:
    """
    DamageCalcInputs は PyQt5 なしで構築できることを確認する。
    collect_calc_inputs() が返す型と同じものを直接生成し、
    各フィールドが意図通りに保持されることを検証する。
    """

    def test_build_without_widgets(self, pikachu: PokemonInstance) -> None:
        """PyQt5 ウィジェットなしで DamageCalcInputs を構築できること"""
        from src.calc.calc_inputs import (
            AttackerCalcConfig,
            DefenderCalcConfig,
            DamageCalcInputs,
            FieldCalcConfig,
        )

        atk = AttackerCalcConfig(
            pokemon=pikachu,
            ev_attack=52,
            nature="ようき",
            ac_rank=1,
            tera="electric",
            is_burned=False,
        )
        def_cfg = DefenderCalcConfig(
            pokemon=PokemonInstance(
                species_id=242, name_ja="ハピナス", name_en="blissey",
                types=["normal"], hp=620,
            ),
            ev_hp=252,
            ev_sp_defense=252,
            nature="おだやか",
            hp_percent=100.0,
        )
        field = FieldCalcConfig(weather="sun", terrain="none")

        inputs = DamageCalcInputs(attacker=atk, defender=def_cfg, field=field)

        assert inputs.attacker.pokemon.name_ja == "ピカチュウ"
        assert inputs.attacker.ev_attack == 52
        assert inputs.attacker.tera == "electric"
        assert inputs.defender.ev_hp == 252
        assert inputs.field.weather == "sun"
        assert inputs.show_bulk_rows is True

    def test_frozen_immutability(self, pikachu: PokemonInstance) -> None:
        """frozen=True なので属性の上書きは TypeError になること"""
        from src.calc.calc_inputs import AttackerCalcConfig
        import pytest

        cfg = AttackerCalcConfig(pokemon=pikachu)
        with pytest.raises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            cfg.ev_attack = 252  # type: ignore[misc]

    def test_default_values(self, pikachu: PokemonInstance) -> None:
        """デフォルト値が正しく設定されていること"""
        from src.calc.calc_inputs import AttackerCalcConfig, DefenderCalcConfig, FieldCalcConfig

        atk = AttackerCalcConfig(pokemon=pikachu)
        assert atk.nature == "まじめ"
        assert atk.ac_rank == 0
        assert atk.is_burned is False
        assert atk.allies_fainted == 0
        assert atk.rivalry_state == "none"

        def_cfg = DefenderCalcConfig(pokemon=None)
        assert def_cfg.hp_percent == 100.0
        assert def_cfg.disguise_intact is True

        field = FieldCalcConfig()
        assert field.weather == "none"
        assert field.is_double is False
        assert field.gravity is False
