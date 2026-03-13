from analysis.price_level_watcher import Level, check_levels
from services.notifier import send_notification
from services.trading_orchestrator import _load_runtime


def load_runtime_levels(symbol: str = "BTCUSDT") -> list[Level]:
    """Load the latest dynamically calculated levels from the orchestrator runtime."""
    runtime = _load_runtime(symbol)
    return list(runtime.levels)


def check_price_and_alert(current_price: float, levels: list[Level]):
    """
    ตรวจสอบว่าราคาชนแนวรับแนวต้านหรือไม่
    ถ้าชนจะส่ง Telegram alert
    """

    alerts = check_levels(current_price, levels)

    for alert in alerts:
        send_notification(alert)

    return alerts
