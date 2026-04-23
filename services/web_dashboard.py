from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from services.terminal_dashboard import build_dashboard_snapshot, render_terminal_dashboard
from execution.execution_health import read_execution_health
from storage.execution_queue_store import ExecutionQueueStore
from storage.account_store import AccountStore
from services.line_bot import handle_webhook, notify_new_account
import os


_COUNTABLE_REASONS = {"TAKE_PROFIT_1", "TAKE_PROFIT_2", "TAKE_PROFIT_3", "STOP_LOSS"}
_TP_W1, _TP_W2, _TP_W3 = 0.40, 0.30, 0.30  # must match execution/models.py defaults


def _realized_rr(row) -> float:
    """Replicate google_sheets_sync._weighted_realized_rr for closed STOPPED trades."""
    reason = (row["close_reason"] or "").upper()
    rr1 = float(row["rr_tp1"]) if row["rr_tp1"] else None
    rr2 = float(row["rr_tp2"]) if row["rr_tp2"] else None
    rr3 = float(row["rr_tp3"]) if row["rr_tp3"] else None
    tp1_hit = bool(row["tp1_hit_at"])
    tp2_hit = bool(row["tp2_hit_at"])
    tp3_hit = bool(row["tp3_hit_at"])

    rr = 0.0
    if tp1_hit and rr1 is not None:
        rr += _TP_W1 * rr1
    if tp2_hit and rr2 is not None:
        rr += _TP_W2 * rr2
    if tp3_hit and rr3 is not None:
        rr += _TP_W3 * rr3

    # residual position that wasn't closed at a TP
    remaining = 1.0 - ((_TP_W1 if tp1_hit else 0) + (_TP_W2 if tp2_hit else 0) + (_TP_W3 if tp3_hit else 0))
    remaining = max(remaining, 0.0)
    if remaining > 0 and reason == "STOP_LOSS":
        stop = float(row["managed_stop_loss"]) if row["managed_stop_loss"] else float(row["stop_loss"])
        entry = float(row["entry_triggered_price"] or row["entry_price"])
        sl_original = float(row["stop_loss"])
        risk = abs(entry - sl_original)
        if risk > 0:
            side = (row["side"] or "").upper()
            if side == "LONG":
                residual = (stop - entry) / risk
            else:
                residual = (entry - stop) / risk
            rr += remaining * residual
        else:
            rr += remaining * -1.0
    elif remaining > 0:
        rr += remaining * -1.0

    return round(rr, 4)


def _trade_result(row) -> tuple[str, float]:
    """Returns (result_label, realized_rr). Only call for countable trades."""
    reason = (row["close_reason"] or "").upper()
    tp1_hit = bool(row["tp1_hit_at"])
    tp2_hit = bool(row["tp2_hit_at"])
    tp3_hit = bool(row["tp3_hit_at"])
    rr = _realized_rr(row)

    if reason == "TAKE_PROFIT_3" or tp3_hit:
        return "TP3_HIT", rr
    if reason == "STOP_LOSS":
        if tp2_hit:
            return "TP2_THEN_SL", rr
        if tp1_hit:
            return "TP1_THEN_SL", rr
        return "SL_HIT", rr
    return reason, rr


def _build_trade_stats(db_path: str) -> dict:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT close_reason, side, entry_price, entry_triggered_price, stop_loss,
                   managed_stop_loss, rr_tp1, rr_tp2, rr_tp3,
                   tp1_hit_at, tp2_hit_at, tp3_hit_at
            FROM signals
            WHERE close_reason IN ('TAKE_PROFIT_1','TAKE_PROFIT_2','TAKE_PROFIT_3','STOP_LOSS')
              AND entry_triggered_at IS NOT NULL
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
        _label, rr = _trade_result(row)
        if rr > 0:
            wins += 1
        else:
            losses += 1
        rr_list.append(rr)
        equity += rr
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

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
        "max_dd": round(max_dd, 2),
    }


