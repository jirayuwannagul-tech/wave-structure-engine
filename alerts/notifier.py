from __future__ import annotations


def send_notification(message: str) -> None:
    print("=== DAILY ALERT ===")
    print(message)


if __name__ == "__main__":
    send_notification("test notification")