"""Kalshi 15m BTC paper trading engine using Elliott Wave analysis on 15m data."""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / "storage" / "wave_engine.db"
_KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
_BINANCE_PRICE = "https://api.binance.com/api/v3/ticker/price"

# Make sure project root is on sys.path so core/ is importable
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Kalshi helpers ──────────────────────────────────────────────────────────

def _kalshi_fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _btc_price() -> float:
    req = urllib.request.Request(f"{_BINANCE_PRICE}?symbol=BTCUSDT", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return float(json.loads(r.read())["price"])


# ── 15m Elliott Wave analysis (pure code, no AI) ───────────────────────────

def run_ew_15m_analysis() -> tuple[str, dict]:
    """Detect EW structure on 15m BTC data using pivot + Dow Theory. No AI.

    bias = 'BULLISH' | 'BEARISH' | 'NEUTRAL'
    """
    # Isolated copy under kalshi_engine/ — intentionally does NOT share code
    # with analysis/ or data/ so changes to the main trading engine can
    # never silently alter Kalshi's 15m predictions, and vice versa.
    from kalshi_engine.indicator_engine import calculate_atr
    from kalshi_engine.pivot_detector import detect_pivots
    from kalshi_engine.trend_classifier import classify_market_trend
    from kalshi_engine.inprogress_detector import detect_inprogress_wave
    from kalshi_engine.candle_utils import drop_unclosed_candle
    from kalshi_engine.market_data_fetcher import MarketDataFetcher

    fetcher = MarketDataFetcher(symbol="BTCUSDT", interval="15m", limit=200)
    df = drop_unclosed_candle(fetcher.fetch_ohlcv())

    # ATR for pivot sensitivity
    df = df.copy()
    df["atr"] = calculate_atr(df, period=14)

    pivots = detect_pivots(df, right=1, min_swing_atr_mult=0.1)
    trend = classify_market_trend(pivots, df=df)

    # Check in-progress wave direction for extra signal
    inprogress = detect_inprogress_wave(pivots)
    wave_dir = None
    wave_position = None
    next_wave = None
    if inprogress:
        wave_dir = getattr(inprogress, "direction", None)
        structure = getattr(inprogress, "structure", None)
        wave_number = getattr(inprogress, "wave_number", None)
        completed_waves = getattr(inprogress, "completed_waves", None)
        # "Confirmed" position: the structure/wave count the engine has
        # validated so far from the last N pivots.
        wave_position = (
            f"{structure} confirmed through wave {completed_waves}, "
            f"forming wave {wave_number} ({wave_dir})"
            if structure and wave_number
            else None
        )
        # "Next wave" prediction: the wave currently forming IS the next
        # wave being called, with its projected target/invalidation levels.
        next_wave = {
            "wave_number": wave_number,
            "direction": wave_dir,
            "fib_targets": getattr(inprogress, "fib_targets", {}) or {},
            "invalidation": getattr(inprogress, "invalidation", None),
            "confidence": getattr(inprogress, "confidence", None),
        }

    state = trend.state  # UPTREND | DOWNTREND | SIDEWAY | BROKEN_UP | BROKEN_DOWN

    if state in ("UPTREND", "BROKEN_UP"):
        bias = "BULLISH"
    elif state in ("DOWNTREND", "BROKEN_DOWN"):
        bias = "BEARISH"
    else:
        # Sideway — use in-progress wave direction as tiebreaker
        if wave_dir == "bullish":
            bias = "BULLISH"
        elif wave_dir == "bearish":
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

    signals = {
        "trend_state": state,
        "swing_structure": trend.swing_structure,
        "confidence": trend.confidence,
        "wave_dir": wave_dir,
        "last_high": trend.last_high,
        "last_low": trend.last_low,
        "wave_position": wave_position,
        "next_wave": next_wave,
        "source": "EW-15m-code",
    }
    return bias, signals


# ── 4H EW bias from DB ──────────────────────────────────────────────────────

def _get_4h_bias(db_path: Path) -> str:
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT bias FROM analysis_snapshots WHERE symbol='BTCUSDT' AND timeframe='4H' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return row[0] if row else "NEUTRAL"
    except Exception:
        return "NEUTRAL"


# ── DB ──────────────────────────────────────────────────────────────────────

def _ensure_table(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kalshi_predictions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            event_ticker TEXT    UNIQUE,
            target_price REAL,
            ew_bias_15m  TEXT,
            ew_bias_4h   TEXT,
            signals_json TEXT,
            prediction   TEXT,
            start_price  REAL,
            end_price    REAL,
            kalshi_result TEXT,
            win          INTEGER,
            created_at   TEXT,
            resolved_at  TEXT,
            expires_at   TEXT
        )
    """)
    conn.commit()
    conn.close()


# ── Kalshi event lookup ─────────────────────────────────────────────────────

_MONTH_MAP = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
              "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}


def _parse_ticker_expiry(ticker: str) -> datetime | None:
    """Parse expiry from ticker like KXBTC15M-26JUL080700 → 2026-07-08 07:00 UTC."""
    try:
        # suffix after last '-'
        suffix = ticker.rsplit("-", 1)[-1]   # e.g. 26JUL080700
        year = 2000 + int(suffix[:2])
        month = _MONTH_MAP[suffix[2:5].upper()]
        day = int(suffix[5:7])
        hour = int(suffix[7:9])
        minute = int(suffix[9:11])
        return datetime(year, month, day, hour, minute, tzinfo=UTC)
    except Exception:
        return None


def _parse_event_expiry(ev: dict) -> datetime | None:
    """Parse expiry from event dict — prefers strike_date (UTC) over ticker parsing."""
    for field in ("strike_date", "expiration_time", "close_time"):
        val = ev.get(field, "")
        if val:
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except ValueError:
                pass
    return None


def _parse_title_price(title: str) -> float | None:
    """Extract price from Kalshi event title e.g. 'BTC 15 min · $62,479.80 target'."""
    import re
    m = re.search(r"\$([0-9,]+(?:\.[0-9]+)?)", title or "")
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass
    return None


def _fetch_active_event() -> dict | None:
    """Return the soonest open KXBTC15M event using strike_date (UTC) for expiry."""
    try:
        data = _kalshi_fetch(f"{_KALSHI_BASE}/events?series_ticker=KXBTC15M&limit=20&status=open")
    except Exception as e:
        print(f"[kalshi] fetch events error: {e}")
        return None

    now = datetime.now(UTC)
    future = []
    for e in data.get("events", []):
        exp = _parse_event_expiry(e)
        if exp is None:
            future.append((now + timedelta(minutes=15), e))
            continue
        if exp > now:
            future.append((exp, e))

    if not future:
        return None
    future.sort(key=lambda x: x[0])
    return future[0][1]


def _get_market_target(event_ticker: str, title: str = "") -> float | None:
    """Return Kalshi floor_strike, falling back to price parsed from event title."""
    try:
        data = _kalshi_fetch(f"{_KALSHI_BASE}/markets?event_ticker={event_ticker}&limit=5")
        markets = data.get("markets", [])
        if markets:
            strike = markets[0].get("floor_strike") or markets[0].get("cap_strike")
            if strike:
                return float(strike)
    except Exception:
        pass
    # Fallback: parse from event title e.g. "BTC 15 min · $62,479.80 target"
    return _parse_title_price(title)


# ── Public: make / resolve / get ────────────────────────────────────────────

def _slot_ticker(now: datetime) -> tuple[str, datetime]:
    """Generate a synthetic ticker + expiry for the current 15-min slot.

    Ticker includes date + hour + slot_start so each 15-min window is unique.
    e.g. BTCPRED-26JUL081145 = 2026-07-08 slot starting at 11:45 UTC
    """
    m = now.minute
    slot_start = (m // 15) * 15          # 0, 15, 30, 45
    slot_end = slot_start + 15
    if slot_end >= 60:
        exp = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        exp = now.replace(minute=slot_end, second=0, microsecond=0)
    # Include hour so 11:01 and 12:01 get different tickers
    tag = now.strftime(f"%y%b%d%H{slot_start:02d}").upper()
    ticker = f"BTCPRED-{tag}"
    return ticker, exp


def make_prediction(db_path: Path | None = None) -> dict | None:
    """Analyse 15m EW bias and record a prediction. Works without Kalshi."""
    db = db_path or _DB_PATH
    _ensure_table(db)

    now = datetime.now(UTC)

    # Try to get a live Kalshi event for the official CF Benchmarks target price
    ev = _fetch_active_event()
    if ev:
        ticker = ev["event_ticker"]
        title = ev.get("title", "")
        exp = _parse_event_expiry(ev)
        if exp is None:
            exp = _parse_ticker_expiry(ticker)
        if exp is None:
            # Neither the event payload nor the ticker suffix parsed — fall back
            # to the synthetic 15m slot expiry so the row is still resolvable.
            _, exp = _slot_ticker(now)
        target = _get_market_target(ticker, title)
        print(f"[kalshi] Kalshi event found: {ticker} | target=${target} | exp={exp}")
    else:
        # No Kalshi event — use synthetic slot ticker
        ticker, exp = _slot_ticker(now)
        target = None
        print(f"[kalshi] No Kalshi event — using synthetic {ticker}")

    # Already recorded this slot?
    conn = sqlite3.connect(str(db))
    exists = conn.execute("SELECT id FROM kalshi_predictions WHERE event_ticker=?", (ticker,)).fetchone()
    conn.close()
    if exists:
        return None

    btc = _btc_price()
    if target is None:
        target = round(btc, 2)

    # 15m Elliott Wave analysis
    try:
        bias_15m, signals = run_ew_15m_analysis()
    except Exception as e:
        print(f"[kalshi] 15m EW analysis failed: {e}")
        return None

    bias_4h = _get_4h_bias(db)

    # Always predict — resolve NEUTRAL via EW cascade
    if bias_15m == "NEUTRAL":
        if bias_4h in ("BULLISH", "BEARISH"):
            # Use higher-timeframe EW structure
            bias_15m = bias_4h
            signals["neutral_resolved_by"] = "4H_ew_bias"
        else:
            # Use price vs EW pivot range midpoint
            last_h = signals.get("last_high")
            last_l = signals.get("last_low")
            if last_h and last_l:
                mid = (last_h + last_l) / 2
                bias_15m = "BULLISH" if btc > mid else "BEARISH"
                signals["neutral_resolved_by"] = f"price_vs_pivot_mid({mid:,.0f})"
            else:
                # Fallback: use last swing state direction
                swing = signals.get("swing_structure", "")
                bias_15m = "BULLISH" if "HH" in str(swing) or "HL" in str(swing) else "BEARISH"
                signals["neutral_resolved_by"] = f"swing_structure({swing})"

    prediction = "UP" if bias_15m == "BULLISH" else "DOWN"
    now_str = now.isoformat()
    exp_str_save = exp.isoformat()

    conn = sqlite3.connect(str(db))
    conn.execute("""
        INSERT INTO kalshi_predictions
            (event_ticker, target_price, ew_bias_15m, ew_bias_4h, signals_json,
             prediction, start_price, created_at, expires_at)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (ticker, target, bias_15m, bias_4h, json.dumps(signals),
          prediction, btc, now_str, exp_str_save))
    conn.commit()
    conn.close()

    src = "Kalshi" if ev else "synthetic"
    print(f"[kalshi] Predicted {prediction} | {ticker} [{src}] | 15m={bias_15m} 4H={bias_4h} | target=${target:,.0f}")
    return {"ticker": ticker, "prediction": prediction, "bias_15m": bias_15m, "bias_4h": bias_4h, "target": target}


