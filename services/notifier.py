from __future__ import annotations

import os

import requests


_TIMEFRAME_TOPIC_ENVS = {
    "1D": "TELEGRAM_TOPIC_ID",
    "4H": "TOPIC_CHAT_ID",
}
_TOPIC_KEY_ENVS = {
    "DAILY_SUMMARY": "TOPIC_NORMAL_ID",
    "NORMAL": "TOPIC_NORMAL_ID",
}


def _clean_env_value(value: str | None) -> str:
    if value is None:
        return ""
    return value.split("#", 1)[0].strip()


def _build_message(message: str) -> str:
    header = _clean_env_value(os.getenv("TELEGRAM_MESSAGE_HEADER", ""))
    footer = _clean_env_value(os.getenv("TELEGRAM_MESSAGE_FOOTER", ""))

    parts = []

    if header:
        parts.append(header)

    parts.append(message)

    if footer:
        parts.append(footer)

    return "\n\n".join(parts)


def resolve_topic_id(
    topic_id: str | int | None = None,
    topic_key: str | None = None,
    timeframe: str | None = None,
) -> int | None:
    if topic_id is not None and str(topic_id).strip():
        return int(str(topic_id).strip())

    if topic_key:
        env_name = _TOPIC_KEY_ENVS.get(topic_key.strip().upper())
        if env_name:
            value = _clean_env_value(os.getenv(env_name))
            if value:
                return int(value)

    if timeframe:
        env_name = _TIMEFRAME_TOPIC_ENVS.get(timeframe.strip().upper())
        if env_name:
            value = _clean_env_value(os.getenv(env_name))
            if value:
                return int(value)

    return None


def send_notification(
    message: str,
    *,
    topic_id: str | int | None = None,
    topic_key: str | None = None,
    timeframe: str | None = None,
    include_layout: bool = True,
) -> bool:
    final_message = _build_message(message) if include_layout else message

    bot_token = _clean_env_value(os.getenv("TELEGRAM_BOT_TOKEN", ""))
    chat_id = _clean_env_value(os.getenv("TELEGRAM_CHAT_ID", ""))

    if not bot_token or not chat_id:
        print(final_message)
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": final_message,
    }

    resolved_topic_id = resolve_topic_id(
        topic_id=topic_id,
        topic_key=topic_key,
        timeframe=timeframe,
    )
    if resolved_topic_id is not None:
        payload["message_thread_id"] = resolved_topic_id

    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    return True
