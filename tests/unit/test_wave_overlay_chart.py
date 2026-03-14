from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from services.wave_overlay_chart import build_wave_overlay_svg


def test_build_wave_overlay_svg_writes_svg(tmp_path, monkeypatch):
    class Pivot:
        def __init__(self, timestamp, price):
            self.timestamp = pd.Timestamp(timestamp, tz="UTC")
            self.price = price

    runtime = SimpleNamespace(
        analyses=[
            {
                "timeframe": "1D",
                "current_price": 70000.0,
                "inprogress": SimpleNamespace(
                    is_valid=True,
                    pivots=[
                        Pivot("2026-03-01", 74050.0),
                        Pivot("2026-03-05", 65618.0),
                        Pivot("2026-03-10", 71777.0),
                    ],
                    wave_number="3",
                ),
                "primary_pattern": None,
            },
            {
                "timeframe": "4H",
                "current_price": 70000.0,
                "inprogress": None,
                "primary_pattern": SimpleNamespace(
                    a=Pivot("2026-03-11 16:00:00", 71321.0),
                    b=Pivot("2026-03-12 04:00:00", 69205.91),
                    c=Pivot("2026-03-12 08:00:00", 70800.0),
                ),
            },
        ]
    )

    df_1d = pd.DataFrame(
        {
            "open_time": pd.to_datetime(["2026-03-01", "2026-03-05", "2026-03-10"], utc=True),
            "close": [73000.0, 66000.0, 70000.0],
        }
    )
    df_4h = pd.DataFrame(
        {
            "open_time": pd.to_datetime(["2026-03-11 16:00:00", "2026-03-12 04:00:00", "2026-03-12 08:00:00"], utc=True),
            "close": [71321.0, 69205.91, 70800.0],
        }
    )

    monkeypatch.setattr("services.wave_overlay_chart._load_runtime", lambda symbol, retries=1: runtime)
    monkeypatch.setattr(
        "services.wave_overlay_chart._load_timeframe_df",
        lambda symbol, timeframe, limit: df_1d if timeframe == "1d" else df_4h,
    )

    output = build_wave_overlay_svg("BTCUSDT", output_path=tmp_path / "overlay.svg")

    content = output.read_text(encoding="utf-8")
    assert output.exists()
    assert "BTCUSDT 1D / 4H Wave Overlay" in content
    assert "#ffffff" in content
    assert "#ef4444" in content