def resolve_predictions(db_path: Path | None = None) -> int:
    """Resolve expired pending predictions. Returns count resolved."""
    db = db_path or _DB_PATH
    _ensure_table(db)

    conn = sqlite3.connect(str(db))
    pending = conn.execute("""
        SELECT id, event_ticker, target_price, prediction, expires_at
        FROM kalshi_predictions
        WHERE win IS NULL AND expires_at IS NOT NULL
    """).fetchall()
    conn.close()

    now = datetime.now(UTC)
    resolved = 0

    for id_, ticker, target, pred, exp_str in pending:
        try:
            exp = datetime.fromisoformat(exp_str.replace("Z", "+00:00")) if exp_str else None
        except ValueError:
            exp = None
        if exp is None:
            exp = _parse_ticker_expiry(ticker)
        if exp is None:
            continue

        # Wait 30 s after expiry so the price is settled
        if now < exp + timedelta(seconds=30):
            continue

        try:
            end_price = _btc_price()
            actual = "UP" if end_price > (target or end_price) else "DOWN"
            win = 1 if pred == actual else 0

            conn = sqlite3.connect(str(db))
            conn.execute("""
                UPDATE kalshi_predictions
                SET end_price=?, kalshi_result=?, win=?, resolved_at=?
                WHERE id=?
            """, (end_price, actual, win, now.isoformat(), id_))
            conn.commit()
            conn.close()

            tag = "WIN ✓" if win else "LOSS ✗"
            print(f"[kalshi] {tag} | {ticker} | pred={pred} actual={actual} | "
                  f"target=${target:,.0f} → end=${end_price:,.0f}")
            resolved += 1
        except Exception as e:
            print(f"[kalshi] resolve error {ticker}: {e}")

    return resolved


