from __future__ import annotations

import copy

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.constants import TYPE_EN_TO_JA
from src.models import PokemonInstance
from src.ui.damage_panel_math import nature_mult_from_name as _nature_mult_from_name
from src.ui.damage_panel_ui_helpers import sep as _sep

_TERA_TYPE_EN_TO_JA: dict[str, str] = {
    **TYPE_EN_TO_JA,
    "stellar": "ステラ",
}


class _AttackerPanel(QWidget):
    """Left panel: attacker name, テラスタル, rank, EV slider."""
    changed = pyqtSignal()
    edit_requested = pyqtSignal()
    change_requested = pyqtSignal()
    new_requested = pyqtSignal()
    clear_requested = pyqtSignal()
    ev_section_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._base_pokemon: PokemonInstance | None = None
        self._tera_visible = False
        self._actions_visible = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        ttl = QLabel("自分のポケモン")
        ttl.setStyleSheet("font-size:15px;font-weight:bold;color:#89b4fa;")
        layout.addWidget(ttl)

        self._name_lbl = QLabel("（未設定）")
        self._name_lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;background:#181825;border:1px solid #45475a;border-radius:4px;padding:4px;")
        layout.addWidget(self._name_lbl)

        self._tera_wrap = QWidget()
        tera_row = QHBoxLayout(self._tera_wrap)
        tera_row.setContentsMargins(0, 0, 0, 0)
        tera_row.setSpacing(4)
        self._tera_cb = QCheckBox("テラスタル")
        self._tera_cb.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;")
        self._tera_cb.toggled.connect(self._on_tera_changed)
        tera_row.addWidget(self._tera_cb)
        self._tera_combo = QComboBox()
        self._tera_combo.addItem("（タイプ未選択）", "")
        for en, ja in _TERA_TYPE_EN_TO_JA.items():
            self._tera_combo.addItem(ja, en)
        self._tera_combo.setStyleSheet("QComboBox { font-size: 15px; min-height: 32px; max-height: 32px; padding: 0px; }")
        self._tera_combo.setFixedHeight(32)
        self._tera_combo.setEnabled(False)
        self._tera_combo.currentIndexChanged.connect(self._emit)
        tera_row.addWidget(self._tera_combo, 1)
        layout.addWidget(self._tera_wrap)
        self._tera_wrap.setVisible(False)

        # Rank modifiers: AC and BD separately
        def _make_rank_row(label_text: str, adj_cb):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(70)
            lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;")
            row.addWidget(lbl)
            d_btn = QPushButton("−")
            d_btn.setFixedSize(42, 32)
            d_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #f38ba8;color:#f38ba8;"
                "font-weight:bold;border-radius:4px;font-size:15px;padding:0px;margin:0px;"
                "min-height:32px;max-height:32px;}"
                "QPushButton:hover{background:#3b3240;}"
            )
            rank_lbl = QLabel(" 0")
            rank_lbl.setFixedSize(42, 32)
            rank_lbl.setAlignment(Qt.AlignCenter)
            rank_lbl.setStyleSheet(
                "font-weight:bold;font-size:15px;color:#cdd6f4;background:#181825;"
                "border:1px solid #45475a;border-radius:4px;padding:0px;margin:0px;"
                "min-height:32px;max-height:32px;"
            )
            u_btn = QPushButton("+")
            u_btn.setFixedSize(42, 32)
            u_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #a6e3a1;color:#a6e3a1;"
                "font-weight:bold;border-radius:4px;font-size:15px;padding:0px;margin:0px;"
                "min-height:32px;max-height:32px;}"
                "QPushButton:hover{background:#2f3c36;}"
            )
            d_btn.clicked.connect(lambda: adj_cb(-1))
            u_btn.clicked.connect(lambda: adj_cb(1))
            row.addWidget(d_btn)
            row.addWidget(rank_lbl)
            row.addWidget(u_btn)
            row.addStretch()
            return row, rank_lbl

        self._ac_rank = 0
        self._bd_rank = 0
        ac_row, self._ac_rank_lbl = _make_rank_row("ACランク:", self._adj_ac_rank)
        bd_row, self._bd_rank_lbl = _make_rank_row("BDランク:", self._adj_bd_rank)
        layout.addLayout(ac_row)
        layout.addLayout(bd_row)

        layout.addWidget(_sep())

        # EV slider collapsible section
        ev_toggle_row = QHBoxLayout()
        ev_toggle_row.setContentsMargins(0, 0, 0, 0)
        ev_toggle_row.setSpacing(4)
        self._ev_toggle_btn = QPushButton("▷ 努力値/性格")
        self._ev_toggle_btn.setCheckable(True)
        self._ev_toggle_btn.setChecked(False)
        self._ev_toggle_btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#89b4fa;"
            "font-size:15px;font-weight:bold;text-align:left;padding:0;}"
            "QPushButton:hover{color:#cdd6f4;}"
        )
        self._ev_toggle_btn.clicked.connect(lambda _: self._toggle_ev_section())
        ev_toggle_row.addWidget(self._ev_toggle_btn)
        ev_toggle_row.addStretch()
        layout.addLayout(ev_toggle_row)

        self._ev_section = QWidget()
        self._ev_section.setVisible(False)
        ev_section_layout = QVBoxLayout(self._ev_section)
        ev_section_layout.setContentsMargins(0, 2, 0, 2)
        ev_section_layout.setSpacing(3)

        # EV sliders for H, A, B, C, D, S
        for slider_attr, val_attr, lbl_attr, label_char in (
            ("_ev_slider_h", "_ev_val_lbl_h", "_stat_lbl_h", "H"),
            ("_ev_slider_a", "_ev_val_lbl_a", "_stat_lbl_a", "A"),
            ("_ev_slider_b", "_ev_val_lbl_b", "_stat_lbl_b", "B"),
            ("_ev_slider_c", "_ev_val_lbl_c", "_stat_lbl_c", "C"),
            ("_ev_slider_d", "_ev_val_lbl_d", "_stat_lbl_d", "D"),
            ("_ev_slider_s", "_ev_val_lbl_s", "_stat_lbl_s", "S"),
        ):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)
            stat_lbl = QLabel("{}(---)".format(label_char))
            stat_lbl.setFixedWidth(50)
            stat_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            stat_lbl.setStyleSheet("font-size:16px;font-weight:bold;color:#cdd6f4;")
            setattr(self, lbl_attr, stat_lbl)
            row.addWidget(stat_lbl)
            minus_btn = QPushButton("\u2212")
            minus_btn.setFixedSize(28, 28)
            minus_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #f38ba8;color:#f38ba8;"
                "font-weight:bold;border-radius:3px;font-size:16px;padding:0;}"
                "QPushButton:hover{background:#3b3240;}"
            )
            row.addWidget(minus_btn)
            row.addStretch()
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 32)
            slider.setValue(0)
            slider.setFixedHeight(28)
            slider.valueChanged.connect(self._emit)
            setattr(self, slider_attr, slider)
            minus_btn.clicked.connect(lambda _, s=slider: s.setValue(max(0, s.value() - 1)))
            plus_btn = QPushButton("+")
            plus_btn.setFixedSize(28, 28)
            plus_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #a6e3a1;color:#a6e3a1;"
                "font-weight:bold;border-radius:3px;font-size:16px;padding:0;}"
                "QPushButton:hover{background:#2f3c36;}"
            )
            plus_btn.clicked.connect(lambda _, s=slider: s.setValue(min(32, s.value() + 1)))
            val_lbl = QLabel("0")
            val_lbl.setFixedWidth(15)
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_lbl.setStyleSheet("font-size:13px;color:#a6adc8;")
            setattr(self, val_attr, val_lbl)
            row.addWidget(slider, 1)
            row.addStretch()
            row.addWidget(plus_btn)
            row.addWidget(val_lbl)
            ev_section_layout.addLayout(row)
            slider.valueChanged.connect(val_lbl.setNum)

        # Nature button (inside collapsible section)
        nat_row = QHBoxLayout()
        nat_row.setContentsMargins(0, 4, 0, 0)
        nat_row.setSpacing(4)
        nat_lbl = QLabel("性格")
        nat_lbl.setFixedWidth(50)
        nat_lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;")
        nat_row.addWidget(nat_lbl)
        self._nat_btn = QPushButton("がんばりや（補正なし）")
        self._nat_btn.setFixedHeight(32)
        self._nat_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._nat_btn.setStyleSheet(
            "QPushButton{font-size:15px;text-align:left;padding:0 6px;"
            "background:#313244;border:1px solid #45475a;border-radius:4px;}"
            "QPushButton:hover{border-color:#89b4fa;}"
        )
        self._nat_btn.clicked.connect(self._open_nature_dialog)
        nat_row.addWidget(self._nat_btn, 1)
        self._panel_nature: str = "がんばりや"
        ev_section_layout.addLayout(nat_row)

        layout.addWidget(self._ev_section)

    def _toggle_ev_section(self, from_sync: bool = False) -> None:
        visible = self._ev_toggle_btn.isChecked()
        self._ev_section.setVisible(visible)
        self._ev_toggle_btn.setText("▽ 努力値/性格" if visible else "▷ 努力値/性格")
        if not from_sync:
            self.ev_section_toggled.emit(visible)

    def sync_ev_section(self, visible: bool) -> None:
        self._ev_toggle_btn.blockSignals(True)
        self._ev_toggle_btn.setChecked(visible)
        self._ev_toggle_btn.blockSignals(False)
        self._ev_section.setVisible(visible)
        self._ev_toggle_btn.setText("▽ 努力値/性格" if visible else "▷ 努力値/性格")

    # ── Public ──────────────────────────────────────────────────────────

    def set_pokemon(self, p: PokemonInstance | None) -> None:
        if p is None:
            self._base_pokemon = None
            self._name_lbl.setText("（未設定）")
            for _s in (self._ev_slider_h, self._ev_slider_a, self._ev_slider_b,
                        self._ev_slider_c, self._ev_slider_d, self._ev_slider_s):
                _s.blockSignals(True)
                _s.setValue(0)
                _s.blockSignals(False)
            self._sync_ev_val_lbls()
            self._set_panel_nature("まじめ", emit=False)
            self._ac_rank = 0
            self._bd_rank = 0
            self._ac_rank_lbl.setText(" 0")
            self._bd_rank_lbl.setText(" 0")
            self._tera_cb.blockSignals(True)
            self._tera_cb.setChecked(False)
            self._tera_cb.blockSignals(False)
            self._tera_combo.blockSignals(True)
            self._tera_combo.setCurrentIndex(0)
            self._tera_combo.blockSignals(False)
            self._tera_combo.setEnabled(False)
            for lbl_attr, ch in (
                ("_stat_lbl_h", "H"), ("_stat_lbl_a", "A"), ("_stat_lbl_b", "B"),
                ("_stat_lbl_c", "C"), ("_stat_lbl_d", "D"), ("_stat_lbl_s", "S"),
            ):
                getattr(self, lbl_attr).setText("{}(---)".format(ch))
            return
        self._base_pokemon = copy.deepcopy(p)
        from src.ui.damage_panel_forms import canonical_display_name

        self._name_lbl.setText(canonical_display_name(p.name_ja or ""))
        ev_map = [
            (self._ev_slider_h, max(0, int((p.ev_hp or 0) / 8))),
            (self._ev_slider_a, max(0, int((p.ev_attack or 0) / 8))),
            (self._ev_slider_b, max(0, int((p.ev_defense or 0) / 8))),
            (self._ev_slider_c, max(0, int((p.ev_sp_attack or 0) / 8))),
            (self._ev_slider_d, max(0, int((p.ev_sp_defense or 0) / 8))),
            (self._ev_slider_s, max(0, int((p.ev_speed or 0) / 8))),
        ]
        for _s, _v in ev_map:
            _s.blockSignals(True)
            _s.setValue(_v)
            _s.blockSignals(False)
        self._sync_ev_val_lbls()
        self._set_panel_nature(p.nature or "まじめ", emit=False)
        self._ac_rank = 0
        self._bd_rank = 0
        self._ac_rank_lbl.setText(" 0")
        self._bd_rank_lbl.setText(" 0")
        tera = (p.terastal_type or "normal")
        enable_tera = False
        self._tera_cb.blockSignals(True)
        self._tera_cb.setChecked(enable_tera)
        self._tera_cb.blockSignals(False)
        idx = self._tera_combo.findData(tera)
        if idx < 0:
            idx = self._tera_combo.findData("normal")
        if idx < 0:
            idx = 0
        self._tera_combo.blockSignals(True)
        self._tera_combo.setCurrentIndex(idx)
        self._tera_combo.blockSignals(False)
        self._tera_combo.setEnabled(enable_tera)
        self._update_stat_display(p)

    def update_stat_display(self, p: PokemonInstance | None) -> None:
        if p:
            self._update_stat_display(p)

    def terastal_type(self) -> str:
        if not self._tera_visible:
            return ""
        if not self._tera_cb.isChecked():
            return ""
        return self._tera_combo.currentData() or ""

    def panel_nature(self) -> str:
        return self._panel_nature

    def nat_mult(self, stat_key: str = "attack") -> float:
        return _nature_mult_from_name(self._panel_nature, stat_key)

    def ac_rank(self) -> int:
        return self._ac_rank

    def bd_rank(self) -> int:
        return self._bd_rank

    def rank(self) -> int:
        return self._ac_rank

    def ev_hp_pts(self) -> int:
        return self._ev_slider_h.value()

    def ev_attack_pts(self) -> int:
        return self._ev_slider_a.value()

    def ev_defense_pts(self) -> int:
        return self._ev_slider_b.value()

    def ev_sp_attack_pts(self) -> int:
        return self._ev_slider_c.value()

    def ev_sp_defense_pts(self) -> int:
        return self._ev_slider_d.value()

    def ev_speed_pts(self) -> int:
        return self._ev_slider_s.value()

    def ev_points(self) -> int:
        """後方互換: A/C の大きい方を返す"""
        return max(self._ev_slider_a.value(), self._ev_slider_c.value())

    def use_sp_attack(self) -> bool:
        """後方互換: C >= A のとき True"""
        return self._ev_slider_c.value() >= self._ev_slider_a.value()

    def set_tera_visible(self, visible: bool) -> None:
        self._tera_visible = bool(visible)
        self._tera_wrap.setVisible(self._tera_visible)
        if not self._tera_visible:
            self._tera_cb.blockSignals(True)
            self._tera_cb.setChecked(False)
            self._tera_cb.blockSignals(False)
            self._tera_combo.blockSignals(True)
            self._tera_combo.setCurrentIndex(0)
            self._tera_combo.blockSignals(False)
            self._tera_combo.setEnabled(False)
            self._emit()

    # ── Private ─────────────────────────────────────────────────────────

    def _update_stat_display(self, p: PokemonInstance) -> None:
        self._stat_lbl_h.setText("H({})".format(p.hp or p.max_hp or "--"))
        if p.ability in ("ちからもち", "ヨガパワー", "Huge Power", "Pure Power"):
            self._stat_lbl_a.setText("A({}×2)".format(p.attack))
        else:
            self._stat_lbl_a.setText("A({})".format(p.attack))
        self._stat_lbl_b.setText("B({})".format(p.defense))
        self._stat_lbl_c.setText("C({})".format(p.sp_attack))
        self._stat_lbl_d.setText("D({})".format(p.sp_defense))
        self._stat_lbl_s.setText("S({})".format(p.speed))

    def _toggle_actions(self) -> None:
        self._actions_visible = not self._actions_visible
        self._action_row_wrap.setVisible(self._actions_visible)

    def _on_tera_changed(self, checked: bool) -> None:
        self._tera_combo.setEnabled(checked)
        self._emit()

    def reset_to_base(self) -> None:
        p = self._base_pokemon
        if p is None:
            return
        ev_map = [
            (self._ev_slider_h, max(0, int((p.ev_hp or 0) / 8))),
            (self._ev_slider_a, max(0, int((p.ev_attack or 0) / 8))),
            (self._ev_slider_b, max(0, int((p.ev_defense or 0) / 8))),
            (self._ev_slider_c, max(0, int((p.ev_sp_attack or 0) / 8))),
            (self._ev_slider_d, max(0, int((p.ev_sp_defense or 0) / 8))),
            (self._ev_slider_s, max(0, int((p.ev_speed or 0) / 8))),
        ]
        for _s, _v in ev_map:
            _s.blockSignals(True)
            _s.setValue(_v)
            _s.blockSignals(False)
        self._sync_ev_val_lbls()
        self._set_panel_nature(p.nature or "まじめ", emit=False)
        self._ac_rank = 0
        self._bd_rank = 0
        self._ac_rank_lbl.setText(" 0")
        self._bd_rank_lbl.setText(" 0")
        tera = (p.terastal_type or "normal")
        enable_tera = False
        self._tera_cb.blockSignals(True)
        self._tera_cb.setChecked(enable_tera)
        self._tera_cb.blockSignals(False)
        idx = self._tera_combo.findData(tera)
        if idx < 0:
            idx = self._tera_combo.findData("normal")
        if idx < 0:
            idx = 0
        self._tera_combo.blockSignals(True)
        self._tera_combo.setCurrentIndex(idx)
        self._tera_combo.blockSignals(False)
        self._tera_combo.setEnabled(enable_tera)
        self._update_stat_display(p)
        self._emit()

    def _sync_ev_val_lbls(self) -> None:
        for slider_attr, val_attr in (
            ("_ev_slider_h", "_ev_val_lbl_h"),
            ("_ev_slider_a", "_ev_val_lbl_a"),
            ("_ev_slider_b", "_ev_val_lbl_b"),
            ("_ev_slider_c", "_ev_val_lbl_c"),
            ("_ev_slider_d", "_ev_val_lbl_d"),
            ("_ev_slider_s", "_ev_val_lbl_s"),
        ):
            getattr(self, val_attr).setText(str(getattr(self, slider_attr).value()))

    def _set_panel_nature(self, nature: str, emit: bool = True) -> None:
        from src.constants import NATURES_JA
        nature = nature if nature in NATURES_JA else "まじめ"
        self._panel_nature = nature
        boost, reduce = NATURES_JA.get(nature, (None, None))
        if boost and reduce:
            from src.ui.pokemon_edit_dialog import _STAT_LABELS
            text = "{}  (↑{} / ↓{})".format(
                nature,
                _STAT_LABELS.get(boost, boost),
                _STAT_LABELS.get(reduce, reduce),
            )
        else:
            text = "{}（補正なし）".format(nature)
        self._nat_btn.setText(text)
        if emit:
            self._emit()

    def _open_nature_dialog(self) -> None:
        from src.ui.pokemon_edit_dialog import NatureSelectDialog
        from src.data import database as db
        usage_name = (self._base_pokemon.usage_name or self._base_pokemon.name_ja) if self._base_pokemon else ""
        ranked = db.get_natures_by_usage(usage_name)[:4] if usage_name else []
        dlg = NatureSelectDialog(self._panel_nature, ranked_natures=ranked, parent=self)
        if dlg.exec_():
            self._set_panel_nature(dlg.selected_nature())

    def _adj_ac_rank(self, delta: int) -> None:
        self._ac_rank = max(-6, min(6, self._ac_rank + delta))
        self._ac_rank_lbl.setText("{:+d}".format(self._ac_rank) if self._ac_rank != 0 else " 0")
        self._emit()

    def _adj_bd_rank(self, delta: int) -> None:
        self._bd_rank = max(-6, min(6, self._bd_rank + delta))
        self._bd_rank_lbl.setText("{:+d}".format(self._bd_rank) if self._bd_rank != 0 else " 0")
        self._emit()

    def _emit(self) -> None:
        self.changed.emit()


