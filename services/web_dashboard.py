from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from services.terminal_dashboard import build_dashboard_snapshot, render_terminal_dashboard
from execution.execution_health import read_execution_health
from storage.execution_queue_store import ExecutionQueueStore
import os


_WIN_REASONS = {"TAKE_PROFIT_1", "TAKE_PROFIT_2", "TAKE_PROFIT_3", "TP1", "TP2", "TP3"}
_LOSS_REASONS = {"STOP_LOSS"}
_COUNT_REASONS = _WIN_REASONS | _LOSS_REASONS  # only these count toward stats/history


def _calc_rr(reason: str, row) -> float:
    r = reason.upper()
    if r in ("TAKE_PROFIT_3", "TP3") and row["rr_tp3"]:
        return 0.4 * float(row["rr_tp1"] or 1.0) + 0.3 * float(row["rr_tp2"] or 1.272) + 0.3 * float(row["rr_tp3"])
    if r in ("TAKE_PROFIT_2", "TP2") and row["rr_tp2"]:
        return 0.4 * float(row["rr_tp1"] or 1.0) + 0.6 * float(row["rr_tp2"])
    if r in ("TAKE_PROFIT_1", "TP1") and row["rr_tp1"]:
        return float(row["rr_tp1"])
    return 1.0


def _calc_exit(reason: str, row):
    r = reason.upper()
    if r in ("TAKE_PROFIT_3", "TP3"):
        return row["tp3_hit_price"]
    if r in ("TAKE_PROFIT_2", "TP2"):
        return row["tp2_hit_price"]
    if r in ("TAKE_PROFIT_1", "TP1"):
        return row["tp1_hit_price"]
    return row["entry_triggered_price"]


def _build_trade_stats(db_path: str) -> dict:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT close_reason, rr_tp1, rr_tp2, rr_tp3, tp1_hit_price, tp2_hit_price, tp3_hit_price
            FROM signals
            WHERE close_reason IS NOT NULL AND entry_triggered_at IS NOT NULL
            ORDER BY closed_at ASC
        """)
        rows = cur.fetchall()
        conn.close()
    except Exception:
        return {"win_rate": 0, "avg_rr": 0, "total": 0, "wins": 0, "losses": 0, "profit_factor": 0, "max_dd": 0}

    wins = losses = 0
    rr_list: list[float] = []
    equity = 0.0
    peak = 0.0
    max_dd = 0.0

    for row in rows:
        reason = (row["close_reason"] or "").upper()
        if reason not in _COUNT_REASONS:
            continue
        if reason in _WIN_REASONS:
            wins += 1
            rr = _calc_rr(reason, row)
            rr_list.append(rr)
            equity += rr
        elif reason in _LOSS_REASONS:
            losses += 1
            rr_list.append(-1.0)
            equity -= 1.0
        else:
            continue
        peak = max(peak, equity)
        dd = peak - equity  # absolute R drawdown (not percentage, avoids divide-by-zero)
        max_dd = max(max_dd, dd)

    total = wins + losses
    win_rate = round(wins / total * 100, 1) if total > 0 else 0
    avg_rr = round(sum(rr_list) / len(rr_list), 2) if rr_list else 0
    gross_win = sum(r for r in rr_list if r > 0)
    gross_loss = abs(sum(r for r in rr_list if r < 0))
    profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else 0

    return {
        "win_rate": win_rate,
        "avg_rr": avg_rr,
        "total": total,
        "wins": wins,
        "losses": losses,
        "profit_factor": profit_factor,
        "max_dd": round(max_dd, 2),  # in R units (e.g. 3.5R drawdown)
    }


def _build_trade_history(db_path: str, limit: int = 200) -> list[dict]:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT symbol, timeframe, side, entry_price, close_reason,
                   tp1_hit_price, tp2_hit_price, tp3_hit_price,
                   rr_tp1, rr_tp2, rr_tp3,
                   entry_triggered_price, closed_at, created_at
            FROM signals
            WHERE close_reason IS NOT NULL AND entry_triggered_at IS NOT NULL
            ORDER BY closed_at DESC
            LIMIT ?
        """, (limit,))
        rows = cur.fetchall()
        conn.close()
    except Exception:
        return []

    result = []
    for row in rows:
        reason = (row["close_reason"] or "").upper()
        if reason not in _COUNT_REASONS:
            continue
        is_win = reason in _WIN_REASONS
        rr = round(_calc_rr(reason, row), 2) if is_win else -1.0
        result.append({
            "closed_at": (row["closed_at"] or row["created_at"] or "")[:16].replace("T", " "),
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "side": (row["side"] or "").upper(),
            "entry": row["entry_price"],
            "exit": _calc_exit(reason, row),
            "close_reason": reason,
            "rr": rr,
            "result": "WIN" if is_win else "LOSS",
        })
    return result


