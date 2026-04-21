"""Line Messaging API bot — admin notifications and activate/deactivate via Line."""

from __future__ import annotations

import hashlib
import hmac
import base64
import json
import logging
import os

import requests

logger = logging.getLogger(__name__)

_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
_ADMIN_USER_ID = os.getenv("LINE_ADMIN_USER_ID", "")
_LINE_API = "https://api.line.me/v2/bot/message"


def verify_signature(body: bytes, signature: str) -> bool:
    expected = base64.b64encode(
        hmac.new(_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def _push(user_id: str, messages: list[dict]) -> None:
    requests.post(
        f"{_LINE_API}/push",
        headers={"Authorization": f"Bearer {_TOKEN}", "Content-Type": "application/json"},
        json={"to": user_id, "messages": messages},
        timeout=10,
    )


def notify_new_account(account_id: int, label: str, token: str) -> None:
    """Send admin a message with Activate button when new account registers."""
    if not _ADMIN_USER_ID:
        return
    dashboard_url = f"https://alphafutures.net/u/{token}"
    _push(_ADMIN_USER_ID, [
        {
            "type": "flex",
            "altText": f"New member: {label}",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [{"type": "text", "text": "⚡ New Member", "weight": "bold", "color": "#ffffff", "size": "lg"}],
                    "backgroundColor": "#3b82f6",
                    "paddingAll": "16px",
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {"type": "text", "text": label, "weight": "bold", "size": "xl"},
                        {"type": "text", "text": f"ID: #{account_id}", "color": "#9ca3af", "size": "sm"},
                        {"type": "text", "text": "Status: INACTIVE — waiting for activation", "color": "#ef4444", "size": "sm", "wrap": True},
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#10b981",
                            "action": {
                                "type": "postback",
                                "label": "✅ Activate",
                                "data": f"action=activate&id={account_id}",
                                "displayText": f"Activate #{account_id} {label}",
                            },
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "uri",
                                "label": "View Dashboard",
                                "uri": dashboard_url,
                            },
                        },
                    ],
                },
            },
        }
    ])


def notify_activated(account_id: int, label: str) -> None:
    if not _ADMIN_USER_ID:
        return
    _push(_ADMIN_USER_ID, [{
        "type": "text",
        "text": f"✅ Activated #{account_id} {label} — system will now trade for this account.",
    }])


def handle_webhook(body: bytes, signature: str, account_store) -> dict:
    """Process incoming Line webhook event. Returns dict for HTTP response."""
    if not verify_signature(body, signature):
        return {"status": 401, "body": "Invalid signature"}

    try:
        data = json.loads(body)
    except Exception:
        return {"status": 400, "body": "Bad JSON"}

    for event in data.get("events", []):
        event_type = event.get("type")
        if event_type == "postback":
            _handle_postback(event, account_store)

    return {"status": 200, "body": "OK"}


def _handle_postback(event: dict, account_store) -> None:
    data = event.get("postback", {}).get("data", "")
    params = dict(kv.split("=", 1) for kv in data.split("&") if "=" in kv)
    action = params.get("action")
    account_id = int(params.get("id", 0))

    if action == "activate" and account_id:
        ok = account_store.activate(account_id)
        acc = account_store.get_by_id(account_id)
        label = acc.label if acc else str(account_id)
        if ok:
            notify_activated(account_id, label)
        reply_token = event.get("replyToken")
        if reply_token:
            _reply(reply_token, f"{'✅ Activated' if ok else '❌ Failed'}: #{account_id} {label}")

    elif action == "deactivate" and account_id:
        ok = account_store.deactivate(account_id)
        acc = account_store.get_by_id(account_id)
        label = acc.label if acc else str(account_id)
        reply_token = event.get("replyToken")
        if reply_token:
            _reply(reply_token, f"{'⛔ Deactivated' if ok else '❌ Failed'}: #{account_id} {label}")


def _reply(reply_token: str, text: str) -> None:
    requests.post(
        f"{_LINE_API}/reply",
        headers={"Authorization": f"Bearer {_TOKEN}", "Content-Type": "application/json"},
        json={"replyToken": reply_token, "messages": [{"type": "text", "text": text}]},
        timeout=10,
    )
