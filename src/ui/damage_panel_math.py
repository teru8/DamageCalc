from __future__ import annotations

import math

from src.constants import NATURES_JA


def rank_mult(rank: int) -> float:
    table = {-6: 2 / 8, -5: 2 / 7, -4: 2 / 6, -3: 2 / 5, -2: 2 / 4, -1: 2 / 3,
             0: 1.0, 1: 3 / 2, 2: 4 / 2, 3: 5 / 2, 4: 6 / 2, 5: 7 / 2, 6: 8 / 2}
    return table.get(max(-6, min(6, rank)), 1.0)


def n_hit_ko(min_dmg: int, max_dmg: int, hp: int) -> str:
    if max_dmg <= 0 or hp <= 0:
        return "効果なし"

    min_hits = max(1, math.ceil(hp / max_dmg))
    if min_dmg <= 0:
        return "乱数{}発以上".format(min_hits)

    max_hits = max(1, math.ceil(hp / min_dmg))
    if min_hits == max_hits:
        if min_dmg * min_hits >= hp:
            return "確定{}発".format(min_hits)
        return "乱数{}発".format(min_hits)

    return "乱数{}発".format(min_hits)


def bar_color(min_pct: float, max_pct: float) -> str:
    if max_pct >= 100:
        return "#f38ba8"
    if min_pct >= 50:
        return "#fab387"
    if max_pct >= 50:
        return "#f9e2af"
    return "#a6e3a1"


def bar_variation_color(min_pct: float, max_pct: float) -> str:
    if max_pct >= 100:
        return "#6b1a2a"
    if min_pct >= 50:
        return "#5e2d10"
    if max_pct >= 50:
        return "#5a4a0a"
    return "#1e4a1a"


def hp_color(remaining_pct: float) -> str:
    if remaining_pct <= 20:
        return "#f38ba8"
    if remaining_pct <= 50:
        return "#f9e2af"
    return "#a6e3a1"


def nature_mult_from_name(nature_ja: str, stat_key: str) -> float:
    boost, reduce = NATURES_JA.get(nature_ja or "", (None, None))
    if boost == stat_key:
        return 1.1
    if reduce == stat_key:
        return 0.9
    return 1.0


def mult_label(value: float) -> str:
    if value <= 0.95:
        return "×0.9"
    if value >= 1.05:
        return "×1.1"
    return "×1.0"


def round1(value: float) -> float:
    # Python round() , 。
    if value >= 0:
        return math.floor(value * 10 + 0.5) / 10
    return math.ceil(value * 10 - 0.5) / 10