_SHARED_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #0a0e1a; --surface: #111827; --surface-2: #1f2937;
  --border: #1f2937; --text: #e5e7eb; --muted: #9ca3af;
  --primary: #3b82f6; --success: #10b981; --danger: #ef4444; --warning: #f59e0b;
  --radius: 12px;
}
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; padding: 16px; }
.container { max-width: 1200px; margin: 0 auto; }
.header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; background: var(--surface); border-radius: var(--radius); margin-bottom: 16px; border: 1px solid var(--border); }
.header h1 { font-size: 20px; font-weight: 700; }
.nav { display: flex; gap: 8px; }
.nav a { padding: 8px 16px; border-radius: 8px; color: var(--muted); text-decoration: none; font-size: 14px; font-weight: 500; transition: .15s; }
.nav a:hover { background: var(--surface-2); color: var(--text); }
.nav a.active { background: var(--primary); color: #fff; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 16px; }
.stat { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; }
.stat-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 6px; }
.stat-value { font-size: 24px; font-weight: 700; }
.stat-sub { font-size: 12px; color: var(--muted); margin-top: 4px; }
.text-success { color: var(--success); }
.text-danger { color: var(--danger); }
.text-warning { color: var(--warning); }
.section { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 16px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px; }
.section h2 { font-size: 16px; font-weight: 600; }
.filter-chips { display: flex; gap: 6px; }
.chip { padding: 6px 12px; border-radius: 6px; background: var(--surface-2); color: var(--muted); font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.chip.active { background: var(--primary); color: #fff; }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); }
.table th { color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; }
.table tr:last-child td { border-bottom: none; }
.badge { padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; display: inline-block; }
.badge-long { background: rgba(16,185,129,.15); color: var(--success); }
.badge-short { background: rgba(239,68,68,.15); color: var(--danger); }
.badge-win { background: rgba(16,185,129,.15); color: var(--success); }
.badge-loss { background: rgba(239,68,68,.15); color: var(--danger); }
.badge-bull { background: rgba(16,185,129,.15); color: var(--success); }
.badge-bear { background: rgba(239,68,68,.15); color: var(--danger); }
.empty { text-align: center; padding: 40px; color: var(--muted); font-size: 14px; }
.table-wrap { overflow-x: auto; }
.err-banner { background: rgba(239,68,68,.1); border: 1px solid rgba(239,68,68,.3); border-radius: 8px; padding: 10px 14px; color: var(--danger); font-size: 13px; margin-bottom: 12px; }
.pos { color: var(--success); font-weight: 600; }
.neg { color: var(--danger); font-weight: 600; }
.muted { color: var(--muted); }
.api-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 16px; }
.api-card h2 { font-size: 14px; color: var(--muted); margin-bottom: 12px; text-transform: uppercase; letter-spacing: .5px; }
.api-row { display: grid; grid-template-columns: 1fr 1fr auto auto; gap: 8px; align-items: end; }
.api-row input { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; color: var(--text); font-size: 14px; font-family: monospace; width: 100%; }
.api-row input:focus { outline: none; border-color: var(--primary); }
.api-status { font-size: 12px; color: var(--muted); margin-top: 8px; }
.api-status .ok { color: var(--success); font-weight: 600; }
.api-status .err { color: var(--danger); font-weight: 600; }
.btn { padding: 10px 16px; border-radius: 8px; border: none; cursor: pointer; font-size: 14px; font-weight: 600; transition: .15s; white-space: nowrap; }
.btn-primary { background: var(--primary); color: #fff; }
.btn-primary:hover { background: #2563eb; }
.btn-ghost { background: var(--surface-2); color: var(--muted); }
.btn-ghost:hover { color: var(--text); }
@media (max-width: 640px) {
  .header { flex-direction: column; gap: 12px; align-items: stretch; }
  .nav { justify-content: center; }
  .api-row { grid-template-columns: 1fr; }
}
"""


def build_web_dashboard_html(symbol: str, refresh_seconds: float) -> str:
    refresh_ms = max(int(refresh_seconds * 1000), 1000)
    escaped_symbol = json.dumps(symbol)
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Trading Dashboard</title>
<style>{_SHARED_CSS}</style>
</head><body>
<div class="container">
  <div class="header">
    <h1>&#x26A1; Trading Dashboard</h1>
    <nav class="nav">
      <a href="/" class="active">Dashboard</a>
      <a href="/history">History</a>
    </nav>
  </div>
  <div id="error-slot"></div>

  <div class="api-card">
    <h2>&#x1F511; Exchange API Credentials</h2>
    <div class="api-row">
      <input type="text" id="api-key" placeholder="API Key" spellcheck="false" autocomplete="off" />
      <input type="password" id="api-secret" placeholder="API Secret" spellcheck="false" autocomplete="off" />
      <button class="btn btn-primary" onclick="saveApiCreds()">Save</button>
      <button class="btn btn-ghost" onclick="clearApiCreds()">Clear</button>
    </div>
    <div class="api-status" id="api-status">Status: <span class="err">Not configured</span></div>
  </div>

  <div class="stats-grid">
    <div class="stat"><div class="stat-label">Win Rate</div><div class="stat-value" id="s-wr">&ndash;</div><div class="stat-sub" id="s-wl">&ndash;</div></div>
    <div class="stat"><div class="stat-label">Avg RR</div><div class="stat-value" id="s-rr">&ndash;</div><div class="stat-sub">risk:reward</div></div>
    <div class="stat"><div class="stat-label">Max Drawdown</div><div class="stat-value text-danger" id="s-dd">&ndash;</div><div class="stat-sub">in R units</div></div>
    <div class="stat"><div class="stat-label">Total Trades</div><div class="stat-value" id="s-total">&ndash;</div><div class="stat-sub">closed</div></div>
    <div class="stat"><div class="stat-label">Profit Factor</div><div class="stat-value" id="s-pf">&ndash;</div><div class="stat-sub">gross W/L</div></div>
    <div class="stat"><div class="stat-label">Balance</div><div class="stat-value" id="s-bal">&ndash;</div><div class="stat-sub">USDT</div></div>
  </div>
  <div class="section">
    <div class="section-head">
      <h2>&#x1F7E2; Open Positions <span id="pos-count" style="color:var(--muted);font-weight:400;">(0)</span></h2>
    </div>
    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Symbol</th><th>Side</th><th>Entry</th><th>Mark</th><th>Qty</th><th>PnL</th></tr></thead>
        <tbody id="positions-body"><tr><td colspan="6" class="empty">Loading&hellip;</td></tr></tbody>
      </table>
    </div>
  </div>
  <div class="section">
    <div class="section-head">
      <h2>&#x26A1; Active Signals <span id="sig-count" style="color:var(--muted);font-weight:400;">(0)</span></h2>
    </div>
    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Symbol</th><th>TF</th><th>Bias</th><th>Entry</th><th>SL</th><th>TP1</th><th>RR</th></tr></thead>
        <tbody id="signals-body"><tr><td colspan="7" class="empty">Loading&hellip;</td></tr></tbody>
      </table>
    </div>
  </div>
</div>
<script>
  const _CREDS_KEY = "ew_api_v1";
  function saveApiCreds() {{
    const k = document.getElementById("api-key").value.trim();
    const s = document.getElementById("api-secret").value.trim();
    if (!k || !s) {{ document.getElementById("api-status").innerHTML = 'Status: <span class="err">Both fields required</span>'; return; }}
    localStorage.setItem(_CREDS_KEY, JSON.stringify({{key: k, secret: s}}));
    document.getElementById("api-status").innerHTML = 'Status: <span class="ok">Saved</span> &bull; key &bull;&bull;&bull;&bull;' + k.slice(-4);
  }}
  function clearApiCreds() {{
    localStorage.removeItem(_CREDS_KEY);
    document.getElementById("api-key").value = "";
    document.getElementById("api-secret").value = "";
    document.getElementById("api-status").innerHTML = 'Status: <span class="err">Cleared</span>';
  }}
  (function loadApiCreds() {{
    try {{
      const raw = localStorage.getItem(_CREDS_KEY);
      if (!raw) return;
      const c = JSON.parse(raw);
      document.getElementById("api-key").value = c.key || "";
      document.getElementById("api-secret").value = c.secret || "";
      document.getElementById("api-status").innerHTML = 'Status: <span class="ok">Saved</span> &bull; key &bull;&bull;&bull;&bull;' + (c.key||"").slice(-4);
    }} catch(_) {{}}
  }})();
</script>
<script>
(function(){{
  const SYMBOL = {escaped_symbol};
  const REFRESH_MS = {refresh_ms};

  function fmt(n, d) {{
    if (n == null || n === "" || isNaN(Number(n))) return "\u2013";
    return Number(n).toLocaleString("en-US", {{minimumFractionDigits: d, maximumFractionDigits: d}});
  }}

  async function tick() {{
    try {{
      const r = await fetch("/api/snapshot", {{cache: "no-store"}});
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || "snapshot failed");
      render(d.snapshot);
      document.getElementById("error-slot").innerHTML = "";
    }} catch(e) {{
      document.getElementById("error-slot").innerHTML =
        '<div class="err-banner">Error: ' + (e.message||e) + '</div>';
    }}
  }}

  function render(d) {{
    const st = d.stats || {{}};
    const wr = st.win_rate ?? null;
    const wrEl = document.getElementById("s-wr");
    wrEl.textContent = wr != null ? wr + "%" : "\u2013";
    wrEl.className = "stat-value" + (wr >= 50 ? " text-success" : wr != null ? " text-danger" : "");
    document.getElementById("s-wl").textContent = st.total ? st.wins + "W / " + st.losses + "L of " + st.total : "\u2013";
    document.getElementById("s-rr").textContent = st.avg_rr ?? "\u2013";
    document.getElementById("s-dd").textContent = st.max_dd != null ? "-" + st.max_dd + "R" : "\u2013";
    document.getElementById("s-total").textContent = st.total ?? "\u2013";
    document.getElementById("s-pf").textContent = st.profit_factor ?? "\u2013";
    document.getElementById("s-bal").textContent = fmt(d.wallet, 2);

    const pos = Array.isArray(d.positions) ? d.positions : [];
    document.getElementById("pos-count").textContent = "(" + pos.length + ")";
    document.getElementById("positions-body").innerHTML = pos.length
      ? pos.map(p => {{
          const pnl = Number(p.pnl);
          const side = (p.side||"").toUpperCase();
          return "<tr>"
            + "<td><b>" + (p.symbol||"\u2013") + "</b></td>"
            + "<td><span class='badge " + (side==="LONG"?"badge-long":"badge-short") + "'>" + side + "</span></td>"
            + "<td>" + fmt(p.entry,4) + "</td>"
            + "<td>" + fmt(p.mark,4) + "</td>"
            + "<td>" + fmt(p.qty,4) + "</td>"
            + "<td class='" + (pnl>0?"pos":"neg") + "'>" + (isFinite(pnl)?(pnl>=0?"+":"")+fmt(pnl,2):"\u2013") + "</td>"
            + "</tr>";
        }}).join("")
      : "<tr><td colspan='6' class='empty'>No open positions</td></tr>";

    const sigs = Array.isArray(d.signals) ? d.signals : [];
    document.getElementById("sig-count").textContent = "(" + sigs.length + ")";
    document.getElementById("signals-body").innerHTML = sigs.length
      ? sigs.map(s => {{
          const entry = parseFloat(s.entry)||0, sl = parseFloat(s.sl)||0, tp1 = parseFloat(s.tp1)||0;
          const risk = Math.abs(entry - sl);
          const rr = risk > 0 ? (Math.abs(tp1-entry)/risk).toFixed(2)+"R" : "\u2013";
          const bias = (s.bias||"").toLowerCase();
          const bb = bias.includes("bull") ? "<span class='badge badge-bull'>" + s.bias + "</span>"
                    : bias.includes("bear") ? "<span class='badge badge-bear'>" + s.bias + "</span>"
                    : s.bias||"\u2013";
          return "<tr>"
            + "<td><b>" + (s.symbol||"\u2013") + "</b></td>"
            + "<td>" + (s.timeframe||"\u2013") + "</td>"
            + "<td>" + bb + "</td>"
            + "<td>" + fmt(s.entry,4) + "</td>"
            + "<td class='neg'>" + fmt(s.sl,4) + "</td>"
            + "<td class='pos'>" + fmt(s.tp1,4) + "</td>"
            + "<td class='muted'>" + rr + "</td>"
            + "</tr>";
        }}).join("")
      : "<tr><td colspan='7' class='empty'>No active signals</td></tr>";
  }}

  tick();
  setInterval(tick, REFRESH_MS);
}})();
</script>
</body></html>
"""


def build_history_html(refresh_seconds: float) -> str:
    refresh_ms = max(int(refresh_seconds * 1000), 1000)
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Trade History</title>
<style>{_SHARED_CSS}</style>
</head><body>
<div class="container">
  <div class="header">
    <h1>&#x26A1; Trading Dashboard</h1>
    <nav class="nav">
      <a href="/">Dashboard</a>
      <a href="/history" class="active">History</a>
    </nav>
  </div>
  <div id="error-slot"></div>
  <div class="section">
    <div class="section-head">
      <h2>&#x1F4C5; Trade History</h2>
      <div class="filter-chips">
        <span class="chip" onclick="setFilter('7')">7 Days</span>
        <span class="chip active" id="chip-30" onclick="setFilter('30')">30 Days</span>
        <span class="chip" onclick="setFilter('all')">All</span>
      </div>
    </div>
    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Closed</th><th>Symbol</th><th>TF</th><th>Side</th><th>Entry</th><th>Exit</th><th>RR</th><th>Result</th></tr></thead>
        <tbody id="history-body"><tr><td colspan="8" class="empty">Loading&hellip;</td></tr></tbody>
      </table>
    </div>
  </div>
</div>
<script>
(function(){{
  const REFRESH_MS = {refresh_ms};
  let currentFilter = "30";
  let allTrades = [];

  function setFilter(f) {{
    currentFilter = f;
    document.querySelectorAll(".chip").forEach(c => c.classList.remove("active"));
    event.target.classList.add("active");
    renderTable();
  }}
  window.setFilter = setFilter;

  function filterTrades(trades, f) {{
    if (f === "all") return trades;
    const days = parseInt(f);
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    return trades.filter(t => t.closed_at && new Date(t.closed_at) >= cutoff);
  }}

  function fmt(n, d) {{
    if (n == null || n === "" || isNaN(Number(n))) return "\u2013";
    return Number(n).toLocaleString("en-US", {{minimumFractionDigits: d, maximumFractionDigits: d}});
  }}

  function renderTable() {{
    const trades = filterTrades(allTrades, currentFilter);
    const tbody = document.getElementById("history-body");
    if (!trades.length) {{
      tbody.innerHTML = "<tr><td colspan='8' class='empty'>No trades found</td></tr>";
      return;
    }}
    tbody.innerHTML = trades.map(t => {{
      const side = (t.side||"").toUpperCase();
      const isWin = t.result === "WIN";
      return "<tr>"
        + "<td class='muted'>" + (t.closed_at||"\u2013") + "</td>"
        + "<td><b>" + (t.symbol||"\u2013") + "</b></td>"
        + "<td class='muted'>" + (t.timeframe||"\u2013") + "</td>"
        + "<td><span class='badge " + (side==="LONG"?"badge-long":"badge-short") + "'>" + side + "</span></td>"
        + "<td>" + fmt(t.entry,4) + "</td>"
        + "<td>" + fmt(t.exit,4) + "</td>"
        + "<td class='" + (t.rr>0?"pos":"neg") + "'>" + (t.rr>0?"+":"") + t.rr + "R</td>"
        + "<td><span class='badge " + (isWin?"badge-win":"badge-loss") + "'>" + (t.result||"\u2013") + "</span></td>"
        + "</tr>";
    }}).join("");
  }}

  async function tick() {{
    try {{
      const r = await fetch("/api/history", {{cache: "no-store"}});
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || "history failed");
      allTrades = d.trades || [];
      renderTable();
      document.getElementById("error-slot").innerHTML = "";
    }} catch(e) {{
      document.getElementById("error-slot").innerHTML =
        '<div class="err-banner">Error: ' + (e.message||e) + '</div>';
    }}
  }}

  tick();
  setInterval(tick, REFRESH_MS);
}})();
</script>
</body></html>
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
    history_html = build_history_html(refresh_seconds)
    db_path = os.getenv("WAVE_DB_PATH", "storage/wave_engine.db")

    _cache: dict = {"payload": None, "updated_at": None}
    _cache_lock = threading.Lock()

    def _refresh_cache() -> None:
        while True:
            try:
                snapshot = build_dashboard_snapshot(symbol)
                snapshot["stats"] = _build_trade_stats(db_path)
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
            if path == "/history":
                self._send_html(history_html)
                return
            if path == "/api/snapshot":
                with _cache_lock:
                    payload = _cache["payload"]
                if payload is None:
                    self._send_json(503, {"ok": False, "error": "snapshot not ready yet, please retry"})
                else:
                    self._send_json(200, payload)
                return
            if path == "/api/history":
                try:
                    trades = _build_trade_history(db_path)
                    self._send_json(200, {"ok": True, "trades": trades})
                except Exception as exc:
                    self._send_json(500, {"ok": False, "error": str(exc)})
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