class _DefenderPanel(QWidget):
    """Left panel: defender quick edit / register select / HP% / rank."""
    changed = pyqtSignal()
    edit_requested = pyqtSignal()
    change_requested = pyqtSignal()
    new_requested = pyqtSignal()
    clear_requested = pyqtSignal()
    ev_section_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._ac_rank = 0
        self._bd_rank = 0
        self._base_pokemon: PokemonInstance | None = None
        self._current_key = ""
        self._tera_visible = False
        self._actions_visible = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        ttl = QLabel("相手のポケモン")
        ttl.setStyleSheet("font-size:15px;font-weight:bold;color:#89b4fa;")
        layout.addWidget(ttl)

        self._name_lbl = QLabel("（未設定）")
        self._name_lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;background:#181825;border:1px solid #45475a;border-radius:4px;padding:4px;")
        layout.addWidget(self._name_lbl)

        self._tera_wrap = QWidget()
        tera_row = QHBoxLayout(self._tera_wrap)
        tera_row.setContentsMargins(0, 0, 0, 0)
        tera_row.setSpacing(4)
        self._tera_cb = QCheckBox("テラスタル")
        self._tera_cb.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;")
        self._tera_cb.toggled.connect(self._on_tera_changed)
        tera_row.addWidget(self._tera_cb)
        self._tera_combo = QComboBox()
        self._tera_combo.addItem("（タイプ未選択）", "")
        for en, ja in _TERA_TYPE_EN_TO_JA.items():
            self._tera_combo.addItem(ja, en)
        self._tera_combo.setStyleSheet("QComboBox { font-size: 15px; min-height: 32px; max-height: 32px; padding: 0px; }")
        self._tera_combo.setFixedHeight(32)
        self._tera_combo.setEnabled(False)
        self._tera_combo.currentIndexChanged.connect(self._emit)
        tera_row.addWidget(self._tera_combo, 1)
        layout.addWidget(self._tera_wrap)
        self._tera_wrap.setVisible(False)

        def _make_rank_row(label_text: str, adj_cb):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(70)
            lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;")
            row.addWidget(lbl)
            d_btn = QPushButton("−")
            d_btn.setFixedSize(42, 32)
            d_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #f38ba8;color:#f38ba8;"
                "font-weight:bold;border-radius:4px;font-size:15px;padding:0px;margin:0px;"
                "min-height:32px;max-height:32px;}"
                "QPushButton:hover{background:#3b3240;}"
            )
            rank_lbl = QLabel(" 0")
            rank_lbl.setFixedSize(42, 32)
            rank_lbl.setAlignment(Qt.AlignCenter)
            rank_lbl.setStyleSheet(
                "font-weight:bold;font-size:15px;color:#cdd6f4;background:#181825;"
                "border:1px solid #45475a;border-radius:4px;padding:0px;margin:0px;"
                "min-height:32px;max-height:32px;"
            )
            u_btn = QPushButton("+")
            u_btn.setFixedSize(42, 32)
            u_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #a6e3a1;color:#a6e3a1;"
                "font-weight:bold;border-radius:4px;font-size:15px;padding:0px;margin:0px;"
                "min-height:32px;max-height:32px;}"
                "QPushButton:hover{background:#2f3c36;}"
            )
            d_btn.clicked.connect(lambda: adj_cb(-1))
            u_btn.clicked.connect(lambda: adj_cb(1))
            row.addWidget(d_btn)
            row.addWidget(rank_lbl)
            row.addWidget(u_btn)
            row.addStretch()
            return row, rank_lbl

        self._ac_rank = 0
        self._bd_rank = 0
        ac_row, self._ac_rank_lbl = _make_rank_row("ACランク:", self._adj_ac_rank)
        bd_row, self._bd_rank_lbl = _make_rank_row("BDランク:", self._adj_bd_rank)
        layout.addLayout(ac_row)
        layout.addLayout(bd_row)
        layout.addWidget(_sep())

        # EV slider collapsible section
        ev_toggle_row = QHBoxLayout()
        ev_toggle_row.setContentsMargins(0, 0, 0, 0)
        ev_toggle_row.setSpacing(4)
        self._ev_toggle_btn = QPushButton("▷ 努力値/性格")
        self._ev_toggle_btn.setCheckable(True)
        self._ev_toggle_btn.setChecked(False)
        self._ev_toggle_btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#89b4fa;"
            "font-size:15px;font-weight:bold;text-align:left;padding:0;}"
            "QPushButton:hover{color:#cdd6f4;}"
        )
        self._ev_toggle_btn.clicked.connect(lambda _: self._toggle_ev_section())
        ev_toggle_row.addWidget(self._ev_toggle_btn)
        ev_toggle_row.addStretch()
        layout.addLayout(ev_toggle_row)

        self._ev_section = QWidget()
        self._ev_section.setVisible(False)
        ev_section_layout = QVBoxLayout(self._ev_section)
        ev_section_layout.setContentsMargins(0, 2, 0, 2)
        ev_section_layout.setSpacing(3)

        # EV sliders for H, A, B, C, D, S
        for slider_attr, val_attr, lbl_attr, label_char in (
            ("_ev_slider_h", "_ev_val_lbl_h", "_stat_lbl_h", "H"),
            ("_ev_slider_a", "_ev_val_lbl_a", "_stat_lbl_a", "A"),
            ("_ev_slider_b", "_ev_val_lbl_b", "_stat_lbl_b", "B"),
            ("_ev_slider_c", "_ev_val_lbl_c", "_stat_lbl_c", "C"),
            ("_ev_slider_d", "_ev_val_lbl_d", "_stat_lbl_d", "D"),
            ("_ev_slider_s", "_ev_val_lbl_s", "_stat_lbl_s", "S"),
        ):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)
            stat_lbl = QLabel("{}(---)".format(label_char))
            stat_lbl.setFixedWidth(50)
            stat_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            stat_lbl.setStyleSheet("font-size:16px;font-weight:bold;color:#cdd6f4;")
            setattr(self, lbl_attr, stat_lbl)
            row.addWidget(stat_lbl)
            minus_btn = QPushButton("\u2212")
            minus_btn.setFixedSize(28, 28)
            minus_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #f38ba8;color:#f38ba8;"
                "font-weight:bold;border-radius:3px;font-size:16px;padding:0;}"
                "QPushButton:hover{background:#3b3240;}"
            )
            row.addWidget(minus_btn)
            row.addStretch()
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 32)
            slider.setValue(0)
            slider.setFixedHeight(28)
            slider.valueChanged.connect(self._emit)
            setattr(self, slider_attr, slider)
            minus_btn.clicked.connect(lambda _, s=slider: s.setValue(max(0, s.value() - 1)))
            plus_btn = QPushButton("+")
            plus_btn.setFixedSize(28, 28)
            plus_btn.setStyleSheet(
                "QPushButton{background:#313244;border:1px solid #a6e3a1;color:#a6e3a1;"
                "font-weight:bold;border-radius:3px;font-size:16px;padding:0;}"
                "QPushButton:hover{background:#2f3c36;}"
            )
            plus_btn.clicked.connect(lambda _, s=slider: s.setValue(min(32, s.value() + 1)))
            val_lbl = QLabel("0")
            val_lbl.setFixedWidth(15)
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_lbl.setStyleSheet("font-size:13px;color:#a6adc8;")
            setattr(self, val_attr, val_lbl)
            row.addWidget(slider, 1)
            row.addStretch()
            row.addWidget(plus_btn)
            row.addWidget(val_lbl)
            ev_section_layout.addLayout(row)
            slider.valueChanged.connect(val_lbl.setNum)

        # Nature button (inside collapsible section)
        nat_row = QHBoxLayout()
        nat_row.setContentsMargins(0, 4, 0, 0)
        nat_row.setSpacing(4)
        nat_lbl = QLabel("性格")
        nat_lbl.setFixedWidth(50)
        nat_lbl.setStyleSheet("font-size:15px;font-weight:bold;color:#cdd6f4;")
        nat_row.addWidget(nat_lbl)
        self._nat_btn = QPushButton("がんばりや（補正なし）")
        self._nat_btn.setFixedHeight(32)
        self._nat_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._nat_btn.setStyleSheet(
            "QPushButton{font-size:15px;text-align:left;padding:0 6px;"
            "background:#313244;border:1px solid #45475a;border-radius:4px;}"
            "QPushButton:hover{border-color:#89b4fa;}"
        )
        self._nat_btn.clicked.connect(self._open_nature_dialog)
        nat_row.addWidget(self._nat_btn, 1)
        self._panel_nature: str = "がんばりや"
        ev_section_layout.addLayout(nat_row)

        layout.addWidget(self._ev_section)

        self._disguise_cb = QCheckBox("ばけのかわ有効")
        self._disguise_cb.setVisible(False)
        self._disguise_cb.toggled.connect(self._emit)
        layout.addWidget(self._disguise_cb)

        self._hp_pct_spin = QSpinBox()
        self._hp_pct_spin.setRange(1, 100)
        self._hp_pct_spin.setValue(100)
        self._hp_pct_spin.setSuffix("%")
        self._hp_pct_spin.setVisible(False)
        self._hp_pct_spin.valueChanged.connect(self._emit)
        layout.addWidget(self._hp_pct_spin)
        self._ability_lbl = QLabel("")
        self._ability_lbl.setVisible(False)
        layout.addWidget(self._ability_lbl)

    def set_pokemon(self, p: PokemonInstance | None) -> None:
        if p is None:
            self._base_pokemon = None
            self._name_lbl.setText("（未設定）")
            self._ability_lbl.setText("")
            self._hp_pct_spin.blockSignals(True)
            self._hp_pct_spin.setValue(100)
            self._hp_pct_spin.blockSignals(False)
            self._tera_cb.blockSignals(True)
            self._tera_cb.setChecked(False)
            self._tera_cb.blockSignals(False)
            self._tera_combo.blockSignals(True)
            self._tera_combo.setCurrentIndex(0)
            self._tera_combo.blockSignals(False)
            self._tera_combo.setEnabled(False)
            self._set_panel_nature("まじめ", emit=False)
            for _s in (self._ev_slider_h, self._ev_slider_a, self._ev_slider_b,
                        self._ev_slider_c, self._ev_slider_d, self._ev_slider_s):
                _s.blockSignals(True)
                _s.setValue(0)
                _s.blockSignals(False)
            self._sync_ev_val_lbls()
            self._ac_rank = 0
            self._bd_rank = 0
            self._ac_rank_lbl.setText(" 0")
            self._bd_rank_lbl.setText(" 0")
            self._disguise_cb.setVisible(False)
            self._disguise_cb.blockSignals(True)
            self._disguise_cb.setChecked(False)
            self._disguise_cb.blockSignals(False)
            for lbl_attr, ch in (
                ("_stat_lbl_h", "H"), ("_stat_lbl_a", "A"), ("_stat_lbl_b", "B"),
                ("_stat_lbl_c", "C"), ("_stat_lbl_d", "D"), ("_stat_lbl_s", "S"),
            ):
                getattr(self, lbl_attr).setText("{}(---)".format(ch))
            self._current_key = ""
            return

        self._base_pokemon = copy.deepcopy(p)
        from src.ui.damage_panel_forms import canonical_display_name

        self._name_lbl.setText(canonical_display_name(p.name_ja or ""))
        self._ability_lbl.setText("特性: {}".format(p.ability or "---"))
        key = "{}|{}|{}|{}|{}|{}|{}|{}|{}".format(
            p.species_id, p.name_ja or "", p.ability or "",
            p.ev_hp, p.ev_attack, p.ev_defense,
            p.ev_sp_attack, p.ev_sp_defense, p.ev_speed,
        )
        if self._current_key != key:
            pct = 100
            max_hp = p.max_hp or p.hp
            if p.current_hp > 0 and max_hp > 0:
                pct = int(round(max(1.0, min(100.0, p.current_hp / max_hp * 100.0))))
            elif p.current_hp_percent > 0:
                pct = int(round(max(1.0, min(100.0, p.current_hp_percent))))
            self._hp_pct_spin.blockSignals(True)
            self._hp_pct_spin.setValue(pct)
            self._hp_pct_spin.blockSignals(False)
            self._ac_rank = 0
            self._bd_rank = 0
            self._ac_rank_lbl.setText(" 0")
            self._bd_rank_lbl.setText(" 0")

            ev_map = [
                (self._ev_slider_h, max(0, int((p.ev_hp or 0) / 8))),
                (self._ev_slider_a, max(0, int((p.ev_attack or 0) / 8))),
                (self._ev_slider_b, max(0, int((p.ev_defense or 0) / 8))),
                (self._ev_slider_c, max(0, int((p.ev_sp_attack or 0) / 8))),
                (self._ev_slider_d, max(0, int((p.ev_sp_defense or 0) / 8))),
                (self._ev_slider_s, max(0, int((p.ev_speed or 0) / 8))),
            ]
            for _s, _v in ev_map:
                _s.blockSignals(True)
                _s.setValue(_v)
                _s.blockSignals(False)
            self._sync_ev_val_lbls()
            self._set_panel_nature(p.nature or "まじめ", emit=False)

            tera = (p.terastal_type or "normal")
            enable_tera = False
            self._tera_cb.blockSignals(True)
            self._tera_cb.setChecked(enable_tera)
            self._tera_cb.blockSignals(False)
            idx = self._tera_combo.findData(tera)
            if idx < 0:
                idx = self._tera_combo.findData("normal")
            if idx < 0:
                idx = 0
            self._tera_combo.blockSignals(True)
            self._tera_combo.setCurrentIndex(idx)
            self._tera_combo.blockSignals(False)
            self._tera_combo.setEnabled(enable_tera)

            self._disguise_cb.blockSignals(True)
            self._disguise_cb.setChecked(False)
            self._disguise_cb.blockSignals(False)
            self._current_key = key

        self._disguise_cb.setVisible(p.ability == "ばけのかわ")
        self._update_stat_display(p)

    def rank(self) -> int:
        return self._ac_rank

    def ac_rank(self) -> int:
        return self._ac_rank

    def bd_rank(self) -> int:
        return self._bd_rank

    def panel_nature(self) -> str:
        return self._panel_nature

    def nat_mult(self, stat_key: str = "defense") -> float:
        return _nature_mult_from_name(self._panel_nature, stat_key)

    def current_hp_percent(self) -> int:
        return self._hp_pct_spin.value()

    def terastal_type(self) -> str:
        if not self._tera_visible:
            return ""
        if not self._tera_cb.isChecked():
            return ""
        return self._tera_combo.currentData() or ""

    def ev_hp_pts(self) -> int:
        return self._ev_slider_h.value()

    def ev_attack_pts(self) -> int:
        return self._ev_slider_a.value()

    def ev_defense_pts(self) -> int:
        return self._ev_slider_b.value()

    def ev_sp_attack_pts(self) -> int:
        return self._ev_slider_c.value()

    def ev_sp_defense_pts(self) -> int:
        return self._ev_slider_d.value()

    def ev_speed_pts(self) -> int:
        return self._ev_slider_s.value()

    def ev_points(self) -> int:
        """後方互換: B/D の大きい方を返す"""
        return max(self._ev_slider_b.value(), self._ev_slider_d.value())

    def use_sp_defense(self) -> bool:
        """後方互換: D >= B のとき True"""
        return self._ev_slider_d.value() >= self._ev_slider_b.value()

    def set_tera_visible(self, visible: bool) -> None:
        self._tera_visible = bool(visible)
        self._tera_wrap.setVisible(self._tera_visible)
        if not self._tera_visible:
            self._tera_cb.blockSignals(True)
            self._tera_cb.setChecked(False)
            self._tera_cb.blockSignals(False)
            self._tera_combo.blockSignals(True)
            self._tera_combo.setCurrentIndex(0)
            self._tera_combo.blockSignals(False)
            self._tera_combo.setEnabled(False)
            self._emit()

    def disguise_intact(self) -> bool:
        return (not self._disguise_cb.isHidden()) and self._disguise_cb.isChecked()

    def update_stat_display(self, p: PokemonInstance | None) -> None:
        if p:
            self._update_stat_display(p)

    def _toggle_ev_section(self, from_sync: bool = False) -> None:
        visible = self._ev_toggle_btn.isChecked()
        self._ev_section.setVisible(visible)
        self._ev_toggle_btn.setText("▽ 努力値/性格" if visible else "▷ 努力値/性格")
        if not from_sync:
            self.ev_section_toggled.emit(visible)

    def sync_ev_section(self, visible: bool) -> None:
        self._ev_toggle_btn.blockSignals(True)
        self._ev_toggle_btn.setChecked(visible)
        self._ev_toggle_btn.blockSignals(False)
        self._ev_section.setVisible(visible)
        self._ev_toggle_btn.setText("▽ 努力値/性格" if visible else "▷ 努力値/性格")

    def _sync_ev_val_lbls(self) -> None:
        for slider_attr, val_attr in (
            ("_ev_slider_h", "_ev_val_lbl_h"),
            ("_ev_slider_a", "_ev_val_lbl_a"),
            ("_ev_slider_b", "_ev_val_lbl_b"),
            ("_ev_slider_c", "_ev_val_lbl_c"),
            ("_ev_slider_d", "_ev_val_lbl_d"),
            ("_ev_slider_s", "_ev_val_lbl_s"),
        ):
            getattr(self, val_attr).setText(str(getattr(self, slider_attr).value()))

    def reset_to_base(self) -> None:
        p = self._base_pokemon
        if p is None:
            return
        pct = 100
        max_hp = p.max_hp or p.hp
        if p.current_hp > 0 and max_hp > 0:
            pct = int(round(max(1.0, min(100.0, p.current_hp / max_hp * 100.0))))
        elif p.current_hp_percent > 0:
            pct = int(round(max(1.0, min(100.0, p.current_hp_percent))))
        self._hp_pct_spin.blockSignals(True)
        self._hp_pct_spin.setValue(pct)
        self._hp_pct_spin.blockSignals(False)
        self._ac_rank = 0
        self._bd_rank = 0
        self._ac_rank_lbl.setText(" 0")
        self._bd_rank_lbl.setText(" 0")
        ev_map = [
            (self._ev_slider_h, max(0, int((p.ev_hp or 0) / 8))),
            (self._ev_slider_a, max(0, int((p.ev_attack or 0) / 8))),
            (self._ev_slider_b, max(0, int((p.ev_defense or 0) / 8))),
            (self._ev_slider_c, max(0, int((p.ev_sp_attack or 0) / 8))),
            (self._ev_slider_d, max(0, int((p.ev_sp_defense or 0) / 8))),
            (self._ev_slider_s, max(0, int((p.ev_speed or 0) / 8))),
        ]
        for _s, _v in ev_map:
            _s.blockSignals(True)
            _s.setValue(_v)
            _s.blockSignals(False)
        self._sync_ev_val_lbls()
        self._set_panel_nature(p.nature or "まじめ", emit=False)
        tera = (p.terastal_type or "normal")
        enable_tera = False
        self._tera_cb.blockSignals(True)
        self._tera_cb.setChecked(enable_tera)
        self._tera_cb.blockSignals(False)
        idx = self._tera_combo.findData(tera)
        if idx < 0:
            idx = self._tera_combo.findData("normal")
        if idx < 0:
            idx = 0
        self._tera_combo.blockSignals(True)
        self._tera_combo.setCurrentIndex(idx)
        self._tera_combo.blockSignals(False)
        self._tera_combo.setEnabled(enable_tera)
        self._disguise_cb.blockSignals(True)
        self._disguise_cb.setChecked(False)
        self._disguise_cb.blockSignals(False)
        self._update_stat_display(p)
        self._emit()

    def _set_panel_nature(self, nature: str, emit: bool = True) -> None:
        from src.constants import NATURES_JA
        nature = nature if nature in NATURES_JA else "まじめ"
        self._panel_nature = nature
        boost, reduce = NATURES_JA.get(nature, (None, None))
        if boost and reduce:
            from src.ui.pokemon_edit_dialog import _STAT_LABELS
            text = "{}  (↑{} / ↓{})".format(
                nature,
                _STAT_LABELS.get(boost, boost),
                _STAT_LABELS.get(reduce, reduce),
            )
        else:
            text = "{}（補正なし）".format(nature)
        self._nat_btn.setText(text)
        if emit:
            self._emit()

    def _open_nature_dialog(self) -> None:
        from src.ui.pokemon_edit_dialog import NatureSelectDialog
        from src.data import database as db
        usage_name = (self._base_pokemon.usage_name or self._base_pokemon.name_ja) if self._base_pokemon else ""
        ranked = db.get_natures_by_usage(usage_name)[:4] if usage_name else []
        dlg = NatureSelectDialog(self._panel_nature, ranked_natures=ranked, parent=self)
        if dlg.exec_():
            self._set_panel_nature(dlg.selected_nature())

    def _adj_ac_rank(self, delta: int) -> None:
        self._ac_rank = max(-6, min(6, self._ac_rank + delta))
        self._ac_rank_lbl.setText("{:+d}".format(self._ac_rank) if self._ac_rank != 0 else " 0")
        self._emit()

    def _adj_bd_rank(self, delta: int) -> None:
        self._bd_rank = max(-6, min(6, self._bd_rank + delta))
        self._bd_rank_lbl.setText("{:+d}".format(self._bd_rank) if self._bd_rank != 0 else " 0")
        self._emit()

    def _on_tera_changed(self, checked: bool) -> None:
        self._tera_combo.setEnabled(checked)
        self._emit()

    def _update_stat_display(self, p: PokemonInstance) -> None:
        self._stat_lbl_h.setText("H({})".format(p.hp or p.max_hp or "---"))
        self._stat_lbl_a.setText("A({})".format(p.attack))
        self._stat_lbl_b.setText("B({})".format(p.defense))
        self._stat_lbl_c.setText("C({})".format(p.sp_attack))
        self._stat_lbl_d.setText("D({})".format(p.sp_defense))
        self._stat_lbl_s.setText("S({})".format(p.speed))

    def _toggle_actions(self) -> None:
        self._actions_visible = not self._actions_visible
        self._action_row_wrap.setVisible(self._actions_visible)

    def _emit(self) -> None:
        self.changed.emit()

