from __future__ import annotations

from dataclasses import dataclass


TARGET_INDEX = {
    "TP1": 0,
    "TP2": 1,
    "TP3": 2,
}


@dataclass
class TradeSetup:
    side: str
    entry_price: float
    stop_loss: float
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    take_profit_3: float | None = None

    def target_for(self, target_label: str) -> float | None:
        target_label = (target_label or "").upper()
        idx = TARGET_INDEX.get(target_label)

        if idx is None:
            return None

        targets = [
            self.take_profit_1,
            self.take_profit_2,
            self.take_profit_3,
        ]
        return targets[idx]


@dataclass
class TradeBacktestResult:
    triggered: bool
    outcome: str
    target_label: str
    entry_index: int | None
    exit_index: int | None
    entry_price: float | None
    exit_price: float | None
    reward_r: float
    gross_pnl_per_unit: float = 0.0
    net_pnl_per_unit: float = 0.0
    fee_paid_per_unit: float = 0.0


def build_trade_setup_from_scenario(scenario) -> TradeSetup | None:
    bias = (getattr(scenario, "bias", None) or "").upper()
    confirmation = getattr(scenario, "confirmation", None)
    stop_loss = getattr(scenario, "stop_loss", None)
    targets = list(getattr(scenario, "targets", []) or [])

    if bias not in {"BULLISH", "BEARISH"}:
        return None

    if confirmation is None or stop_loss is None:
        return None

    return TradeSetup(
        side="LONG" if bias == "BULLISH" else "SHORT",
        entry_price=float(confirmation),
        stop_loss=float(stop_loss),
        take_profit_1=float(targets[0]) if len(targets) >= 1 else None,
        take_profit_2=float(targets[1]) if len(targets) >= 2 else None,
        take_profit_3=float(targets[2]) if len(targets) >= 3 else None,
    )


def _risk_per_unit(setup: TradeSetup) -> float:
    return abs(float(setup.entry_price) - float(setup.stop_loss))


def _is_long(setup: TradeSetup) -> bool:
    return (setup.side or "").upper() == "LONG"


def _triggered_by_candle(candle, setup: TradeSetup) -> bool:
    # Entry is confirmed by a close through the scenario level.
    # Keep this aligned with the raw signal logic instead of adding an extra
    # percentage buffer, so KPI/backtests measure the EW entry directly.
    entry = float(setup.entry_price)
    close = float(candle["close"])
    if _is_long(setup):
        return close >= entry
    return close <= entry


def _stop_hit(candle, setup: TradeSetup) -> bool:
    if _is_long(setup):
        return float(candle["low"]) <= float(setup.stop_loss)
    return float(candle["high"]) >= float(setup.stop_loss)


def _target_hit(candle, target_price: float, setup: TradeSetup) -> bool:
    if _is_long(setup):
        return float(candle["high"]) >= float(target_price)
    return float(candle["low"]) <= float(target_price)


def _effective_entry_price(setup: TradeSetup, slippage_rate: float) -> float:
    if _is_long(setup):
        return float(setup.entry_price) * (1 + slippage_rate)
    return float(setup.entry_price) * (1 - slippage_rate)


def _effective_exit_price(raw_exit_price: float, setup: TradeSetup, slippage_rate: float) -> float:
    if _is_long(setup):
        return float(raw_exit_price) * (1 - slippage_rate)
    return float(raw_exit_price) * (1 + slippage_rate)


def _effective_entry_from_open(open_price: float, setup: TradeSetup, slippage_rate: float) -> float:
    if _is_long(setup):
        return float(open_price) * (1 + slippage_rate)
    return float(open_price) * (1 - slippage_rate)


def _net_pnl_per_unit(
    entry_price: float,
    exit_price: float,
    setup: TradeSetup,
    fee_rate: float,
) -> tuple[float, float, float]:
    direction = 1.0 if _is_long(setup) else -1.0
    gross_pnl = (float(exit_price) - float(entry_price)) * direction
    fee_paid = (float(entry_price) + float(exit_price)) * fee_rate
    net_pnl = gross_pnl - fee_paid
    return gross_pnl, net_pnl, fee_paid


