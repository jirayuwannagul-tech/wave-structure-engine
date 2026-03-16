from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from analysis.backtest_timeframe_context import resolve_backtest_higher_timeframe_context
from analysis.setup_filter import apply_trade_filters
from analysis.trade_backtest import (
    TradeSetup,
    _effective_entry_from_open,
    _effective_exit_price,
    _is_long,
    _net_pnl_per_unit,
    _stop_hit,
    _target_hit,
    _triggered_by_candle,
    build_trade_setup_from_scenario,
)
from core.engine import build_dataframe_analysis
from storage.experience_store import get_pattern_edge


@dataclass
class TradeLifecycleResult:
    triggered: bool
    outcome: str
    entry_index: int | None
    exit_index: int | None
    entry_time: pd.Timestamp | None
    exit_time: pd.Timestamp | None
    entry_price: float | None
    exit_price: float | None
    reward_r: float
    realized_targets: list[str]
    realized_size_pct: float
    gross_pnl_per_unit: float
    net_pnl_per_unit: float
    fee_paid_per_unit: float


@dataclass
class PortfolioTradeRecord:
    symbol: str
    timeframe: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: str
    structure: str | None
    outcome: str
    reward_r: float
    equity_before: float
    equity_after: float
    risk_amount_usdt: float
    pnl_usdt: float


@dataclass
class TradeCandidate:
    symbol: str
    timeframe: str
    structure: str | None
    side: str
    outcome: str
    reward_r: float
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp | None
    entry_price: float | None
    exit_price: float | None
    priority_score: float


@dataclass
class PortfolioBacktestSummary:
    symbol: str
    timeframe: str
    total_windows: int
    analyzed_cases: int
    setups_built: int
    triggered_trades: int
    closed_trades: int
    open_trades: int
    skipped_max_concurrent: int
    win_rate: float
    avg_r_per_trade: float
    avg_win_r: float
    avg_loss_r: float
    max_drawdown_pct: float
    max_drawdown_usdt: float
    final_equity_usdt: float
    net_profit_usdt: float


def _serialize_trade_record(record: PortfolioTradeRecord) -> dict:
    payload = asdict(record)
    payload["entry_time"] = record.entry_time.isoformat()
    payload["exit_time"] = record.exit_time.isoformat()
    return payload


@dataclass
class PortfolioCandidateSummary:
    symbol: str
    timeframe: str
    total_windows: int
    analyzed_cases: int
    setups_built: int
    triggered_candidates: int


def _candidate_key(symbol: str, timeframe: str) -> str:
    return f"{symbol.upper()}:{timeframe.upper()}"


def _candidate_priority(
    *,
    symbol: str,
    timeframe: str,
    pattern: str | None,
    side: str,
    confidence: float,
    probability: float,
) -> float:
    edge = get_pattern_edge(symbol, timeframe, pattern, side)
    edge_bonus = 0.0
    if edge is not None:
        if edge.positive:
            edge_bonus = 0.25
        elif edge.negative:
            edge_bonus = -0.15
    return round((confidence * 0.45) + (probability * 0.35) + edge_bonus, 6)


def _timestamp_at(df, idx: int | None) -> pd.Timestamp | None:
    if idx is None or "open_time" not in df.columns or idx >= len(df):
        return None
    value = df.iloc[idx]["open_time"]
    if pd.isna(value):
        return None
    return pd.Timestamp(value)


