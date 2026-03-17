from services.notifier import _build_message, resolve_topic_id


def test_resolve_topic_id_uses_env_mapping(monkeypatch):
    monkeypatch.setenv("TOPIC_NORMAL_ID", "2")
    monkeypatch.setenv("TELEGRAM_TOPIC_ID", "590")
    monkeypatch.setenv("TOPIC_CHAT_ID", "1")

    assert resolve_topic_id(topic_key="daily_summary") == 2
    assert resolve_topic_id(timeframe="1D") == 590
    assert resolve_topic_id(timeframe="4H") == 1


def test_build_message_replaces_symbol_placeholder_in_header(monkeypatch):
    monkeypatch.setenv("TELEGRAM_MESSAGE_HEADER", "📊 {symbol} Elliott Wave Alert")
    monkeypatch.setenv("TELEGRAM_MESSAGE_FOOTER", "")

    message = _build_message("signal ready", symbol="ethusdt", timeframe="4h")

    assert message.startswith("📊 ETHUSDT Elliott Wave Alert")
    assert message.endswith("signal ready")


def test_build_message_replaces_legacy_btc_header_with_actual_symbol(monkeypatch):
    monkeypatch.setenv("TELEGRAM_MESSAGE_HEADER", "📊 BTCUSDT Elliott Wave Alert")
    monkeypatch.setenv("TELEGRAM_MESSAGE_FOOTER", "")

    message = _build_message("signal ready", symbol="DOGEUSDT")

    assert message.startswith("📊 DOGEUSDT Elliott Wave Alert")
