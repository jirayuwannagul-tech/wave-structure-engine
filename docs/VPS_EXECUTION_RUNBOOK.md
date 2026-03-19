# VPS execution runbook (Binance + Sheet entry alignment)

This repo **cannot** SSH into your server for you. Follow the steps below once on the VPS so the bot opens on Binance **from the same signal entry plan**, updates SQLite to the **actual average fill**, pushes **the same numbers to Google Sheets**, and places **SL + TP**.

## 1. One `.env` for orchestrator + scripts

Use the **same** `WorkingDirectory` and `.env` as `elliott-wave-orchestrator.service`.

| Variable | Purpose |
|----------|---------|
| `BINANCE_EXECUTION_ENABLED=1` | Turn on execution |
| `BINANCE_LIVE_ORDER_ENABLED=1` | **Required** to send SL/TP/entry orders (default in code is off) |
| `KILL_SWITCH=0` | Must be off |
| `BINANCE_FUTURES_API_KEY` / `BINANCE_FUTURES_API_SECRET` | Live or testnet keys |
| `BINANCE_USE_TESTNET=false` | Set `true` only for testnet keys |
| `WAVE_DB_PATH` | Same DB path the orchestrator uses (default `storage/wave_engine.db`) |
| `GOOGLE_SHEETS_ENABLED=1` | Optional: sheet sync |
| `GOOGLE_SHEETS_ID` / `GOOGLE_CREDENTIALS_PATH` / `GOOGLE_SHEETS_TAB` | Sheet target |

### Entry alignment (signal vs Binance vs Sheet)

- **`BINANCE_ENTRY_STYLE=market`** — fill price can slip vs planned `entry_price`; after fill the engine **rewrites `signals.entry_price` and `entry_triggered_price` to the Binance average** and **recalculates `rr_tp*`** so the Sheet row matches the exchange.
- **`BINANCE_ENTRY_STYLE=signal_price`** — entry is a **LIMIT or STOP** at the signal entry so fill is usually **much closer** to the planned level (recommended if you want “same number” on chart, DB, and exchange).

## 2. Deploy code

```bash
cd /path/to/repo   # e.g. /root/wave-structure-engine
git fetch origin main && git reset --hard origin/main
.venv/bin/pip install -q -r requirements.txt
sudo systemctl restart elliott-wave-orchestrator
```

## 3. Protections on **already open** positions (no market close)

```bash
set -a && source .env && set +a
.venv/bin/python scripts/ensure_position_protections.py
```

## 3b. See which `signal_id` the DB links to each open position (Sheet has no id column)

```bash
set -a && source .env && set +a
.venv/bin/python scripts/report_execution_state.py
```

Compare `source_signal_id` / `signal_row` to your Sheet row using **symbol + timeframe + side + entry** (the `wave_log` tab does not store SQLite `signals.id`).

## 4. Refresh Sheet from DB (optional)

After a fill or manual DB fix:

```bash
set -a && source .env && set +a
.venv/bin/python scripts/sync_sheet_signals.py
# or one symbol:
.venv/bin/python scripts/sync_sheet_signals.py BTCUSDT
```

## 5. Automated checklist script

```bash
./scripts/vps_bootstrap_execution.sh
```

Prints what is missing from env and whether key files exist.

## What “done” means

- [ ] `BINANCE_EXECUTION_ENABLED` and `BINANCE_LIVE_ORDER_ENABLED` are **1** on VPS `.env`
- [ ] Orchestrator service **active** and using that `.env`
- [ ] New entry: Binance position exists, **open orders include SL + TP1/2/3** (or remaining legs after partials)
- [ ] SQLite `signals.entry_price` matches **avg fill** after open; Sheet **entry** column updated (or run `sync_sheet_signals.py`)

If SL/TP still missing, run `ensure_position_protections.py` and read JSON `diagnostic` + `results`.
