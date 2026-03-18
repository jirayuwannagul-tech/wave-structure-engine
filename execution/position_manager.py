"""Open and protect futures positions from signal rows (market entry + SL/TP reduce-only)."""

from __future__ import annotations

import os
import traceback
from typing import Any

import requests

from execution.binance_futures_client import BinanceFuturesClient
from execution.exchange_info import (
    round_price,
    round_quantity,
    round_quantity_clamped,
    validate_order,
)
from execution.models import ExecutionConfig
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


def _open_order_cids_and_sl_flag(client: BinanceFuturesClient, symbol: str) -> tuple[set[str], bool]:
    raw = client.get_open_orders(symbol) or []
    if not isinstance(raw, list):
        return set(), False
    cids: set[str] = set()
    has_sl = False
    for o in raw:
        cid = o.get("clientOrderId")
        if cid:
            cids.add(str(cid))
        if str(o.get("type") or "").upper() == "STOP_MARKET":
            ro = str(o.get("reduceOnly") or "").lower()
            if ro in ("true", "1"):
                has_sl = True
    return cids, has_sl


def _entry_duplicate_response(
    exc: BaseException,
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    fallback_qty: float,
    fallback_price: float,
) -> dict | None:
    """If Binance reports duplicate client order id, synthesize response from position."""
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

    def ensure_protection(self, symbol: str) -> dict[str, Any]:
        """If DB has OPEN and exchange has size but no reduce-only STOP_MARKET, place SL."""
        if not self.config.live_order_enabled:
            return {"ok": True, "skipped": "live_off"}
        symbol_u = symbol.upper()
        row = self.store.get_open_position_by_symbol(symbol_u)
        if row is None:
            return {"ok": True, "skipped": "no_db_open"}
        pos = self.client.get_position(symbol_u)
        amt = _position_amt_local(pos)
        if abs(amt) < 1e-12:
            return {"ok": True, "skipped": "flat"}
        _, has_sl = _open_order_cids_and_sl_flag(self.client, symbol_u)
        if has_sl:
            return {"ok": True, "skipped": "has_sl"}
        side = "LONG" if amt > 0 else "SHORT"
        exec_qty = round_quantity(self.client, symbol_u, abs(amt))
        if exec_qty <= 0:
            return {"ok": False, "error": "qty_zero"}
        sl_raw = row["stop_loss_price"]
        emergency = False
        if sl_raw is None:
            emergency = True
            pct = float(os.getenv("RECOVERY_EMERGENCY_SL_PCT", "5")) / 100.0
            try:
                entry = float(pos.get("entryPrice") or row["entry_price"] or 0)
            except (TypeError, ValueError):
                entry = 0.0
            if side == "LONG":
                sl_px = round_price(self.client, symbol_u, entry * (1.0 - pct) if entry > 0 else entry)
            else:
                sl_px = round_price(self.client, symbol_u, entry * (1.0 + pct) if entry > 0 else entry)
        else:
            try:
                sl_px = round_price(self.client, symbol_u, float(sl_raw))
            except (TypeError, ValueError):
                return {"ok": False, "error": "invalid_stop_loss_price"}
        try:
            sid = row["source_signal_id"]
            signal_id = int(sid) if sid is not None else 0
        except (TypeError, ValueError):
            signal_id = 0
        cid_sl = (f"E{signal_id}SL"[:36]) if signal_id else None
        try:
            sl_resp = self.client.place_stop_market_reduce_only(
                symbol=symbol_u,
                side=side,
                stop_price=sl_px,
                quantity=exec_qty,
                client_order_id=cid_sl,
            )
        except Exception as exc:
            self.store.append_event(int(row["id"]), "SL_ENSURE_FAILED", {"error": str(exc)})
            return {"ok": False, "error": str(exc)}
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
        self.store.append_event(int(row["id"]), "SL_ENSURE_PLACED", {"emergency": emergency})
        return {"ok": True, "placed": True, "emergency_sl": emergency}

    def open_from_signal(
        self,
        signal_row: Any,
        account_equity_usdt: float | None = None,
    ) -> dict[str, Any]:
        """Market entry + STOP_MARKET SL + TAKE_PROFIT_MARKET TP1/2/3. No strategy filters."""
        signal_id = int(signal_row["id"])
        symbol = str(signal_row["symbol"]).upper()

        if self.store.has_open_position_for_signal(signal_id):
            return {"ok": True, "skipped": "already_open_for_signal"}
        if self.store.has_open_position_for_symbol(symbol):
            return {"ok": True, "skipped": "symbol_already_has_open_position"}

        pos_chk = self.client.get_position(symbol)
        if abs(_position_amt_local(pos_chk)) > 1e-12 and self.store.get_open_position_by_symbol(symbol) is None:
            return {"ok": False, "error": "exchange_position_without_db_run_reconcile"}

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

        entry_px = float(intent.entry_price)
        sl_px = round_price(self.client, symbol, float(intent.stop_loss))
        try:
            qty = round_quantity_clamped(
                self.client,
                symbol,
                float(intent.quantity),
                reference_price=entry_px,
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        try:
            validate_order(self.client, symbol, entry_px, qty)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

        signal_hash = None
        try:
            if hasattr(signal_row, "keys") and "signal_hash" in signal_row.keys():
                signal_hash = signal_row["signal_hash"]
            elif isinstance(signal_row, dict):
                signal_hash = signal_row.get("signal_hash")
        except Exception:
            pass

        side = intent.side.upper()
        cid_entry = f"E{signal_id}EN"[:36]
        cid_sl = f"E{signal_id}SL"[:36]

        try:
            self.client.set_margin_type(symbol, self.config.margin_type)
            self.client.set_leverage(symbol, int(self.config.leverage))
        except Exception as exc:
            return {"ok": False, "error": f"margin_leverage:{exc}"}

        entry_resp: dict | None = None
        try:
            entry_resp = self.client.place_market_order(
                symbol=symbol,
                side=side,
                quantity=qty,
                client_order_id=cid_entry,
            )
        except requests.HTTPError as exc:
            entry_resp = _entry_duplicate_response(exc, self.client, symbol, side, qty, entry_px)
            if entry_resp is None:
                traceback.print_exc()
                return {"ok": False, "error": f"entry_failed:{exc}"}
        except Exception as exc:
            entry_resp = _entry_duplicate_response(exc, self.client, symbol, side, qty, entry_px)
            if entry_resp is None:
                traceback.print_exc()
                return {"ok": False, "error": f"entry_failed:{exc}"}

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
        pos_id = self.store.create_position_from_signal(
            signal_row,
            intent,
            entry_payload,
            stop_loss_price=sl_px,
            recovered=0,
        )
        row_entry = self.store.record_order(
            pos_id,
            order_kind="ENTRY",
            order_id=oid_entry,
            client_order_id=cid_entry,
            side="BUY" if side == "LONG" else "SELL",
            order_type="MARKET",
            quantity=exec_qty,
            stop_price=None,
            status="FILLED",
            reduce_only=False,
        )
        if oid_entry is not None:
            self.store.update_order_exchange_id(row_entry, oid_entry)

        cids_open, has_sl_book = _open_order_cids_and_sl_flag(self.client, symbol)
        if cid_sl in cids_open or has_sl_book:
            if cid_sl not in cids_open and has_sl_book:
                self.store.append_event(pos_id, "SL_ALREADY_ON_BOOK", {})
        else:
            try:
                sl_resp = self.client.place_stop_market_reduce_only(
                    symbol=symbol,
                    side=side,
                    stop_price=sl_px,
                    quantity=exec_qty,
                    client_order_id=cid_sl,
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
        cids_open, _ = _open_order_cids_and_sl_flag(self.client, symbol)
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
        return {"ok": True, "position_id": pos_id, "executed_qty": exec_qty, "avg_price": avg_px}

    def close_symbol_cleanup(self, symbol: str, reason: str) -> dict[str, Any]:
        """Cancel open reduce-only orders and market-close remaining position."""
        symbol_u = symbol.upper()
        open_row = self.store.get_open_position_by_symbol(symbol_u)
        try:
            self.client.cancel_all_orders(symbol=symbol_u)
        except Exception:
            pass
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
        if open_row:
            close_px: float | None = None
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
