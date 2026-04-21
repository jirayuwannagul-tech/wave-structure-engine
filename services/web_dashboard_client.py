"""Client-facing dashboard page for a single managed account."""

from __future__ import annotations

from storage.account_store import Account


def build_client_html(account: Account, refresh_seconds: float = 5.0) -> str:
    refresh_ms = max(int(refresh_seconds * 1000), 1000)
    token = account.token
    label = account.label
    status_badge = (
        '<span style="background:rgba(16,185,129,.15);color:#10b981;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:700">&#9679; ACTIVE</span>'
        if account.active else
        '<span style="background:rgba(239,68,68,.15);color:#ef4444;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:700">&#9679; INACTIVE</span>'
    )

    from services.web_dashboard import _SHARED_CSS
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{label} — AlphaFutures</title>
<style>{_SHARED_CSS}
.account-hero {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px 24px; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
.account-name {{ font-size: 20px; font-weight: 700; }}
.account-meta {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
</style></head><body>
<div class="container">

  <div class="header">
    <h1>&#x26A1; AlphaFutures</h1>
  </div>

  <div class="account-hero">
    <div>
      <div class="account-name">{label}</div>
      <div class="account-meta" id="last-updated">Loading...</div>
    </div>
    <div style="display:flex;align-items:center;gap:12px">
      {status_badge}
    </div>
  </div>

  {"" if account.active else '<div class="section" style="text-align:center;padding:40px;color:var(--muted)"><p style=\'font-size:16px\'>&#x23F3; Your account is pending activation.</p><p style=\'font-size:13px;margin-top:8px\'>Please complete your payment. Your account will be activated within 24 hours.</p></div>'}

  <div id="active-content" style="display:{'block' if account.active else 'none'}">
    <div class="stats-grid">
      <div class="stat"><div class="stat-label">Wallet Balance</div><div class="stat-value" id="c-wallet">&ndash;</div><div class="stat-sub">USDT</div></div>
      <div class="stat"><div class="stat-label">Available</div><div class="stat-value" id="c-avail">&ndash;</div><div class="stat-sub">USDT</div></div>
      <div class="stat"><div class="stat-label">Unrealized PnL</div><div class="stat-value" id="c-upnl">&ndash;</div><div class="stat-sub">USDT</div></div>
      <div class="stat"><div class="stat-label">Open Positions</div><div class="stat-value" id="c-pos-count">&ndash;</div><div class="stat-sub">active</div></div>
    </div>

    <div class="section">
      <div class="section-head"><h2>Open Positions</h2></div>
      <div id="positions-wrap">
        <p style="color:var(--muted);font-size:13px">Loading...</p>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h2>Recent Trades</h2></div>
      <div id="history-wrap">
        <p style="color:var(--muted);font-size:13px">Loading...</p>
      </div>
    </div>
  </div>

  <div id="error-slot"></div>
</div>

<script>
const TOKEN = "{token}";
const REFRESH_MS = {refresh_ms};

function fmt(v, d=2) {{
  const n = parseFloat(v);
  return isNaN(n) ? (v || "–") : n.toFixed(d);
}}

function fmtPnl(v) {{
  const n = parseFloat(v);
  if (isNaN(n)) return "–";
  const cls = n >= 0 ? "text-success" : "text-danger";
  const sign = n >= 0 ? "+" : "";
  return `<span class="${{cls}}">${{sign}}${{n.toFixed(2)}}</span>`;
}}

async function tick() {{
  try {{
    const res = await fetch("/api/client/" + TOKEN);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const d = await res.json();
    if (!d.ok) throw new Error(d.error);

    document.getElementById("c-wallet").textContent = fmt(d.wallet);
    document.getElementById("c-avail").textContent = fmt(d.available);
    document.getElementById("c-upnl").innerHTML = fmtPnl(d.upnl);
    document.getElementById("c-pos-count").textContent = (d.positions || []).length;
    document.getElementById("last-updated").textContent = "Updated " + (d.updated_at || "");

    // Positions table
    const posWrap = document.getElementById("positions-wrap");
    if (!d.positions || !d.positions.length) {{
      posWrap.innerHTML = '<p style="color:var(--muted);font-size:13px">No open positions</p>';
    }} else {{
      posWrap.innerHTML = `<table class="table">
        <thead><tr><th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th><th>Mark</th><th>uPnL</th><th>Liq</th></tr></thead>
        <tbody>${{d.positions.map(p => `
          <tr>
            <td style="font-weight:600">${{p.symbol}}</td>
            <td><span class="badge badge-${{p.side.toLowerCase()}}">${{p.side}}</span></td>
            <td>${{fmt(p.size, 4)}}</td>
            <td>${{fmt(p.entry_price)}}</td>
            <td>${{fmt(p.mark_price)}}</td>
            <td>${{fmtPnl(p.upnl)}}</td>
            <td style="color:var(--danger)">${{fmt(p.liq_price)}}</td>
          </tr>`).join("")}}</tbody>
      </table>`;
    }}

    // History table
    const histWrap = document.getElementById("history-wrap");
    if (!d.history || !d.history.length) {{
      histWrap.innerHTML = '<p style="color:var(--muted);font-size:13px">No closed trades yet</p>';
    }} else {{
      histWrap.innerHTML = `<table class="table">
        <thead><tr><th>Date</th><th>Symbol</th><th>TF</th><th>Side</th><th>Result</th><th>RR</th></tr></thead>
        <tbody>${{d.history.map(t => `
          <tr>
            <td style="color:var(--muted);font-size:12px">${{t.closed_at}}</td>
            <td style="font-weight:600">${{t.symbol}}</td>
            <td style="color:var(--muted)">${{t.timeframe}}</td>
            <td><span class="badge badge-${{t.side.toLowerCase()}}">${{t.side}}</span></td>
            <td><span class="badge badge-${{t.result.toLowerCase()}}">${{t.close_reason}}</span></td>
            <td class="${{t.rr >= 0 ? 'text-success' : 'text-danger'}}">${{t.rr >= 0 ? '+' : ''}}${{t.rr}}R</td>
          </tr>`).join("")}}</tbody>
      </table>`;
    }}

    document.getElementById("error-slot").innerHTML = "";
  }} catch(e) {{
    document.getElementById("error-slot").innerHTML =
      '<div style="background:rgba(239,68,68,.1);color:#ef4444;padding:12px;border-radius:8px;margin-top:8px;font-size:13px">Error: ' + (e.message||e) + '</div>';
  }}
}}

{"tick(); setInterval(tick, REFRESH_MS);" if account.active else ""}
</script>
</body></html>
"""
