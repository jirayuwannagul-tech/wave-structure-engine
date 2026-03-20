"""Sync local exchange_positions with Binance position state."""

from __future__ import annotations

import os

from execution.binance_futures_client import BinanceFuturesClient
from execution.exchange_info import round_price, round_quantity
from execution.models import ExecutionConfig
from execution.position_manager import (
    PositionManager,
    _is_protective_exit_order,
    _is_stop_order,
    _is_take_profit_order,
    _order_quantity,
    exit_order_side_for_position,
)
from storage.position_store import PositionStore


def _position_amt(row: dict | None) -> float:
    if not row:
        return 0.0
    try:
        return float(row.get("positionAmt") or 0)
    except (TypeError, ValueError):
        return 0.0


def _emergency_sl_price(
    client: BinanceFuturesClient,
    symbol_u: str,
    side: str,
    entry_price: float,
) -> float:
    pct = float(os.getenv("RECOVERY_EMERGENCY_SL_PCT", "5")) / 100.0
    ep = float(entry_price or 0.0)
    if side.upper() == "LONG":
        raw = ep * (1.0 - pct) if ep > 0 else ep
    else:
        raw = ep * (1.0 + pct) if ep > 0 else ep
    return round_price(client, symbol_u, raw)


def _query_sync_protective_orders(
    client: BinanceFuturesClient,
    store: PositionStore,
    position_id: int,
    symbol_u: str,
) -> None:
    """Update DB rows from exchange order status (FILLED / CANCELED / …)."""
    qo = getattr(client, "query_order", None)
    if not callable(qo):
        return
    for r in store.list_open_protective_orders(position_id):
        if str(r["status"] or "") not in ("NEW", "OFF_BOOK", "UNKNOWN"):
            continue
        oid = r["order_id"]
        if oid is None:
            continue
        try:
            info = qo(symbol=symbol_u, order_id=int(oid))
            ex = str(info.get("status") or "").upper()
            if ex and ex != "NEW":
                store.update_position_order_row_status(int(r["id"]), ex)
        except Exception:
            pass


def _sync_off_exchange_book(
    client: BinanceFuturesClient,
    store: PositionStore,
    position_id: int,
    symbol_u: str,
) -> None:
    """Rows still NEW but not in openOrders → query status or UNKNOWN."""
    orders = client.get_open_orders(symbol_u) or []
    open_ids: set[int] = set()
    for o in orders:
        oid = o.get("orderId")
        if oid is not None:
            try:
                open_ids.add(int(oid))
            except (TypeError, ValueError):
                pass
    qo = getattr(client, "query_order", None)
    for r in store.list_open_protective_orders(position_id):
        if str(r["status"] or "") != "NEW":
            continue
        oid = r["order_id"]
        if oid is None:
            continue
        try:
            oid_i = int(oid)
        except (TypeError, ValueError):
            continue
        if oid_i in open_ids:
            continue
        if callable(qo):
            try:
                info = qo(symbol=symbol_u, order_id=oid_i)
                ex = str(info.get("status") or "").upper()
                if ex:
                    store.update_position_order_row_status(int(r["id"]), ex)
                    continue
            except Exception:
                pass
        store.update_position_order_row_status(int(r["id"]), "UNKNOWN")


def _maybe_resize_stop_loss_qty(
    client: BinanceFuturesClient,
    store: PositionStore,
    config: ExecutionConfig | None,
    symbol_u: str,
    row: object,
    amt: float,
) -> None:
    """Keep SL reduce qty aligned with current position (after TP partial or scale-in)."""
    if config is None or not config.live_order_enabled:
        return
    pos_qty = round_quantity(client, symbol_u, abs(amt))
    if pos_qty <= 0:
        return
    orders = client.get_open_orders(symbol_u) or []
    close_side = exit_order_side_for_position(str(row["side"]))
    pst = row["position_side_tag"]
    sls: list[dict] = []
    for o in orders:
        if not isinstance(o, dict):
            continue
        if not _is_stop_order(o):
            continue
        if not _is_protective_exit_order(o):
            continue
        if str(o.get("side") or "").upper() != close_side:
            continue
        if config.hedge_position_mode and pst:
            if str(o.get("positionSide") or "").upper() != str(pst).upper():
                continue
        sls.append(o)
    if not sls:
        return
    if any(str(o.get("closePosition") or "").lower() in ("true", "1") or o.get("closePosition") is True for o in sls):
        return
    mismatch = False
    for o in sls:
        try:
            oq = _order_quantity(o, pos_qty)
        except (TypeError, ValueError):
            oq = 0.0
        oq_r = round_quantity(client, symbol_u, oq)
        # Replace if SL qty differs materially from current position qty
        if abs(oq_r - pos_qty) > 1e-9:
            mismatch = True
            break
    if not mismatch:
        return
    canceled: list[int] = []
    for o in sls:
        try:
            oid = int(o["orderId"])
            client.cancel_order(symbol=symbol_u, order_id=oid)
            canceled.append(oid)
        except Exception:
            pass
    pid = int(row["id"])  # type: ignore[arg-type]
    for r in store.list_open_protective_orders(pid):
        if str(r["order_kind"]) != "SL":
            continue
        oid = r["order_id"]
        if oid is None:
            continue
        try:
            if int(oid) in canceled and str(r["status"]) == "NEW":
                store.update_position_order_row_status(int(r["id"]), "CANCELED")
        except (TypeError, ValueError):
            pass
    store.append_event(pid, "SL_RESIZED_TO_POSITION_QTY", {"position_qty": pos_qty})
    if config is not None:
        PositionManager(client, config, store).ensure_protection(symbol_u)


