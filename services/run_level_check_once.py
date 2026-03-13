from services.binance_price_service import get_last_price
from services.level_alert_service import check_price_and_alert, load_runtime_levels


def run_once(symbol: str = "BTCUSDT"):
    price = get_last_price(symbol)
    levels = load_runtime_levels(symbol)
    alerts = check_price_and_alert(price, levels)

    print(f"ราคาปัจจุบัน: {price}")
    print(alerts)


if __name__ == "__main__":
    run_once()
