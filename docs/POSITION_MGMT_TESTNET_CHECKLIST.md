# Position management — Binance USDT-M testnet checklist

## Spec API map (100% naming)

| Spec | Implementation |
|------|----------------|
| `positions` / `position_orders` / `position_events` | SQLite **views** over `exchange_*` tables |
| `get_exchange_info_cached(client, symbol)` | `execution.exchange_info.get_exchange_info_cached` |
| `round_qty` | `round_qty` / `round_quantity` |
| `round_quantity_clamped(..., reference_price=)` | After lot step, bump to **minQty** if notional OK |
| `get_account_balance` | `BinanceFuturesClient.get_account_balance` (= `get_balance`) |
| `place_market_entry` | `place_market_entry` (= `place_market_order`) |
| `create_position_from_signal` | `PositionStore.create_position_from_signal` |
| `get_open_position` / `get_position_by_signal` | Aliases on `PositionStore` |
| `update_order_status(order_id, status)` | `PositionStore.update_order_status` |
| `close_position(..., close_price)` | `PositionStore.close_position(..., close_price=)` |
| `open_from_signal(row, account_equity_usdt=)` | `PositionManager.open_from_signal` |
| `close_position_market(symbol, reason)` | `PositionManager.close_position_market` (= full-symbol `close_symbol_cleanup`) |
| Close on signal exit | `PositionManager.close_for_signal(signal_row, reason)` (orchestrator) |
| Portfolio / hedge | See [PORTFOLIO_EXECUTION.md](./PORTFOLIO_EXECUTION.md) |

---

# Position management — Binance USDT-M testnet checklist

Real execution: **MARKET** entry, **STOP_MARKET** SL, **TAKE_PROFIT_MARKET** TP1/2/3 (reduce-only). No strategy filters (no confidence/indicator gating); safety only (exchange rules, kill switch, SL required when opening).

## Before enabling live orders

1. Copy `.env.example` → `.env`; set `BINANCE_USE_TESTNET=true`.
2. `BINANCE_TP1_SIZE_PCT` + `BINANCE_TP2_SIZE_PCT` + `BINANCE_TP3_SIZE_PCT` must sum to a **positive** value (normalized to ~1.0). Sum ≤ 0 → startup error.
3. `KILL_SWITCH=0` when you intend to place orders; `1` blocks all order APIs.
4. `BINANCE_EXECUTION_ENABLED=true`, `BINANCE_LIVE_ORDER_ENABLED=true`, valid testnet API key/secret.

## Dry run on testnet

1. Run orchestrator / pipeline until a signal reaches **`ENTRY_TRIGGERED`** (or inject a test signal row).
2. In Binance Futures **testnet** UI, confirm:
   - Position opened (one-way).
   - **Stop Market** reduce-only order (SL) visible.
   - **Take Profit Market** orders for TP splits.
3. Partial TP: after a TP fills, next reconcile cycle should **resize SL** to remaining quantity (if live orders enabled).
4. Lifecycle exit (`STOP_LOSS_HIT`, `TP3_HIT`, etc.): open orders cancelled, position market-closed, DB row closed.

## Reconcile behaviour

- DB **OPEN** but exchange **flat** → DB closed (`RECONCILE_EXCHANGE_FLAT`).
- Exchange **has position**, DB **no OPEN** → recovered row + optional SL placement.
- Protective orders: status synced via **`query_order`** when possible; missing from open book → **FILLED** / **CANCELED** / **UNKNOWN**.

## Emergency SL

If no stop price in DB/exchange: `RECOVERY_EMERGENCY_SL_PCT` (default 5%) from entry for protective placement.
