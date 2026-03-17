import time

from analysis.level_state_engine import detect_level_state
from analysis.price_level_watcher import Level
from services.alert_state_store import AlertStateStore
from services.binance_price_service import get_last_price
from services.level_alert_service import load_runtime_levels
from services.notifier import send_notification


def _process_price_update(
    symbol: str,
    current_price: float,
    levels: list[Level],
    store: AlertStateStore,
    tolerance: float = 0.002,
) -> None:
    for level in levels:
        state = detect_level_state(
            current_price=current_price,
            level_price=level.price,
            level_type=level.level_type,
            tolerance=tolerance,
        )

        if state is None:
            continue

        key = f"{symbol}:{level.name}"

        if not store.should_alert(key, state):
            continue

        if state == "NEAR":
            send_notification(
                f"⚠️ ราคาเข้าใกล้ {level.name} ({level.price})\n"
                f"ราคาปัจจุบัน: {current_price}",
                symbol=symbol,
            )
        elif state == "BREAK":
            send_notification(
                f"🚨 ราคา BREAK {level.name} ({level.price})\n"
                f"ราคาปัจจุบัน: {current_price}",
                symbol=symbol,
            )


def run_monitor(
    symbol: str = "BTCUSDT",
    poll_interval: float = 5.0,
    levels_refresh_interval: float = 60.0,
    max_cycles: int | None = None,
):
    levels: list[Level] = []
    next_level_refresh_at = 0.0
    store = AlertStateStore()
    completed_cycles = 0

    print("Starting live price monitor...")

    while True:
        try:
            now = time.time()
            if not levels or now >= next_level_refresh_at:
                levels = load_runtime_levels(symbol)
                next_level_refresh_at = now + max(float(levels_refresh_interval), 0.0)
                print(f"Loaded {len(levels)} levels for {symbol}")

            price = get_last_price(symbol)
            print(f"{symbol} price: {price}")
            _process_price_update(symbol, price, levels, store)

            completed_cycles += 1
            if max_cycles is not None and completed_cycles >= max_cycles:
                return

            time.sleep(poll_interval)

        except Exception as e:
            print("Error:", e)
            next_level_refresh_at = 0.0
            time.sleep(10)


if __name__ == "__main__":
    run_monitor()