def get_predictions(db_path: Path | None = None, limit: int = 50) -> dict:
    """Return prediction history + win/loss stats (today in LA timezone)."""
    import zoneinfo as _zi
    db = db_path or _DB_PATH
    _ensure_table(db)

    # Today's date in LA time → UTC window for SQL
    _la = _zi.ZoneInfo("America/Los_Angeles")
    _now_la = datetime.now(_la)
    _today_la = _now_la.date()
    # midnight LA → UTC
    _day_start_utc = datetime(_today_la.year, _today_la.month, _today_la.day,
                              tzinfo=_la).astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
    _day_end_la = datetime(_today_la.year, _today_la.month, _today_la.day, 23, 59, 59,
                           tzinfo=_la).astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(str(db))
    rows = conn.execute("""
        SELECT event_ticker, target_price, ew_bias_15m, ew_bias_4h, prediction,
               start_price, end_price, kalshi_result, win, created_at, resolved_at, expires_at
        FROM kalshi_predictions
        ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()

    # Stats: only today (LA time)
    sr = conn.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN win=1 THEN 1 ELSE 0 END),
               SUM(CASE WHEN win=0 THEN 1 ELSE 0 END),
               SUM(CASE WHEN win IS NULL THEN 1 ELSE 0 END)
        FROM kalshi_predictions
        WHERE created_at >= ? AND created_at <= ?
    """, (_day_start_utc, _day_end_la)).fetchone()
    conn.close()

    predictions = [
        {
            "event_ticker": r[0],
            "target_price": r[1],
            "ew_bias_15m": r[2],
            "ew_bias_4h": r[3],
            "prediction": r[4],
            "start_price": r[5],
            "end_price": r[6],
            "kalshi_result": r[7],
            "win": r[8],
            "created_at": (r[9] or "")[:16],
            "resolved_at": (r[10] or "")[:16],
            "expires_at": (r[11] or "")[:16],
        }
        for r in rows
    ]

    total, wins, losses, pending = (sr or (0, 0, 0, 0))
    total = total or 0; wins = wins or 0; losses = losses or 0; pending = pending or 0
    settled = wins + losses

    return {
        "predictions": predictions,
        "stats": {
            "total": total,
            "wins": wins,
            "losses": losses,
            "pending": pending,
            "win_rate": round(wins / settled, 3) if settled > 0 else None,
            "date_la": _today_la.isoformat(),
        },
    }


