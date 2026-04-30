from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget


class StealthRockRow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        iro = QLabel("ステロ:")
        iro.setStyleSheet("color:#a6adc8;font-size:12px;")
        layout.addWidget(iro)
        self._lbl = QLabel("---")
        self._lbl.setStyleSheet("font-size:12px;color:#f9e2af;")
        layout.addWidget(self._lbl)
        layout.addStretch()

    def refresh_data(
        self,
        defender_types: list[str],
        hp_custom: int,
        hp_hbd0: int,
        hp_hbd252: int,
        show_bulk_rows: bool = True,
    ) -> None:
        from src.calc.damage_calc import calc_stealth_rock_damage

        parts = []
        if hp_custom > 0:
            d = calc_stealth_rock_damage(hp_custom, defender_types)
            parts.append("調整:{} ({:.1f}%)".format(d, d / hp_custom * 100))
        if show_bulk_rows and hp_hbd0 > 0:
            d = calc_stealth_rock_damage(hp_hbd0, defender_types)
            parts.append("無振り:{} ({:.1f}%)".format(d, d / hp_hbd0 * 100))
        if show_bulk_rows and hp_hbd252 > 0:
            d = calc_stealth_rock_damage(hp_hbd252, defender_types)
            parts.append("極振り:{} ({:.1f}%)".format(d, d / hp_hbd252 * 100))
        self._lbl.setText("   ".join(parts) if parts else "---")
