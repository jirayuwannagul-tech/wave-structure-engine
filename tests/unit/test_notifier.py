from alerts.notifier import send_notification


def test_send_notification_prints_message(capsys):
    send_notification("hello test")

    captured = capsys.readouterr()

    assert "=== DAILY ALERT ===" in captured.out
    assert "hello test" in captured.out