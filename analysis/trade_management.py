from __future__ import annotations

from dataclasses import dataclass


TIME_STOP_BARS = {
    "4H": 6,
    "1D": 4,
}
MAX_ENTRY_STRETCH_R = 0.35
FAKEOUT_WICK_RATIO = 0.45
FAKEOUT_BODY_RATIO = 0.35
VOLATILITY_SPIKE_ATR_MULTIPLIER = 2.2


@dataclass
class EntryGuardDecision:
    allow_entry: bool
    reason: str | None = None


@dataclass(frozen=True)
class LiveEntryDecision:
    actionable: bool
    reason: str | None = None
    crossed: bool = False
    stretch_r: float = 0.0
    entry_style: str = "market"


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _range_components(candle) -> tuple[float, float, float, float]:
    open_price = float(candle["open"])
    close_price = float(candle["close"])
    high_price = float(candle["high"])
    low_price = float(candle["low"])
    total_range = max(high_price - low_price, 0.0)
    body = abs(close_price - open_price)
    upper_wick = max(high_price - max(open_price, close_price), 0.0)
    lower_wick = max(min(open_price, close_price) - low_price, 0.0)
    return total_range, body, upper_wick, lower_wick


def entry_stretch_r(side: str, planned_entry: float, actual_entry: float, stop_loss: float) -> float:
    risk = abs(float(planned_entry) - float(stop_loss))
    if risk <= 0:
        return 0.0
    if (side or "").upper() == "LONG":
        return max(0.0, float(actual_entry) - float(planned_entry)) / risk
    return max(0.0, float(planned_entry) - float(actual_entry)) / risk


def is_overextended_entry(
    side: str,
    planned_entry: float,
    actual_entry: float,
    stop_loss: float,
    *,
    max_stretch_r: float = MAX_ENTRY_STRETCH_R,
) -> bool:
    return entry_stretch_r(side, planned_entry, actual_entry, stop_loss) > max_stretch_r


def normalize_entry_style(entry_style: str | None) -> str:
    raw = str(entry_style or "market").strip().lower()
    if raw in {"signal", "signal_price", "entry", "limit", "planned", "plan"}:
        return "signal_price"
    return "market"


def _entry_crossed(side: str, current_price: float, planned_entry: float) -> bool:
    if (side or "").upper() == "LONG":
        return float(current_price) >= float(planned_entry)
    return float(current_price) <= float(planned_entry)


def _stop_crossed(side: str, current_price: float, stop_loss: float) -> bool:
    if (side or "").upper() == "LONG":
        return float(current_price) <= float(stop_loss)
    return float(current_price) >= float(stop_loss)


def _invalidation_crossed(side: str, current_price: float, invalidation_price: float) -> bool:
    if (side or "").upper() == "LONG":
        return float(current_price) < float(invalidation_price)
    return float(current_price) > float(invalidation_price)


def evaluate_live_entry_actionability(
    *,
    side: str,
    planned_entry: float | None,
    stop_loss: float | None,
    current_price: float | None,
    entry_style: str | None = "market",
    invalidation_price: float | None = None,
    max_stretch_r: float = MAX_ENTRY_STRETCH_R,
) -> LiveEntryDecision:
    planned = _safe_float(planned_entry)
    stop = _safe_float(stop_loss)
    current = _safe_float(current_price)
    invalidation = _safe_float(invalidation_price)
    style = normalize_entry_style(entry_style)
    normalized_side = (side or "").upper()

    if normalized_side not in {"LONG", "SHORT"}:
        return LiveEntryDecision(False, reason="invalid_side", entry_style=style)
    if planned is None or stop is None or current is None:
        return LiveEntryDecision(False, reason="missing_live_entry_fields", entry_style=style)

    if invalidation is not None and _invalidation_crossed(normalized_side, current, invalidation):
        return LiveEntryDecision(False, reason="invalidation_crossed", entry_style=style)
    if _stop_crossed(normalized_side, current, stop):
        return LiveEntryDecision(False, reason="stop_crossed", entry_style=style)

    crossed = _entry_crossed(normalized_side, current, planned)
    stretch = entry_stretch_r(normalized_side, planned, current, stop)

    if style == "signal_price":
        if crossed:
            return LiveEntryDecision(
                False,
                reason="already_crossed_for_signal_price",
                crossed=True,
                stretch_r=stretch,
                entry_style=style,
            )
        return LiveEntryDecision(
            True,
            reason="waiting_confirmation",
            crossed=False,
            stretch_r=stretch,
            entry_style=style,
        )

    if not crossed:
        return LiveEntryDecision(
            False,
            reason="not_confirmed",
            crossed=False,
            stretch_r=stretch,
            entry_style=style,
        )

    if is_overextended_entry(
        normalized_side,
        planned,
        current,
        stop,
        max_stretch_r=max_stretch_r,
    ):
        return LiveEntryDecision(
            False,
            reason="overextended_entry",
            crossed=True,
            stretch_r=stretch,
            entry_style=style,
        )

    return LiveEntryDecision(
        True,
        reason="confirmed",
        crossed=True,
        stretch_r=stretch,
        entry_style=style,
    )