def simulate_trade_lifecycle(
    df: pd.DataFrame,
    setup: TradeSetup,
    fee_rate: float = 0.0,
    slippage_rate: float = 0.0,
    tp_allocations: tuple[float, float, float] = (0.4, 0.3, 0.3),
) -> TradeLifecycleResult:
    targets = [
        ("TP1", setup.take_profit_1, float(tp_allocations[0])),
        ("TP2", setup.take_profit_2, float(tp_allocations[1])),
        ("TP3", setup.take_profit_3, float(tp_allocations[2])),
    ]
    targets = [(label, price, size) for label, price, size in targets if price is not None and size > 0]

    if len(df) < 2 or not targets:
        return TradeLifecycleResult(
            triggered=False,
            outcome="INVALID" if not targets else "NO_TRIGGER",
            entry_index=None,
            exit_index=None,
            entry_time=None,
            exit_time=None,
            entry_price=None,
            exit_price=None,
            reward_r=0.0,
            realized_targets=[],
            realized_size_pct=0.0,
            gross_pnl_per_unit=0.0,
            net_pnl_per_unit=0.0,
            fee_paid_per_unit=0.0,
        )

    trigger_index = None
    for i in range(len(df) - 1):
        if _triggered_by_candle(df.iloc[i], setup):
            trigger_index = i
            break

    if trigger_index is None:
        return TradeLifecycleResult(
            triggered=False,
            outcome="NO_TRIGGER",
            entry_index=None,
            exit_index=None,
            entry_time=None,
            exit_time=None,
            entry_price=None,
            exit_price=None,
            reward_r=0.0,
            realized_targets=[],
            realized_size_pct=0.0,
            gross_pnl_per_unit=0.0,
            net_pnl_per_unit=0.0,
            fee_paid_per_unit=0.0,
        )

    entry_index = trigger_index + 1
    if entry_index >= len(df):
        return TradeLifecycleResult(
            triggered=False,
            outcome="NO_TRIGGER",
            entry_index=None,
            exit_index=None,
            entry_time=None,
            exit_time=None,
            entry_price=None,
            exit_price=None,
            reward_r=0.0,
            realized_targets=[],
            realized_size_pct=0.0,
            gross_pnl_per_unit=0.0,
            net_pnl_per_unit=0.0,
            fee_paid_per_unit=0.0,
        )

    entry_candle = df.iloc[entry_index]
    effective_entry = _effective_entry_from_open(float(entry_candle["open"]), setup, slippage_rate)
    effective_stop = _effective_exit_price(float(setup.stop_loss), setup, slippage_rate)
    _, stop_net_pnl_per_unit, _ = _net_pnl_per_unit(effective_entry, effective_stop, setup, fee_rate)
    risk_per_unit = abs(stop_net_pnl_per_unit)

    if risk_per_unit == 0:
        return TradeLifecycleResult(
            triggered=False,
            outcome="INVALID",
            entry_index=entry_index,
            exit_index=None,
            entry_time=_timestamp_at(df, entry_index),
            exit_time=None,
            entry_price=round(effective_entry, 6),
            exit_price=None,
            reward_r=0.0,
            realized_targets=[],
            realized_size_pct=0.0,
            gross_pnl_per_unit=0.0,
            net_pnl_per_unit=0.0,
            fee_paid_per_unit=0.0,
        )

    remaining_size = 1.0
    target_cursor = 0
    realized_targets: list[str] = []
    realized_size_pct = 0.0
    gross_total = 0.0
    net_total = 0.0
    fee_total = 0.0
    exit_index: int | None = None
    exit_price: float | None = None
    stopped_after_partial = False

    entry_open = float(entry_candle["open"])
    stop_gap_hit = (_is_long(setup) and entry_open <= float(setup.stop_loss)) or (
        (not _is_long(setup)) and entry_open >= float(setup.stop_loss)
    )
    if stop_gap_hit:
        immediate_exit = _effective_exit_price(entry_open, setup, slippage_rate)
        gross_pnl, net_pnl, fee_paid = _net_pnl_per_unit(effective_entry, immediate_exit, setup, fee_rate)
        reward_r = max(net_pnl / risk_per_unit, -3.0)  # max loss cap
        return TradeLifecycleResult(
            triggered=True,
            outcome="STOP_LOSS",
            entry_index=entry_index,
            exit_index=entry_index,
            entry_time=_timestamp_at(df, entry_index),
            exit_time=_timestamp_at(df, entry_index),
            entry_price=round(effective_entry, 6),
            exit_price=round(immediate_exit, 6),
            reward_r=round(reward_r, 3),
            realized_targets=[],
            realized_size_pct=0.0,
            gross_pnl_per_unit=round(gross_pnl, 6),
            net_pnl_per_unit=round(net_pnl, 6),
            fee_paid_per_unit=round(fee_paid, 6),
        )

    for i in range(entry_index, len(df)):
        candle = df.iloc[i]
        stop_hit = _stop_hit(candle, setup)
        next_label = None
        next_target_price = None
        if target_cursor < len(targets):
            next_label, next_target_price, _ = targets[target_cursor]
        target_hit = next_target_price is not None and _target_hit(candle, float(next_target_price), setup)

        if stop_hit and target_hit:
            stop_exit = _effective_exit_price(float(setup.stop_loss), setup, slippage_rate)
            gross_pnl, net_pnl, fee_paid = _net_pnl_per_unit(effective_entry, stop_exit, setup, fee_rate)
            gross_total += gross_pnl * remaining_size
            net_total += net_pnl * remaining_size
            fee_total += fee_paid * remaining_size
            exit_index = i
            exit_price = stop_exit
            stopped_after_partial = bool(realized_targets)
            remaining_size = 0.0
            break

        if stop_hit:
            stop_exit = _effective_exit_price(float(setup.stop_loss), setup, slippage_rate)
            gross_pnl, net_pnl, fee_paid = _net_pnl_per_unit(effective_entry, stop_exit, setup, fee_rate)
            gross_total += gross_pnl * remaining_size
            net_total += net_pnl * remaining_size
            fee_total += fee_paid * remaining_size
            exit_index = i
            exit_price = stop_exit
            stopped_after_partial = bool(realized_targets)
            remaining_size = 0.0
            break

        while target_cursor < len(targets):
            label, target_price, size_pct = targets[target_cursor]
            if not _target_hit(candle, float(target_price), setup):
                break

            effective_target = _effective_exit_price(float(target_price), setup, slippage_rate)
            gross_pnl, net_pnl, fee_paid = _net_pnl_per_unit(effective_entry, effective_target, setup, fee_rate)
            fill_size = min(remaining_size, size_pct)
            gross_total += gross_pnl * fill_size
            net_total += net_pnl * fill_size
            fee_total += fee_paid * fill_size
            realized_targets.append(label)
            realized_size_pct += fill_size
            remaining_size -= fill_size
            exit_index = i
            exit_price = effective_target
            target_cursor += 1
            if remaining_size <= 1e-9:
                remaining_size = 0.0
                break

        if remaining_size <= 0:
            break

    if exit_index is None:
        return TradeLifecycleResult(
            triggered=True,
            outcome="OPEN",
            entry_index=entry_index,
            exit_index=None,
            entry_time=_timestamp_at(df, entry_index),
            exit_time=None,
            entry_price=round(effective_entry, 6),
            exit_price=None,
            reward_r=round(net_total / risk_per_unit, 3),
            realized_targets=realized_targets,
            realized_size_pct=round(realized_size_pct, 6),
            gross_pnl_per_unit=round(gross_total, 6),
            net_pnl_per_unit=round(net_total, 6),
            fee_paid_per_unit=round(fee_total, 6),
        )

    if stopped_after_partial:
        outcome = "PARTIAL_STOPPED"
    elif remaining_size <= 0 and realized_targets:
        outcome = "TP3_HIT" if "TP3" in realized_targets else realized_targets[-1]
    elif realized_targets:
        outcome = "PARTIAL_STOPPED"
    else:
        outcome = "STOP_LOSS"

    # Override outcome if net PnL is negative despite hitting all targets
    # (fees/slippage can erode profits to negative even when all targets hit)
    if net_total <= 0 and outcome in ("TP3_HIT", "TP2_HIT", "TP1_HIT"):
        outcome = "STOP_LOSS"

    raw_r = net_total / risk_per_unit
    capped_r = max(raw_r, -3.0)  # max loss cap: never lose more than 3R per trade
    return TradeLifecycleResult(
        triggered=True,
        outcome=outcome,
        entry_index=entry_index,
        exit_index=exit_index,
        entry_time=_timestamp_at(df, entry_index),
        exit_time=_timestamp_at(df, exit_index),
        entry_price=round(effective_entry, 6),
        exit_price=round(exit_price, 6) if exit_price is not None else None,
        reward_r=round(capped_r, 3),
        realized_targets=realized_targets,
        realized_size_pct=round(realized_size_pct, 6),
        gross_pnl_per_unit=round(gross_total, 6),
        net_pnl_per_unit=round(net_total, 6),
        fee_paid_per_unit=round(fee_total, 6),
    )


