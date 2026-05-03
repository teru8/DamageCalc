"""Copy & Discord send dialog for damage calculation results."""
from __future__ import annotations

import json
import urllib.request
from typing import TYPE_CHECKING

from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from src.ui.damage_panel import DamagePanel


def _pokemon_header(pokemon) -> str:
    if pokemon is None:
        return "（未設定）"
    name = pokemon.name_ja or "？"
    item = pokemon.item or ""
    ability = pokemon.ability or ""
    nature = getattr(pokemon, "nature", "") or ""

    evs = getattr(pokemon, "evs", None)
    hp = getattr(pokemon, "hp", 0) or 0
    atk = getattr(pokemon, "atk", 0) or 0
    def_ = getattr(pokemon, "def_", 0) or 0
    spa = getattr(pokemon, "spa", 0) or 0
    spd = getattr(pokemon, "spd", 0) or 0
    spe = getattr(pokemon, "spe", 0) or 0

    def _ev(v: int) -> int:
        if evs and isinstance(evs, dict):
            return evs.get(v, 0)
        return 0

    stats = "{hp}({ev_hp})-{atk}({ev_atk})-{def_}({ev_def})-{spa}-{spd}-{spe}({ev_spe})".format(
        hp=hp, ev_hp=_ev("hp"),
        atk=atk, ev_atk=_ev("atk"),
        def_=def_, ev_def=_ev("def_"),
        spa=spa,
        spd=spd,
        spe=spe, ev_spe=_ev("spe"),
    )

    parts = [p for p in [item, ability, nature] if p]
    header = "【{} @ {} / {}】".format(name, " / ".join(parts), stats) if parts else "【{}】".format(name)
    return header


def _send_discord(url: str, text: str) -> None:
    chunks = [text[i : i + 2000] for i in range(0, len(text), 2000)]
    for chunk in chunks:
        data = json.dumps({"content": chunk}).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)


