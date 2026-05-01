"""Extracted methods from damage_panel.py."""
from __future__ import annotations


def _bootstrap() -> None:
    from src.ui import damage_panel_deps as _dp
    globals().update(_dp.__dict__)

def _build_ui(self) -> None:
    _bootstrap()
    root = QHBoxLayout(self)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    # Scrollable main content (cards + moves + party slots)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
    scroll.setLayoutDirection(Qt.RightToLeft)
    content = QWidget()
    content.setLayoutDirection(Qt.LeftToRight)
    scroll.setWidget(content)
    self._content_layout = QVBoxLayout(content)
    self._content_layout.setContentsMargins(6, 6, 6, 6)
    self._content_layout.setSpacing(6)
    root.addWidget(scroll, 1)

    self._build_side_panel()
    self._build_content()


def _build_side_panel(self) -> None:
    _bootstrap()
    """Build attacker/defender detail controls + battle conditions as a standalone widget."""
    sp_scroll = QScrollArea()
    sp_scroll.setWidgetResizable(True)
    sp_scroll.setFrameShape(QFrame.NoFrame)
    sp_content = QWidget()
    sp_scroll.setWidget(sp_content)
    self._side_panel = sp_scroll

    sp = QVBoxLayout(sp_content)
    sp.setContentsMargins(6, 6, 6, 6)
    sp.setSpacing(6)

    # Attacker + Defender side by side
    panels_row = QHBoxLayout()
    panels_row.setSpacing(6)

    self._atk_panel = _AttackerPanel()
    self._atk_panel.changed.connect(self._on_atk_panel_changed)
    self._atk_panel.edit_requested.connect(self._edit_attacker)
    self._atk_panel.change_requested.connect(self._change_attacker)
    self._atk_panel.new_requested.connect(self._new_attacker)
    self._atk_panel.clear_requested.connect(self._clear_attacker)
    panels_row.addWidget(self._atk_panel, 1, Qt.AlignTop)

    self._def_panel = _DefenderPanel()
    self._def_panel.changed.connect(self._on_def_panel_changed)
    self._def_panel.edit_requested.connect(self._edit_defender)
    self._def_panel.change_requested.connect(self._change_defender)
    self._def_panel.new_requested.connect(self._new_defender)
    self._def_panel.clear_requested.connect(self._clear_defender)
    panels_row.addWidget(self._def_panel, 1, Qt.AlignTop)

    self._atk_panel.ev_section_toggled.connect(self._def_panel.sync_ev_section)
    self._def_panel.ev_section_toggled.connect(self._atk_panel.sync_ev_section)

    sp.addLayout(panels_row)
    self.set_terastal_controls_visible(False)

    # Detail toggle button (for backwards compatibility but hidden)
    self._detail_toggle_btn = QPushButton("詳細設定を表示")
    self._detail_toggle_btn.setCheckable(True)
    self._detail_toggle_btn.setChecked(True)
    self._detail_toggle_btn.toggled.connect(self._toggle_details)
    self._detail_toggle_btn.setText("詳細設定を隠す")
    self._detail_toggle_btn.setVisible(False)  # Hidden, always show details

    self._detail_container = QWidget()
    self._detail_container.setVisible(True)
    dl = QVBoxLayout(self._detail_container)
    dl.setContentsMargins(0, 0, 0, 0)
    dl.setSpacing(6)
    sp.addWidget(self._detail_container)

    dl.addWidget(_sep())

    self._set_battle_format("single")

    wf_row = QHBoxLayout()
    wf_row.setContentsMargins(0, 0, 0, 0)
    wf_row.setSpacing(8)

    _weather_col = QVBoxLayout()
    _weather_col.setContentsMargins(0, 0, 0, 0)
    _weather_col.setSpacing(2)
    _weather_col.addWidget(_row_label("天気"))
    self._weather_grp = _RadioGroup(["はれ", "あめ", "すな", "ゆき"])
    self._weather_grp.set_button_metrics(font_size=14, height=28, min_width=48, pad_h=4, pad_v=2)
    self._weather_grp.changed.connect(self.recalculate)
    _weather_col.addWidget(self._weather_grp)
    wf_row.addLayout(_weather_col)
    wf_row.setAlignment(_weather_col, Qt.AlignTop)

    _terrain_col = QVBoxLayout()
    _terrain_col.setContentsMargins(0, 0, 0, 0)
    _terrain_col.setSpacing(2)
    _terrain_col.addWidget(_row_label("フィールド"))
    self._terrain_grp = _RadioGroup(["エレキ", "グラス", "ミスト", "サイコ"])
    self._terrain_grp.set_button_metrics(font_size=14, height=28, min_width=48, pad_h=4, pad_v=2)
    self._terrain_grp.changed.connect(self.recalculate)
    _terrain_col.addWidget(self._terrain_grp)
    wf_row.addLayout(_terrain_col, 4)
    wf_row.setAlignment(_terrain_col, Qt.AlignTop)

    _gravity_col = QVBoxLayout()
    _gravity_col.setContentsMargins(0, 0, 0, 0)
    _gravity_col.setSpacing(2)
    _gravity_lbl = _row_label("じゅうりょく")
    _gravity_lbl.setStyleSheet("color: transparent; font-size:14px; font-weight:bold;")
    _gravity_col.addWidget(_gravity_lbl)
    self._gravity_btn = _ToggleBtn("じゅうりょく")
    self._gravity_btn.set_metrics(font_size=14, pad_h=4, pad_v=2)
    self._gravity_btn.setFixedHeight(28)
    self._gravity_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    self._gravity_btn.toggled.connect(lambda _: self.recalculate())
    _gravity_col.addWidget(self._gravity_btn)
    wf_row.addLayout(_gravity_col, 1)
    wf_row.setAlignment(_gravity_col, Qt.AlignTop)

    dl.addLayout(wf_row)

    dl.addWidget(_sep())

    # 2
    both_sides_row = QHBoxLayout()
    both_sides_row.setContentsMargins(0, 0, 0, 0)
    both_sides_row.setSpacing(8)

    self_side_col = QVBoxLayout()
    self_side_col.setContentsMargins(0, 0, 0, 0)
    self_side_col.setSpacing(4)
    self_side_col.addWidget(_row_label("自分側補助"))

    self_side_col.addWidget(_row_label("  攻撃側:"))
    atk_cond_ability = QHBoxLayout()
    atk_cond_ability.setContentsMargins(0, 0, 0, 0)
    atk_cond_ability.setSpacing(4)
    atk_cond4 = QHBoxLayout()
    atk_cond4.setContentsMargins(0, 0, 0, 0)
    atk_cond4.setSpacing(6)
    atk_cond1a = QHBoxLayout()        # 1:
    atk_cond1a.setContentsMargins(0, 0, 0, 0)
    atk_cond1a.setSpacing(4)
    atk_cond1b = QHBoxLayout()        # 2:
    atk_cond1b.setContentsMargins(0, 0, 0, 0)
    atk_cond1b.setSpacing(4)
    atk_cond1c = QHBoxLayout()        # 3:
    atk_cond1c.setContentsMargins(0, 0, 0, 0)
    atk_cond1c.setSpacing(4)
    self._burn_btn = _ToggleBtn("やけど")
    self._crit_btn = _ToggleBtn("きゅうしょ")
    self._fairy_aura_btn = _ToggleBtn("フェアリーオーラ")
    self._dark_aura_btn = _ToggleBtn("ダークオーラ")
    self._charge_btn = _ToggleBtn("じゅうでん")
    self._helping_btn = _ToggleBtn("てだすけ")
    self._steel_spirit_btn = _ToggleBtn("はがねのせいしん\n（未対応）")
    self._overgrow_btn = _ToggleBtn("しんりょく", cond_style=True)
    self._blaze_btn = _ToggleBtn("もうか", cond_style=True)
    self._torrent_btn = _ToggleBtn("げきりゅう", cond_style=True)
    self._swarm_btn = _ToggleBtn("むしのしらせ", cond_style=True)
    self._toxic_boost_btn = _ToggleBtn("どくぼうそう", cond_style=True)
    self._stakeout_btn = _ToggleBtn("はりこみ", cond_style=True)
    self._flash_fire_boost_btn = _ToggleBtn("もらいび", cond_style=True)
    self._protosynthesis_btn = _ToggleBtn("こだいかっせい", cond_style=True)
    self._quark_drive_btn = _ToggleBtn("クォークチャージ", cond_style=True)
    self._analytic_btn = _ToggleBtn("アナライズ", cond_style=True)
    self._flare_boost_btn = _ToggleBtn("ねつぼうそう", cond_style=True)
    self._guts_btn = _ToggleBtn("こんじょう", cond_style=True)
    self._attacker_ability_cond_btns: dict[str, _ToggleBtn] = {
        "しんりょく": self._overgrow_btn,
        "もうか": self._blaze_btn,
        "げきりゅう": self._torrent_btn,
        "むしのしらせ": self._swarm_btn,
        "どくぼうそう": self._toxic_boost_btn,
    }
    self._attacker_trigger_cond_btns: dict[str, _ToggleBtn] = {
        "はりこみ": self._stakeout_btn,
        "もらいび": self._flash_fire_boost_btn,
        "こだいかっせい": self._protosynthesis_btn,
        "クォークチャージ": self._quark_drive_btn,
        "アナライズ": self._analytic_btn,
        "ねつぼうそう": self._flare_boost_btn,
        "こんじょう": self._guts_btn,
    }
    for btn in (self._burn_btn, self._crit_btn, self._fairy_aura_btn,
                self._dark_aura_btn, self._charge_btn, self._helping_btn,
                self._steel_spirit_btn):
        btn.setFixedHeight(40)
        btn.setMinimumWidth(70)
        btn.toggled.connect(lambda _: self.recalculate())
    for btn in self._attacker_ability_cond_btns.values():
        btn.setFixedHeight(28)
        btn.setMinimumWidth(70)
        btn.toggled.connect(lambda _: self.recalculate())
        btn.setVisible(False)
        atk_cond_ability.addWidget(btn)
    for btn in self._attacker_trigger_cond_btns.values():
        btn.setFixedHeight(28)
        btn.setMinimumWidth(70)
        btn.toggled.connect(lambda _: self.recalculate())
        btn.setVisible(False)
        atk_cond_ability.addWidget(btn)
    for btn in (self._burn_btn, self._crit_btn, self._charge_btn):
        atk_cond1a.addWidget(btn)
    for btn in (self._fairy_aura_btn, self._dark_aura_btn):
        atk_cond1b.addWidget(btn)
    for btn in (self._helping_btn, self._steel_spirit_btn):
        atk_cond1c.addWidget(btn)

    self._supreme_combo = QComboBox()
    self._supreme_combo.setFixedHeight(24)
    self._supreme_combo.addItem("そうだいしょう", 0)
    for i in range(1, 6):
        self._supreme_combo.addItem("{}体ひんし".format(i), i)
    self._supreme_combo.setStyleSheet(
        "QComboBox{background:#3a3218;color:#f9e2af;border:1px solid #a87d3a;"
        "border-radius:4px;padding:4px 8px;font-size:14px;}"
        "QComboBox::drop-down{border:none;}"
        "QComboBox::down-arrow{image:none;width:0;height:0;}"
        "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
    )
    self._supreme_combo.currentIndexChanged.connect(self._refresh_supreme_combo)
    self._supreme_combo.setVisible(False)
    self._atk_multiscale_btn = _ToggleBtn("マルチスケイル", cond_style=True)
    self._atk_shadow_shield_btn = _ToggleBtn("ファントムガード", cond_style=True)
    self._atk_tera_shell_btn = _ToggleBtn("テラスシェル", cond_style=True)
    self._attacker_full_hp_guard_btns: dict[str, _ToggleBtn] = {
        "マルチスケイル": self._atk_multiscale_btn,
        "ファントムガード": self._atk_shadow_shield_btn,
        "テラスシェル": self._atk_tera_shell_btn,
    }
    for btn in self._attacker_full_hp_guard_btns.values():
        btn.setFixedHeight(28)
        btn.setMinimumWidth(90)
        btn.toggled.connect(lambda _: self.recalculate())
        btn.setChecked(True)
        btn.setVisible(False)
        atk_cond4.addWidget(btn)

    self._rivalry_combo = QComboBox()
    self._rivalry_combo.setFixedHeight(24)
    self._rivalry_combo.addItem("とうそうしん", "none")
    self._rivalry_combo.addItem("同性", "same")
    self._rivalry_combo.addItem("異性", "opposite")
    self._rivalry_combo.setStyleSheet(
        "QComboBox{background:#3a3218;color:#f9e2af;border:1px solid #a87d3a;"
        "border-radius:4px;padding:4px 8px;font-size:14px;}"
        "QComboBox::drop-down{border:none;}"
        "QComboBox::down-arrow{image:none;width:0;height:0;}"
        "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
    )
    self._rivalry_combo.currentIndexChanged.connect(self._refresh_rivalry_combo)
    self._rivalry_combo.setVisible(False)
    atk_cond4.addWidget(self._supreme_combo)
    atk_cond4.addWidget(self._rivalry_combo)
    atk_cond_ability.addStretch()
    atk_cond4.addStretch()
    atk_cond1a.addStretch()
    atk_cond1b.addStretch()
    atk_cond1c.addStretch()
    self_side_col.addLayout(atk_cond_ability)
    self_side_col.addLayout(atk_cond4)
    self_side_col.addLayout(atk_cond1a)
    self_side_col.addLayout(atk_cond1b)
    self_side_col.addLayout(atk_cond1c)

    self_side_col.addSpacing(8)
    self_side_col.addWidget(_row_label("  防御側:"))
    self_def_cond = QHBoxLayout()
    self_def_cond.setContentsMargins(0, 0, 0, 4)
    self_def_cond.setSpacing(4)
    self._self_reflect_btn = _ToggleBtn("リフレクター")
    self._self_lightscreen_btn = _ToggleBtn("ひかりのかべ")
    self._self_friend_guard_btn = _ToggleBtn("フレンドガード")
    self._self_tailwind_btn = _ToggleBtn("おいかぜ")
    self_def_cond2 = QHBoxLayout()
    self_def_cond2.setContentsMargins(0, 0, 0, 4)
    self_def_cond2.setSpacing(4)
    for btn in (self._self_reflect_btn, self._self_lightscreen_btn, self._self_tailwind_btn, self._self_friend_guard_btn):
        btn.setFixedHeight(40)
        btn.setMinimumWidth(70)
        btn.toggled.connect(lambda _: self.recalculate())
    for btn in (self._self_reflect_btn, self._self_lightscreen_btn, self._self_tailwind_btn):
        self_def_cond.addWidget(btn)
    self_def_cond2.addWidget(self._self_friend_guard_btn)
    self_def_cond.addStretch()
    self_def_cond2.addStretch()
    self_side_col.addLayout(self_def_cond)
    self_side_col.addLayout(self_def_cond2)
    self_side_col.addStretch()

    opp_side_col = QVBoxLayout()
    opp_side_col.setContentsMargins(0, 0, 0, 0)
    opp_side_col.setSpacing(4)
    opp_side_col.addWidget(_row_label("相手側補助"))

    opp_side_col.addWidget(_row_label("  攻撃側:"))
    opp_atk_cond_ability = QHBoxLayout()
    opp_atk_cond_ability.setContentsMargins(0, 0, 0, 0)
    opp_atk_cond_ability.setSpacing(4)
    opp_atk_cond4 = QHBoxLayout()
    opp_atk_cond4.setContentsMargins(0, 0, 0, 0)
    opp_atk_cond4.setSpacing(6)
    opp_atk_cond1a = QHBoxLayout()          # 1:
    opp_atk_cond1a.setContentsMargins(0, 0, 0, 0)
    opp_atk_cond1a.setSpacing(4)
    opp_atk_cond1b = QHBoxLayout()          # 2:
    opp_atk_cond1b.setContentsMargins(0, 0, 0, 0)
    opp_atk_cond1b.setSpacing(4)
    opp_atk_cond1c = QHBoxLayout()          # 3:
    opp_atk_cond1c.setContentsMargins(0, 0, 0, 0)
    opp_atk_cond1c.setSpacing(4)
    self._opp_burn_btn = _ToggleBtn("やけど")
    self._opp_crit_btn = _ToggleBtn("きゅうしょ")
    self._opp_fairy_aura_btn = _ToggleBtn("フェアリーオーラ")
    self._opp_dark_aura_btn = _ToggleBtn("ダークオーラ")
    self._opp_charge_btn = _ToggleBtn("じゅうでん")
    self._opp_helping_btn = _ToggleBtn("てだすけ")
    self._opp_steel_spirit_btn = _ToggleBtn("はがねのせいしん\n（未対応）")
    for btn in (self._opp_burn_btn, self._opp_crit_btn, self._opp_fairy_aura_btn,
                self._opp_dark_aura_btn, self._opp_charge_btn, self._opp_helping_btn,
                self._opp_steel_spirit_btn):
        btn.setFixedHeight(40)
        btn.setMinimumWidth(70)
        btn.toggled.connect(lambda _: self.recalculate())
    for btn in (self._opp_burn_btn, self._opp_crit_btn, self._opp_charge_btn):
        opp_atk_cond1a.addWidget(btn)
    for btn in (self._opp_fairy_aura_btn, self._opp_dark_aura_btn):
        opp_atk_cond1b.addWidget(btn)
    for btn in (self._opp_helping_btn, self._opp_steel_spirit_btn):
        opp_atk_cond1c.addWidget(btn)
    self._opp_overgrow_btn = _ToggleBtn("しんりょく", cond_style=True)
    self._opp_blaze_btn = _ToggleBtn("もうか", cond_style=True)
    self._opp_torrent_btn = _ToggleBtn("げきりゅう", cond_style=True)
    self._opp_swarm_btn = _ToggleBtn("むしのしらせ", cond_style=True)
    self._opp_toxic_boost_btn = _ToggleBtn("どくぼうそう", cond_style=True)
    self._opp_stakeout_btn = _ToggleBtn("はりこみ", cond_style=True)
    self._opp_flash_fire_btn = _ToggleBtn("もらいび", cond_style=True)
    self._opp_protosynthesis_btn = _ToggleBtn("こだいかっせい", cond_style=True)
    self._opp_quark_drive_btn = _ToggleBtn("クォークチャージ", cond_style=True)
    self._opp_analytic_btn = _ToggleBtn("アナライズ", cond_style=True)
    self._opp_flare_boost_btn = _ToggleBtn("ねつぼうそう", cond_style=True)
    self._opp_guts_btn = _ToggleBtn("こんじょう", cond_style=True)
    self._defender_ability_cond_btns: dict[str, _ToggleBtn] = {
        "しんりょく": self._opp_overgrow_btn,
        "もうか": self._opp_blaze_btn,
        "げきりゅう": self._opp_torrent_btn,
        "むしのしらせ": self._opp_swarm_btn,
        "どくぼうそう": self._opp_toxic_boost_btn,
    }
    self._defender_trigger_cond_btns: dict[str, _ToggleBtn] = {
        "はりこみ": self._opp_stakeout_btn,
        "もらいび": self._opp_flash_fire_btn,
        "こだいかっせい": self._opp_protosynthesis_btn,
        "クォークチャージ": self._opp_quark_drive_btn,
        "アナライズ": self._opp_analytic_btn,
        "ねつぼうそう": self._opp_flare_boost_btn,
        "こんじょう": self._opp_guts_btn,
    }
    for btn in self._defender_ability_cond_btns.values():
        btn.setFixedHeight(28)
        btn.setMinimumWidth(70)
        btn.toggled.connect(lambda _: self.recalculate())
        btn.setVisible(False)
        opp_atk_cond_ability.addWidget(btn)
    for btn in self._defender_trigger_cond_btns.values():
        btn.setFixedHeight(28)
        btn.setMinimumWidth(70)
        btn.toggled.connect(lambda _: self.recalculate())
        btn.setVisible(False)
        opp_atk_cond_ability.addWidget(btn)

    self._opp_supreme_combo = QComboBox()
    self._opp_supreme_combo.setFixedHeight(24)
    self._opp_supreme_combo.addItem("そうだいしょう", 0)
    for i in range(1, 6):
        self._opp_supreme_combo.addItem("{}体ひんし".format(i), i)
    self._opp_supreme_combo.setStyleSheet(
        "QComboBox{background:#3a3218;color:#f9e2af;border:1px solid #a87d3a;"
        "border-radius:4px;padding:4px 8px;font-size:14px;}"
        "QComboBox::drop-down{border:none;}"
        "QComboBox::down-arrow{image:none;width:0;height:0;}"
        "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
    )
    self._opp_supreme_combo.currentIndexChanged.connect(self._refresh_opp_supreme_combo)
    self._opp_supreme_combo.setVisible(False)
    self._opp_multiscale_btn = _ToggleBtn("マルチスケイル", cond_style=True)
    self._opp_shadow_shield_btn = _ToggleBtn("ファントムガード", cond_style=True)
    self._opp_tera_shell_btn = _ToggleBtn("テラスシェル", cond_style=True)
    self._defender_full_hp_guard_btns: dict[str, _ToggleBtn] = {
        "マルチスケイル": self._opp_multiscale_btn,
        "ファントムガード": self._opp_shadow_shield_btn,
        "テラスシェル": self._opp_tera_shell_btn,
    }
    for btn in self._defender_full_hp_guard_btns.values():
        btn.setFixedHeight(28)
        btn.setMinimumWidth(90)
        btn.toggled.connect(lambda _: self.recalculate())
        btn.setChecked(True)
        btn.setVisible(False)
        opp_atk_cond4.addWidget(btn)

    self._opp_rivalry_combo = QComboBox()
    self._opp_rivalry_combo.setFixedHeight(24)
    self._opp_rivalry_combo.addItem("とうそうしん", "none")
    self._opp_rivalry_combo.addItem("同性", "same")
    self._opp_rivalry_combo.addItem("異性", "opposite")
    self._opp_rivalry_combo.setStyleSheet(
        "QComboBox{background:#3a3218;color:#f9e2af;border:1px solid #a87d3a;"
        "border-radius:4px;padding:4px 8px;font-size:14px;}"
        "QComboBox::drop-down{border:none;}"
        "QComboBox::down-arrow{image:none;width:0;height:0;}"
        "QComboBox QAbstractItemView{background:#3a3218;color:#f9e2af;selection-background-color:#f9e2af;selection-color:#3a3218;}"
    )
    self._opp_rivalry_combo.currentIndexChanged.connect(self._refresh_opp_rivalry_combo)
    self._opp_rivalry_combo.setVisible(False)
    opp_atk_cond4.addWidget(self._opp_supreme_combo)
    opp_atk_cond4.addWidget(self._opp_rivalry_combo)
    opp_atk_cond_ability.addStretch()
    opp_atk_cond4.addStretch()
    opp_atk_cond1a.addStretch()
    opp_atk_cond1b.addStretch()
    opp_atk_cond1c.addStretch()
    opp_side_col.addLayout(opp_atk_cond_ability)
    opp_side_col.addLayout(opp_atk_cond4)
    opp_side_col.addLayout(opp_atk_cond1a)
    opp_side_col.addLayout(opp_atk_cond1b)
    opp_side_col.addLayout(opp_atk_cond1c)

    opp_side_col.addSpacing(8)
    opp_side_col.addWidget(_row_label("  防御側:"))
    def_cond = QHBoxLayout()
    def_cond.setContentsMargins(0, 0, 0, 4)
    def_cond.setSpacing(4)
    self._reflect_btn = _ToggleBtn("リフレクター")
    self._lightscreen_btn = _ToggleBtn("ひかりのかべ")
    self._friend_guard_btn = _ToggleBtn("フレンドガード")
    self._tailwind_btn = _ToggleBtn("おいかぜ")
    def_cond2 = QHBoxLayout()
    def_cond2.setContentsMargins(0, 0, 0, 4)
    def_cond2.setSpacing(4)
    for btn in (self._reflect_btn, self._lightscreen_btn, self._tailwind_btn, self._friend_guard_btn):
        btn.setFixedHeight(40)
        btn.setMinimumWidth(70)
        btn.toggled.connect(lambda _: self.recalculate())
    for btn in (self._reflect_btn, self._lightscreen_btn, self._tailwind_btn):
        def_cond.addWidget(btn)
    def_cond2.addWidget(self._friend_guard_btn)
    def_cond.addStretch()
    def_cond2.addStretch()
    opp_side_col.addLayout(def_cond)
    opp_side_col.addLayout(def_cond2)
    opp_side_col.addStretch()

    both_sides_row.addLayout(self_side_col, 1)
    both_sides_row.addLayout(opp_side_col, 1)
    dl.addLayout(both_sides_row)

    self._helping_btn.setVisible(False)
    self._opp_helping_btn.setVisible(False)
    self._steel_spirit_btn.setVisible(False)
    self._opp_steel_spirit_btn.setVisible(False)
    self._self_friend_guard_btn.setVisible(False)
    self._friend_guard_btn.setVisible(False)
    self._self_tailwind_btn.setVisible(False)
    self._tailwind_btn.setVisible(False)

    sp.addStretch()
    sp.addWidget(_sep())

    # Reset button at bottom – 50% width, left-aligned
    _reset_btn = QPushButton("リセット")
    _reset_btn.setFixedHeight(36)
    _reset_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    _reset_btn.setStyleSheet(
        "QPushButton{font-size:14px;font-weight:bold;background:#313244;"
        "color:#cdd6f4;border:1px solid #45475a;border-radius:4px;}"
        "QPushButton:hover{background:#45475a;}"
    )
    _reset_btn.clicked.connect(self._reset_conditions)
    _reset_row = QHBoxLayout()
    _reset_row.setContentsMargins(0, 4, 0, 0)
    _reset_row.addWidget(_reset_btn, 1)
    _reset_row.addStretch(1)
    sp.addLayout(_reset_row)


