from services.web_dashboard import build_web_dashboard_html


def test_build_web_dashboard_html_contains_terminal_shell_and_api_refresh():
    html = build_web_dashboard_html("BTCUSDT", 5.0)

    assert "Elliott Wave Dashboard" in html
    assert "read-only" in html
    assert "/api/snapshot" in html
    assert "setInterval(loop, refreshMs)" in html
    assert "BTCUSDT" in html
