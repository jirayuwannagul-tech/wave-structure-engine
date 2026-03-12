from services.notifier import resolve_topic_id


def test_resolve_topic_id_uses_env_mapping(monkeypatch):
    monkeypatch.setenv("TOPIC_NORMAL_ID", "2")
    monkeypatch.setenv("TELEGRAM_TOPIC_ID", "590")
    monkeypatch.setenv("TOPIC_CHAT_ID", "1")

    assert resolve_topic_id(topic_key="daily_summary") == 2
    assert resolve_topic_id(timeframe="1D") == 590
    assert resolve_topic_id(timeframe="4H") == 1
