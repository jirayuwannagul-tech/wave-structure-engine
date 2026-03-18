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
- **Order queue (optional)** — set `EXECUTION_QUEUE_ENABLED=1`. Orchestrator enqueues tasks and a per-cycle worker processes up to `EXECUTION_QUEUE_MAX_TASKS_PER_CYCLE` with retry/backoff.
- **Circuit breaker (optional)** — `EXECUTION_CIRCUIT_BREAKER_ENABLED=1` (default), opens after `EXECUTION_CIRCUIT_BREAKER_FAILURES` and cools down for `EXECUTION_CIRCUIT_BREAKER_COOLDOWN_SEC` (persisted in `system_events`).
- **Drawdown de-risk (optional)** — `PORTFOLIO_DRAWDOWN_DE_RISK_ENABLED=1`: scales entry size by a risk multiplier based on equity drawdown vs peak.

## Net scale-in (B scope)

Binance futures net positions per leg. With hedge mode + `BINANCE_ALLOW_SCALE_IN_SAME_LEG=1`, a new signal in the **same leg** will:
- add to the net position,
- update DB row quantity + weighted-average entry,
- cancel & re-place protective orders for that `position_id` using stored `tp1_price/tp2_price/tp3_price`.

## Reconcile

With hedge mode and tagged OPEN rows, reconcile runs per-leg (stale close + recovery + SL sync).
