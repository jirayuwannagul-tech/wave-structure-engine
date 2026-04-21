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
<title>Elliott Wave \u2022 {symbol}</title>
<style>
  :root {{
    --bg:#07090c; --bg-2:#0b0f15; --card:#10151d; --card-2:#141a24;
    --border:#1c2430; --border-2:#2a3342;
    --text:#e6ecf3; --muted:#7689a0; --muted-2:#4a5668;
    --green:#22d39a; --green-dim:rgba(34,211,154,.12);
    --red:#ff5d6c; --red-dim:rgba(255,93,108,.12);
    --yellow:#f5b942; --yellow-dim:rgba(245,185,66,.12);
    --blue:#5b9dff; --blue-dim:rgba(91,157,255,.12);
    --accent:#6366f1; --accent-2:#8b5cf6;
    --grad: linear-gradient(135deg,#6366f1 0%,#8b5cf6 50%,#ec4899 100%);
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{height:100%}}
  body{{
    background:
      radial-gradient(1200px 600px at 80% -10%, rgba(99,102,241,.10), transparent 60%),
      radial-gradient(900px 500px at -10% 110%, rgba(236,72,153,.08), transparent 60%),
      var(--bg);
    color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;
    font-size:13.5px; line-height:1.5;
    -webkit-font-smoothing:antialiased;
  }}
  .header{{
    display:flex; align-items:center; justify-content:space-between;
    padding:14px 22px; border-bottom:1px solid var(--border);
    background:rgba(7,9,12,.85); backdrop-filter:blur(12px);
    position:sticky; top:0; z-index:20;
  }}
  .brand{{display:flex;align-items:center;gap:12px}}
  .logo{{
    width:32px;height:32px;border-radius:9px;
    background:var(--grad); display:grid;place-items:center;
    font-weight:800;font-size:14px;color:#fff;
    box-shadow:0 6px 18px rgba(99,102,241,.45);
  }}
  .brand-text{{display:flex;flex-direction:column;line-height:1.1}}
  .brand-title{{font-size:14px;font-weight:700;letter-spacing:.02em}}
  .brand-sub{{font-size:11px;color:var(--muted)}}
  .brand-sub b{{color:var(--blue);font-weight:600}}
  .header-right{{display:flex;align-items:center;gap:14px}}
  .live{{
    display:inline-flex;align-items:center;gap:6px;
    padding:4px 10px;border-radius:999px;
    background:var(--green-dim); color:var(--green);
    font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
    border:1px solid rgba(34,211,154,.25);
  }}
  .dot{{width:6px;height:6px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);animation:pulse 1.6s ease-in-out infinite}}
  @keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
  #last-update{{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}}
  .page{{
    max-width:1400px; margin:0 auto; padding:18px 22px 32px;
    display:grid; grid-template-columns: 1fr; gap:14px;
  }}
  .row{{display:grid;gap:14px}}
  .row-2{{grid-template-columns:1.2fr .8fr}}
  .row-3{{grid-template-columns:repeat(3,1fr)}}
  .row-2-1{{grid-template-columns:2fr 1fr}}
  @media (max-width:1080px){{
    .row-2,.row-3,.row-2-1{{grid-template-columns:1fr}}
  }}
  .card{{
    background:linear-gradient(180deg,var(--card) 0%, var(--bg-2) 100%);
    border:1px solid var(--border); border-radius:14px;
    overflow:hidden; box-shadow:0 1px 0 rgba(255,255,255,.02) inset, 0 8px 24px rgba(0,0,0,.25);
  }}
  .card-h{{
    display:flex;align-items:center;justify-content:space-between;
    padding:11px 16px; border-bottom:1px solid var(--border);
    background:linear-gradient(180deg, rgba(255,255,255,.02), transparent);
  }}
  .card-title{{
    font-size:11px;font-weight:700;letter-spacing:.1em;
    text-transform:uppercase;color:var(--muted);
  }}
  .card-title .accent{{color:var(--text)}}
  .card-b{{padding:14px 16px}}
  .hero{{
    display:flex;align-items:center;justify-content:space-between;
    gap:18px; padding:18px 20px;
    background:
      radial-gradient(600px 200px at 100% 0%, rgba(99,102,241,.12), transparent 70%),
      linear-gradient(180deg,var(--card-2),var(--card));
  }}
  .hero-left{{display:flex;flex-direction:column;gap:6px;min-width:0}}
  .hero-symbol{{
    display:flex;align-items:center;gap:10px;
    font-size:13px;color:var(--muted);font-weight:600;letter-spacing:.04em;
  }}
  .hero-symbol .sym{{
    color:var(--text);font-size:18px;font-weight:700;letter-spacing:.01em;
  }}
  .hero-symbol .ex{{
    padding:2px 8px;border:1px solid var(--border-2);border-radius:6px;
    font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;
  }}
  .price{{
    font-size:42px;font-weight:800;letter-spacing:-.02em;
    font-variant-numeric:tabular-nums; line-height:1.05;
    background:var(--grad); -webkit-background-clip:text;background-clip:text;
    -webkit-text-fill-color:transparent;
  }}
  .price-meta{{display:flex;gap:10px;align-items:center;color:var(--muted);font-size:12px}}
  .hero-right{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:flex-end}}
  .pill{{
    display:inline-flex;align-items:center;gap:6px;
    padding:6px 11px;border-radius:999px;
    background:var(--card-2); border:1px solid var(--border-2);
    font-size:11.5px;color:var(--muted);font-weight:600;
  }}
  .pill .k{{color:var(--muted-2)}}
  .pill .v{{color:var(--text);font-variant-numeric:tabular-nums}}
  .pill.ok .v{{color:var(--green)}}
  .pill.warn .v{{color:var(--yellow)}}
  .pill.err .v{{color:var(--red)}}
  .pill .led{{width:6px;height:6px;border-radius:50%;background:var(--muted-2)}}
  .pill.ok .led{{background:var(--green);box-shadow:0 0 6px var(--green)}}
  .pill.warn .led{{background:var(--yellow);box-shadow:0 0 6px var(--yellow)}}
  .pill.err .led{{background:var(--red);box-shadow:0 0 6px var(--red)}}
  .wallet-grid{{display:grid;grid-template-columns:repeat(3,1fr)}}
  .w-item{{padding:16px 18px;border-right:1px solid var(--border);display:flex;flex-direction:column;gap:6px}}
  .w-item:last-child{{border-right:none}}
  .w-label{{font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;font-weight:600}}
  .w-value{{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.01em}}
  .w-unit{{font-size:11px;color:var(--muted);font-weight:500;margin-left:4px}}
  @media (max-width:640px){{.wallet-grid{{grid-template-columns:1fr}}.w-item{{border-right:none;border-bottom:1px solid var(--border)}}}}
  .table-wrap{{overflow-x:auto}}
  table{{width:100%;border-collapse:collapse;min-width:520px}}
  th{{
    padding:9px 14px;text-align:left;font-size:10.5px;font-weight:700;
    color:var(--muted);text-transform:uppercase;letter-spacing:.08em;
    border-bottom:1px solid var(--border);white-space:nowrap;
    background:rgba(255,255,255,.015);
  }}
  td{{padding:11px 14px;border-bottom:1px solid var(--border);font-variant-numeric:tabular-nums;font-size:13px;white-space:nowrap}}
  tr:last-child td{{border-bottom:none}}
  tbody tr{{transition:background .12s}}
  tbody tr:hover td{{background:rgba(99,102,241,.05)}}
  .empty td{{text-align:center;color:var(--muted-2);padding:28px;font-style:italic}}
  .badge{{display:inline-flex;align-items:center;padding:3px 9px;border-radius:6px;font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}}
  .b-bull{{background:var(--green-dim);color:var(--green);border:1px solid rgba(34,211,154,.25)}}
  .b-bear{{background:var(--red-dim);color:var(--red);border:1px solid rgba(255,93,108,.25)}}
  .b-neu{{background:rgba(118,137,160,.12);color:var(--muted);border:1px solid var(--border-2)}}
  .pos{{color:var(--green);font-weight:600}}
  .neg{{color:var(--red);font-weight:600}}
  .neu{{color:var(--muted)}}
  .chips{{display:flex;flex-wrap:wrap;gap:6px}}
  .chip{{
    padding:4px 10px;border-radius:7px;
    background:var(--card-2);border:1px solid var(--border);
    font-size:11.5px;font-weight:600;color:var(--text);
    font-variant-numeric:tabular-nums;
  }}
  .err-banner{{
    background:var(--red-dim);border:1px solid rgba(255,93,108,.3);
    border-radius:10px;padding:11px 14px;color:var(--red);font-size:12.5px;
  }}
  .skeleton{{color:var(--muted-2);font-style:italic}}