def simulate_trade_from_setup(
    df,
    setup: TradeSetup,
    target_label: str = "TP1",
    fee_rate: float = 0.0,
    slippage_rate: float = 0.0,
) -> TradeBacktestResult:
    target_label = (target_label or "TP1").upper()
    target_price = setup.target_for(target_label)

    if target_price is None:
        return TradeBacktestResult(
            triggered=False,
            outcome="INVALID",
            target_label=target_label,
            entry_index=None,
            exit_index=None,
            entry_price=None,
            exit_price=None,
            reward_r=0.0,
        )

    if len(df) < 2:
        return TradeBacktestResult(
            triggered=False,
            outcome="NO_TRIGGER",
            target_label=target_label,
            entry_index=None,
            exit_index=None,
            entry_price=None,
            exit_price=None,
            reward_r=0.0,
        )

    trigger_index = None

    for i in range(len(df) - 1):
        candle = df.iloc[i]
        if _triggered_by_candle(candle, setup):
            trigger_index = i
            break

    entry_index = None if trigger_index is None else trigger_index + 1
    if entry_index is None or entry_index >= len(df):
        return TradeBacktestResult(
            triggered=False,
            outcome="NO_TRIGGER",
            target_label=target_label,
            entry_index=None,
            exit_index=None,
            entry_price=None,
            exit_price=None,
            reward_r=0.0,
        )

    entry_candle = df.iloc[entry_index]
    effective_entry = _effective_entry_from_open(float(entry_candle["open"]), setup, slippage_rate)
    effective_stop = _effective_exit_price(float(setup.stop_loss), setup, slippage_rate)
    stop_gross_pnl, stop_net_pnl, stop_fee_paid = _net_pnl_per_unit(
        effective_entry,
        effective_stop,
        setup,
        fee_rate,
    )
    risk_amount = abs(stop_net_pnl)

    if risk_amount == 0:
        return TradeBacktestResult(
            triggered=False,
            outcome="INVALID",
            target_label=target_label,
            entry_index=entry_index,
            exit_index=None,
            entry_price=round(effective_entry, 6),
            exit_price=None,
            reward_r=0.0,
        )

    # Entry is taken strictly on the next candle's open.
    # If the market gaps through the stop or target at the open, resolve that immediately.
    stop_gap_hit = (_is_long(setup) and float(entry_candle["open"]) <= float(setup.stop_loss)) or (
        (not _is_long(setup)) and float(entry_candle["open"]) >= float(setup.stop_loss)
    )
    target_gap_hit = (_is_long(setup) and float(entry_candle["open"]) >= float(target_price)) or (
        (not _is_long(setup)) and float(entry_candle["open"]) <= float(target_price)
    )

    if stop_gap_hit:
        immediate_stop = _effective_exit_price(float(entry_candle["open"]), setup, slippage_rate)
        gross_pnl, net_pnl, fee_paid = _net_pnl_per_unit(
            effective_entry,
            immediate_stop,
            setup,
            fee_rate,
        )
        reward_r = net_pnl / risk_amount if risk_amount else -1.0
        return TradeBacktestResult(
            triggered=True,
            outcome="STOP_LOSS",
            target_label=target_label,
            entry_index=entry_index,
            exit_index=entry_index,
            entry_price=round(effective_entry, 6),
            exit_price=round(immediate_stop, 6),
            reward_r=round(reward_r, 3),
            gross_pnl_per_unit=round(gross_pnl, 6),
            net_pnl_per_unit=round(net_pnl, 6),
            fee_paid_per_unit=round(fee_paid, 6),
        )

    if target_gap_hit:
        immediate_target = _effective_exit_price(float(entry_candle["open"]), setup, slippage_rate)
        gross_pnl, net_pnl, fee_paid = _net_pnl_per_unit(
            effective_entry,
            immediate_target,
            setup,
            fee_rate,
        )
        reward_r = net_pnl / risk_amount if risk_amount else 0.0
        return TradeBacktestResult(
            triggered=True,
            outcome=target_label,
            target_label=target_label,
            entry_index=entry_index,
            exit_index=entry_index,
            entry_price=round(effective_entry, 6),
            exit_price=round(immediate_target, 6),
            reward_r=round(reward_r, 3),
            gross_pnl_per_unit=round(gross_pnl, 6),
            net_pnl_per_unit=round(net_pnl, 6),
            fee_paid_per_unit=round(fee_paid, 6),
        )

    for i in range(entry_index, len(df)):
        candle = df.iloc[i]
        stop_hit = _stop_hit(candle, setup)
        target_hit = _target_hit(candle, target_price, setup)

        # Intrabar order is unknown, so same-bar stop/target is treated conservatively.
        if stop_hit and target_hit:
            return TradeBacktestResult(
                triggered=True,
                outcome="STOP_LOSS",
                target_label=target_label,
                entry_index=entry_index,
                exit_index=i,
                entry_price=round(effective_entry, 6),
                exit_price=round(effective_stop, 6),
                reward_r=-1.0,
                gross_pnl_per_unit=round(stop_gross_pnl, 6),
                net_pnl_per_unit=round(stop_net_pnl, 6),
                fee_paid_per_unit=round(stop_fee_paid, 6),
            )

        if stop_hit:
            return TradeBacktestResult(
                triggered=True,
                outcome="STOP_LOSS",
                target_label=target_label,
                entry_index=entry_index,
                exit_index=i,
                entry_price=round(effective_entry, 6),
                exit_price=round(effective_stop, 6),
                reward_r=-1.0,
                gross_pnl_per_unit=round(stop_gross_pnl, 6),
                net_pnl_per_unit=round(stop_net_pnl, 6),
                fee_paid_per_unit=round(stop_fee_paid, 6),
            )

        if target_hit:
            effective_target = _effective_exit_price(float(target_price), setup, slippage_rate)
            gross_pnl, net_pnl, fee_paid = _net_pnl_per_unit(
                effective_entry,
                effective_target,
                setup,
                fee_rate,
            )
            reward_r = net_pnl / risk_amount
            return TradeBacktestResult(
                triggered=True,
                outcome=target_label,
                target_label=target_label,
                entry_index=entry_index,
                exit_index=i,
                entry_price=round(effective_entry, 6),
                exit_price=round(effective_target, 6),
                reward_r=round(reward_r, 3),
                gross_pnl_per_unit=round(gross_pnl, 6),
                net_pnl_per_unit=round(net_pnl, 6),
                fee_paid_per_unit=round(fee_paid, 6),
            )

    return TradeBacktestResult(
        triggered=True,
        outcome="OPEN",
        target_label=target_label,
        entry_index=entry_index,
        exit_index=None,
        entry_price=round(effective_entry, 6),
        exit_price=None,
        reward_r=0.0,
    )
