from __future__ import annotations

import json
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from services.terminal_dashboard import build_dashboard_snapshot, render_terminal_dashboard
from execution.execution_health import read_execution_health
from storage.execution_queue_store import ExecutionQueueStore
import os


def build_web_dashboard_html(symbol: str, refresh_seconds: float) -> str:
    refresh_ms = max(int(refresh_seconds * 1000), 1000)
    escaped_symbol = json.dumps(symbol)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Elliott Wave Terminal</title>
    <style>
      :root {{
        --bg: #0b0d10;
        --panel: #11151b;
        --panel-top: #1b2027;
        --border: #29303a;
        --text: #d8e1ea;
        --muted: #8ea0b5;
        --green: #9cff57;
        --red: #ff5f56;
        --yellow: #ffbd2e;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        min-height: 100vh;
        background:
          radial-gradient(circle at top left, rgba(69, 90, 120, 0.22), transparent 32%),
          radial-gradient(circle at bottom right, rgba(13, 148, 136, 0.14), transparent 28%),
          var(--bg);
        color: var(--text);
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        display: grid;
        place-items: center;
        padding: 24px;
      }}
      .window {{
        width: min(1080px, 100%);
        border: 1px solid var(--border);
        border-radius: 16px;
        overflow: hidden;
        box-shadow: 0 30px 80px rgba(0, 0, 0, 0.45);
        background: rgba(10, 12, 15, 0.92);
        backdrop-filter: blur(10px);
      }}
      .topbar {{
        display: flex;
        align-items: center;
        gap: 14px;
        background: linear-gradient(180deg, var(--panel-top), #141820);
        border-bottom: 1px solid var(--border);
        padding: 12px 16px;
      }}
      .lights {{
        display: flex;
        gap: 8px;
      }}
      .light {{
        width: 12px;
        height: 12px;
        border-radius: 999px;
      }}
      .red {{ background: var(--red); }}
      .yellow {{ background: var(--yellow); }}
      .green {{ background: #27c93f; }}
      .title {{
        color: var(--muted);
        font-size: 14px;
        letter-spacing: 0.02em;
      }}
      .screen {{
        background: linear-gradient(180deg, rgba(19,23,29,0.96), rgba(10,12,15,0.98));
        padding: 20px;
      }}
      pre {{
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;
        font-size: 15px;
        line-height: 1.6;
        color: var(--green);
      }}
      .footer {{
        display: flex;
        justify-content: space-between;
        gap: 12px;
        padding: 12px 16px;
        border-top: 1px solid var(--border);
        color: var(--muted);
        font-size: 13px;
        background: rgba(13, 16, 20, 0.95);
      }}
    </style>
  </head>
  <body>
    <div class="window">
      <div class="topbar">
        <div class="lights">
          <span class="light red"></span>
          <span class="light yellow"></span>
          <span class="light green"></span>
        </div>
        <div class="title">Elliott Wave Terminal | {symbol}</div>
      </div>
      <div class="screen">
        <pre id="screen">$ loading dashboard...</pre>
      </div>
      <div class="footer">
        <span id="status">refreshing...</span>
        <span>read-only dashboard</span>
      </div>
    </div>
    <script>
      const symbol = {escaped_symbol};
      const refreshMs = {refresh_ms};

      async function refresh() {{
        const res = await fetch(`/api/snapshot?symbol=${{encodeURIComponent(symbol)}}`, {{ cache: 'no-store' }});
        const payload = await res.json();
        if (!payload.ok) {{
          throw new Error(payload.error || 'snapshot failed');
        }}
        document.getElementById('screen').textContent = payload.terminal;
        document.getElementById('status').textContent = `last update: ${{payload.updated_at}}`;
      }}

      async function loop() {{
        try {{
          await refresh();
        }} catch (error) {{
          document.getElementById('screen').textContent = `$ dashboard error\\n${{error.message}}`;
          document.getElementById('status').textContent = 'update failed';
        }}
      }}

      loop();
      setInterval(loop, refreshMs);
    </script>
  </body>
</html>
"""


def run_web_dashboard(
    symbol: str = "BTCUSDT",
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    refresh_seconds: float = 5.0,
) -> None:
    html = build_web_dashboard_html(symbol, refresh_seconds)

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send_html(html)
                return
            if path == "/api/snapshot":
                self._send_snapshot(symbol)
                return
            if path == "/healthz":
                self._send_json(200, {"ok": True})
                return
            if path == "/api/execution_health":
                self._send_execution_health()
                return
            self._send_json(404, {"ok": False, "error": "not found"})

        def log_message(self, format, *args):  # noqa: A003
            return

        def _send_html(self, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send_snapshot(self, dashboard_symbol: str) -> None:
            try:
                snapshot = build_dashboard_snapshot(dashboard_symbol)
                payload = {
                    "ok": True,
                    "snapshot": snapshot,
                    "terminal": render_terminal_dashboard(snapshot),
                    "updated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
                }
                self._send_json(200, payload)
            except Exception as exc:  # pragma: no cover - defensive
                self._send_json(500, {"ok": False, "error": str(exc)})

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_execution_health(self) -> None:
            db_path = os.getenv("WAVE_DB_PATH", "storage/wave_engine.db")
            q = ExecutionQueueStore(db_path=db_path)
            keys = [
                "execution:last_open_ok",
                "execution:last_close_ok",
                "execution:last_queue_enqueue",
                "execution:last_queue_ok",
                "execution:last_queue_error",
                "execution:circuit_opened",
                "execution:circuit_until",
                "execution:circuit_failures",
                "execution:last_de_risk_applied",
            ]
            payload = {k: read_execution_health(k, db_path=db_path) for k in keys}
            payload["queue_pending"] = q.count_pending()
            self._send_json(200, {"ok": True, "execution": payload})

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Web dashboard running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
