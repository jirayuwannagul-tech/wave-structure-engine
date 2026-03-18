from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from scheduler.daily_scheduler import build_daily_scenario_message


THAI_TZ = ZoneInfo("Asia/Bangkok")


@dataclass
class Scenario:
    bias: str
    confirmation: float
    invalidation: float


@dataclass
class Pos:
    structure: str = "ABC_CORRECTION"
    position: str = "WAVE_C_END"
    bias: str = "BULLISH"


class Runtime:
    def __init__(self, symbol: str, *, bias: str):
        self.symbol = symbol
        self.analyses = [
            {
                "timeframe": "1D",
                "position": Pos(),
                "scenarios": [Scenario(bias=bias, confirmation=10.0, invalidation=8.0)],
            }
        ]


def test_build_daily_scenario_message_includes_support_resistance_and_wave():
    now = datetime(2026, 3, 18, 7, 5, tzinfo=THAI_TZ)
    msg = build_daily_scenario_message(
        [Runtime("AAAUSDT", bias="BULLISH"), Runtime("BBBUSDT", bias="BEARISH")],
        now=now,
        timeframe="1D",
    )

    assert "📌 Scenario Update" in msg
    assert "AAAUSDT" in msg
    assert "BBBUSDT" in msg

    # Bullish: support=invalidation (8), resistance=confirmation (10)
    assert "AAAUSDT\n- แนวรับ: 8\n- แนวต้าน: 10\n- เฝ้าดู:" in msg
    # Bearish: support=confirmation (10), resistance=invalidation (8)
    assert "BBBUSDT\n- แนวรับ: 10\n- แนวต้าน: 8\n- เฝ้าดู:" in msg