def _build_trade_history(db_path: str, limit: int = 200) -> list[dict]:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT symbol, timeframe, side, entry_price, stop_loss, managed_stop_loss,
                   close_reason, entry_triggered_price,
                   tp1_hit_at, tp2_hit_at, tp3_hit_at,
                   tp1_hit_price, tp2_hit_price, tp3_hit_price,
                   rr_tp1, rr_tp2, rr_tp3,
                   closed_at, created_at
            FROM signals
            WHERE close_reason IN ('TAKE_PROFIT_1','TAKE_PROFIT_2','TAKE_PROFIT_3','STOP_LOSS')
              AND entry_triggered_at IS NOT NULL
            ORDER BY closed_at DESC
            LIMIT ?
        """, (limit,))
        rows = cur.fetchall()
        conn.close()
    except Exception:
        return []

    result = []
    for row in rows:
        label, rr = _trade_result(row)
        is_win = rr > 0
        result.append({
            "closed_at": (row["closed_at"] or row["created_at"] or "")[:16].replace("T", " "),
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "side": (row["side"] or "").upper(),
            "entry": row["entry_price"],
            "exit": row["tp3_hit_price"] or row["tp2_hit_price"] or row["tp1_hit_price"] or row["entry_triggered_price"],
            "close_reason": label,
            "rr": round(rr, 2),
            "result": "WIN" if is_win else "LOSS",
        })
    return result


def _build_active_trades(db_path: str) -> list[dict]:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT symbol, timeframe, side, status, entry_price, entry_triggered_price,
                   stop_loss, tp1, tp2, tp3, tp1_hit_at, tp2_hit_at, created_at
            FROM signals
            WHERE status IN ('ACTIVE','PARTIAL_TP1','PARTIAL_TP2')
              AND entry_triggered_at IS NOT NULL
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
        conn.close()
    except Exception:
        return []

    result = []
    for row in rows:
        result.append({
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "side": (row["side"] or "").upper(),
            "status": row["status"],
            "entry": row["entry_triggered_price"] or row["entry_price"],
            "sl": row["stop_loss"],
            "tp1": row["tp1"],
            "tp2": row["tp2"],
            "tp3": row["tp3"],
            "tp1_hit": bool(row["tp1_hit_at"]),
            "tp2_hit": bool(row["tp2_hit_at"]),
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
body.light {
  --bg: #f1f5f9; --surface: #ffffff; --surface-2: #e2e8f0;
  --border: #e2e8f0; --text: #0f172a; --muted: #64748b;
}
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; padding: 16px; transition: background .2s, color .2s; }
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
      <button onclick="toggleTheme()" id="theme-btn" style="padding:8px 14px;border-radius:8px;border:1px solid var(--border);background:var(--surface-2);color:var(--text);font-size:13px;cursor:pointer;">&#x263D; Dark</button>
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
      <h2>&#x1F4CC; Open Trades <span id="active-count" style="color:var(--muted);font-weight:400;">(0)</span></h2>
    </div>
    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Symbol</th><th>TF</th><th>Side</th><th>Entry</th><th>SL</th><th>TP1</th><th>TP2</th><th>TP3</th><th>Status</th></tr></thead>
        <tbody id="active-body"><tr><td colspan="9" class="empty">Loading&hellip;</td></tr></tbody>
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

  // Dark/Light theme toggle
  function applyTheme(mode) {{
    document.body.classList.toggle("light", mode === "light");
    const btn = document.getElementById("theme-btn");
    if (btn) btn.textContent = mode === "light" ? "\u2600\uFE0F Light" : "\u263D Dark";
  }}
  function toggleTheme() {{
    const next = document.body.classList.contains("light") ? "dark" : "light";
    localStorage.setItem("ew_theme", next);
    applyTheme(next);
  }}
  applyTheme(localStorage.getItem("ew_theme") || "dark");

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

    const acts = Array.isArray(d.active_trades) ? d.active_trades : [];
    document.getElementById("active-count").textContent = "(" + acts.length + ")";
    document.getElementById("active-body").innerHTML = acts.length
      ? acts.map(t => {{
          const side = (t.side||"").toUpperCase();
          const sideBadge = side === "LONG"
            ? "<span class='badge badge-long'>LONG</span>"
            : "<span class='badge badge-short'>SHORT</span>";
          const status = (t.status||"").replace("_"," ");
          return "<tr>"
            + "<td><b>" + (t.symbol||"\u2013") + "</b></td>"
            + "<td>" + (t.timeframe||"\u2013") + "</td>"
            + "<td>" + sideBadge + "</td>"
            + "<td>" + fmt(t.entry,4) + "</td>"
            + "<td class='neg'>" + fmt(t.sl,4) + "</td>"
            + "<td class='pos'>" + fmt(t.tp1,4) + "</td>"
            + "<td class='pos'>" + fmt(t.tp2,4) + "</td>"
            + "<td class='pos'>" + fmt(t.tp3,4) + "</td>"
            + "<td><span class='badge'>" + status + "</span></td>"
            + "</tr>";
        }}).join("")
      : "<tr><td colspan='9' class='empty'>No open trades</td></tr>";
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
      <button onclick="toggleTheme()" id="theme-btn" style="padding:8px 14px;border-radius:8px;border:1px solid var(--border);background:var(--surface-2);color:var(--text);font-size:13px;cursor:pointer;">&#x263D; Dark</button>
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

  function applyTheme(mode) {{
    document.body.classList.toggle("light", mode === "light");
    const btn = document.getElementById("theme-btn");
    if (btn) btn.textContent = mode === "light" ? "\u2600\uFE0F Light" : "\u263D Dark";
  }}
  function toggleTheme() {{
    const next = document.body.classList.contains("light") ? "dark" : "light";
    localStorage.setItem("ew_theme", next);
    applyTheme(next);
  }}
  applyTheme(localStorage.getItem("ew_theme") || "dark");

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


_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin1234")


def build_register_html() -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Register — AlphaFutures</title>
<style>{_SHARED_CSS}
.form-card {{ max-width: 480px; margin: 60px auto; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 32px; }}
.form-card h2 {{ font-size: 20px; font-weight: 700; margin-bottom: 8px; }}
.form-card p {{ color: var(--muted); font-size: 13px; margin-bottom: 24px; line-height: 1.5; }}
label {{ display: block; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 6px; }}
input[type=text], input[type=password] {{ width: 100%; background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; color: var(--text); font-size: 14px; margin-bottom: 16px; outline: none; }}
input:focus {{ border-color: var(--primary); }}
.btn {{ width: 100%; padding: 12px; background: var(--primary); color: #fff; border: none; border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer; }}
.btn:disabled {{ opacity: .5; cursor: not-allowed; }}
.msg {{ margin-top: 16px; padding: 12px; border-radius: 8px; font-size: 13px; display: none; }}
.msg-ok {{ background: rgba(16,185,129,.15); color: var(--success); }}
.msg-err {{ background: rgba(239,68,68,.15); color: var(--danger); }}
</style></head><body>
<div class="container">
  <div class="header">
    <h1>&#x26A1; AlphaFutures</h1>
    <nav class="nav"><a href="/">Dashboard</a></nav>
  </div>
  <div class="form-card">
    <h2>Connect your Binance account</h2>
    <p>Enter your Binance Futures API key and secret. Your keys are stored securely and used only to execute trades on your behalf.<br><br>Required permission: <strong>Futures Trading</strong> only. Do NOT enable Withdrawals.</p>
    <label>Your Name / Label</label>
    <input type="text" id="label" placeholder="e.g. John" />
    <label>Binance API Key</label>
    <input type="text" id="apikey" placeholder="Paste your API key" autocomplete="off" />
    <label>Binance API Secret</label>
    <input type="password" id="apisecret" placeholder="Paste your API secret" autocomplete="off" />
    <button class="btn" id="submit-btn" onclick="submit()">Register</button>
    <div class="msg msg-ok" id="msg-ok"></div>
    <div class="msg msg-err" id="msg-err"></div>
  </div>
</div>
<script>
async function submit() {{
  const label = document.getElementById('label').value.trim();
  const apikey = document.getElementById('apikey').value.trim();
  const apisecret = document.getElementById('apisecret').value.trim();
  const btn = document.getElementById('submit-btn');
  const ok = document.getElementById('msg-ok');
  const err = document.getElementById('msg-err');
  ok.style.display = 'none'; err.style.display = 'none';
  if (!label || !apikey || !apisecret) {{ err.textContent = 'Please fill in all fields.'; err.style.display = 'block'; return; }}
  btn.disabled = true; btn.textContent = 'Registering...';
  try {{
    const res = await fetch('/api/register', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{label, api_key: apikey, api_secret: apisecret}})
    }});
    const d = await res.json();
    if (d.ok) {{
      ok.innerHTML = '&#10003; Registered! Your dashboard link:<br><a href="/u/' + d.token + '" style="color:var(--primary)">/u/' + d.token.substring(0,16) + '...</a><br><br>Save this link — it is your personal dashboard.';
      ok.style.display = 'block';
      btn.textContent = 'Registered';
      document.getElementById('label').value = '';
      document.getElementById('apikey').value = '';
      document.getElementById('apisecret').value = '';
    }} else {{
      err.textContent = d.error || 'Registration failed.';
      err.style.display = 'block';
      btn.disabled = false; btn.textContent = 'Register';
    }}
  }} catch(e) {{
    err.textContent = 'Network error: ' + e.message;
    err.style.display = 'block';
    btn.disabled = false; btn.textContent = 'Register';
  }}
}}
</script>
</body></html>
"""


