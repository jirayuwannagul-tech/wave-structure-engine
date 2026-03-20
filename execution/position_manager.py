"""Open and protect futures positions from signal rows (market entry + SL/TP reduce-only)."""

from __future__ import annotations

import os
import traceback
from typing import Any

import requests

from analysis.trade_management import evaluate_live_entry_actionability
from execution.binance_futures_client import BinanceFuturesClient
from execution.exchange_info import (
    round_price,
    round_quantity,
    round_quantity_clamped,
    validate_order,
)
from execution.execution_health import (
    clear_execution_health,
    read_execution_health,
    record_execution_health,
)
from execution.models import ExecutionConfig
from execution.portfolio_manager import evaluate_new_position
from execution.signal_mapper import build_order_intent_from_signal
from storage.position_store import PositionStore


def _usdt_equity(client: BinanceFuturesClient) -> float:
    bal = client.get_account_balance()
    if not isinstance(bal, list):
        return 0.0
    for row in bal:
        if str(row.get("asset") or "").upper() == "USDT":
            for key in ("availableBalance", "walletBalance", "balance"):
                v = row.get(key)
                if v is not None:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        pass
    return 0.0


def _order_id(resp: Any) -> int | None:
    if not isinstance(resp, dict):
        return None
    oid = resp.get("orderId")
    if oid is None:
        oid = resp.get("algoId")
    try:
        return int(oid) if oid is not None else None
    except (TypeError, ValueError):
        return None


def _executed_qty_price(resp: Any, fallback_qty: float, fallback_price: float) -> tuple[float, float]:
    if not isinstance(resp, dict):
        return float(fallback_qty), float(fallback_price)
    try:
        q = float(resp.get("executedQty") or fallback_qty)
    except (TypeError, ValueError):
        q = float(fallback_qty)
    ap = resp.get("avgPrice") or resp.get("price")
    try:
        p = float(ap) if ap not in (None, "", "0") else float(fallback_price)
    except (TypeError, ValueError):
        p = float(fallback_price)
    return q, p


def _position_amt_local(pos: dict | None) -> float:
    if not pos:
        return 0.0
    try:
        return float(pos.get("positionAmt") or 0)
    except (TypeError, ValueError):
        return 0.0


def _position_side_param(config: ExecutionConfig, side_long_short: str) -> str | None:
    return str(side_long_short).upper() if config.hedge_position_mode else None


def _pid_cid(position_id: int, suffix: str) -> str:
    return f"P{int(position_id)}{suffix}"[:36]


def exit_order_side_for_position(position_side_long_short: str) -> str:
    """Binance order *side* that closes a LONG/SHORT futures position (reduce-only exit)."""
    return "SELL" if str(position_side_long_short).upper() == "LONG" else "BUY"


def _open_order_client_ids_from_orders(orders: list[Any]) -> set[str]:
    out: set[str] = set()
    for o in orders:
        cid = o.get("clientOrderId")
        if cid:
            out.add(str(cid))
    return out


def _order_type(order: dict[str, Any]) -> str:
    return str(order.get("type") or order.get("orderType") or "").upper()


def _order_flag(order: dict[str, Any], key: str) -> bool:
    value = order.get(key)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "on"}


def _is_protective_exit_order(order: dict[str, Any]) -> bool:
    return _order_flag(order, "reduceOnly") or _order_flag(order, "closePosition")


def _is_stop_order(order: dict[str, Any]) -> bool:
    return _order_type(order) in {"STOP", "STOP_MARKET"}


def _is_take_profit_order(order: dict[str, Any]) -> bool:
    return _order_type(order) in {"TAKE_PROFIT", "TAKE_PROFIT_MARKET"}


def _order_quantity(order: dict[str, Any], fallback: float = 0.0) -> float:
    raw = order.get("origQty")
    if raw in (None, "", "0", "0.0"):
        raw = order.get("quantity")
    if raw in (None, "", "0", "0.0") and _order_flag(order, "closePosition"):
        raw = fallback
    try:
        return float(raw) if raw is not None else float(fallback)
    except (TypeError, ValueError):
        return float(fallback)


def _hedge_order_matches_leg(
    config: ExecutionConfig,
    position_side_tag: str | None,
    order: dict[str, Any],
) -> bool:
    if not (config.hedge_position_mode and position_side_tag):
        return True
    pst = str(position_side_tag).upper()
    ops = str(order.get("positionSide") or "").upper()
    return ops == pst


def stop_loss_reduce_on_book_from_orders(
    orders: list[Any],
    config: ExecutionConfig,
    *,
    position_side: str,
    position_side_tag: str | None,
) -> bool:
    """True if a protective stop exists that would close *this* leg."""
    exit_side = exit_order_side_for_position(position_side)
    for o in orders:
        if not isinstance(o, dict):
            continue
        if not _is_stop_order(o):
            continue
        if not _is_protective_exit_order(o):
            continue
        if str(o.get("side") or "").upper() != exit_side:
            continue
        if not _hedge_order_matches_leg(config, position_side_tag, o):
            continue
        return True
    return False


def stop_loss_reduce_on_book_for_position(
    client: BinanceFuturesClient,
    symbol: str,
    config: ExecutionConfig,
    *,
    position_side: str,
    position_side_tag: str | None,
) -> bool:
    raw = client.get_open_orders(symbol) or []
    if not isinstance(raw, list):
        return False
    return stop_loss_reduce_on_book_from_orders(
        raw,
        config,
        position_side=position_side,
        position_side_tag=position_side_tag,
    )


def take_profit_reduce_on_book_from_orders(
    client: BinanceFuturesClient,
    symbol: str,
    config: ExecutionConfig,
    orders: list[Any],
    *,
    position_side: str,
    position_side_tag: str | None,
    stop_price: float,
) -> bool:
    exit_side = exit_order_side_for_position(position_side)
    want_px = round_price(client, symbol, float(stop_price))
    for o in orders:
        if not isinstance(o, dict):
            continue
        if not _is_take_profit_order(o):
            continue
        if not _is_protective_exit_order(o):
            continue
        if str(o.get("side") or "").upper() != exit_side:
            continue
        if not _hedge_order_matches_leg(config, position_side_tag, o):
            continue
        try:
            sp = float(o.get("stopPrice") or 0)
        except (TypeError, ValueError):
            continue
        sp_r = round_price(client, symbol, sp)
        if sp_r == want_px:
            return True
    return False


