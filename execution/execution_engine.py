from __future__ import annotations

from execution.binance_futures_client import BinanceFuturesClient
from execution.models import ExecutionConfig, OrderIntent
from execution.settings import load_execution_config
from execution.signal_mapper import build_order_intent_from_signal


class ExecutionEngine:
    def __init__(
        self,
        config: ExecutionConfig | None = None,
        client: BinanceFuturesClient | None = None,
    ):
        self.config = config or load_execution_config()
        self.client = client or BinanceFuturesClient(self.config)

    def _build_exit_plan(self, intent: OrderIntent) -> list[dict]:
        plan: list[dict] = []
        exit_specs = [
            ("TP1", intent.tp1, float(self.config.tp1_size_pct)),
            ("TP2", intent.tp2, float(self.config.tp2_size_pct)),
            ("TP3", intent.tp3, float(self.config.tp3_size_pct)),
        ]

        for label, target_price, size_pct in exit_specs:
            if target_price is None or size_pct <= 0:
                continue
            plan.append(
                {
                    "label": label,
                    "target_price": target_price,
                    "size_pct": round(size_pct, 4),
                    "quantity": round(float(intent.quantity) * size_pct, 6),
                }
            )
        return plan

    def preview_signal(self, signal_row, *, account_equity_usdt: float) -> dict:
        intent = build_order_intent_from_signal(
            signal_row,
            account_equity_usdt=account_equity_usdt,
            config=self.config,
        )
        return self._build_preview(intent)

    def execute_signal(self, signal_row, *, account_equity_usdt: float) -> dict:
        intent = build_order_intent_from_signal(
            signal_row,
            account_equity_usdt=account_equity_usdt,
            config=self.config,
        )
        if not self.config.enabled:
            raise RuntimeError("Binance execution is disabled.")
        if not self.config.live_order_enabled:
            raise RuntimeError("Live Binance order placement is disabled.")

        self.client.set_margin_type(intent.symbol, self.config.margin_type)
        self.client.set_leverage(intent.symbol, self.config.leverage)
        order_response = self.client.place_market_order(
            symbol=intent.symbol,
            side=intent.side,
            quantity=intent.quantity,
        )
        return {
            "intent": self._serialize_intent(intent),
            "order_response": order_response,
        }

    def _build_preview(self, intent: OrderIntent) -> dict:
        return {
            "mode": "preview",
            "intent": self._serialize_intent(intent),
            "entry_order": {
                "symbol": intent.symbol,
                "side": "BUY" if intent.side == "LONG" else "SELL",
                "type": "MARKET",
                "quantity": intent.quantity,
            },
            "protection": {
                "stop_loss": intent.stop_loss,
                "tp1": intent.tp1,
                "tp2": intent.tp2,
                "tp3": intent.tp3,
            },
            "exit_plan": self._build_exit_plan(intent),
        }

    @staticmethod
    def _serialize_intent(intent: OrderIntent) -> dict:
        return {
            "symbol": intent.symbol,
            "timeframe": intent.timeframe,
            "side": intent.side,
            "entry_price": intent.entry_price,
            "stop_loss": intent.stop_loss,
            "tp1": intent.tp1,
            "tp2": intent.tp2,
            "tp3": intent.tp3,
            "risk_amount_usdt": intent.risk_amount_usdt,
            "quantity": intent.quantity,
            "source_signal_id": intent.source_signal_id,
        }