def build_admin_html() -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Admin — AlphaFutures</title>
<style>{_SHARED_CSS}
.login-card {{ max-width: 360px; margin: 100px auto; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 32px; }}
.login-card h2 {{ font-size: 18px; font-weight: 700; margin-bottom: 20px; }}
label {{ display: block; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 6px; }}
input[type=password] {{ width: 100%; background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; color: var(--text); font-size: 14px; margin-bottom: 16px; outline: none; }}
input:focus {{ border-color: var(--primary); }}
.btn {{ padding: 8px 16px; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; }}
.btn-primary {{ background: var(--primary); color: #fff; }}
.btn-success {{ background: var(--success); color: #fff; }}
.btn-danger {{ background: var(--danger); color: #fff; }}
.btn:disabled {{ opacity: .5; cursor: not-allowed; }}
.badge-active {{ background: rgba(16,185,129,.15); color: var(--success); padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
.badge-inactive {{ background: rgba(239,68,68,.15); color: var(--danger); padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
#main {{ display: none; }}
.err {{ color: var(--danger); font-size: 13px; margin-top: 8px; }}
</style></head><body>
<div class="container">
  <div id="login-view">
    <div class="login-card">
      <h2>&#x1F512; Admin Login</h2>
      <label>Password</label>
      <input type="password" id="pw" placeholder="Enter admin password" onkeydown="if(event.key==='Enter')login()" />
      <button class="btn btn-primary" onclick="login()" style="width:100%">Login</button>
      <div class="err" id="login-err"></div>
    </div>
  </div>

  <div id="main">
    <div class="header">
      <h1>&#x26A1; Admin Panel</h1>
      <nav class="nav">
        <a href="/">Dashboard</a>
        <a href="/admin" class="active">Admin</a>
      </nav>
    </div>
    <div class="section">
      <div class="section-head">
        <h2>Members (<span id="total-count">0</span>)</h2>
        <div style="font-size:13px;color:var(--muted)">
          Active: <span id="active-count" style="color:var(--success);font-weight:600">0</span>
        </div>
      </div>
      <table class="table">
        <thead><tr>
          <th>ID</th><th>Label</th><th>API Key</th><th>Status</th>
          <th>Registered</th><th>Activated</th><th>Action</th>
        </tr></thead>
        <tbody id="accounts-tbody"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
let _pw = '';

async function login() {{
  _pw = document.getElementById('pw').value;
  const res = await fetch('/api/admin/accounts', {{
    headers: {{'X-Admin-Password': _pw}}
  }});
  if (res.status === 401) {{
    document.getElementById('login-err').textContent = 'Wrong password';
    return;
  }}
  const d = await res.json();
  if (!d.ok) {{ document.getElementById('login-err').textContent = d.error || 'Error'; return; }}
  document.getElementById('login-view').style.display = 'none';
  document.getElementById('main').style.display = 'block';
  renderAccounts(d.accounts);
}}

function renderAccounts(accounts) {{
  document.getElementById('total-count').textContent = accounts.length;
  document.getElementById('active-count').textContent = accounts.filter(a=>a.active).length;
  const tbody = document.getElementById('accounts-tbody');
  if (!accounts.length) {{
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:32px">No members yet</td></tr>';
    return;
  }}
  tbody.innerHTML = accounts.map(a => `
    <tr>
      <td>#${{a.id}}</td>
      <td style="font-weight:600">${{a.label}}</td>
      <td style="font-family:monospace;font-size:12px">${{a.api_key_masked}}</td>
      <td><span class="${{a.active ? 'badge-active' : 'badge-inactive'}}">${{a.active ? 'ACTIVE' : 'INACTIVE'}}</span></td>
      <td style="color:var(--muted);font-size:12px">${{a.created_at.substring(0,10)}}</td>
      <td style="color:var(--muted);font-size:12px">${{a.activated_at ? a.activated_at.substring(0,10) : '—'}}</td>
      <td>
        ${{a.active
          ? `<button class="btn btn-danger" onclick="toggle(${{a.id}}, false)">Deactivate</button>`
          : `<button class="btn btn-success" onclick="toggle(${{a.id}}, true)">Activate</button>`
        }}
      </td>
    </tr>
  `).join('');
}}

async function toggle(id, activate) {{
  const endpoint = activate ? '/api/admin/activate' : '/api/admin/deactivate';
  const res = await fetch(endpoint, {{
    method: 'POST',
    headers: {{'Content-Type':'application/json','X-Admin-Password':_pw}},
    body: JSON.stringify({{id}})
  }});
  const d = await res.json();
  if (!d.ok) {{ alert(d.error); return; }}
  const res2 = await fetch('/api/admin/accounts', {{headers:{{'X-Admin-Password':_pw}}}});
  const d2 = await res2.json();
  renderAccounts(d2.accounts);
}}
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
    register_html = build_register_html()
    admin_html = build_admin_html()
    db_path = os.getenv("WAVE_DB_PATH", "storage/wave_engine.db")
    account_store = AccountStore(db_path=db_path)

    _cache: dict = {"payload": None, "updated_at": None}
    _cache_lock = threading.Lock()

    def _refresh_cache() -> None:
        while True:
            try:
                snapshot = build_dashboard_snapshot(symbol)
                snapshot["stats"] = _build_trade_stats(db_path)
                snapshot["active_trades"] = _build_active_trades(db_path)
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
            if path == "/register":
                self._send_html(register_html)
                return
            if path == "/admin":
                self._send_html(admin_html)
                return
            if path.startswith("/u/"):
                token = path[3:]
                acc = account_store.get_by_token(token)
                if acc is None:
                    self._send_html("<h2>Account not found</h2>")
                else:
                    from services.web_dashboard_client import build_client_html
                    self._send_html(build_client_html(acc, refresh_seconds))
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
            if path == "/api/admin/accounts":
                if not self._check_admin():
                    return
                accounts = account_store.list_all()
                self._send_json(200, {"ok": True, "accounts": [a.to_dict() for a in accounts]})
                return
            if path.startswith("/api/client/"):
                token = path[len("/api/client/"):]
                self._handle_client_api(token)
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

        def do_POST(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/webhook/line":
                self._handle_line_webhook()
                return
            if path == "/api/register":
                self._handle_register()
                return
            if path == "/api/admin/activate":
                if not self._check_admin():
                    return
                body = self._read_json()
                if body is None:
                    return
                ok = account_store.activate(int(body.get("id", 0)))
                self._send_json(200, {"ok": ok})
                return
            if path == "/api/admin/deactivate":
                if not self._check_admin():
                    return
                body = self._read_json()
                if body is None:
                    return
                ok = account_store.deactivate(int(body.get("id", 0)))
                self._send_json(200, {"ok": ok})
                return
            self._send_json(404, {"ok": False, "error": "not found"})

        def _handle_client_api(self, token: str) -> None:
            acc = account_store.get_by_token(token)
            if acc is None:
                self._send_json(404, {"ok": False, "error": "account not found"})
                return
            if not acc.active:
                self._send_json(200, {"ok": True, "wallet": 0, "available": 0, "upnl": 0,
                                       "positions": [], "history": [], "updated_at": ""})
                return
            try:
                from execution.binance_futures_client import BinanceFuturesClient
                client = BinanceFuturesClient(api_key=acc.api_key, api_secret=acc.api_secret)
                balance_info = client.get_account_balance()
                wallet = next((float(b["balance"]) for b in balance_info if b["asset"] == "USDT"), 0.0)
                available = next((float(b["availableBalance"]) for b in balance_info if b["asset"] == "USDT"), 0.0)
                positions_raw = client.get_position_risk()
                positions = [
                    {
                        "symbol": p["symbol"],
                        "side": "LONG" if float(p["positionAmt"]) > 0 else "SHORT",
                        "size": abs(float(p["positionAmt"])),
                        "entry_price": float(p["entryPrice"]),
                        "mark_price": float(p.get("markPrice", 0)),
                        "upnl": float(p["unRealizedProfit"]),
                        "liq_price": float(p.get("liquidationPrice", 0)),
                    }
                    for p in positions_raw if float(p.get("positionAmt", 0)) != 0
                ]
                upnl = sum(p["upnl"] for p in positions)
                history = _build_trade_history(db_path, limit=50)
                updated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                self._send_json(200, {
                    "ok": True,
                    "wallet": round(wallet, 2),
                    "available": round(available, 2),
                    "upnl": round(upnl, 2),
                    "positions": positions,
                    "history": history,
                    "updated_at": updated_at,
                })
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})

        def _check_admin(self) -> bool:
            pw = self.headers.get("X-Admin-Password", "")
            if pw != _ADMIN_PASSWORD:
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return False
            return True

        def _read_json(self) -> dict | None:
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                return json.loads(body)
            except Exception:
                self._send_json(400, {"ok": False, "error": "invalid JSON"})
                return None

        def _handle_line_webhook(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                signature = self.headers.get("X-Line-Signature", "")
                result = handle_webhook(body, signature, account_store)
                status = result.get("status", 200)
                resp = result.get("body", "OK").encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})

        def _handle_register(self) -> None:
            body = self._read_json()
            if body is None:
                return
            label = (body.get("label") or "").strip()
            api_key = (body.get("api_key") or "").strip()
            api_secret = (body.get("api_secret") or "").strip()
            if not label or not api_key or not api_secret:
                self._send_json(400, {"ok": False, "error": "label, api_key, and api_secret are required"})
                return
            try:
                acc = account_store.create(label, api_key, api_secret)
                try:
                    notify_new_account(acc.id, acc.label, acc.token)
                except Exception:
                    pass
                self._send_json(200, {"ok": True, "token": acc.token, "id": acc.id})
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})

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