def _entry_duplicate_response(
    exc: BaseException,
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    fallback_qty: float,
    fallback_price: float,
    *,
    hedge: bool = False,
) -> dict | None:
    dup = False
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        try:
            body = exc.response.json()
        except Exception:
            body = {}
        msg = str(body.get("msg") or "").lower()
        code = body.get("code")
        dup = code in (-2011, -4116) or "duplicate" in msg
    else:
        t = str(exc).lower()
        dup = "duplicate" in t or "-4116" in str(exc)
    if not dup:
        return None
    if hedge:
        amt = client.get_position_leg_amt(symbol, side)
        if amt < 1e-12:
            return None
        want_long = side.upper() == "LONG"
        if not want_long and side.upper() != "SHORT":
            return None
        ep = float(fallback_price)
        pos = client.get_position(symbol)
        if pos:
            try:
                ep = float(pos.get("entryPrice") or ep)
            except (TypeError, ValueError):
                pass
        return {
            "orderId": None,
            "executedQty": str(amt),
            "avgPrice": str(ep) if ep else str(fallback_price),
        }
    pos = client.get_position(symbol)
    amt = _position_amt_local(pos)
    if abs(amt) < 1e-12:
        return None
    want_long = side.upper() == "LONG"
    if (amt > 0) != want_long:
        return None
    try:
        ep = float(pos.get("entryPrice") or fallback_price)
    except (TypeError, ValueError):
        ep = float(fallback_price)
    return {
        "orderId": None,
        "executedQty": str(abs(amt)),
        "avgPrice": str(ep) if ep else str(fallback_price),
    }


def _pending_entry_health_key(signal_id: int) -> str:
    return f"execution:pending_entry:{int(signal_id)}"


def _entry_response_status(resp: Any) -> str:
    if not isinstance(resp, dict):
        return ""
    return str(resp.get("status") or resp.get("algoStatus") or "").upper()


def _normalize_filled_entry_from_query(q: dict[str, Any]) -> dict[str, Any]:
    eq = q.get("executedQty")
    if eq in (None, "", "0"):
        eq = q.get("cumQty")
    ap = q.get("avgPrice") or q.get("price")
    return {
        "orderId": q.get("orderId"),
        "executedQty": str(eq or 0),
        "avgPrice": ap,
        "status": "FILLED",
    }


def _signal_price_entry_kind(side: str, mark: float, entry: float) -> tuple[str, float]:
    """Pick LIMIT vs STOP_MARKET so the order rests until price reaches *entry* (rounded)."""
    ep = float(entry)
    m = float(mark)
    rel = max(1e-12, abs(ep) * 1e-9)
    if side.upper() == "LONG":
        if m > ep + rel:
            return "LIMIT", ep
        return "STOP_MARKET", ep
    if m < ep - rel:
        return "LIMIT", ep
    return "STOP_MARKET", ep


def _exchange_open_without_matching_db(
    client: BinanceFuturesClient,
    store: PositionStore,
    symbol: str,
    side: str,
    config: ExecutionConfig,
) -> bool:
    if config.hedge_position_mode:
        amt = client.get_position_leg_amt(symbol, side)
        if amt <= 1e-12:
            return False
        return not store.has_open_leg_for_symbol(symbol, side)
    pos = client.get_position(symbol)
    if abs(_position_amt_local(pos)) <= 1e-12:
        return False
    return store.get_open_position_by_symbol(symbol) is None


