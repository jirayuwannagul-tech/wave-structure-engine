from analysis.price_level_watcher import Level, check_levels
from services.notifier import send_notification


def check_price_and_alert(current_price: float, levels: list[Level]):
    """
    ตรวจสอบว่าราคาชนแนวรับแนวต้านหรือไม่
    ถ้าชนจะส่ง Telegram alert
    """

    alerts = check_levels(current_price, levels)

    for alert in alerts:
        send_notification(alert)

    return alerts