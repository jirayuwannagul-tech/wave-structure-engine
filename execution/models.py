from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionConfig:
    enabled: bool = False
    live_order_enabled: bool = False
    use_testnet: bool = True
    api_key: str | None = None
    api_secret: str | None = None
    recv_window: int = 5000
    risk_per_trade: float = 0.01
    leverage: int = 1
    margin_type: str = "ISOLATED"
    allow_long: bool = True
    allow_short: bool = True

    @property
    def credentials_ready(self) -> bool:
        return bool(self.api_key and self.api_secret)

    @property
    def base_url(self) -> str:
        if self.use_testnet:
            return "https://testnet.binancefuture.com"
        return "https://fapi.binance.com"


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    timeframe: str
    side: str
    entry_price: float
    stop_loss: float
    tp1: float | None
    tp2: float | None
    tp3: float | None
    risk_amount_usdt: float
    quantity: float
    source_signal_id: int | None = None

    @property
    def stop_distance(self) -> float:
        return abs(float(self.entry_price) - float(self.stop_loss))