</style>
</head>
<body>
  <div class="header">
    <div class="brand">
      <div class="logo">EW</div>
      <div class="brand-text">
        <div class="brand-title">Elliott Wave <span style="color:var(--muted)">&bull;</span> <b style="color:var(--blue)">{symbol}</b></div>
        <div class="brand-sub">Realtime trading dashboard</div>
      </div>
    </div>
    <div class="header-right">
      <span class="live"><span class="dot"></span> Live</span>
      <span id="last-update">&ndash;</span>
    </div>
  </div>

  <div class="page">
    <div id="error-slot"></div>

    <div class="card">
      <div class="hero">
        <div class="hero-left">
          <div class="hero-symbol">
            <span class="sym" id="h-symbol">&ndash;</span>
            <span class="ex" id="h-exchange">&ndash;</span>
          </div>
          <div class="price" id="h-price">&ndash;</div>
          <div class="price-meta">
            <span>Last update <span id="h-time">&ndash;</span></span>
          </div>
        </div>
        <div class="hero-right">
          <span class="pill" id="p-conn"><span class="led"></span><span class="k">Conn</span>&nbsp;<span class="v">&ndash;</span></span>
          <span class="pill" id="p-orch"><span class="led"></span><span class="k">Orch</span>&nbsp;<span class="v">&ndash;</span></span>
          <span class="pill" id="p-news"><span class="led"></span><span class="k">News</span>&nbsp;<span class="v">&ndash;</span></span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-h"><span class="card-title">Wallet <span class="accent">USDT</span></span></div>
      <div class="wallet-grid">
        <div class="w-item">
          <span class="w-label">Total Balance</span>
          <span class="w-value"><span id="w-wallet">&ndash;</span><span class="w-unit">USDT</span></span>
        </div>
        <div class="w-item">
          <span class="w-label">Available</span>
          <span class="w-value"><span id="w-available">&ndash;</span><span class="w-unit">USDT</span></span>
        </div>
        <div class="w-item">
          <span class="w-label">Unrealized PnL</span>
          <span class="w-value" id="w-upnl">&ndash;</span>
        </div>
      </div>
    </div>

    <div class="row row-2">
      <div class="card">
        <div class="card-h">
          <span class="card-title">Open Positions</span>
          <span class="card-title" id="pos-count" style="color:var(--text)">0</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr>
              <th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th><th>Mark</th><th style="text-align:right">PnL</th>
            </tr></thead>
            <tbody id="positions-body">
              <tr class="empty"><td colspan="6">Loading&hellip;</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-h">
          <span class="card-title">Active Signals</span>
          <span class="card-title" id="sig-count" style="color:var(--text)">0</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr>
              <th>Symbol</th><th>TF</th><th>Bias</th><th>Entry</th><th>SL</th><th>TP1</th>
            </tr></thead>
            <tbody id="signals-body">
              <tr class="empty"><td colspan="6">Loading&hellip;</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-h">
        <span class="card-title">Monitored</span>
        <span class="card-title" id="sym-count" style="color:var(--text)">0</span>
      </div>
      <div class="card-b">
        <div class="chips" id="symbols-chips"><span class="skeleton">Loading&hellip;</span></div>
      </div>
    </div>
  </div>

