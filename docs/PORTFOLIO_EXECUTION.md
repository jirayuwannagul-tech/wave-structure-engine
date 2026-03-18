# Portfolio execution (manager + multi-position + production)

No extra **signal filters** and no change to wave/signal **logic** — only execution layer.

## Portfolio caps (env)

| Variable | Default | Meaning |
|----------|---------|---------|
| `PORTFOLIO_MAX_OPEN_POSITIONS` | `100` | Max concurrent OPEN rows in `exchange_positions`. `≤0` treated as no limit. |
| `PORTFOLIO_MAX_RISK_FRACTION` | `1.0` | If `≤ 0.999`, sum of *(estimated risk of all OPEN rows + new trade)* must be ≤ `equity × fraction`. Risk per row ≈ `qty × \|entry − stop\|`. Set e.g. `0.35` for ~35% equity cap. |
| `PORTFOLIO_PAUSE_NEW_ENTRIES` | `0` | If `1` / `true`, all new opens return `skipped` (soft). |

## Multi-position

- **One-way (default)** — At most one OPEN position per symbol (unchanged behaviour).
- **Hedge** — Set `BINANCE_HEDGE_POSITION_MODE=1`. Account must be in **dual-side / hedge** on Binance. Then you can hold **LONG and SHORT** on the same symbol as separate legs (one DB row per leg). Second LONG on the same leg is still blocked (exchange merges adds).

Orders send `positionSide` when hedge mode is on.

## Close by signal

Lifecycle exits (`STOP_LOSS_HIT`, `TP3_HIT`, etc.) call **`close_for_signal(signal_row, …)`**: cancels that signal’s orders and reduces only that leg. Falls back to full symbol cleanup if no DB row for that signal (e.g. recovered-only rows).

## Production-hardening

- **HTTP retries** on timeout / 429 / 5xx — `BINANCE_HTTP_MAX_RETRIES` (default `3`), `BINANCE_HTTP_RETRY_BACKOFF_SEC` (default `0.6`).
- **Health markers** in `system_events` (same DB as `WAVE_DB_PATH`): `execution:last_open_ok`, `execution:last_portfolio_skip`, `execution:last_close_ok`.

## Reconcile

With hedge mode and tagged OPEN rows, reconcile runs per-leg (stale close + recovery + SL sync).