class CopyDialog(QDialog):
    def __init__(self, damage_panel: "DamagePanel", webhook_url: str = "", parent=None):
        super().__init__(parent)
        self._panel = damage_panel
        self._webhook_url = webhook_url
        self._checks_atk: list[QCheckBox] = []
        self._checks_def: list[QCheckBox] = []
        self._status_lbl = QLabel("")
        self.setWindowTitle("コピー / Discord送信")
        self.setMinimumWidth(700)
        self._build_ui()

    def _build_ui(self) -> None:
        p = self._panel
        atk = p._atk
        def_ = p._def_custom

        main = QVBoxLayout(self)
        main.setSpacing(8)

        # Header row
        atk_name = atk.name_ja if atk else "（未設定）"
        def_name = def_.name_ja if def_ else "（未設定）"
        atk_item = atk.item or "" if atk else ""
        def_item = def_.item or "" if def_ else ""
        atk_ability = atk.ability or "" if atk else ""
        def_ability = def_.ability or "" if def_ else ""

        def _short(pokemon) -> str:
            if pokemon is None:
                return "（未設定）"
            parts = [p for p in [pokemon.item, pokemon.ability] if p]
            return "{} @ {}".format(pokemon.name_ja or "？", " / ".join(parts)) if parts else (pokemon.name_ja or "？")

        hdr = QLabel("<b>{}</b>  ⇔  <b>{}</b>".format(_short(atk), _short(def_)))
        hdr.setStyleSheet("font-size:14px;padding:4px;")
        main.addWidget(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("QFrame{border:none;border-top:1px solid #45475a;}")
        main.addWidget(sep)

        # Move rows
        move_grid = QHBoxLayout()
        move_grid.setSpacing(12)

        atk_col = QVBoxLayout()
        atk_col.setSpacing(4)
        atk_col_lbl = QLabel("→ 攻撃")
        atk_col_lbl.setStyleSheet("font-size:13px;color:#89b4fa;font-weight:bold;")
        atk_col.addWidget(atk_col_lbl)

        def_col = QVBoxLayout()
        def_col.setSpacing(4)
        def_col_lbl = QLabel("← 防御")
        def_col_lbl.setStyleSheet("font-size:13px;color:#f38ba8;font-weight:bold;")
        def_col.addWidget(def_col_lbl)

        for i in range(4):
            sec = p._move_sections[i]
            opp_sec = p._opp_move_sections[i]

            # atk→def
            move_name = sec._move.name_ja if sec._move else ""
            dmg_txt = sec._row_custom._detail_txt.text() if sec._row_custom else ""
            ko_txt = sec._row_custom._ko_txt.text() if sec._row_custom else ""
            has_damage = bool(move_name) and dmg_txt not in ("---", "", "0-0 (0.0~0.0%)")

            cb = QCheckBox()
            cb.setChecked(False)
            cb.setEnabled(has_damage)
            label_text = "{}: {} {}".format(move_name or "---", dmg_txt, ko_txt).strip()
            row_w = QWidget()
            row_layout = QHBoxLayout(row_w)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            row_layout.addWidget(cb)
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size:13px;" + ("" if has_damage else "color:#585b70;"))
            row_layout.addWidget(lbl)
            row_layout.addStretch()
            atk_col.addWidget(row_w)
            self._checks_atk.append(cb)

            # def→atk
            opp_move_name = opp_sec._move.name_ja if opp_sec._move else ""
            opp_dmg_txt = opp_sec._row_custom._detail_txt.text() if opp_sec._row_custom else ""
            opp_ko_txt = opp_sec._row_custom._ko_txt.text() if opp_sec._row_custom else ""
            opp_has_damage = bool(opp_move_name) and opp_dmg_txt not in ("---", "", "0-0 (0.0~0.0%)")

            ocb = QCheckBox()
            ocb.setChecked(False)
            ocb.setEnabled(opp_has_damage)
            opp_label = "{}: {} {}".format(opp_move_name or "---", opp_dmg_txt, opp_ko_txt).strip()
            orow_w = QWidget()
            orow_layout = QHBoxLayout(orow_w)
            orow_layout.setContentsMargins(0, 0, 0, 0)
            orow_layout.setSpacing(4)
            orow_layout.addWidget(ocb)
            olbl = QLabel(opp_label)
            olbl.setStyleSheet("font-size:13px;" + ("" if opp_has_damage else "color:#585b70;"))
            orow_layout.addWidget(olbl)
            orow_layout.addStretch()
            def_col.addWidget(orow_w)
            self._checks_def.append(ocb)

        atk_col.addStretch()
        def_col.addStretch()
        move_grid.addLayout(atk_col, 1)

        vsep = QFrame()
        vsep.setFrameShape(QFrame.VLine)
        vsep.setStyleSheet("QFrame{border:none;border-left:1px solid #45475a;}")
        move_grid.addWidget(vsep)

        move_grid.addLayout(def_col, 1)
        main.addLayout(move_grid)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("QFrame{border:none;border-top:1px solid #45475a;}")
        main.addWidget(sep2)

        # Status label
        self._status_lbl.setStyleSheet("font-size:13px;color:#a6e3a1;")
        main.addWidget(self._status_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        copy_btn = QPushButton("コピー")
        copy_btn.setFixedHeight(32)
        copy_btn.setMinimumWidth(80)
        copy_btn.setStyleSheet(
            "QPushButton{background:#313244;border:1px solid #89b4fa;color:#89b4fa;"
            "font-weight:bold;border-radius:4px;font-size:14px;}"
            "QPushButton:hover{background:#3b3250;}"
        )
        copy_btn.clicked.connect(self._on_copy)
        btn_row.addWidget(copy_btn)

        discord_btn = QPushButton("Discord送信")
        discord_btn.setFixedHeight(32)
        discord_btn.setMinimumWidth(100)
        has_webhook = bool(self._webhook_url)
        discord_btn.setEnabled(has_webhook)
        discord_btn.setStyleSheet(
            "QPushButton{background:#313244;border:1px solid #cba6f7;color:#cba6f7;"
            "font-weight:bold;border-radius:4px;font-size:14px;}"
            "QPushButton:hover{background:#3b3250;}"
            "QPushButton:disabled{border-color:#585b70;color:#585b70;}"
        )
        discord_btn.clicked.connect(self._on_discord)
        btn_row.addWidget(discord_btn)

        close_btn = QPushButton("閉じる")
        close_btn.setFixedHeight(32)
        close_btn.setMinimumWidth(70)
        close_btn.setStyleSheet(
            "QPushButton{background:#313244;border:1px solid #45475a;color:#cdd6f4;"
            "font-weight:bold;border-radius:4px;font-size:14px;}"
            "QPushButton:hover{background:#45475a;}"
        )
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)

        main.addLayout(btn_row)

    def _build_text(self) -> str | None:
        p = self._panel
        atk = p._atk
        def_ = p._def_custom

        atk_lines = []
        def_lines = []

        for i, cb in enumerate(self._checks_atk):
            if not cb.isChecked():
                continue
            sec = p._move_sections[i]
            if not sec._move:
                continue
            move = sec._move
            dmg = sec._row_custom._detail_txt.text()
            ko = sec._row_custom._ko_txt.text()
            cat_map = {"ぶつり": "物理", "とくしゅ": "特殊", "へんか": "変化"}
            cat = cat_map.get(move.category or "", move.category or "")
            type_ja = move.move_type or ""
            suffix = " {}".format(ko) if ko else ""
            atk_lines.append("→ {} ({}/{}): {}{}".format(move.name_ja, type_ja, cat, dmg, suffix))

        for i, cb in enumerate(self._checks_def):
            if not cb.isChecked():
                continue
            sec = p._opp_move_sections[i]
            if not sec._move:
                continue
            move = sec._move
            dmg = sec._row_custom._detail_txt.text()
            ko = sec._row_custom._ko_txt.text()
            cat_map = {"ぶつり": "物理", "とくしゅ": "特殊", "へんか": "変化"}
            cat = cat_map.get(move.category or "", move.category or "")
            type_ja = move.move_type or ""
            suffix = " {}".format(ko) if ko else ""
            def_lines.append("← {} ({}/{}): {}{}".format(move.name_ja, type_ja, cat, dmg, suffix))

        if not atk_lines and not def_lines:
            return None

        def _fmt_pokemon(pokemon) -> str:
            if pokemon is None:
                return "（未設定）"
            name = pokemon.name_ja or "？"
            parts: list[str] = []
            if pokemon.item:
                parts.append(pokemon.item)
            if pokemon.ability:
                parts.append(pokemon.ability)
            nature = getattr(pokemon, "nature", "") or ""
            if nature:
                parts.append(nature)
            hp = getattr(pokemon, "hp", 0) or 0
            atk_v = getattr(pokemon, "atk", 0) or 0
            def_v = getattr(pokemon, "def_", 0) or 0
            spa = getattr(pokemon, "spa", 0) or 0
            spd = getattr(pokemon, "spd", 0) or 0
            spe = getattr(pokemon, "spe", 0) or 0
            ev_hp = getattr(pokemon, "ev_hp", 0) or 0
            ev_atk = getattr(pokemon, "ev_atk", 0) or 0
            ev_def = getattr(pokemon, "ev_def", 0) or 0
            ev_spe = getattr(pokemon, "ev_spe", 0) or 0
            stats = "{hp}({ev_hp})-{atk}({ev_atk})-{def_}({ev_def})-{spa}-{spd}-{spe}({ev_spe})".format(
                hp=hp, ev_hp=ev_hp,
                atk=atk_v, ev_atk=ev_atk,
                def_=def_v, ev_def=ev_def,
                spa=spa, spd=spd,
                spe=spe, ev_spe=ev_spe,
            )
            parts.append(stats)
            return "【{} @ {}】".format(name, " / ".join(parts))

        lines: list[str] = [
            _fmt_pokemon(atk),
            "vs",
            _fmt_pokemon(def_),
            "",
        ]
        lines.extend(atk_lines)
        if atk_lines and def_lines:
            lines.append("")
        lines.extend(def_lines)
        return "\n".join(lines)

    def _on_copy(self) -> None:
        text = self._build_text()
        if text is None:
            self._status_lbl.setStyleSheet("font-size:13px;color:#f38ba8;")
            self._status_lbl.setText("技を1つ以上チェックしてください")
            return
        QApplication.clipboard().setText(text)
        self._status_lbl.setStyleSheet("font-size:13px;color:#a6e3a1;")
        self._status_lbl.setText("クリップボードにコピーしました")

    def _on_discord(self) -> None:
        text = self._build_text()
        if text is None:
            self._status_lbl.setStyleSheet("font-size:13px;color:#f38ba8;")
            self._status_lbl.setText("技を1つ以上チェックしてください")
            return
        try:
            _send_discord(self._webhook_url, text)
            self._status_lbl.setStyleSheet("font-size:13px;color:#a6e3a1;")
            self._status_lbl.setText("送信しました")
        except Exception as exc:
            QMessageBox.critical(self, "送信エラー", "Discord送信に失敗しました:\n{}".format(exc))
