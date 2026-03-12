import time

from analysis.level_state_engine import detect_level_state
from analysis.price_level_watcher import Level
from services.alert_state_store import AlertStateStore
from services.binance_price_service import get_last_price
from services.notifier import send_notification


def run_monitor():
    levels = [
        Level("1D Support", 65618, "support"),
        Level("1D Resistance", 74050, "resistance"),
        Level("4H Support", 69266, "support"),
        Level("4H Resistance", 71777, "resistance"),
    ]

    store = AlertStateStore()

    print("Starting live price monitor...")

    while True:
        try:
            price = get_last_price("BTCUSDT")
            print(f"BTC price: {price}")

            for level in levels:
                state = detect_level_state(
                    current_price=price,
                    level_price=level.price,
                    level_type=level.level_type,
                    tolerance=0.002,
                )

                if state is None:
                    continue

                key = f"BTCUSDT:{level.name}"

                if not store.should_alert(key, state):
                    continue

                if state == "NEAR":
                    send_notification(
                        f"⚠️ ราคาเข้าใกล้ {level.name} ({level.price})\n"
                        f"ราคาปัจจุบัน: {price}"
                    )
                elif state == "BREAK":
                    send_notification(
                        f"🚨 ราคา BREAK {level.name} ({level.price})\n"
                        f"ราคาปัจจุบัน: {price}"
                    )

            time.sleep(5)

        except Exception as e:
            print("Error:", e)
            time.sleep(10)


if __name__ == "__main__":
    run_monitor()