def _summarize_portfolio_records(
    *,
    symbol: str,
    timeframe: str,
    total_windows: int,
    analyzed_cases: int,
    setups_built: int,
    skipped_max_concurrent: int,
    initial_capital: float,
    records: list[PortfolioTradeRecord],
) -> PortfolioBacktestSummary:
    closed = [record for record in records if record.outcome != "OPEN"]
    open_count = sum(1 for record in records if record.outcome == "OPEN")
    wins = [record for record in closed if record.reward_r > 0]
    losses = [record for record in closed if record.reward_r <= 0]
    win_rate = len(wins) / len(closed) if closed else 0.0
    avg_r_per_trade = sum(record.reward_r for record in closed) / len(closed) if closed else 0.0
    avg_win_r = sum(record.reward_r for record in wins) / len(wins) if wins else 0.0
    avg_loss_r = sum(record.reward_r for record in losses) / len(losses) if losses else 0.0

    peak = initial_capital
    max_drawdown_usdt = 0.0
    max_drawdown_pct = 0.0
    for record in records:
        peak = max(peak, record.equity_before, record.equity_after)
        drawdown_usdt = peak - record.equity_after
        if drawdown_usdt > max_drawdown_usdt:
            max_drawdown_usdt = drawdown_usdt
            max_drawdown_pct = drawdown_usdt / peak if peak else 0.0

    final_equity = records[-1].equity_after if records else initial_capital
    net_profit = final_equity - initial_capital

    return PortfolioBacktestSummary(
        symbol=symbol,
        timeframe=timeframe,
        total_windows=total_windows,
        analyzed_cases=analyzed_cases,
        setups_built=setups_built,
        triggered_trades=len(records),
        closed_trades=len(closed),
        open_trades=open_count,
        skipped_max_concurrent=skipped_max_concurrent,
        win_rate=round(win_rate, 3),
        avg_r_per_trade=round(avg_r_per_trade, 3),
        avg_win_r=round(avg_win_r, 3),
        avg_loss_r=round(avg_loss_r, 3),
        max_drawdown_pct=round(max_drawdown_pct, 3),
        max_drawdown_usdt=round(max_drawdown_usdt, 3),
        final_equity_usdt=round(final_equity, 3),
        net_profit_usdt=round(net_profit, 3),
    )