# ── Loop ────────────────────────────────────────────────────────────────────

_PRED_MINUTES = (1, 16, 31, 46)  # UTC minutes to predict each hour


def _secs_to_next_slot() -> int:
    """Seconds until the next :01/:16/:31/:46 UTC mark."""
    now = datetime.now(UTC)
    m, s = now.minute, now.second
    for target in _PRED_MINUTES:
        if m < target or (m == target and s < 10):
            return max((target - m) * 60 - s, 1)
    # wrap to next hour
    return max((60 - m + _PRED_MINUTES[0]) * 60 - s, 1)


def run_loop(db_path: Path | None = None) -> None:
    """Blocking prediction loop aligned to :01/:16/:31/:46 UTC."""
    db = db_path or _DB_PATH
    slots = "/".join(f":{m:02d}" for m in _PRED_MINUTES)
    print(f"[kalshi] Predictor started — slots at {slots} UTC")

    # Kick off immediately on startup (resolve any stale + predict if possible)
    try:
        resolve_predictions(db)
        make_prediction(db)
    except Exception as e:
        print(f"[kalshi] startup error: {e}")

    while True:
        wait = _secs_to_next_slot()
        print(f"[kalshi] next slot in {wait}s ({wait//60}m{wait%60:02d}s)")
        time.sleep(wait)
        try:
            resolve_predictions(db)
            make_prediction(db)
        except Exception as e:
            print(f"[kalshi] loop error: {e}")