def trigger_candle_looks_fake(candle, side: str) -> bool:
    total_range, body, upper_wick, lower_wick = _range_components(candle)
    if total_range <= 0:
        return False

    body_ratio = body / total_range
    upper_ratio = upper_wick / total_range
    lower_ratio = lower_wick / total_range
    normalized_side = (side or "").upper()

    if normalized_side == "LONG":
        return upper_ratio >= FAKEOUT_WICK_RATIO and body_ratio <= FAKEOUT_BODY_RATIO
    if normalized_side == "SHORT":
        return lower_ratio >= FAKEOUT_WICK_RATIO and body_ratio <= FAKEOUT_BODY_RATIO
    return False


def managed_stop_after_target(
    *,
    side: str,
    current_stop: float,
    entry_price: float,
    tp1: float | None = None,
    target_label: str,
) -> float:
    normalized_side = (side or "").upper()
    label = (target_label or "").upper()

    if normalized_side == "LONG":
        if label == "TP1":
            return max(float(current_stop), float(entry_price))
        if label == "TP2" and tp1 is not None:
            return max(float(current_stop), float(tp1))
    elif normalized_side == "SHORT":
        if label == "TP1":
            return min(float(current_stop), float(entry_price))
        if label == "TP2" and tp1 is not None:
            return min(float(current_stop), float(tp1))

    return float(current_stop)


def time_stop_bars_for_timeframe(timeframe: str | None) -> int | None:
    if not timeframe:
        return None
    return TIME_STOP_BARS.get(timeframe.upper())


def time_stop_hit(
    *,
    entry_index: int,
    current_index: int,
    timeframe: str | None,
    realized_targets: list[str],
) -> bool:
    if realized_targets:
        return False
    limit = time_stop_bars_for_timeframe(timeframe)
    if limit is None:
        return False
    return (current_index - entry_index) >= limit


def volatility_spike_against_position(candle, side: str, atr_value: float | None, entry_price: float) -> bool:
    atr = _safe_float(atr_value)
    if atr is None or atr <= 0:
        return False

    total_range, _body, _upper_wick, _lower_wick = _range_components(candle)
    if total_range < atr * VOLATILITY_SPIKE_ATR_MULTIPLIER:
        return False

    close_price = float(candle["close"])
    normalized_side = (side or "").upper()
    if normalized_side == "LONG":
        return close_price < float(entry_price)
    if normalized_side == "SHORT":
        return close_price > float(entry_price)
    return False


def evaluate_entry_guardrails(
    *,
    trigger_candle,
    entry_open: float,
    side: str,
    planned_entry: float,
    stop_loss: float,
) -> EntryGuardDecision:
    if trigger_candle_looks_fake(trigger_candle, side):
        return EntryGuardDecision(False, "FAKEOUT_TRIGGER")

    if is_overextended_entry(side, planned_entry, entry_open, stop_loss):
        return EntryGuardDecision(False, "OVEREXTENDED_ENTRY")

    return EntryGuardDecision(True, None)
