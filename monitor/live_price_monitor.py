from __future__ import annotations

from services.live_price_monitor import run_monitor


def monitor(symbol: str = "BTCUSDT", interval: str = "1d", limit: int = 200, sleep_seconds: int = 10) -> None:
    """Compatibility wrapper for the canonical service live monitor."""
    _ = interval
    _ = limit
    run_monitor(symbol=symbol, poll_interval=sleep_seconds)


if __name__ == "__main__":
    monitor()