def _build_content(self) -> None:
    _bootstrap()
    cl = self._content_layout

    # ── Party selection rows (top) ────────────────────────────────
    self._my_party_row_label = _row_label("")
    cl.addWidget(self._my_party_row_label)
    my_party_row = QHBoxLayout()
    my_party_row.setContentsMargins(0, 0, 0, 0)
    my_party_row.setSpacing(4)
    self._my_party_slots: list[_PartySlot] = []
    for i in range(6):
        slot = _PartySlot(i)
        slot.clicked_signal.connect(self._on_my_party_slot_clicked)
        slot.context_menu_requested.connect(lambda idx, pos: self._on_party_slot_context_menu("my", idx, pos))
        my_party_row.addWidget(slot)
        self._my_party_slots.append(slot)
    my_party_row.addStretch()
    cl.addLayout(my_party_row)

    self._opp_party_row_label = _row_label("")
    cl.addWidget(self._opp_party_row_label)
    opp_party_row = QHBoxLayout()
    opp_party_row.setContentsMargins(0, 0, 0, 0)
    opp_party_row.setSpacing(4)
    self._opp_party_slots: list[_PartySlot] = []
    for i in range(6):
        slot = _PartySlot(i)
        slot.clicked_signal.connect(self._on_opp_party_slot_clicked)
        slot.context_menu_requested.connect(lambda idx, pos: self._on_party_slot_context_menu("opp", idx, pos))
        opp_party_row.addWidget(slot)
        self._opp_party_slots.append(slot)
    self._opp_party_action_host = QWidget()
    self._opp_party_action_layout = QVBoxLayout(self._opp_party_action_host)
    self._opp_party_action_layout.setContentsMargins(0, 0, 0, 0)
    self._opp_party_action_layout.setSpacing(0)
    opp_party_row.addWidget(self._opp_party_action_host, 0, Qt.AlignVCenter)
    opp_party_row.addStretch()
    cl.addLayout(opp_party_row)

    cl.addWidget(_sep())

    # ── Attacker / Defender cards in one horizontal row ───────────
    cards_row = QHBoxLayout()
    cards_row.setContentsMargins(0, 0, 0, 0)
    cards_row.setSpacing(4)

    self._atk_card = _AttackerCard()
    self._atk_card.ability_change_requested.connect(self._change_atk_ability)
    self._atk_card.item_change_requested.connect(self._change_atk_item)
    cards_row.addWidget(self._atk_card, 1)

    self._def_card = _DefenderCard()
    self._def_card.ability_change_requested.connect(self._change_def_ability)
    self._def_card.item_change_requested.connect(self._change_def_item)
    self._def_card.form_change_requested.connect(self._on_form_change_def)
    cards_row.addWidget(self._def_card, 1)

    self._atk_card.form_change_requested.connect(self._on_form_change_atk)

    cl.addLayout(cards_row)

    cl.addWidget(_sep())

    # Move sections: left (→) + right (→) pairs
    self._move_sections: list[_MoveSection] = []
    self._opp_move_sections: list[_MoveSection] = []
    for i in range(4):
        pair = QWidget()
        pair_layout = QHBoxLayout(pair)
        pair_layout.setContentsMargins(0, 0, 0, 0)
        pair_layout.setSpacing(0)

        sec = _MoveSection(i, right_side=False)
        sec.move_change_requested.connect(self._change_move)
        sec._pow_combo.currentIndexChanged.connect(self.recalculate)
        sec._hit_spin.valueChanged.connect(self.recalculate)
        sec.set_bulk_rows_visible(self._show_bulk_rows)
        self._move_sections.append(sec)
        pair_layout.addWidget(sec, 1)

        vsep = QFrame()
        vsep.setFrameShape(QFrame.VLine)
        vsep.setStyleSheet("QFrame{border:none;border-left:1px solid #45475a;}")
        pair_layout.addWidget(vsep)

        opp_sec = _MoveSection(i, right_side=True)
        opp_sec.move_change_requested.connect(self._change_opp_move)
        opp_sec._pow_combo.currentIndexChanged.connect(self.recalculate)
        opp_sec._hit_spin.valueChanged.connect(self.recalculate)
        opp_sec.set_bulk_rows_visible(self._show_bulk_rows)
        self._opp_move_sections.append(opp_sec)
        pair_layout.addWidget(opp_sec, 1)

        cl.addWidget(pair)
        if i < 3:
            cl.addWidget(_sep())

    cl.addWidget(_sep())
    cl.addStretch()
    self._refresh_party_selector_labels()

# ── Public API ────────────────────────────────────────────────────


