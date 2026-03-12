from analysis.price_level_watcher import Level
from services.binance_price_service import get_last_price
from services.level_alert_service import check_price_and_alert


def run_once():
    price = get_last_price("BTCUSDT")

    levels = [
        Level("1D Support", 65618, "support"),
        Level("1D Resistance", 74050, "resistance"),
        Level("4H Support", 69266, "support"),
        Level("4H Resistance", 71777, "resistance"),
    ]
    alerts = check_price_and_alert(price, levels)

    print(f"ราคาปัจจุบัน: {price}")
    print(alerts)


if __name__ == "__main__":
    run_once()