def run_portfolio_backtest(
    *,
    csv_path: str,
    symbol: str,
    timeframe: str,
    min_window: int,
    step: int = 1,
    fee_rate: float = 0.0,
    slippage_rate: float = 0.0,
    initial_capital: float = 1000.0,
    risk_per_trade: float = 0.01,
    max_concurrent: int = 1,
    tp_allocations: tuple[float, float, float] = (0.4, 0.3, 0.3),
    higher_timeframe_csv_path: str | None = None,
    higher_timeframe_min_window: int | None = None,
    parent_timeframe_csv_path: str | None = None,
    parent_timeframe_min_window: int | None = None,
) -> dict:
    from analysis.indicator_engine import calculate_atr as _calc_atr

    df = pd.read_csv(csv_path).copy()
    if "open_time" in df.columns:
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True, errors="coerce")
    if "atr" not in df.columns:
        df["atr"] = _calc_atr(df, period=14)

    higher_timeframe_df = None
    if higher_timeframe_csv_path:
        higher_timeframe_df = pd.read_csv(higher_timeframe_csv_path).copy()
        if "open_time" in higher_timeframe_df.columns:
            higher_timeframe_df["open_time"] = pd.to_datetime(
                higher_timeframe_df["open_time"],
                utc=True,
                errors="coerce",
            )
        if "atr" not in higher_timeframe_df.columns:
            higher_timeframe_df["atr"] = _calc_atr(higher_timeframe_df, period=14)

    parent_timeframe_df = None
    if parent_timeframe_csv_path:
        parent_timeframe_df = pd.read_csv(parent_timeframe_csv_path).copy()
        if "open_time" in parent_timeframe_df.columns:
            parent_timeframe_df["open_time"] = pd.to_datetime(
                parent_timeframe_df["open_time"],
                utc=True,
                errors="coerce",
            )
        if "atr" not in parent_timeframe_df.columns:
            parent_timeframe_df["atr"] = _calc_atr(parent_timeframe_df, period=14)

    total_windows = 0
    analyzed_cases = 0
    setups_built = 0
    skipped_max_concurrent = 0
    equity = float(initial_capital)
    records: list[PortfolioTradeRecord] = []
    open_positions: list[pd.Timestamp] = []

    for end_idx in range(min_window, len(df) - 1, step):
        total_windows += 1
        sample_df = df.iloc[:end_idx].copy()
        future_df = df.iloc[end_idx:].copy()

        analysis = build_dataframe_analysis(
            symbol=symbol,
            timeframe=timeframe,
            df=sample_df,
            current_price=float(sample_df.iloc[-1]["close"]),
        )
        higher_timeframe_bias, higher_timeframe_context, allow_analysis = (
            resolve_backtest_higher_timeframe_context(
                symbol=symbol,
                timeframe=timeframe,
                sample_df=sample_df,
                higher_timeframe_df=higher_timeframe_df,
                higher_timeframe_min_window=higher_timeframe_min_window,
                parent_timeframe_df=parent_timeframe_df,
                parent_timeframe_min_window=parent_timeframe_min_window,
            )
        )
        if not allow_analysis:
            continue

        htf_wave_number = str((higher_timeframe_context or {}).get("wave_number") or "").upper() or None
        analysis = apply_trade_filters(
            analysis,
            higher_timeframe_bias=higher_timeframe_bias,
            htf_wave_number=htf_wave_number,
            higher_timeframe_context=higher_timeframe_context,
        )

        # ── Hierarchical wave count injection (1D only) ────────────────────
        # When the pattern detector finds nothing OR filters all scenarios,
        # try the hierarchical counter (Primary 1W + Intermediate 1D).
        # This enables entries at every wave: 1,2,3,4,5,A,B,C — not just
        # at pattern completion points detected by the single-TF detector.
        if (
            higher_timeframe_df is not None
            and higher_timeframe_min_window is not None
            and timeframe.upper() == "1D"
        ):
            cutoff_time = (
                sample_df.iloc[-1]["open_time"]
                if "open_time" in sample_df.columns
                else None
            )
            if cutoff_time is not None and not (analysis.get("scenarios") or []):
                weekly_sample = higher_timeframe_df[
                    higher_timeframe_df["open_time"] <= cutoff_time
                ].copy()
                if len(weekly_sample) >= 20:
                    from analysis.hierarchical_wave_counter import (
                        build_hierarchical_count_from_dfs,
                    )
                    hier_count = build_hierarchical_count_from_dfs(
                        symbol=symbol,
                        primary_df=weekly_sample,
                        intermediate_df=sample_df,
                        current_price=float(sample_df.iloc[-1]["close"]),
                    )
                    htf_aligned = (
                        higher_timeframe_bias is None
                        or hier_count.trade_bias == higher_timeframe_bias
                    )
                    if (
                        htf_aligned
                        and hier_count.scenarios
                        and hier_count.hierarchical_confidence >= 0.30
                        and hier_count.is_consistent
                    ):
                        active_pos = hier_count.intermediate or hier_count.primary
                        wave_label = (
                            f"{active_pos.structure}_W{active_pos.wave_number}"
                            if active_pos
                            else "HIERARCHICAL"
                        )
                        analysis = dict(analysis)
                        analysis["scenarios"] = hier_count.scenarios
                        analysis["has_pattern"] = True
                        analysis["primary_pattern_type"] = wave_label
                        analysis["hierarchical_count"] = hier_count
                        # Re-run quality filter so hierarchical scenarios obey the same rules
                        analysis = apply_trade_filters(
                            analysis,
                            higher_timeframe_bias=higher_timeframe_bias,
                            htf_wave_number=htf_wave_number,
                            higher_timeframe_context=higher_timeframe_context,
                        )

        if not analysis.get("has_pattern"):
            continue

        analyzed_cases += 1
        scenarios = analysis.get("scenarios") or []
        if not scenarios:
            continue

        main_scenario = scenarios[0]
        setup = build_trade_setup_from_scenario(main_scenario)
        if setup is None:
            continue

        setups_built += 1
        priority_score = _candidate_priority(
            symbol=symbol,
            timeframe=timeframe,
            pattern=analysis.get("primary_pattern_type"),
            side=setup.side,
            confidence=float(analysis.get("confidence") or 0.0),
            probability=float(analysis.get("probability") or 0.0),
        )
        lifecycle = simulate_trade_lifecycle(
            future_df,
            setup,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            tp_allocations=tp_allocations,
        )
        if not lifecycle.triggered or lifecycle.entry_time is None:
            continue

        open_positions = [exit_time for exit_time in open_positions if exit_time > lifecycle.entry_time]
        if len(open_positions) >= max_concurrent:
            skipped_max_concurrent += 1
            continue

        risk_amount = equity * float(risk_per_trade)
        pnl = risk_amount * float(lifecycle.reward_r)
        equity_before = equity
        equity_after = equity + pnl if lifecycle.exit_time is not None else equity

        open_positions.append(lifecycle.exit_time or pd.Timestamp.max.tz_localize("UTC"))

        records.append(
            PortfolioTradeRecord(
                symbol=symbol,
                timeframe=timeframe.upper(),
                entry_time=lifecycle.entry_time,
                exit_time=lifecycle.exit_time or lifecycle.entry_time,
                side=setup.side,
                structure=analysis.get("primary_pattern_type"),
                outcome=lifecycle.outcome,
                reward_r=float(lifecycle.reward_r),
                equity_before=round(equity_before, 6),
                equity_after=round(equity_after, 6),
                risk_amount_usdt=round(risk_amount, 6),
                pnl_usdt=round(pnl if lifecycle.exit_time is not None else 0.0, 6),
            )
        )
        if lifecycle.exit_time is not None:
            equity = equity_after

    summary = _summarize_portfolio_records(
        symbol=symbol,
        timeframe=timeframe.upper(),
        total_windows=total_windows,
        analyzed_cases=analyzed_cases,
        setups_built=setups_built,
        skipped_max_concurrent=skipped_max_concurrent,
        initial_capital=initial_capital,
        records=records,
    )

    return {
        "summary": asdict(summary),
        "trades": [asdict(record) for record in records],
    }


