from services.news_rss_monitor import (
    _extract_items,
    _extract_tags,
    _is_btc_relevant,
    build_news_digest,
    translate_summary_to_thai,
)


RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Bitcoin ETF inflows rise as macro sentiment improves</title>
      <link>https://example.com/btc-etf</link>
      <description><![CDATA[Bitcoin gains traction as ETF demand and softer inflation data support risk appetite.]]></description>
      <pubDate>Thu, 12 Mar 2026 08:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Altcoin meme rally cools</title>
      <link>https://example.com/altcoins</link>
      <description><![CDATA[Speculative interest fades across meme coins.]]></description>
      <pubDate>Thu, 12 Mar 2026 09:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def test_extract_items_parses_rss_feed():
    items = _extract_items(RSS_XML, "CoinDesk")

    assert len(items) == 2
    assert items[0]["source"] == "CoinDesk"
    assert items[0]["title"] == "Bitcoin ETF inflows rise as macro sentiment improves"
    assert items[0]["link"] == "https://example.com/btc-etf"


def test_btc_relevance_and_tags():
    title = "Bitcoin ETF inflows rise as macro sentiment improves"
    summary = "Bitcoin gains traction as ETF demand and softer inflation data support risk appetite."

    assert _is_btc_relevant(title, summary) is True
    assert _extract_tags(title, summary) == ["BTC", "ETF", "INFLATION", "MACRO"]


def test_build_news_digest_contains_expected_fields():
    digest = build_news_digest(
        [
            {
                "source": "CoinDesk",
                "title": "Bitcoin ETF inflows rise as macro sentiment improves",
                "link": "https://example.com/btc-etf",
                "summary": "Bitcoin gains traction as ETF demand and softer inflation data support risk appetite.",
                "summary_th": "บิตคอยน์ได้แรงหนุนจากความต้องการ ETF และข้อมูลเงินเฟ้อที่ผ่อนคลายลง",
                "published_display": "2026-03-12 15:00 ICT",
                "tags": ["BTC", "ETF", "INFLATION"],
            }
        ]
    )

    assert "📰 BTC News Context" in digest
    assert "[CoinDesk] Bitcoin ETF inflows rise as macro sentiment improves" in digest
    assert "Tags: BTC | ETF | INFLATION" in digest
    assert "Thai Summary: บิตคอยน์ได้แรงหนุนจากความต้องการ ETF และข้อมูลเงินเฟ้อที่ผ่อนคลายลง" in digest
    assert "Link: https://example.com/btc-etf" in digest


def test_translate_summary_to_thai_uses_translator_and_falls_back():
    class TranslatorStub:
        def translate(self, text):
            return "สรุปภาษาไทย"

    assert translate_summary_to_thai("Bitcoin rises", translator=TranslatorStub()) == "สรุปภาษาไทย"

    class BrokenTranslator:
        def translate(self, text):
            raise RuntimeError("boom")

    assert translate_summary_to_thai("Bitcoin rises", translator=BrokenTranslator()) == "Bitcoin rises"
