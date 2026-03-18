"""Contract tests: recorded Binance-style JSON shapes (no live HTTP)."""

import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "binance_query_order_filled.json"


def test_recorded_query_order_response_has_expected_status_fields():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data.get("status") == "FILLED"
    assert "orderId" in data
    assert data.get("reduceOnly") is True
