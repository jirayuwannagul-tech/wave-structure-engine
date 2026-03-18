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
    tp1_size_pct: float = 0.40
    tp2_size_pct: float = 0.30
    tp3_size_pct: float = 0.30
    # Portfolio execution (caps only; no strategy filters)
    portfolio_max_open_positions: int = 100
    portfolio_max_risk_fraction: float = 1.0
    hedge_position_mode: bool = False
    http_max_retries: int = 3
    http_retry_backoff_sec: float = 0.6

    @property
    def credentials_ready(self) -> bool:
        return bool(self.api_key and self.api_secret)

    @property
    def base_url(self) -> str:
        if self.use_testnet:
            return "https://testnet.binancefuture.com"
        return "https://fapi.binance.com"

    @property
    def tp_allocation_total(self) -> float:
        return float(self.tp1_size_pct) + float(self.tp2_size_pct) + float(self.tp3_size_pct)


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