class PositionManager:
    def __init__(
        self,
        client: BinanceFuturesClient,
        config: ExecutionConfig,
        store: PositionStore | None = None,
    ):
        self.client = client
        self.config = config
        self.store = store or PositionStore()

    def _backfill_open_targets_from_active_signals(self, symbol_u: str) -> None:
        """Fill missing TP/SL/signal link on OPEN rows from matching ACTIVE-family signals."""
        try:
            from storage.wave_repository import WaveRepository
        except Exception:
            return
        try:
            active = WaveRepository(db_path=self.store.db_path).fetch_active_signals(symbol_u)
        except Exception:
            return
        if not active:
            return
        for row in self.store.list_open_positions_for_symbol(symbol_u):
            side = str(row["side"]).upper()
            sym_r = str(row["symbol"]).upper()
            candidates = [
                s
                for s in active
                if str(s["symbol"] or "").upper() == sym_r and str(s["side"] or "").upper() == side
            ]
            if not candidates:
                continue
            # Multiple ACTIVE rows for same symbol+side (e.g. LINK): picking max(id) surprises
            # operators ("why did it jump to signal 27?"). Default: oldest active = min(id).
            pick = str(os.getenv("POSITION_BACKFILL_SIGNAL_PICK") or "oldest").strip().lower()
            if pick in {"newest", "max", "latest"}:
                sig = max(candidates, key=lambda s: int(s["id"]))
            else:
                sig = min(candidates, key=lambda s: int(s["id"]))
            pid = int(row["id"])
            updates: dict[str, Any] = {}
            if row["tp1_price"] is None and sig["tp1"] is not None:
                try:
                    updates["tp1_price"] = float(sig["tp1"])
                except (TypeError, ValueError):
                    pass
            if row["tp2_price"] is None and sig["tp2"] is not None:
                try:
                    updates["tp2_price"] = float(sig["tp2"])
                except (TypeError, ValueError):
                    pass
            if row["tp3_price"] is None and sig["tp3"] is not None:
                try:
                    updates["tp3_price"] = float(sig["tp3"])
                except (TypeError, ValueError):
                    pass
            if row["stop_loss_price"] is None and sig["stop_loss"] is not None:
                try:
                    updates["stop_loss_price"] = float(sig["stop_loss"])
                except (TypeError, ValueError):
                    pass
            if row["source_signal_id"] is None:
                updates["source_signal_id"] = int(sig["id"])
            if updates:
                self.store.update_protection_prices(pid, **updates)
                self.store.append_event(
                    pid,
                    "TARGETS_BACKFILLED_FROM_SIGNAL",
                    {"signal_id": int(sig["id"])},
                )

    def _find_matching_order_row(
        self,
        symbol_u: str,
        existing_rows: list[Any],
        *,
        order_id: int | None,
        client_order_id: str | None,
        order_kind: str,
        stop_price: float | None,
    ) -> Any | None:
        for existing in existing_rows:
            try:
                existing_oid = existing["order_id"]
            except (KeyError, TypeError):
                existing_oid = None
            if order_id is not None and existing_oid is not None:
                try:
                    if int(existing_oid) == int(order_id):
                        return existing
                except (TypeError, ValueError):
                    pass
            try:
                existing_cid = str(existing["client_order_id"] or "")
            except (KeyError, TypeError):
                existing_cid = ""
            if client_order_id and existing_cid == client_order_id:
                return existing
            try:
                existing_kind = str(existing["order_kind"] or "")
            except (KeyError, TypeError):
                existing_kind = ""
            if existing_kind != order_kind:
                continue
            try:
                existing_status = str(existing["status"] or "").upper()
            except (KeyError, TypeError):
                existing_status = ""
            if existing_status not in {"NEW", "OFF_BOOK", "UNKNOWN"}:
                continue
            try:
                existing_stop = existing["stop_price"]
            except (KeyError, TypeError):
                existing_stop = None
            if stop_price is None or existing_stop is None:
                continue
            try:
                want = round_price(self.client, symbol_u, float(stop_price))
                have = round_price(self.client, symbol_u, float(existing_stop))
            except (TypeError, ValueError):
                continue
            if want == have:
                return existing
        return None

    def _infer_take_profit_kind(self, symbol_u: str, row: Any, order: dict[str, Any]) -> str | None:
        cid = str(order.get("clientOrderId") or "").upper()
        if "TP1" in cid:
            return "TP1"
        if "TP2" in cid:
            return "TP2"
        if "TP3" in cid:
            return "TP3"
        try:
            stop_price = float(order.get("stopPrice") or 0)
        except (TypeError, ValueError):
            stop_price = 0.0
        if stop_price <= 0:
            return None
        want = round_price(self.client, symbol_u, stop_price)
        for label, field in (("TP1", "tp1_price"), ("TP2", "tp2_price"), ("TP3", "tp3_price")):
            level = row[field]
            if level is None:
                continue
            try:
                level_r = round_price(self.client, symbol_u, float(level))
            except (TypeError, ValueError):
                continue
            if level_r == want:
                return label
        return None

    def _record_or_refresh_protective_order_row(
        self,
        symbol_u: str,
        row: Any,
        existing_rows: list[Any],
        *,
        order_kind: str,
        order: dict[str, Any],
        fallback_qty: float,
    ) -> str | None:
        pid = int(row["id"])
        order_id = _order_id(order)
        client_order_id = str(order.get("clientOrderId") or "").strip() or None
        try:
            stop_price = float(order.get("stopPrice") or 0)
        except (TypeError, ValueError):
            stop_price = 0.0
        stop_price = stop_price if stop_price > 0 else None
        match = self._find_matching_order_row(
            symbol_u,
            existing_rows,
            order_id=order_id,
            client_order_id=client_order_id,
            order_kind=order_kind,
            stop_price=stop_price,
        )
        if match is not None:
            if order_id is not None and match["order_id"] is None:
                self.store.update_order_exchange_id(int(match["id"]), order_id)
            if str(match["status"] or "").upper() != "NEW":
                self.store.update_position_order_row_status(int(match["id"]), "NEW")
            return "refreshed"

        quantity = _order_quantity(order, fallback_qty)
        try:
            quantity = round_quantity(self.client, symbol_u, quantity)
        except ValueError:
            quantity = float(quantity)

        row_id = self.store.record_order(
            pid,
            order_kind=order_kind,
            order_id=order_id,
            client_order_id=client_order_id,
            side=str(order.get("side") or "").upper() or None,
            order_type=_order_type(order) or order_kind,
            quantity=quantity if quantity > 0 else None,
            stop_price=stop_price,
            status="NEW",
            reduce_only=_is_protective_exit_order(order),
        )
        if order_id is not None:
            self.store.update_order_exchange_id(row_id, order_id)
        existing_rows.append(
            {
                "id": row_id,
                "order_id": order_id,
                "client_order_id": client_order_id,
                "order_kind": order_kind,
                "status": "NEW",
                "stop_price": stop_price,
            }
        )
        self.store.append_event(
            pid,
            "PROTECTIVE_ORDER_IMPORTED_FROM_BOOK",
            {"order_kind": order_kind, "order_id": order_id, "client_order_id": client_order_id},
        )
        return "imported"

    def _sync_protective_rows_from_book(
        self,
        symbol_u: str,
        row: Any,
        amt: float,
        open_orders: list[Any],
    ) -> dict[str, int]:
        if not isinstance(open_orders, list):
            return {"imported": 0, "refreshed": 0}
        side = str(row["side"]).upper()
        pst = row["position_side_tag"]
        exit_side = exit_order_side_for_position(side)
        fallback_qty = abs(float(amt or 0))
        existing_rows = list(self.store.list_orders_for_position(int(row["id"])))
        imported = 0
        refreshed = 0
        for order in open_orders:
            if not isinstance(order, dict):
                continue
            if not _is_protective_exit_order(order):
                continue
            if str(order.get("side") or "").upper() != exit_side:
                continue
            if not _hedge_order_matches_leg(self.config, pst, order):
                continue
            order_kind: str | None = None
            if _is_stop_order(order):
                order_kind = "SL"
            elif _is_take_profit_order(order):
                order_kind = self._infer_take_profit_kind(symbol_u, row, order)
            if not order_kind:
                continue
            action = self._record_or_refresh_protective_order_row(
                symbol_u,
                row,
                existing_rows,
                order_kind=order_kind,
                order=order,
                fallback_qty=fallback_qty,
            )
            if action == "imported":
                imported += 1
            elif action == "refreshed":
                refreshed += 1
        return {"imported": imported, "refreshed": refreshed}

    def _ensure_take_profits_for_row(
        self,
        symbol_u: str,
        row: Any,
        amt: float,
        open_orders: list[Any],
    ) -> dict[str, Any]:
        """Place missing TAKE_PROFIT_MARKET reduce-only orders from DB TP levels vs exchange size."""
        pid = int(row["id"])
        side = str(row["side"]).upper()
        pst = row["position_side_tag"]
        ps = _position_side_param(self.config, side)
        if not isinstance(open_orders, list):
            open_orders = []
        open_ids: set[int] = set()
        cids = _open_order_client_ids_from_orders(open_orders)
        for o in open_orders:
            oid = o.get("orderId")
            if oid is not None:
                try:
                    open_ids.add(int(oid))
                except (TypeError, ValueError):
                    pass
        try:
            sid = row["source_signal_id"]
            signal_id = int(sid) if sid is not None else 0
        except (TypeError, ValueError):
            signal_id = 0
        exec_qty = round_quantity(self.client, symbol_u, abs(amt))
        if exec_qty <= 0:
            return {"position_id": pid, "skipped": "qty_zero"}
        tp_levels = [
            ("TP1", row["tp1_price"], float(self.config.tp1_size_pct)),
            ("TP2", row["tp2_price"], float(self.config.tp2_size_pct)),
            ("TP3", row["tp3_price"], float(self.config.tp3_size_pct)),
        ]
        valid = [(lab, px, w) for lab, px, w in tp_levels if px is not None and w > 0]
        if not valid:
            return {"position_id": pid, "skipped": "no_tp_levels"}
        wsum = sum(w for _, _, w in valid)
        placed_qty = 0.0
        level_results: list[dict[str, Any]] = []
        for j, (label, tp_px_raw, w) in enumerate(valid):
            if j == len(valid) - 1:
                tp_qty = round_quantity(self.client, symbol_u, exec_qty - placed_qty)
            else:
                tp_qty = round_quantity(
                    self.client, symbol_u, exec_qty * (w / wsum) if wsum > 0 else 0
                )
            placed_qty = round_quantity(self.client, symbol_u, placed_qty + tp_qty)
            if tp_qty <= 0:
                continue
            tp_px = round_price(self.client, symbol_u, float(tp_px_raw))
            cid_primary = (f"E{signal_id}{label}"[:36]) if signal_id else None
            cid_fallback = _pid_cid(pid, label)
            expected_cids = {c for c in (cid_primary, cid_fallback) if c}
            if any(c in cids for c in expected_cids):
                level_results.append({"level": label, "skipped": "cid_on_book"})
                continue
            if take_profit_reduce_on_book_from_orders(
                self.client,
                symbol_u,
                self.config,
                open_orders,
                position_side=side,
                position_side_tag=pst,
                stop_price=tp_px,
            ):
                level_results.append({"level": label, "skipped": "price_on_book"})
                continue
            db_skip = False
            for rord in self.store.list_open_protective_orders(pid):
                if str(rord["order_kind"]) != label:
                    continue
                if str(rord["status"] or "") == "NEW" and rord["order_id"] is not None:
                    try:
                        if int(rord["order_id"]) in open_ids:
                            db_skip = True
                            break
                    except (TypeError, ValueError):
                        pass
            if db_skip:
                level_results.append({"level": label, "skipped": "db_new_on_book"})
                continue
            use_cid = cid_primary or cid_fallback
            try:
                tp_resp = self.client.place_take_profit_market_reduce_only(
                    symbol=symbol_u,
                    side=side,
                    stop_price=tp_px,
                    quantity=tp_qty,
                    client_order_id=use_cid,
                    position_side=ps,
                )
                oid_tp = _order_id(tp_resp)
                row_tp = self.store.record_order(
                    pid,
                    order_kind=label,
                    order_id=oid_tp,
                    client_order_id=use_cid,
                    side=exit_order_side_for_position(side),
                    order_type="TAKE_PROFIT_MARKET",
                    quantity=tp_qty,
                    stop_price=tp_px,
                    status="NEW",
                )
                if oid_tp:
                    self.store.update_order_exchange_id(row_tp, oid_tp)
                if use_cid:
                    cids.add(use_cid)
                level_results.append({"level": label, "placed": True, "order_id": oid_tp})
            except Exception as exc:
                self.store.append_event(pid, f"{label}_ENSURE_FAILED", {"error": str(exc)})
                level_results.append({"level": label, "error": str(exc)})
        return {"position_id": pid, "tp_levels": level_results}

    def ensure_protection(self, symbol: str) -> dict[str, Any]:
        """Backfill TP/SL from signals if needed; ensure reduce-only SL; ensure TP ladders."""
        if not self.config.live_order_enabled:
            return {"ok": True, "skipped": "live_off"}
        symbol_u = symbol.upper()
        self._backfill_open_targets_from_active_signals(symbol_u)
        rows = self.store.list_open_positions_for_symbol(symbol_u)
        if not rows:
            return {"ok": True, "skipped": "no_db_open"}
        results: list[dict[str, Any]] = []
        tp_results: list[dict[str, Any]] = []
        for row in rows:
            pst = row["position_side_tag"]
            if self.config.hedge_position_mode and pst:
                amt = self.client.get_position_leg_amt(symbol_u, str(pst))
            else:
                pos = self.client.get_position(symbol_u)
                amt = _position_amt_local(pos)
            if abs(amt) < 1e-12:
                results.append({"position_id": int(row["id"]), "skipped": "flat"})
                continue
            open_orders = self.client.get_open_orders(symbol_u) or []
            if not isinstance(open_orders, list):
                open_orders = []
            sync_info = self._sync_protective_rows_from_book(symbol_u, row, amt, open_orders)
            if sync_info.get("imported") or sync_info.get("refreshed"):
                results.append({"position_id": int(row["id"]), "book_sync": sync_info})
            side_row = str(row["side"]).upper()
            if stop_loss_reduce_on_book_from_orders(
                open_orders,
                self.config,
                position_side=side_row,
                position_side_tag=pst,
            ):
                results.append({"position_id": int(row["id"]), "skipped": "has_sl"})
            else:
                side = side_row
                exec_qty = round_quantity(self.client, symbol_u, abs(amt))
                if exec_qty <= 0:
                    results.append({"position_id": int(row["id"]), "error": "qty_zero"})
                else:
                    sl_raw = row["stop_loss_price"]
                    emergency = False
                    if sl_raw is None:
                        emergency = True
                        pct = float(os.getenv("RECOVERY_EMERGENCY_SL_PCT", "5")) / 100.0
                        try:
                            entry = float(
                                self.client.get_position(symbol_u).get("entryPrice")
                                or row["entry_price"]
                                or 0
                            )
                        except (TypeError, ValueError):
                            entry = 0.0
                        if side == "LONG":
                            sl_px = round_price(
                                self.client, symbol_u, entry * (1.0 - pct) if entry > 0 else entry
                            )
                        else:
                            sl_px = round_price(
                                self.client, symbol_u, entry * (1.0 + pct) if entry > 0 else entry
                            )
                    else:
                        try:
                            sl_px = round_price(self.client, symbol_u, float(sl_raw))
                        except (TypeError, ValueError):
                            results.append({"position_id": int(row["id"]), "error": "invalid_sl"})
                            sl_px = None
                    if sl_px is not None:
                        try:
                            sid = row["source_signal_id"]
                            signal_id = int(sid) if sid is not None else 0
                        except (TypeError, ValueError):
                            signal_id = 0
                        cid_sl = (f"E{signal_id}SL"[:36]) if signal_id else None
                        ps = _position_side_param(self.config, side)
                        try:
                            sl_resp = self.client.place_stop_market_reduce_only(
                                symbol=symbol_u,
                                side=side,
                                stop_price=sl_px,
                                quantity=exec_qty,
                                client_order_id=cid_sl,
                                position_side=ps,
                            )
                        except Exception as exc:
                            self.store.append_event(int(row["id"]), "SL_ENSURE_FAILED", {"error": str(exc)})
                            results.append({"position_id": int(row["id"]), "error": str(exc)})
                        else:
                            oid_sl = _order_id(sl_resp)
                            self.store.record_order(
                                int(row["id"]),
                                order_kind="SL",
                                order_id=oid_sl,
                                client_order_id=cid_sl,
                                side="SELL" if side == "LONG" else "BUY",
                                order_type="STOP_MARKET",
                                quantity=exec_qty,
                                stop_price=sl_px,
                                status="NEW",
                            )
                            if emergency:
                                self.store.update_stop_loss_price(int(row["id"]), sl_px)
                            self.store.append_event(
                                int(row["id"]), "SL_ENSURE_PLACED", {"emergency": emergency}
                            )
                            results.append(
                                {"position_id": int(row["id"]), "placed": True, "emergency_sl": emergency}
                            )
            tp_results.append(self._ensure_take_profits_for_row(symbol_u, row, amt, open_orders))
        ok = True
        for item in results:
            if "error" in item:
                ok = False
                break
        if ok:
            for item in tp_results:
                for level in item.get("tp_levels") or []:
                    if "error" in level:
                        ok = False
                        break
                if not ok:
                    break
        return {"ok": ok, "results": results, "tp": tp_results}

    def _sync_signal_entry_after_binance_fill(self, signal_id: int, avg_entry: float) -> None:
        """Keep SQLite `signals` (and thus Google Sheet) entry aligned with Binance avg fill."""
        try:
            ep = float(avg_entry)
        except (TypeError, ValueError):
            return
        if ep <= 0:
            return
        try:
            from storage.wave_repository import WaveRepository

            repo = WaveRepository(db_path=self.store.db_path)
            if not repo.mark_signal_entry_filled_from_exchange(int(signal_id), ep):
                repo.update_signal_entry_to_exchange_average(int(signal_id), ep)
        except Exception:
            pass

    def _cancel_pending_entry_for_signal(self, signal_id: int, symbol: str) -> dict[str, Any] | None:
        pend_key = _pending_entry_health_key(signal_id)
        pend = read_execution_health(pend_key, db_path=self.store.db_path)
        if not pend:
            return None

        oid = pend.get("order_id")
        cid = pend.get("client_order_id")
        try:
            if oid is not None:
                self.client.cancel_order(symbol=symbol, order_id=int(oid))
            elif cid:
                self.client.cancel_order(symbol=symbol, client_order_id=str(cid))
        except Exception as exc:
            return {"ok": False, "error": f"pending_entry_cancel:{exc}", "signal_id": int(signal_id)}

        clear_execution_health(pend_key, db_path=self.store.db_path)
        record_execution_health(
            "execution:last_pending_entry_cancel",
            {"symbol": symbol, "signal_id": int(signal_id)},
            db_path=self.store.db_path,
        )
        return {"ok": True, "signal_id": int(signal_id), "pending_entry_canceled": True}

    def open_from_signal(
        self,
        signal_row: Any,
        account_equity_usdt: float | None = None,
    ) -> dict[str, Any]:
        """Open from signal: MARKET (default) or signal entry (LIMIT / STOP_MARKET) + SL/TP.

        When ``entry_style`` is ``signal_price``, entry rests until fill; caller should poll
        (execution queue uses ``mark_defer``) and SL/TP are placed only after fill.
        """
        signal_id = int(signal_row["id"])
        symbol = str(signal_row["symbol"]).upper()

        if self.store.has_open_position_for_signal(signal_id):
            return {"ok": True, "skipped": "already_open_for_signal"}

        equity = (
            float(account_equity_usdt)
            if account_equity_usdt is not None
            else _usdt_equity(self.client)
        )
        if equity <= 0:
            return {"ok": False, "error": "zero_or_missing_usdt_equity"}

        try:
            intent = build_order_intent_from_signal(
                signal_row,
                account_equity_usdt=equity,
                config=self.config,
            )
        except Exception as exc:
            return {"ok": False, "error": f"intent_failed:{exc}"}

        side = intent.side.upper()
        pst = _position_side_param(self.config, side)
        existing_leg = (
            self.store.get_open_leg_position(symbol, side)
            if (self.config.hedge_position_mode and self.config.allow_scale_in_same_leg)
            else None
        )
        block = evaluate_new_position(
            store=self.store,
            config=self.config,
            equity_usdt=equity,
            new_trade_risk_usdt=float(intent.risk_amount_usdt),
            symbol=symbol,
            position_side=side,
            allow_existing_leg=existing_leg is not None,
        )
        if block.get("skipped"):
            record_execution_health(
                "execution:last_portfolio_skip",
                {"skipped": block["skipped"], "symbol": symbol, "signal_id": signal_id, **block},
                db_path=self.store.db_path,
            )
            return {"ok": True, "skipped": block["skipped"], **{k: v for k, v in block.items() if k != "skipped"}}

        if _exchange_open_without_matching_db(self.client, self.store, symbol, side, self.config):
            return {"ok": False, "error": "exchange_position_without_db_run_reconcile"}

        entry_px = float(intent.entry_price)
        sl_px = round_price(self.client, symbol, float(intent.stop_loss))
        live_mark = self.client.get_mark_price(symbol)
        if live_mark is None or live_mark <= 0:
            pos_hint = self.client.get_position(symbol)
            live_mark = None
            if pos_hint:
                for key in ("markPrice", "lastPrice", "indexPrice", "entryPrice"):
                    value = pos_hint.get(key)
                    if value not in (None, "", "0"):
                        try:
                            live_mark = float(value)
                            break
                        except (TypeError, ValueError):
                            pass
        invalidation_price = None
        try:
            if isinstance(signal_row, dict):
                invalidation_price = signal_row.get("invalidation_price")
            elif hasattr(signal_row, "keys") and "invalidation_price" in signal_row.keys():
                invalidation_price = signal_row["invalidation_price"]
        except Exception:
            invalidation_price = None
        live_entry = evaluate_live_entry_actionability(
            side=side,
            planned_entry=entry_px,
            stop_loss=sl_px,
            current_price=live_mark,
            entry_style=getattr(self.config, "entry_style", "market"),
            invalidation_price=invalidation_price,
        )
        if not live_entry.actionable:
            try:
                from storage.wave_repository import WaveRepository

                repo = WaveRepository(db_path=self.store.db_path)
                reason = str(live_entry.reason or "entry_not_actionable").upper()
                if reason in {"STOP_CROSSED", "INVALIDATION_CROSSED"}:
                    repo.close_open_signal(
                        signal_id,
                        status="INVALIDATED",
                        close_reason="STOP_LOSS_BEFORE_ENTRY",
                        current_price=live_mark,
                        event_type="STOP_LOSS_BEFORE_ENTRY",
                    )
                else:
                    repo.close_open_signal(
                        signal_id,
                        status="INVALIDATED",
                        close_reason=reason,
                        current_price=live_mark,
                        event_type="ENTRY_SKIPPED",
                    )
            except Exception:
                pass
            return {"ok": True, "skipped": f"signal_not_actionable:{live_entry.reason}"}
        risk_mult = 1.0
        try:
            risk_mult = float(block.get("risk_multiplier") or 1.0)
        except (TypeError, ValueError):
            risk_mult = 1.0
        try:
            qty = round_quantity_clamped(
                self.client,
                symbol,
                float(intent.quantity) * risk_mult,
                reference_price=entry_px,
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        if abs(risk_mult - 1.0) > 1e-9:
            record_execution_health(
                "execution:last_de_risk_applied",
                {"symbol": symbol, "signal_id": signal_id, "risk_multiplier": risk_mult, "qty": qty},
                db_path=self.store.db_path,
            )
        try:
            validate_order(self.client, symbol, entry_px, qty)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

        cid_entry = f"E{signal_id}EN"[:36]
        cid_sl = f"E{signal_id}SL"[:36]

        try:
            self.client.set_margin_type(symbol, self.config.margin_type)
            self.client.set_leverage(symbol, int(self.config.leverage))
        except Exception as exc:
            return {"ok": False, "error": f"margin_leverage:{exc}"}

        use_signal_price = str(getattr(self.config, "entry_style", "market") or "market").lower() == "signal_price"
        pend_key = _pending_entry_health_key(signal_id) if use_signal_price else ""
        entry_resp: dict | None = None
        entry_order_label = "MARKET"

        if use_signal_price and pend_key:
            pend = read_execution_health(pend_key, db_path=self.store.db_path)
            oid_pend = pend.get("order_id") if pend else None
            if oid_pend is not None:
                try:
                    oid_i = int(oid_pend)
                except (TypeError, ValueError):
                    oid_i = None
                if oid_i is not None:
                    try:
                        q = self.client.query_order(symbol=symbol, order_id=oid_i)
                    except Exception as exc:
                        return {"ok": False, "error": f"pending_entry_query:{exc}"}
                    if isinstance(q, dict):
                        st = _entry_response_status(q)
                        if st in ("NEW", "PARTIALLY_FILLED"):
                            return {
                                "ok": True,
                                "awaiting_entry_fill": True,
                                "order_id": oid_i,
                                "status": st,
                            }
                        if st == "FILLED":
                            clear_execution_health(pend_key, db_path=self.store.db_path)
                            entry_resp = _normalize_filled_entry_from_query(q)
                            entry_order_label = str((pend or {}).get("order_type") or "LIMIT")
                        elif st in ("CANCELED", "EXPIRED", "REJECTED"):
                            clear_execution_health(pend_key, db_path=self.store.db_path)
                            entry_resp = None
                        else:
                            return {"ok": False, "error": f"pending_entry_unknown_status:{st}"}

        if entry_resp is None:
            try:
                if use_signal_price:
                    mark = self.client.get_mark_price(symbol)
                    if mark is None or mark <= 0:
                        pos_hint = self.client.get_position(symbol)
                        mark = None
                        if pos_hint:
                            for k in ("markPrice", "lastPrice", "indexPrice"):
                                v = pos_hint.get(k)
                                if v not in (None, "", "0"):
                                    try:
                                        mark = float(v)
                                        break
                                    except (TypeError, ValueError):
                                        pass
                    if mark is None or mark <= 0:
                        return {"ok": False, "error": "missing_mark_price_for_signal_entry"}

                    ex_px = round_price(self.client, symbol, float(entry_px))
                    kind, trig = _signal_price_entry_kind(side, float(mark), float(ex_px))
                    trig_r = round_price(self.client, symbol, float(trig))

                    if kind == "LIMIT":
                        entry_resp = self.client.place_limit_entry_order(
                            symbol=symbol,
                            side=side,
                            quantity=qty,
                            price=float(trig_r),
                            client_order_id=cid_entry,
                            position_side=pst,
                        )
                        entry_order_label = "LIMIT"
                    else:
                        entry_resp = self.client.place_stop_market_entry_order(
                            symbol=symbol,
                            side=side,
                            quantity=qty,
                            stop_price=float(trig_r),
                            client_order_id=cid_entry,
                            position_side=pst,
                        )
                        entry_order_label = "STOP_MARKET"
                else:
                    entry_resp = self.client.place_market_order(
                        symbol=symbol,
                        side=side,
                        quantity=qty,
                        client_order_id=cid_entry,
                        position_side=pst,
                    )
                    entry_order_label = "MARKET"
            except requests.HTTPError as exc:
                entry_resp = _entry_duplicate_response(
                    exc,
                    self.client,
                    symbol,
                    side,
                    qty,
                    entry_px,
                    hedge=self.config.hedge_position_mode,
                )
                if entry_resp is None:
                    traceback.print_exc()
                    return {"ok": False, "error": f"entry_failed:{exc}"}
            except Exception as exc:
                entry_resp = _entry_duplicate_response(
                    exc,
                    self.client,
                    symbol,
                    side,
                    qty,
                    entry_px,
                    hedge=self.config.hedge_position_mode,
                )
                if entry_resp is None:
                    traceback.print_exc()
                    return {"ok": False, "error": f"entry_failed:{exc}"}

        if use_signal_price and pend_key:
            st_now = _entry_response_status(entry_resp)
            if st_now in ("NEW", "PARTIALLY_FILLED"):
                oid_new = _order_id(entry_resp)
                record_execution_health(
                    pend_key,
                    {
                        "order_id": oid_new,
                        "symbol": symbol,
                        "client_order_id": cid_entry,
                        "order_type": entry_order_label,
                        "status": st_now,
                    },
                    db_path=self.store.db_path,
                )
                return {
                    "ok": True,
                    "awaiting_entry_fill": True,
                    "order_id": oid_new,
                    "order_type": entry_order_label,
                    "status": st_now,
                }

        exec_qty, avg_px = _executed_qty_price(entry_resp, qty, entry_px)
        exec_qty = round_quantity(self.client, symbol, exec_qty)
        if exec_qty <= 0:
            try:
                exec_qty = round_quantity_clamped(
                    self.client,
                    symbol,
                    float(_executed_qty_price(entry_resp, qty, entry_px)[0]),
                    reference_price=avg_px,
                )
            except ValueError:
                return {"ok": False, "error": "executed_qty_zero_after_round"}

        oid_entry = _order_id(entry_resp)
        entry_payload = {
            "executedQty": exec_qty,
            "avgPrice": avg_px,
            "orderId": oid_entry,
        }
        pos_tag = str(side).upper() if self.config.hedge_position_mode else None

        # Net scale-in (hedge leg): update the existing OPEN row instead of creating a new one.
        if existing_leg is not None:
            pos_id = int(existing_leg["id"])
            try:
                prev_qty = float(existing_leg["quantity"] or 0)
            except (TypeError, ValueError):
                prev_qty = 0.0
            prev_ep = existing_leg["entry_price"]
            try:
                prev_ep_f = float(prev_ep) if prev_ep is not None else None
            except (TypeError, ValueError):
                prev_ep_f = None
            new_qty = round_quantity(self.client, symbol, prev_qty + exec_qty)
            new_ep = avg_px
            if prev_qty > 0 and prev_ep_f is not None:
                new_ep = (prev_qty * prev_ep_f + exec_qty * avg_px) / (prev_qty + exec_qty)
            self.store.update_position_size_and_entry(pos_id, new_quantity=new_qty, new_entry_price=float(new_ep))
            self.store.append_event(
                pos_id,
                "SCALE_IN_FILLED",
                {
                    "added_qty": exec_qty,
                    "added_avg_price": avg_px,
                    "new_qty": new_qty,
                    "new_entry_price": new_ep,
                    "source_signal_id": signal_id,
                },
            )
        else:
            pos_id = self.store.create_position_from_signal(
                signal_row,
                intent,
                entry_payload,
                stop_loss_price=sl_px,
                recovered=0,
                position_side_tag=pos_tag,
            )
        row_entry = self.store.record_order(
            pos_id,
            order_kind="ENTRY",
            order_id=oid_entry,
            client_order_id=cid_entry,
            side="BUY" if side == "LONG" else "SELL",
            order_type=entry_order_label,
            quantity=exec_qty,
            stop_price=None,
            status="FILLED",
            reduce_only=False,
        )
        if oid_entry is not None:
            self.store.update_order_exchange_id(row_entry, oid_entry)

        if existing_leg is not None:
            # Re-place SL/TP for the whole net position size using stored levels.
            for r in self.store.list_open_protective_orders(pos_id):
                oid = r["order_id"]
                if oid is not None:
                    try:
                        self.client.cancel_order(symbol=symbol, order_id=int(oid))
                    except Exception:
                        pass
                if str(r["status"] or "") == "NEW":
                    try:
                        self.store.update_position_order_row_status(int(r["id"]), "CANCELED")
                    except Exception:
                        pass
            self.ensure_protection(symbol)
            # Replace TP orders (if stored on the position row)
            row_now = self.store.get_open_leg_position(symbol, side)
            if row_now is not None:
                tp_levels = [
                    ("TP1", row_now["tp1_price"], float(self.config.tp1_size_pct)),
                    ("TP2", row_now["tp2_price"], float(self.config.tp2_size_pct)),
                    ("TP3", row_now["tp3_price"], float(self.config.tp3_size_pct)),
                ]
                valid = [(lab, px, w) for lab, px, w in tp_levels if px is not None and w > 0]
                wsum = sum(w for _, _, w in valid)
                placed = 0.0
                total_qty = round_quantity(self.client, symbol, float(row_now["quantity"] or 0))
                for j, (label, tp_px_raw, w) in enumerate(valid):
                    if j == len(valid) - 1:
                        tp_qty = round_quantity(self.client, symbol, total_qty - placed)
                    else:
                        tp_qty = round_quantity(self.client, symbol, total_qty * (w / wsum) if wsum > 0 else 0)
                    placed = round_quantity(self.client, symbol, placed + tp_qty)
                    if tp_qty <= 0:
                        continue
                    tp_px = round_price(self.client, symbol, float(tp_px_raw))
                    cid = _pid_cid(pos_id, label)
                    try:
                        tp_resp = self.client.place_take_profit_market_reduce_only(
                            symbol=symbol,
                            side=side,
                            stop_price=tp_px,
                            quantity=tp_qty,
                            client_order_id=cid,
                            position_side=pst,
                        )
                        oid_tp = _order_id(tp_resp)
                        row_tp = self.store.record_order(
                            pos_id,
                            order_kind=label,
                            order_id=oid_tp,
                            client_order_id=cid,
                            side="SELL" if side == "LONG" else "BUY",
                            order_type="TAKE_PROFIT_MARKET",
                            quantity=tp_qty,
                            stop_price=tp_px,
                            status="NEW",
                        )
                        if oid_tp:
                            self.store.update_order_exchange_id(row_tp, oid_tp)
                    except Exception as exc:
                        self.store.append_event(pos_id, f"{label}_REPLACE_FAILED", {"error": str(exc)})
            self.store.append_event(pos_id, "SCALE_IN_PROTECTION_REPLACED", {})
            record_execution_health(
                "execution:last_open_ok",
                {"symbol": symbol, "signal_id": signal_id, "position_id": pos_id, "scale_in": True},
                db_path=self.store.db_path,
            )
            if use_signal_price and pend_key:
                clear_execution_health(pend_key, db_path=self.store.db_path)
            row_sync = self.store.get_open_leg_position(symbol, side)
            if row_sync is not None and row_sync.get("entry_price") is not None:
                try:
                    self._sync_signal_entry_after_binance_fill(signal_id, float(row_sync["entry_price"]))
                except (TypeError, ValueError):
                    pass
            else:
                self._sync_signal_entry_after_binance_fill(signal_id, avg_px)
            return {"ok": True, "position_id": pos_id, "executed_qty": exec_qty, "avg_price": avg_px, "scale_in": True}

        raw_orders = self.client.get_open_orders(symbol) or []
        if not isinstance(raw_orders, list):
            raw_orders = []
        row_now = self.store.get_open_position_by_signal(signal_id)
        if row_now is None and self.config.hedge_position_mode:
            row_now = self.store.get_open_leg_position(symbol, side)
        if row_now is not None:
            self._sync_protective_rows_from_book(symbol, row_now, exec_qty, raw_orders)
        cids_open = _open_order_client_ids_from_orders(raw_orders)
        has_sl_strict = stop_loss_reduce_on_book_from_orders(
            raw_orders,
            self.config,
            position_side=side,
            position_side_tag=pos_tag,
        )
        if cid_sl in cids_open or has_sl_strict:
            if cid_sl not in cids_open and has_sl_strict:
                self.store.append_event(pos_id, "SL_ALREADY_ON_BOOK", {})
        else:
            try:
                sl_resp = self.client.place_stop_market_reduce_only(
                    symbol=symbol,
                    side=side,
                    stop_price=sl_px,
                    quantity=exec_qty,
                    client_order_id=cid_sl,
                    position_side=pst,
                )
                oid_sl = _order_id(sl_resp)
                row_sl = self.store.record_order(
                    pos_id,
                    order_kind="SL",
                    order_id=oid_sl,
                    client_order_id=cid_sl,
                    side="SELL" if side == "LONG" else "BUY",
                    order_type="STOP_MARKET",
                    quantity=exec_qty,
                    stop_price=sl_px,
                    status="NEW",
                )
                if oid_sl:
                    self.store.update_order_exchange_id(row_sl, oid_sl)
            except Exception as exc:
                self.store.append_event(pos_id, "SL_PLACE_FAILED", {"error": str(exc)})
                traceback.print_exc()
                return {"ok": False, "error": f"sl_failed:{exc}", "position_id": pos_id}

        w1 = float(self.config.tp1_size_pct)
        w2 = float(self.config.tp2_size_pct)
        w3 = float(self.config.tp3_size_pct)
        tps = [
            ("TP1", intent.tp1, w1),
            ("TP2", intent.tp2, w2),
            ("TP3", intent.tp3, w3),
        ]
        valid_tps = [(lab, px, w) for lab, px, w in tps if px is not None and w > 0]
        wsum = sum(w for _, _, w in valid_tps)
        placed_qty = 0.0
        raw_orders_tp = self.client.get_open_orders(symbol) or []
        if not isinstance(raw_orders_tp, list):
            raw_orders_tp = []
        cids_open = _open_order_client_ids_from_orders(raw_orders_tp)
        for j, (label, tp_raw, w) in enumerate(valid_tps):
            if j == len(valid_tps) - 1:
                tp_qty = round_quantity(self.client, symbol, exec_qty - placed_qty)
            else:
                tp_qty = round_quantity(
                    self.client, symbol, exec_qty * (w / wsum) if wsum > 0 else 0
                )
            placed_qty = round_quantity(self.client, symbol, placed_qty + tp_qty)
            if tp_qty <= 0:
                continue
            tp_px = round_price(self.client, symbol, float(tp_raw))
            cid = f"E{signal_id}{label}"[:36]
            if cid in cids_open:
                continue
            try:
                tp_resp = self.client.place_take_profit_market_reduce_only(
                    symbol=symbol,
                    side=side,
                    stop_price=tp_px,
                    quantity=tp_qty,
                    client_order_id=cid,
                    position_side=pst,
                )
                oid_tp = _order_id(tp_resp)
                row_tp = self.store.record_order(
                    pos_id,
                    order_kind=label,
                    order_id=oid_tp,
                    client_order_id=cid,
                    side="SELL" if side == "LONG" else "BUY",
                    order_type="TAKE_PROFIT_MARKET",
                    quantity=tp_qty,
                    stop_price=tp_px,
                    status="NEW",
                )
                if oid_tp:
                    self.store.update_order_exchange_id(row_tp, oid_tp)
            except Exception as exc:
                self.store.append_event(
                    pos_id,
                    f"{label}_PLACE_FAILED",
                    {"error": str(exc)},
                )
                traceback.print_exc()

        self.store.append_event(pos_id, "PROTECTION_PLACED", {})
        record_execution_health(
            "execution:last_open_ok",
            {"symbol": symbol, "signal_id": signal_id, "position_id": pos_id},
            db_path=self.store.db_path,
        )
        if use_signal_price and pend_key:
            clear_execution_health(pend_key, db_path=self.store.db_path)
        self._sync_signal_entry_after_binance_fill(signal_id, avg_px)
        return {"ok": True, "position_id": pos_id, "executed_qty": exec_qty, "avg_price": avg_px}

    def close_for_signal(self, signal_row: Any, reason: str) -> dict[str, Any]:
        """Cancel this signal's protective orders and reduce-close the matching exchange leg."""
        sym = str(signal_row["symbol"]).upper()
        sid = int(signal_row["id"])
        row = self.store.get_open_position_by_signal(sid)
        if row is None:
            pending = self._cancel_pending_entry_for_signal(sid, sym)
            if pending is not None:
                return pending
            open_rows = self.store.list_open_positions_for_symbol(sym)
            if len(open_rows) == 1 and open_rows[0]["source_signal_id"] is None:
                return self.close_symbol_cleanup(sym, reason)
            return {"ok": True, "skipped": "no_open_position_for_signal"}

        pid = int(row["id"])
        side = str(row["side"]).upper()
        pst = row["position_side_tag"]
        ps = str(pst).upper() if pst else None

        with self.store._connect() as conn:
            oids = conn.execute(
                """
                SELECT DISTINCT order_id FROM exchange_position_orders
                WHERE position_id = ? AND order_id IS NOT NULL
                """,
                (pid,),
            ).fetchall()
        for (oid,) in oids:
            try:
                self.client.cancel_order(symbol=sym, order_id=int(oid))
            except Exception:
                pass

        if self.config.hedge_position_mode and ps:
            leg = self.client.get_position_leg_amt(sym, ps)
        else:
            pos = self.client.get_position(sym)
            leg = abs(_position_amt_local(pos))
        try:
            row_q = float(row["quantity"] or 0)
        except (TypeError, ValueError):
            row_q = 0.0
        q = round_quantity(self.client, sym, min(row_q, leg))
        if q > 0:
            close_side = "SELL" if side == "LONG" else "BUY"
            try:
                self.client.place_market_reduce_only(
                    symbol=sym,
                    side=close_side,
                    quantity=q,
                    client_order_id=None,
                    position_side=ps if self.config.hedge_position_mode else None,
                )
            except Exception as exc:
                return {"ok": False, "error": str(exc), "position_id": pid}

        close_px: float | None = None
        pos = self.client.get_position(sym)
        if pos:
            for k in ("markPrice", "entryPrice", "lastPrice"):
                v = pos.get(k)
                if v not in (None, "", "0"):
                    try:
                        close_px = float(v)
                        break
                    except (TypeError, ValueError):
                        pass
        self.store.close_position(pid, reason, close_price=close_px)
        record_execution_health(
            "execution:last_close_ok",
            {"symbol": sym, "signal_id": sid, "reason": reason},
            db_path=self.store.db_path,
        )
        return {"ok": True, "position_id": pid}

    def close_symbol_cleanup(self, symbol: str, reason: str) -> dict[str, Any]:
        """Cancel all symbol orders and market-close all exchange exposure; close DB rows."""
        symbol_u = symbol.upper()
        try:
            self.client.cancel_all_orders(symbol=symbol_u)
        except Exception:
            pass

        if self.config.hedge_position_mode:
            for row in self.client.get_position_risk() or []:
                if str(row.get("symbol") or "").upper() != symbol_u:
                    continue
                try:
                    amt = float(row.get("positionAmt") or 0)
                except (TypeError, ValueError):
                    amt = 0.0
                if abs(amt) < 1e-12:
                    continue
                ps = str(row.get("positionSide") or "BOTH").upper()
                q = round_quantity(self.client, symbol_u, abs(amt))
                if q <= 0:
                    continue
                close_side = "SELL" if amt > 0 else "BUY"
                leg_ps = None if ps == "BOTH" else ps
                try:
                    self.client.place_market_reduce_only(
                        symbol=symbol_u,
                        side=close_side,
                        quantity=q,
                        client_order_id=None,
                        position_side=leg_ps,
                    )
                except Exception:
                    pass
        else:
            pos = self.client.get_position(symbol_u)
            amt = 0.0
            if pos:
                try:
                    amt = float(pos.get("positionAmt") or 0)
                except (TypeError, ValueError):
                    amt = 0.0
            if abs(amt) > 0:
                close_side = "SELL" if amt > 0 else "BUY"
                q = round_quantity(self.client, symbol_u, abs(amt))
                if q > 0:
                    try:
                        self.client.place_market_reduce_only(
                            symbol=symbol_u,
                            side=close_side,
                            quantity=q,
                            client_order_id=None,
                        )
                    except Exception as exc:
                        return {"ok": False, "error": str(exc)}

        for open_row in self.store.list_open_positions_for_symbol(symbol_u):
            close_px: float | None = None
            pos = self.client.get_position(symbol_u)
            if pos:
                for k in ("markPrice", "entryPrice", "lastPrice"):
                    v = pos.get(k)
                    if v not in (None, "", "0"):
                        try:
                            close_px = float(v)
                            break
                        except (TypeError, ValueError):
                            pass
            self.store.close_position(int(open_row["id"]), reason, close_price=close_px)
        return {"ok": True}

    def close_position_market(self, symbol: str, reason: str) -> dict[str, Any]:
        """Spec name for :meth:`close_symbol_cleanup`."""
        return self.close_symbol_cleanup(symbol, reason)
