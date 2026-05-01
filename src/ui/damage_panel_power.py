from __future__ import annotations

from typing import Callable

from src.models import MoveInfo


def power_option_value(data: object) -> int:
    if isinstance(data, tuple) and len(data) >= 1:
        try:
            return int(data[0])
        except (TypeError, ValueError):
            return 0
    try:
        return int(data)
    except (TypeError, ValueError):
        return 0


def discrete_options(values: list[int], prefix: str = "威力") -> list[tuple[str, object]]:
    result: list[tuple[str, object]] = []
    used: set[int] = set()
    for value in values:
        v = int(value)
        if v <= 0 or v in used:
            continue
        used.add(v)
        result.append(("{} {}".format(prefix, v), v))
    return result


def hp_percent_options(
    label_prefix: str,
    percent_to_power: Callable[[int], int],
) -> list[tuple[str, object]]:
    # 1% 10%。
    hp_steps = [100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 1]
    options: list[tuple[str, object]] = []
    for pct in hp_steps:
        power = max(1, int(percent_to_power(pct)))
        options.append(("{}{}% (威力 {})".format(label_prefix, pct, power), (power, pct)))
    return options


def reversal_flail_power_from_hp_percent(hp_percent: int) -> int:
    # /: HP/HP (Gen3+)
    scaled = int(hp_percent) * 48
    if scaled <= 100:
        return 200
    if scaled <= 400:
        return 150
    if scaled <= 900:
        return 100
    if scaled <= 1600:
        return 80
    if scaled <= 3200:
        return 40
    return 20


def eruption_family_power_from_hp_percent(hp_percent: int) -> int:
    return max(1, (150 * int(hp_percent)) // 100)


def wring_out_family_power_from_hp_percent(hp_percent: int) -> int:
    return max(1, (120 * int(hp_percent)) // 100 + 1)


def variable_power_options(move: MoveInfo) -> list[tuple[str, object]]:
    name = move.name_ja
    base_power = move.power or 1

    if name in ("ころがる", "アイスボール"):
        normal = [30, 60, 120, 240, 480]
        rolled = [value * 2 for value in normal]
        options: list[tuple[str, int]] = []
        for idx, value in enumerate(normal, start=1):
            options.append(("{} {}回目 ({})".format(name, idx, value), value))
        for idx, value in enumerate(rolled, start=1):
            options.append(("まるくなる後 {}回目 ({})".format(idx, value), value))
        return options

    if name == "れんぞくぎり":
        return [
            ("1回目 (40)", 40),
            ("2回目 (80)", 80),
            ("3回目以降 (160)", 160),
        ]

    if name == "おはかまいり":
        return [("味方{}体ひんし ({})".format(i, 50 + 50 * i), 50 + 50 * i) for i in range(0, 6)]

    if name == "ふんどのこぶし":
        return [("被弾{}回 ({})".format(i, 50 + 50 * i), 50 + 50 * i) for i in range(0, 7)]

    if name == "エコーボイス":
        return [("連続{}回目 ({})".format(i, min(200, 40 * i)), min(200, 40 * i)) for i in range(1, 6)]

    if name in ("アシストパワー", "つけあがる"):
        return [("上昇ランク合計 {} ({})".format(i, 20 + 20 * i), 20 + 20 * i) for i in range(0, 43)]

    if name == "おしおき":
        return [("相手上昇ランク合計 {} ({})".format(i, min(200, 60 + 20 * i)), min(200, 60 + 20 * i)) for i in range(0, 8)]

    if name in ("しおふき", "ふんか", "ドラゴンエナジー"):
        return hp_percent_options("自分HP ", eruption_family_power_from_hp_percent)

    if name in ("じたばた", "きしかいせい"):
        return hp_percent_options("自分HP ", reversal_flail_power_from_hp_percent)

    if name in ("しぼりとる", "にぎりつぶす"):
        return hp_percent_options("相手HP ", wring_out_family_power_from_hp_percent)

    if name == "からげんき":
        return [("通常 (70)", 70), ("状態異常時 (140)", 140)]

    if name in ("たたりめ", "ベノムショック", "しおみず", "かたきうち"):
        return [("通常 ({})".format(base_power), base_power), ("条件成立 ({})".format(base_power * 2), base_power * 2)]

    if name == "ジャイロボール":
        return discrete_options(list(range(150, 0, -1)))

    if name == "エレキボール":
        return discrete_options([40, 60, 80, 120, 150])

    if name == "ゆきなだれ":
        return [("通常 (60)", 60), ("後攻被弾後 (120)", 120)]

    if name == "はたきおとす":
        return [("通常 (65)", 65), ("道具あり対象 (97)", 97)]

    if name == "マグニチュード":
        return discrete_options([10, 30, 50, 70, 90, 110, 150])

    return []