def build_trade_candidates(
    *,
    csv_path: str,
    symbol: str,
    timeframe: str,
    min_window: int,
    step: int = 1,
    fee_rate: float = 0.0,
    slippage_rate: float = 0.0,
    tp_allocations: tuple[float, float, float] = (0.4, 0.3, 0.3),
    higher_timeframe_csv_path: str | None = None,
    higher_timeframe_min_window: int | None = None,
    parent_timeframe_csv_path: str | None = None,
    parent_timeframe_min_window: int | None = None,
    minor_timeframe_csv_path: str | None = None,
    minor_timeframe_min_window: int | None = None,
    sub_minor_csv_path: str | None = None,
    sub_minor_min_window: int | None = None,
) -> dict:
    from analysis.indicator_engine import calculate_atr as _calc_atr

    def _load_tf_df(path: str) -> pd.DataFrame:
        d = pd.read_csv(path).copy()
        if "open_time" in d.columns:
            d["open_time"] = pd.to_datetime(d["open_time"], utc=True, errors="coerce")
        if "atr" not in d.columns:
            d["atr"] = _calc_atr(d, period=14)
        return d

    df = pd.read_csv(csv_path).copy()
    if "open_time" in df.columns:
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True, errors="coerce")
    if "atr" not in df.columns:
        df["atr"] = _calc_atr(df, period=14)

    higher_timeframe_df = _load_tf_df(higher_timeframe_csv_path) if higher_timeframe_csv_path else None
    parent_timeframe_df = _load_tf_df(parent_timeframe_csv_path) if parent_timeframe_csv_path else None
    minor_timeframe_df = _load_tf_df(minor_timeframe_csv_path) if minor_timeframe_csv_path else None
    sub_minor_df = _load_tf_df(sub_minor_csv_path) if sub_minor_csv_path else None

    total_windows = 0
    analyzed_cases = 0
    setups_built = 0
    candidates: list[TradeCandidate] = []
    # Deduplication: track the last wave fingerprint entered per (symbol, timeframe).
    # Prevents re-entering the same wave instance on consecutive bars.
    hier_wave_seen: dict[str, str] = {}

    for end_idx in range(min_window, len(df) - 1, step):
        total_windows += 1
        sample_df = df.iloc[:end_idx].copy()
        future_df = df.iloc[end_idx:].copy()

        analysis = build_dataframe_analysis(
            symbol=symbol,
            timeframe=timeframe,
            df=sample_df,
            current_price=float(sample_df.iloc[-1]["close"]),
        )
        higher_timeframe_bias, higher_timeframe_context, allow_analysis = (
            resolve_backtest_higher_timeframe_context(
                symbol=symbol,
                timeframe=timeframe,
                sample_df=sample_df,
                higher_timeframe_df=higher_timeframe_df,
                higher_timeframe_min_window=higher_timeframe_min_window,
                parent_timeframe_df=parent_timeframe_df,
                parent_timeframe_min_window=parent_timeframe_min_window,
            )
        )
        if not allow_analysis:
            continue

        htf_wave_number = str((higher_timeframe_context or {}).get("wave_number") or "").upper() or None
        analysis = apply_trade_filters(
            analysis,
            higher_timeframe_bias=higher_timeframe_bias,
            htf_wave_number=htf_wave_number,
            higher_timeframe_context=higher_timeframe_context,
        )

        # ── Hierarchical wave count injection (1D only) ────────────────────
        if (
            higher_timeframe_df is not None
            and higher_timeframe_min_window is not None
            and timeframe.upper() == "1D"
        ):
            cutoff_time = (
                sample_df.iloc[-1]["open_time"]
                if "open_time" in sample_df.columns
                else None
            )
            if cutoff_time is not None and not (analysis.get("scenarios") or []):
                weekly_sample = higher_timeframe_df[
                    higher_timeframe_df["open_time"] <= cutoff_time
                ].copy()
                if len(weekly_sample) >= 20:
                    from analysis.hierarchical_wave_counter import (
                        build_hierarchical_count_from_dfs,
                    )
                    # Slice minor (4H) and sub_minor (1H) up to cutoff.
                    # Limit to last N bars — pivot detection only needs recent history.
                    _MINOR_MAX_BARS = 300     # ~75 days of 4H
                    _SUB_MINOR_MAX_BARS = 500  # ~3 weeks of 1H
                    minor_sample = None
                    if (
                        minor_timeframe_df is not None
                        and minor_timeframe_min_window is not None
                    ):
                        _ms = minor_timeframe_df[
                            minor_timeframe_df["open_time"] <= cutoff_time
                        ]
                        if len(_ms) >= minor_timeframe_min_window:
                            minor_sample = _ms.iloc[-_MINOR_MAX_BARS:].copy()

                    sub_minor_sample = None
                    if (
                        sub_minor_df is not None
                        and sub_minor_min_window is not None
                        and minor_sample is not None
                    ):
                        _ss = sub_minor_df[
                            sub_minor_df["open_time"] <= cutoff_time
                        ]
                        if len(_ss) >= sub_minor_min_window:
                            sub_minor_sample = _ss.iloc[-_SUB_MINOR_MAX_BARS:].copy()

                    hier_count = build_hierarchical_count_from_dfs(
                        symbol=symbol,
                        primary_df=weekly_sample,
                        intermediate_df=sample_df,
                        minor_df=minor_sample,
                        sub_minor_df=sub_minor_sample,
                        current_price=float(sample_df.iloc[-1]["close"]),
                    )
                    htf_aligned = (
                        higher_timeframe_bias is None
                        or hier_count.trade_bias == higher_timeframe_bias
                    )
                    # Deduplicate: skip if this exact wave instance was already entered
                    dedup_key = f"{symbol}:{timeframe.upper()}"
                    already_entered = (
                        hier_wave_seen.get(dedup_key) == hier_count.wave_fingerprint
                        and bool(hier_count.wave_fingerprint)
                    )
                    if (
                        htf_aligned
                        and hier_count.scenarios
                        and hier_count.hierarchical_confidence >= 0.30
                        and hier_count.is_consistent
                        and not already_entered
                    ):
                        active_pos = hier_count.intermediate or hier_count.primary
                        wave_label = (
                            f"{active_pos.structure}_W{active_pos.wave_number}"
                            if active_pos
                            else "HIERARCHICAL"
                        )
                        analysis = dict(analysis)
                        analysis["scenarios"] = hier_count.scenarios
                        analysis["has_pattern"] = True
                        analysis["primary_pattern_type"] = wave_label
                        analysis["hierarchical_count"] = hier_count
                        analysis["_hier_fingerprint"] = hier_count.wave_fingerprint
                        analysis["_hier_dedup_key"] = dedup_key
                        # Re-run quality filter so hierarchical scenarios obey the same rules
                        analysis = apply_trade_filters(
                            analysis,
                            higher_timeframe_bias=higher_timeframe_bias,
                            htf_wave_number=htf_wave_number,
                            higher_timeframe_context=higher_timeframe_context,
                        )

        if not analysis.get("has_pattern"):
            continue

        analyzed_cases += 1
        scenarios = analysis.get("scenarios") or []
        if not scenarios:
            continue

        main_scenario = scenarios[0]
        setup = build_trade_setup_from_scenario(main_scenario)
        if setup is None:
            continue

        setups_built += 1

        # Record the wave fingerprint so we don't re-enter the same wave
        hier_fp = analysis.get("_hier_fingerprint")
        hier_dk = analysis.get("_hier_dedup_key")
        if hier_fp and hier_dk:
            hier_wave_seen[hier_dk] = hier_fp

        priority_score = _candidate_priority(
            symbol=symbol,
            timeframe=timeframe,
            pattern=analysis.get("primary_pattern_type"),
            side=setup.side,
            confidence=float(analysis.get("confidence") or 0.0),
            probability=float(analysis.get("probability") or 0.0),
        )
        lifecycle = simulate_trade_lifecycle(
            future_df,
            setup,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            tp_allocations=tp_allocations,
        )
        if not lifecycle.triggered or lifecycle.entry_time is None:
            continue

        candidates.append(
            TradeCandidate(
                symbol=symbol.upper(),
                timeframe=timeframe.upper(),
                structure=analysis.get("primary_pattern_type"),
                side=setup.side,
                outcome=lifecycle.outcome,
                reward_r=float(lifecycle.reward_r),
                entry_time=lifecycle.entry_time,
                exit_time=lifecycle.exit_time,
                entry_price=lifecycle.entry_price,
                exit_price=lifecycle.exit_price,
                priority_score=priority_score,
            )
        )

    summary = PortfolioCandidateSummary(
        symbol=symbol.upper(),
        timeframe=timeframe.upper(),
        total_windows=total_windows,
        analyzed_cases=analyzed_cases,
        setups_built=setups_built,
        triggered_candidates=len(candidates),
    )
    return {
        "summary": asdict(summary),
        "candidates": [asdict(candidate) for candidate in candidates],
    }


