from __future__ import annotations

import hashlib
import html
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

from services.notifier import send_notification
from storage.wave_repository import WaveRepository


THAI_TZ = ZoneInfo("Asia/Bangkok")
NEWS_FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
]
BTC_KEYWORDS = {"btc", "bitcoin"}
CONTEXT_KEYWORDS = {
    "etf": "ETF",
    "fed": "FED",
    "cpi": "CPI",
    "inflation": "INFLATION",
    "rates": "RATES",
    "rate": "RATES",
    "sec": "SEC",
    "macro": "MACRO",
}


def _translate_enabled() -> bool:
    return (os.getenv("NEWS_TRANSLATE_SUMMARY_TH", "true") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _localname(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = html.unescape(clean)
    return re.sub(r"\s+", " ", clean).strip()


def _first_sentence(text: str, max_len: int = 180) -> str:
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    sentence = parts[0].strip() if parts else text.strip()
    if len(sentence) < 20 and len(parts) > 1:
        sentence = text.strip()
    if len(sentence) <= max_len:
        return sentence
    return sentence[: max_len - 3].rstrip() + "..."


def translate_summary_to_thai(summary: str, translator=None) -> str:
    if not summary:
        return ""

    if not _translate_enabled():
        return summary

    try:
        if translator is None:
            from deep_translator import GoogleTranslator

            translator = GoogleTranslator(source="auto", target="th")

        translated = (translator.translate(summary) or "").strip()
        return translated or summary
    except Exception:
        return summary


def _parse_datetime(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None

    try:
        dt = parsedate_to_datetime(raw)
    except Exception:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return raw, raw

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    published_at = dt.astimezone(UTC).replace(microsecond=0).isoformat()
    display = dt.astimezone(THAI_TZ).strftime("%Y-%m-%d %H:%M ICT")
    return published_at, display


def _extract_items(feed_xml: str, source: str) -> list[dict]:
    root = ET.fromstring(feed_xml)
    items: list[dict] = []

    for element in root.iter():
        if _localname(element.tag) not in {"item", "entry"}:
            continue

        title = ""
        link = ""
        description = ""
        published_raw = None

        for child in list(element):
            tag = _localname(child.tag)
            text = (child.text or "").strip()

            if tag == "title":
                title = text
            elif tag in {"description", "summary", "content"} and not description:
                description = text
            elif tag in {"pubDate", "published", "updated"} and published_raw is None:
                published_raw = text
            elif tag == "link":
                if text:
                    link = text
                elif child.attrib.get("href"):
                    link = child.attrib["href"]

        if not title or not link:
            continue

        published_at, published_display = _parse_datetime(published_raw)
        items.append(
            {
                "source": source,
                "title": _strip_html(title),
                "link": link.strip(),
                "summary": _first_sentence(_strip_html(description)),
                "published_at": published_at,
                "published_display": published_display or "",
            }
        )

    return items


def _extract_tags(title: str, summary: str) -> list[str]:
    haystack = f"{title} {summary}".lower()
    tags = []

    if any(keyword in haystack for keyword in BTC_KEYWORDS):
        tags.append("BTC")

    for keyword, label in CONTEXT_KEYWORDS.items():
        if keyword in haystack and label not in tags:
            tags.append(label)

    return tags


def _is_btc_relevant(title: str, summary: str) -> bool:
    haystack = f"{title} {summary}".lower()
    return any(keyword in haystack for keyword in BTC_KEYWORDS)


def _external_id(item: dict) -> str:
    raw = f"{item['source']}|{item['link']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_relevant_btc_news() -> list[dict]:
    news_items: list[dict] = []

    for source, url in NEWS_FEEDS:
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            feed_items = _extract_items(response.text, source)
        except Exception as exc:
            print(f"RSS fetch failed for {source}: {exc}")
            continue

        for item in feed_items:
            if not _is_btc_relevant(item["title"], item["summary"]):
                continue
            item["tags"] = _extract_tags(item["title"], item["summary"])
            item["summary_th"] = translate_summary_to_thai(item["summary"])
            item["external_id"] = _external_id(item)
            news_items.append(item)

    news_items.sort(
        key=lambda item: item.get("published_at") or "",
        reverse=True,
    )
    return news_items


def build_news_digest(items: list[dict], now: datetime | None = None) -> str:
    if now is None:
        now = datetime.now(THAI_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=THAI_TZ)
    else:
        now = now.astimezone(THAI_TZ)

    lines = [
        "📰 BTC News Context",
        f"🕒 Updated: {now.strftime('%Y-%m-%d %H:%M ICT')}",
        "",
    ]

    for idx, item in enumerate(items, start=1):
        tags = " | ".join(item.get("tags") or ["BTC"])
        lines.extend(
            [
                f"{idx}. [{item['source']}] {item['title']}",
                f"Tags: {tags}",
                f"Time: {item.get('published_display') or '-'}",
            ]
        )
        if item.get("summary_th") or item.get("summary"):
            lines.append(f"Thai Summary: {item.get('summary_th') or item.get('summary')}")
        lines.append(f"Link: {item['link']}")
        if idx != len(items):
            lines.append("")

    return "\n".join(lines)


def process_news_cycle(
    repository: WaveRepository | None = None,
    max_items: int = 3,
) -> list[dict]:
    repository = repository or WaveRepository()
    fetched = fetch_relevant_btc_news()
    unsent = [item for item in fetched if not repository.has_news_item(item["external_id"])]

    if not unsent:
        return []

    selected = unsent[:max_items]
    message = build_news_digest(selected)
    send_notification(message, topic_key="normal", include_layout=False)

    for item in selected:
        repository.record_news_item(
            source=item["source"],
            title=item["title"],
            link=item["link"],
            published_at=item.get("published_at"),
            summary_text=item.get("summary_th") or item.get("summary"),
            tag_text=",".join(item.get("tags") or []),
            external_id=item["external_id"],
        )

    return selected


def run_news_monitor(
    poll_interval: float = 900.0,
    once: bool = False,
    repository: WaveRepository | None = None,
) -> None:
    repository = repository or WaveRepository()

    while True:
        try:
            selected = process_news_cycle(repository=repository)
            print(f"news items sent: {len(selected)}")

            if once:
                return

            time.sleep(poll_interval)
        except Exception as exc:
            print(f"news monitor error: {exc}")
            if once:
                raise
            time.sleep(max(poll_interval, 60.0))