<script>
(function(){{
  const SYMBOL = {escaped_symbol};
  const REFRESH_MS = {refresh_ms};
  const $ = (id) => document.getElementById(id);

  function fmt(n, d){{
    if (n === null || n === undefined || n === "" || Number.isNaN(Number(n))) return "\u2013";
    const x = Number(n);
    return x.toLocaleString("en-US", {{minimumFractionDigits: d, maximumFractionDigits: d}});
  }}
  function pnlClass(n){{
    const x = Number(n);
    if (!isFinite(x) || x === 0) return "neu";
    return x > 0 ? "pos" : "neg";
  }}
  function setStatusPill(el, val){{
    el.classList.remove("ok","warn","err");
    const v = (val ?? "").toString().toLowerCase();
    let cls = "warn", txt = val ?? "\u2013";
    if (["ok","online","running","connected","active","up","healthy"].includes(v)) cls = "ok";
    else if (["off","offline","stopped","error","down","disconnected","fail","failed"].includes(v)) cls = "err";
    el.classList.add(cls);
    el.querySelector(".v").textContent = txt;
  }}

  async function tick(){{
    try{{
      const r = await fetch("/api/snapshot", {{cache:"no-store"}});
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || "snapshot failed");
      render(d.snapshot);
      $("error-slot").innerHTML = "";
    }}catch(e){{
      $("error-slot").innerHTML =
        '<div class="err-banner">Connection error: ' + (e.message||e) + '</div>';
    }}
    $("last-update").textContent = "Updated " + new Date().toLocaleTimeString();
  }}

  function render(d){{
    $("h-symbol").textContent   = d.symbol || SYMBOL;
    $("h-exchange").textContent = d.exchange || "\u2013";
    $("h-price").textContent    = fmt(d.current_price, 4);
    $("h-time").textContent     = new Date().toLocaleTimeString();

    setStatusPill($("p-conn"), d.connection);
    setStatusPill($("p-orch"), d.orchestrator);
    setStatusPill($("p-news"), d.news_monitor);

    $("w-wallet").textContent    = fmt(d.wallet, 2);
    $("w-available").textContent = fmt(d.available, 2);
    const upnl = Number(d.upnl);
    const upnlEl = $("w-upnl");
    upnlEl.textContent = (isFinite(upnl) ? (upnl >= 0 ? "+" : "") + fmt(upnl, 2) + " USDT" : "\u2013");
    upnlEl.className = "w-value " + pnlClass(upnl);

    const pb = $("positions-body");
    const pos = Array.isArray(d.positions) ? d.positions : [];
    $("pos-count").textContent = pos.length;
    pb.innerHTML = pos.length ? pos.map(p => {{
      const side = (p.side||"").toLowerCase();
      const sb = side === "long" || side === "buy"
        ? '<span class="badge b-bull">'+(p.side||"LONG")+'</span>'
        : '<span class="badge b-bear">'+(p.side||"SHORT")+'</span>';
      const pnl = Number(p.pnl);
      return '<tr>'
        + '<td><b>'+(p.symbol||"\u2013")+'</b></td>'
        + '<td>'+sb+'</td>'
        + '<td>'+fmt(p.qty,4)+'</td>'
        + '<td>'+fmt(p.entry,4)+'</td>'
        + '<td>'+fmt(p.mark,4)+'</td>'
        + '<td style="text-align:right" class="'+pnlClass(pnl)+'">'+(isFinite(pnl)?(pnl>=0?"+":"")+fmt(pnl,2):"\u2013")+'</td>'
        + '</tr>';
    }}).join("") : '<tr class="empty"><td colspan="6">No open positions</td></tr>';

    const sb = $("signals-body");
    const sigs = Array.isArray(d.signals) ? d.signals : [];
    $("sig-count").textContent = sigs.length;
    sb.innerHTML = sigs.length ? sigs.map(s => {{
      const bias = (s.bias||"").toLowerCase();
      const bb = bias.includes("bull") || bias === "long"
        ? '<span class="badge b-bull">'+(s.bias||"BULL")+'</span>'
        : (bias.includes("bear") || bias === "short"
            ? '<span class="badge b-bear">'+(s.bias||"BEAR")+'</span>'
            : '<span class="badge b-neu">'+(s.bias||"\u2013")+'</span>');
      return '<tr>'
        + '<td><b>'+(s.symbol||"\u2013")+'</b></td>'
        + '<td>'+(s.timeframe||"\u2013")+'</td>'
        + '<td>'+bb+'</td>'
        + '<td>'+fmt(s.entry,4)+'</td>'
        + '<td class="neg">'+fmt(s.sl,4)+'</td>'
        + '<td class="pos">'+fmt(s.tp1,4)+'</td>'
        + '</tr>';
    }}).join("") : '<tr class="empty"><td colspan="6">No active signals</td></tr>';

    const syms = Array.isArray(d.monitored_symbols) ? d.monitored_symbols : [];
    $("sym-count").textContent = syms.length;
    $("symbols-chips").innerHTML = syms.length
      ? syms.map(s => '<span class="chip">'+s+'</span>').join("")
      : '<span class="skeleton">No symbols</span>';
  }}

  tick();
  setInterval(tick, REFRESH_MS);
}})();
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
    import threading

    html = build_web_dashboard_html(symbol, refresh_seconds)

    _cache: dict = {"payload": None, "updated_at": None}
    _cache_lock = threading.Lock()

    def _refresh_cache() -> None:
        while True:
            try:
                snapshot = build_dashboard_snapshot(symbol)
                updated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                payload = {
                    "ok": True,
                    "snapshot": snapshot,
                    "terminal": render_terminal_dashboard(snapshot),
                    "updated_at": updated_at,
                }
            except Exception as exc:
                payload = {"ok": False, "error": str(exc)}
            with _cache_lock:
                _cache["payload"] = payload
                _cache["updated_at"] = datetime.now(UTC)
            import time as _time
            _time.sleep(30)

    t = threading.Thread(target=_refresh_cache, daemon=True)
    t.start()

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send_html(html)
                return
            if path == "/api/snapshot":
                with _cache_lock:
                    payload = _cache["payload"]
                if payload is None:
                    self._send_json(503, {"ok": False, "error": "snapshot not ready yet, please retry"})
                else:
                    self._send_json(200, payload)
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