def run_global_portfolio_backtest(
    *,
    datasets: list[dict],
    fee_rate: float = 0.0,
    slippage_rate: float = 0.0,
    initial_capital: float = 1000.0,
    risk_per_trade: float = 0.01,
    max_concurrent: int = 1,
    tp_allocations: tuple[float, float, float] = (0.4, 0.3, 0.3),
) -> dict:
    candidate_summaries: dict[str, dict] = {}
    candidates: list[TradeCandidate] = []

    for item in datasets:
        result = build_trade_candidates(
            csv_path=item["csv_path"],
            symbol=item["symbol"],
            timeframe=item["timeframe"],
            min_window=item["min_window"],
            step=item.get("step", 1),
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            tp_allocations=tp_allocations,
            higher_timeframe_csv_path=item.get("higher_timeframe_csv_path"),
            higher_timeframe_min_window=item.get("higher_timeframe_min_window"),
            parent_timeframe_csv_path=item.get("parent_timeframe_csv_path"),
            parent_timeframe_min_window=item.get("parent_timeframe_min_window"),
            minor_timeframe_csv_path=item.get("minor_timeframe_csv_path"),
            minor_timeframe_min_window=item.get("minor_timeframe_min_window"),
            sub_minor_csv_path=item.get("sub_minor_csv_path"),
            sub_minor_min_window=item.get("sub_minor_min_window"),
        )
        key = _candidate_key(item["symbol"], item["timeframe"])
        candidate_summaries[key] = result["summary"]
        candidates.extend(
            TradeCandidate(**candidate_dict)
            for candidate_dict in result["candidates"]
        )

    candidates.sort(key=lambda item: (item.entry_time, -item.priority_score, item.symbol, item.timeframe))

    # Deduplicate: for same (symbol, timeframe, entry_time), keep highest priority_score only
    seen_keys: set[tuple] = set()
    deduped: list[TradeCandidate] = []
    for c in candidates:
        key = (c.symbol, c.timeframe, c.entry_time)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(c)
    candidates = deduped

    equity = float(initial_capital)
    open_positions: list[dict] = []
    records: list[PortfolioTradeRecord] = []
    skipped_max_concurrent = 0

    def settle_until(cutoff: pd.Timestamp | None) -> None:
        nonlocal equity
        closable = [
            trade for trade in open_positions
            if trade["exit_time"] is not None and (cutoff is None or trade["exit_time"] <= cutoff)
        ]
        closable.sort(key=lambda trade: trade["exit_time"])
        for trade in closable:
            if trade not in open_positions:
                continue
            equity_before = equity
            pnl = trade["risk_amount_usdt"] * trade["reward_r"]
            equity_after = equity + pnl
            records.append(
                PortfolioTradeRecord(
                    symbol=trade["symbol"],
                    timeframe=trade["timeframe"],
                    entry_time=trade["entry_time"],
                    exit_time=trade["exit_time"],
                    side=trade["side"],
                    structure=trade["structure"],
                    outcome=trade["outcome"],
                    reward_r=trade["reward_r"],
                    equity_before=round(equity_before, 6),
                    equity_after=round(equity_after, 6),
                    risk_amount_usdt=round(trade["risk_amount_usdt"], 6),
                    pnl_usdt=round(pnl, 6),
                )
            )
            equity = equity_after
            open_positions.remove(trade)

    for candidate in candidates:
        settle_until(candidate.entry_time)
        if len(open_positions) >= max_concurrent:
            skipped_max_concurrent += 1
            continue

        # Skip if we already have an open position in the same symbol+timeframe
        already_open = any(
            trade["symbol"] == candidate.symbol and trade["timeframe"] == candidate.timeframe
            for trade in open_positions
        )
        if already_open:
            skipped_max_concurrent += 1
            continue

        open_positions.append(
            {
                "symbol": candidate.symbol,
                "timeframe": candidate.timeframe,
                "entry_time": candidate.entry_time,
                "exit_time": candidate.exit_time,
                "side": candidate.side,
                "structure": candidate.structure,
                "outcome": candidate.outcome,
                "reward_r": candidate.reward_r,
                "risk_amount_usdt": equity * float(risk_per_trade),
            }
        )

    settle_until(None)

    unresolved = [trade for trade in open_positions if trade["exit_time"] is None]
    for trade in unresolved:
        records.append(
            PortfolioTradeRecord(
                symbol=trade["symbol"],
                timeframe=trade["timeframe"],
                entry_time=trade["entry_time"],
                exit_time=trade["entry_time"],
                side=trade["side"],
                structure=trade["structure"],
                outcome="OPEN",
                reward_r=trade["reward_r"],
                equity_before=round(equity, 6),
                equity_after=round(equity, 6),
                risk_amount_usdt=round(trade["risk_amount_usdt"], 6),
                pnl_usdt=0.0,
            )
        )

    records.sort(key=lambda item: (item.exit_time, item.entry_time, item.symbol, item.timeframe))

    def summarize_subset(subset: list[PortfolioTradeRecord], label_symbol: str, label_timeframe: str) -> dict:
        closed = [record for record in subset if record.outcome != "OPEN"]
        open_count = sum(1 for record in subset if record.outcome == "OPEN")
        wins = [record for record in closed if record.reward_r > 0]
        losses = [record for record in closed if record.reward_r <= 0]
        win_rate = len(wins) / len(closed) if closed else 0.0
        avg_r_per_trade = sum(record.reward_r for record in closed) / len(closed) if closed else 0.0
        avg_win_r = sum(record.reward_r for record in wins) / len(wins) if wins else 0.0
        avg_loss_r = sum(record.reward_r for record in losses) / len(losses) if losses else 0.0

        running_equity = initial_capital
        peak = initial_capital
        max_dd_usdt = 0.0
        max_dd_pct = 0.0
        for record in subset:
            if record.outcome != "OPEN":
                running_equity += record.pnl_usdt
            peak = max(peak, running_equity)
            dd = peak - running_equity
            if dd > max_dd_usdt:
                max_dd_usdt = dd
                max_dd_pct = dd / peak if peak else 0.0

        final_equity = initial_capital + sum(record.pnl_usdt for record in subset if record.outcome != "OPEN")
        return asdict(
            PortfolioBacktestSummary(
                symbol=label_symbol,
                timeframe=label_timeframe,
                total_windows=sum(summary["total_windows"] for summary in candidate_summaries.values()),
                analyzed_cases=sum(summary["analyzed_cases"] for summary in candidate_summaries.values()),
                setups_built=sum(summary["setups_built"] for summary in candidate_summaries.values()),
                triggered_trades=len(subset),
                closed_trades=len(closed),
                open_trades=open_count,
                skipped_max_concurrent=skipped_max_concurrent,
                win_rate=round(win_rate, 3),
                avg_r_per_trade=round(avg_r_per_trade, 3),
                avg_win_r=round(avg_win_r, 3),
                avg_loss_r=round(avg_loss_r, 3),
                max_drawdown_pct=round(max_dd_pct, 3),
                max_drawdown_usdt=round(max_dd_usdt, 3),
                final_equity_usdt=round(final_equity, 3),
                net_profit_usdt=round(final_equity - initial_capital, 3),
            )
        )

    by_symbol: dict[str, dict] = {}
    for symbol in sorted({record.symbol for record in records}):
        subset = [record for record in records if record.symbol == symbol]
        by_symbol[symbol] = summarize_subset(subset, symbol, "ALL")

    by_timeframe: dict[str, dict] = {}
    for timeframe in sorted({record.timeframe for record in records}):
        subset = [record for record in records if record.timeframe == timeframe]
        by_timeframe[timeframe] = summarize_subset(subset, "ALL", timeframe)

    by_symbol_timeframe: dict[str, dict] = {}
    for key in sorted(candidate_summaries):
        symbol, timeframe = key.split(":")
        subset = [record for record in records if record.symbol == symbol and record.timeframe == timeframe]
        summary = summarize_subset(subset, symbol, timeframe)
        summary["candidate_total_windows"] = candidate_summaries[key]["total_windows"]
        summary["candidate_analyzed_cases"] = candidate_summaries[key]["analyzed_cases"]
        summary["candidate_setups_built"] = candidate_summaries[key]["setups_built"]
        summary["candidate_triggered_trades"] = candidate_summaries[key]["triggered_candidates"]
        by_symbol_timeframe[key] = summary

    overall = summarize_subset(records, "ALL", "ALL")
    return {
        "overall": overall,
        "by_symbol": by_symbol,
        "by_timeframe": by_timeframe,
        "by_symbol_timeframe": by_symbol_timeframe,
        "trades": [_serialize_trade_record(record) for record in records],
    }
