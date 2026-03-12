from __future__ import annotations

from dataclasses import dataclass

from analysis.level_state_engine import detect_level_state


@dataclass
class Level:
    name: str
    price: float
    level_type: str  # "support" หรือ "resistance"


def check_levels(current_price: float, levels: list[Level], tolerance: float = 0.002):
    alerts = []

    for level in levels:
        state = detect_level_state(
            current_price=current_price,
            level_price=level.price,
            level_type=level.level_type,
            tolerance=tolerance,
        )

        if state == "NEAR":
            alerts.append(
                f"⚠️ ราคาเข้าใกล้ {level.name} ({level.price})\n"
                f"ราคาปัจจุบัน: {current_price}"
            )

        elif state == "BREAK":
            alerts.append(
                f"🚨 ราคา BREAK {level.name} ({level.price})\n"
                f"ราคาปัจจุบัน: {current_price}"
            )

    return alerts