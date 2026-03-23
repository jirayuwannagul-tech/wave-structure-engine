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
    <title>Elliott Wave Dashboard</title>
    <style>
      :root {{
        --bg: #0b0d10;
        --card: #11151b;
        --card-header: #161b23;
        --border: #1e2530;
        --border-bright: #29303a;
        --text: #d8e1ea;
        --muted: #6b7f96;
        --green: #3dd68c;
        --green-dim: #1a4a33;
        --red: #f87171;
        --red-dim: #4a1a1a;
        --yellow: #fbbf24;
        --yellow-dim: #3d2e0a;
        --blue: #60a5fa;
        --blue-dim: #0d2040;
        --accent: #2563eb;
      }}
      * {{ box-sizing: border-box; margin: 0; padding: 0; }}
      body {{
        min-height: 100vh;
        background: var(--bg);
        color: var(--text);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 14px;
        line-height: 1.5;
      }}
      /* ── Header ── */
      .header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 14px 24px;
        border-bottom: 1px solid var(--border);
        background: #0d1117;
        position: sticky;
        top: 0;
        z-index: 10;
      }}
      .header-left {{
        display: flex;
        align-items: center;
        gap: 10px;
      }}
      .logo-dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--green);
        box-shadow: 0 0 8px var(--green);
        animation: pulse 2s ease-in-out infinite;
      }}
      @keyframes pulse {{
        0%, 100% {{ opacity: 1; }}
        50% {{ opacity: 0.4; }}
      }}
      .logo-text {{
        font-size: 15px;
        font-weight: 600;
        letter-spacing: 0.02em;
        color: var(--text);
      }}
      .logo-sym {{
        color: var(--blue);
      }}
      .header-right {{
        display: flex;
        align-items: center;
        gap: 16px;
        color: var(--muted);
        font-size: 12px;
      }}
      #last-update {{
        font-variant-numeric: tabular-nums;
      }}
      /* ── Layout ── */
      .page {{
        max-width: 1200px;
        margin: 0 auto;
        padding: 20px 24px 40px;
        display: flex;
        flex-direction: column;
        gap: 20px;
      }}
      /* ── Cards ── */
      .card {{
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 10px;
        overflow: hidden;
      }}
      .card-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 10px 16px;
        background: var(--card-header);
        border-bottom: 1px solid var(--border);
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
      }}
      .card-body {{
        padding: 14px 16px;
      }}
      /* ── Status grid ── */
      .status-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 12px;
        padding: 14px 16px;
      }}
      .status-item {{
        display: flex;
        flex-direction: column;
        gap: 4px;
      }}
      .status-label {{
        font-size: 11px;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }}
      .status-value {{
        font-size: 15px;
        font-weight: 600;
        font-variant-numeric: tabular-nums;
      }}
      /* ── Balance row ── */
      .balance-row {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 0;
      }}
      .balance-item {{
        padding: 14px 20px;
        border-right: 1px solid var(--border);
        display: flex;
        flex-direction: column;
        gap: 4px;
      }}
      .balance-item:last-child {{
        border-right: none;
      }}
      .balance-label {{
        font-size: 11px;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }}
      .balance-value {{
        font-size: 22px;
        font-weight: 700;
        font-variant-numeric: tabular-nums;
        letter-spacing: -0.01em;
      }}
      .balance-unit {{
        font-size: 12px;
        color: var(--muted);
        font-weight: 400;
      }}
      /* ── Table ── */
      table {{
        width: 100%;
        border-collapse: collapse;
      }}
      th {{
        padding: 8px 12px;
        text-align: left;
        font-size: 11px;
        font-weight: 600;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.06em;
        border-bottom: 1px solid var(--border);
        white-space: nowrap;
      }}
      td {{
        padding: 10px 12px;
        border-bottom: 1px solid var(--border);
        font-variant-numeric: tabular-nums;
        font-size: 13px;
      }}
      tr:last-child td {{
        border-bottom: none;
      }}
      tr:hover td {{
        background: rgba(255,255,255,0.02);
      }}
      .empty-row td {{
        text-align: center;
        color: var(--muted);
        padding: 20px;
      }}
      /* ── Badges ── */
      .badge {{
        display: inline-flex;
        align-items: center;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }}
      .badge-bullish {{
        background: var(--green-dim);
        color: var(--green);
        border: 1px solid rgba(61,214,140,0.25);
      }}
      .badge-bearish {{
        background: var(--red-dim);
        color: var(--red);
        border: 1px solid rgba(248,113,113,0.25);
      }}
      .badge-ok {{
        background: var(--green-dim);
        color: var(--green);
      }}
      .badge-err {{
        background: var(--red-dim);
        color: var(--red);
      }}
      .badge-warn {{
        background: var(--yellow-dim);
        color: var(--yellow);
      }}
      /* ── PnL colors ── */
      .pos {{ color: var(--green); }}
      .neg {{ color: var(--red); }}
      .neu {{ color: var(--muted); }}
      /* ── Price chip ── */
      .price-chip {{
        display: inline-flex;
        align-items: baseline;
        gap: 4px;
        font-size: 28px;
        font-weight: 700;
        letter-spacing: -0.02em;
        font-variant-numeric: tabular-nums;
      }}
      .price-sym {{
        font-size: 13px;
        color: var(--muted);
        font-weight: 400;
        letter-spacing: 0;
      }}
      /* ── Top row ── */
      .top-row {{
        display: grid;
        grid-template-columns: 1fr 2fr;
        gap: 20px;
      }}
      @media (max-width: 640px) {{
        .top-row {{ grid-template-columns: 1fr; }}
        .balance-row {{ grid-template-columns: 1fr; }}
        .balance-item {{ border-right: none; border-bottom: 1px solid var(--border); }}
      }}
      /* ── Error / loading ── */
      .error-banner {{
        background: var(--red-dim);
        border: 1px solid rgba(248,113,113,0.3);
        border-radius: 8px;
        padding: 12px 16px;
        color: var(--red);
        font-size: 13px;
      }}
    </style>
  </head>
  <body>
    <div class="header">
      <div class="header-left">
        <div class="logo-dot" id="live-dot"></div>
        <span class="logo-text">Elliott Wave <span class="logo-sym">{symbol}</span></span>
      </div>
      <div class="header-right">
        <span id="last-update">–</span>
        <span>read-only</span>
      </div>
    </div>

    <div class="page" id="page">
      <div style="color:var(--muted);padding:40px;text-align:center">Loading…</div>
    </div>

    <script>
      const symbol = {escaped_symbol};
      const refreshMs = {refresh_ms};

      function fmt(v) {{
        if (v == null || v === '' || v === '-') return '–';
        const n = parseFloat(v);
        if (isNaN(n)) return String(v);
        if (Math.abs(n) >= 10000) return n.toLocaleString('en-US', {{maximumFractionDigits: 2}});
        if (Math.abs(n) >= 100)   return n.toLocaleString('en-US', {{maximumFractionDigits: 4}});
        return n.toLocaleString('en-US', {{maximumFractionDigits: 6}});
      }}

      function pnlClass(v) {{
        const n = parseFloat(v);
        if (isNaN(n)) return 'neu';
        return n > 0 ? 'pos' : n < 0 ? 'neg' : 'neu';
      }}

      function badge(bias) {{
        const b = (bias || '').toLowerCase();
        if (b === 'bullish') return '<span class="badge badge-bullish">▲ Long</span>';
        if (b === 'bearish') return '<span class="badge badge-bearish">▼ Short</span>';
        return '<span class="badge badge-warn">' + (bias || '–') + '</span>';
      }}

      function statusBadge(val) {{
        if (val === 'active') return '<span class="badge badge-ok">● active</span>';
        if (val === 'ok')     return '<span class="badge badge-ok">● ok</span>';
        if (val === 'n/a')    return '<span class="badge badge-warn">n/a</span>';
        return '<span class="badge badge-err">✕ ' + (val || 'unknown') + '</span>';
      }}

      function renderDashboard(s) {{
        const signals = s.signals || [];
        const positions = s.positions || [];

        const priceCard = `
          <div class="card">
            <div class="card-header"><span>Market</span></div>
            <div class="card-body">
              <div class="price-chip">
                ${{fmt(s.current_price)}}
                <span class="price-sym">USDT</span>
              </div>
              <div style="margin-top:10px;font-size:12px;color:var(--muted)">
                ${{s.symbol}} · ${{s.exchange}}
              </div>
              <div style="margin-top:10px;font-size:12px;color:var(--muted)">
                Monitoring: ${{(s.monitored_symbols||[]).join(' · ')}}
              </div>
            </div>
          </div>`;

        const sysCard = `
          <div class="card">
            <div class="card-header"><span>System</span></div>
            <div class="status-grid">
              <div class="status-item">
                <div class="status-label">Connection</div>
                <div class="status-value">${{statusBadge(s.connection)}}</div>
              </div>
              <div class="status-item">
                <div class="status-label">Orchestrator</div>
                <div class="status-value">${{statusBadge(s.orchestrator)}}</div>
              </div>
              <div class="status-item">
                <div class="status-label">News Monitor</div>
                <div class="status-value">${{statusBadge(s.news_monitor)}}</div>
              </div>
            </div>
          </div>`;

        const balCard = `
          <div class="card">
            <div class="card-header"><span>Wallet</span></div>
            <div class="balance-row">
              <div class="balance-item">
                <div class="balance-label">Total</div>
                <div class="balance-value">${{fmt(s.wallet)}} <span class="balance-unit">USDT</span></div>
              </div>
              <div class="balance-item">
                <div class="balance-label">Available</div>
                <div class="balance-value">${{fmt(s.available)}} <span class="balance-unit">USDT</span></div>
              </div>
              <div class="balance-item">
                <div class="balance-label">Unrealized PnL</div>
                <div class="balance-value ${{pnlClass(s.upnl)}}">${{fmt(s.upnl)}} <span class="balance-unit">USDT</span></div>
              </div>
            </div>
          </div>`;

        const posRows = positions.length
          ? positions.map(p => `
            <tr>
              <td style="font-weight:600">${{p.symbol}}</td>
              <td><span class="badge ${{p.side==='LONG'?'badge-bullish':'badge-bearish'}}">${{p.side==='LONG'?'▲':'▼'}} ${{p.side}}</span></td>
              <td>${{fmt(p.qty)}}</td>
              <td>${{fmt(p.entry)}}</td>
              <td>${{fmt(p.mark)}}</td>
              <td class="${{pnlClass(p.pnl)}}">${{fmt(p.pnl)}}</td>
            </tr>`).join('')
          : '<tr class="empty-row"><td colspan="6">No open positions</td></tr>';

        const posCard = `
          <div class="card">
            <div class="card-header">
              <span>Positions</span>
              <span>${{positions.length}} open</span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Symbol</th><th>Side</th><th>Qty</th>
                  <th>Entry</th><th>Mark</th><th>PnL</th>
                </tr>
              </thead>
              <tbody>${{posRows}}</tbody>
            </table>
          </div>`;

        const sigRows = signals.length
          ? signals.map(sig => {{
              const entry = parseFloat(sig.entry) || 0;
              const sl    = parseFloat(sig.sl)    || 0;
              const tp1   = parseFloat(sig.tp1)   || 0;
              const risk  = Math.abs(entry - sl);
              const rr    = risk > 0 ? Math.abs(tp1 - entry) / risk : 0;
              return `
                <tr>
                  <td style="font-weight:600">${{sig.symbol}}</td>
                  <td><span style="background:rgba(255,255,255,0.06);padding:2px 7px;border-radius:4px;font-size:11px">${{sig.timeframe}}</span></td>
                  <td>${{badge(sig.bias)}}</td>
                  <td style="font-weight:600">${{fmt(sig.entry)}}</td>
                  <td class="neg">${{fmt(sig.sl)}}</td>
                  <td class="pos">${{fmt(sig.tp1)}}</td>
                  <td style="color:var(--muted)">${{rr > 0 ? rr.toFixed(2) + 'R' : '–'}}</td>
                </tr>`;
            }}).join('')
          : '<tr class="empty-row"><td colspan="7">No active signals</td></tr>';

        const sigCard = `
          <div class="card">
            <div class="card-header">
              <span>Signals</span>
              <span>${{signals.length}} active</span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Symbol</th><th>TF</th><th>Bias</th>
                  <th>Entry</th><th>SL</th><th>TP1</th><th>RR</th>
                </tr>
              </thead>
              <tbody>${{sigRows}}</tbody>
            </table>
          </div>`;

        return `
          <div class="top-row">
            ${{priceCard}}
            ${{sysCard}}
          </div>
          ${{balCard}}
          ${{posCard}}
          ${{sigCard}}`;
      }}

      async function refresh() {{
        const res = await fetch(`/api/snapshot?symbol=${{encodeURIComponent(symbol)}}`, {{ cache: 'no-store' }});
        const payload = await res.json();
        if (!payload.ok) throw new Error(payload.error || 'snapshot failed');
        document.getElementById('page').innerHTML = renderDashboard(payload.snapshot);
        document.getElementById('last-update').textContent = payload.updated_at;
        document.getElementById('live-dot').style.background = 'var(--green)';
      }}

      async function loop() {{
        try {{
          await refresh();
        }} catch (error) {{
          document.getElementById('page').innerHTML =
            `<div class="error-banner">⚠ Dashboard error: ${{error.message}}</div>`;
          document.getElementById('live-dot').style.background = 'var(--red)';
          document.getElementById('last-update').textContent = 'update failed';
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
            if path == "/heartbeat":
                self._send_heartbeat()
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

        def _send_heartbeat(self) -> None:
            try:
                with open("heartbeat.txt") as f:
                    import json as _json
                    data = _json.load(f)
                self._send_json(200, {"ok": True, **data})
            except FileNotFoundError:
                self._send_json(503, {"ok": False, "error": "heartbeat.txt not found — orchestrator not running"})
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})

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