def _reconcile_symbol_hedge(
    client: BinanceFuturesClient,
    store: PositionStore,
    symbol_u: str,
    config: ExecutionConfig | None,
) -> dict[str, str | int | None]:
    for row in list(store.list_open_positions_for_symbol(symbol_u)):
        pid = int(row["id"])
        pst = row["position_side_tag"]
        if pst:
            amt = client.get_position_leg_amt(symbol_u, str(pst))
        else:
            pos = client.get_position(symbol_u)
            amt = _position_amt(pos)
        if abs(amt) < 1e-12:
            store.close_position(pid, "RECONCILE_EXCHANGE_FLAT")
    for row in store.list_open_positions_for_symbol(symbol_u):
        pid = int(row["id"])
        _query_sync_protective_orders(client, store, pid, symbol_u)
        pst = row["position_side_tag"]
        if pst:
            amt = client.get_position_leg_amt(symbol_u, str(pst))
        else:
            amt = _position_amt(client.get_position(symbol_u))
        _maybe_resize_stop_loss_qty(client, store, config, symbol_u, row, amt)
    if config is not None:
        PositionManager(client, config, store).ensure_protection(symbol_u)
    for row in store.list_open_positions_for_symbol(symbol_u):
        pid = int(row["id"])
        _query_sync_protective_orders(client, store, pid, symbol_u)
        _sync_off_exchange_book(client, store, pid, symbol_u)

    for r in client.get_position_risk() or []:
        if str(r.get("symbol") or "").upper() != symbol_u:
            continue
        try:
            amt = float(r.get("positionAmt") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        if abs(amt) < 1e-12:
            continue
        ps = str(r.get("positionSide") or "BOTH").upper()
        if ps == "BOTH":
            side = "LONG" if amt > 0 else "SHORT"
            if store.has_open_position_for_symbol(symbol_u):
                continue
            qty = abs(amt)
            entry_price = float(r.get("entryPrice") or 0)
            sl_px = _emergency_sl_price(client, symbol_u, side, entry_price)
            pid = store.create_position(
                symbol=symbol_u,
                side=side,
                source_signal_id=None,
                signal_hash=None,
                quantity=qty,
                entry_price=entry_price or None,
                entry_order_id=None,
                stop_loss_price=sl_px,
                recovered=1,
                position_side_tag=None,
            )
            store.append_event(pid, "RECOVERED_FROM_EXCHANGE", {"quantity": qty})
            if config is not None:
                PositionManager(client, config, store).ensure_protection(symbol_u)
            return {"action": "recovered", "position_id": pid}
        if store.has_open_leg_for_symbol(symbol_u, ps):
            continue
        qty = abs(amt)
        try:
            entry_price = float(r.get("entryPrice") or 0)
        except (TypeError, ValueError):
            entry_price = 0.0
        sl_px = _emergency_sl_price(client, symbol_u, ps, entry_price)
        pid = store.create_position(
            symbol=symbol_u,
            side=ps,
            source_signal_id=None,
            signal_hash=None,
            quantity=qty,
            entry_price=entry_price or None,
            entry_order_id=None,
            stop_loss_price=sl_px,
            recovered=1,
            position_side_tag=ps,
        )
        store.append_event(pid, "RECOVERED_FROM_EXCHANGE_HEDGE", {"leg": ps, "quantity": qty})
        if config is not None:
            PositionManager(client, config, store).ensure_protection(symbol_u)
        return {"action": "recovered_hedge", "position_id": pid}

    if store.list_open_positions_for_symbol(symbol_u):
        return {"action": "still_open_hedge"}
    return {"action": "none"}


def reconcile_symbol(
    client: BinanceFuturesClient,
    store: PositionStore,
    symbol: str,
    config: ExecutionConfig | None = None,
) -> dict[str, str | int | None]:
    """Close stale DB rows; recover DB from exchange position; ensure SL on book."""
    symbol_u = symbol.upper()
    rows_open = store.list_open_positions_for_symbol(symbol_u)
    if config and config.hedge_position_mode and (
        len(rows_open) > 1 or bool(rows_open and rows_open[0]["position_side_tag"])
    ):
        return _reconcile_symbol_hedge(client, store, symbol_u, config)

    row = store.get_open_position_by_symbol(symbol_u)
    pos = client.get_position(symbol_u)
    amt = _position_amt(pos)

    if row is not None and abs(amt) < 1e-12:
        store.close_position(int(row["id"]), "RECONCILE_EXCHANGE_FLAT")
        return {"action": "closed_stale", "position_id": int(row["id"])}

    if row is None and abs(amt) > 1e-12:
        side = "LONG" if amt > 0 else "SHORT"
        qty = abs(amt)
        try:
            entry_price = float(pos.get("entryPrice") or 0)
        except (TypeError, ValueError):
            entry_price = 0.0
        orders = client.get_open_orders(symbol_u) or []
        close_side = exit_order_side_for_position(side)
        sl_px: float | None = None
        tp1_px: float | None = None
        tp2_px: float | None = None
        tp3_px: float | None = None
        for o in orders:
            oside = str(o.get("side") or "").upper()
            if oside != close_side:
                continue
            if not _is_protective_exit_order(o):
                continue
            try:
                sp = float(o.get("stopPrice") or 0)
            except (TypeError, ValueError):
                sp = 0.0
            if _is_stop_order(o) and sp > 0 and sl_px is None:
                sl_px = sp
            elif _is_take_profit_order(o) and sp > 0:
                cid = str(o.get("clientOrderId") or "")
                if "TP2" in cid:
                    tp2_px = tp2_px or sp
                elif "TP3" in cid:
                    tp3_px = tp3_px or sp
                else:
                    tp1_px = tp1_px or sp
        if sl_px is None:
            sl_px = _emergency_sl_price(client, symbol_u, side, entry_price)
        pid = store.create_position(
            symbol=symbol_u,
            side=side,
            source_signal_id=None,
            signal_hash=None,
            quantity=qty,
            entry_price=entry_price or None,
            entry_order_id=None,
            stop_loss_price=sl_px,
            recovered=1,
            tp1_price=tp1_px,
            tp2_price=tp2_px,
            tp3_price=tp3_px,
        )
        store.append_event(pid, "RECOVERED_FROM_EXCHANGE", {"quantity": qty, "entry_price": entry_price})
        for o in orders:
            oside = str(o.get("side") or "").upper()
            if oside != close_side:
                continue
            if not _is_protective_exit_order(o):
                continue
            if _is_stop_order(o):
                try:
                    oid = int(o["orderId"]) if o.get("orderId") is not None else None
                except (TypeError, ValueError):
                    oid = None
                try:
                    sp = float(o.get("stopPrice") or 0)
                except (TypeError, ValueError):
                    sp = 0.0
                try:
                    q = _order_quantity(o, qty)
                except (TypeError, ValueError):
                    q = qty
                store.record_order(
                    pid,
                    order_kind="SL",
                    order_id=oid,
                    client_order_id=o.get("clientOrderId"),
                    side=close_side,
                    order_type="STOP_MARKET",
                    quantity=q,
                    stop_price=sp or sl_px,
                    status="NEW",
                    reduce_only=_is_protective_exit_order(o),
                )
            elif _is_take_profit_order(o):
                try:
                    oid = int(o["orderId"]) if o.get("orderId") is not None else None
                except (TypeError, ValueError):
                    oid = None
                cid = str(o.get("clientOrderId") or "")
                kind = "TP1"
                if "TP2" in cid:
                    kind = "TP2"
                elif "TP3" in cid:
                    kind = "TP3"
                try:
                    sp = float(o.get("stopPrice") or 0)
                except (TypeError, ValueError):
                    sp = 0.0
                try:
                    q = _order_quantity(o, qty)
                except (TypeError, ValueError):
                    q = 0.0
                store.record_order(
                    pid,
                    order_kind=kind,
                    order_id=oid,
                    client_order_id=o.get("clientOrderId"),
                    side=close_side,
                    order_type="TAKE_PROFIT_MARKET",
                    quantity=q,
                    stop_price=sp,
                    status="NEW",
                    reduce_only=_is_protective_exit_order(o),
                )
        if config is not None:
            PositionManager(client, config, store).ensure_protection(symbol_u)
        return {"action": "recovered", "position_id": pid}

    if row is not None and abs(amt) > 1e-12:
        pid = int(row["id"])
        _query_sync_protective_orders(client, store, pid, symbol_u)
        _maybe_resize_stop_loss_qty(client, store, config, symbol_u, row, amt)
        if config is not None:
            PositionManager(client, config, store).ensure_protection(symbol_u)
        _query_sync_protective_orders(client, store, pid, symbol_u)
        _sync_off_exchange_book(client, store, pid, symbol_u)
        return {"action": "still_open", "position_id": pid}

    return {"action": "none"}
