from __future__ import annotations

import os

import requests


def _build_message(message: str) -> str:
    header = os.getenv("TELEGRAM_MESSAGE_HEADER", "").strip()
    footer = os.getenv("TELEGRAM_MESSAGE_FOOTER", "").strip()

    parts = []

    if header:
        parts.append(header)

    parts.append(message)

    if footer:
        parts.append(footer)

    return "\n\n".join(parts)


def send_notification(message: str) -> bool:
    """
    ส่งข้อความไป Telegram
    ถ้ายังไม่ได้ตั้งค่า env จะ fallback เป็น print()
    """

    final_message = _build_message(message)

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not bot_token or not chat_id:
        print(final_message)
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": final_message,
    }

    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    return True