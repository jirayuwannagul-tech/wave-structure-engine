"""Kalshi 15m BTC paper trading engine using 15m technical bias + 4H EW context."""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

_DB_PATH = Path(__file__).parent.parent / "storage" / "wave_engine.db"
_KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
_BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
_BINANCE_PRICE = "https://api.binance.com/api/v3/ticker/price"


# ── Kalshi helpers ──────────────────────────────────────────────────────────

def _kalshi_fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _btc_price() -> float:
    req = urllib.request.Request(f"{_BINANCE_PRICE}?symbol=BTCUSDT", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return float(json.loads(r.read())["price"])


# ── 15m technical bias ──────────────────────────────────────────────────────

def _fetch_15m_candles(limit: int = 100) -> pd.DataFrame:
    url = f"{_BINANCE_KLINES}?symbol=BTCUSDT&interval=15m&limit={limit}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = json.loads(r.read())
    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_vol", "trades", "tb_base", "tb_quote", "ignore",
    ])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    return df.iloc[:-1].reset_index(drop=True)  # drop unclosed candle


def compute_15m_bias(df: pd.DataFrame) -> tuple[str, dict]:
    """Return (bias, signals) from EMA/RSI/MACD on 15m data.

    bias = 'BULLISH' | 'BEARISH' | 'NEUTRAL'
    """
    close = df["close"]

    # EMA 9 / 21
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()

    # RSI 14
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_g = gain.ewm(span=14, adjust=False).mean()
    avg_l = loss.ewm(span=14, adjust=False).mean()
    rsi = 100 - 100 / (1 + avg_g / avg_l.replace(0, 1e-10))

    # MACD histogram (12/26/9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    hist = (ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()

    ema_bull = float(ema9.iloc[-1]) > float(ema21.iloc[-1])
    rsi_val = float(rsi.iloc[-1])
    rsi_bull = rsi_val > 50
    macd_rising = float(hist.iloc[-1]) > float(hist.iloc[-2]) if len(hist) >= 2 else None
    # Price momentum: last 4 candles vs 4 candles before that
    mom_up = float(close.iloc[-1]) > float(close.iloc[-4]) if len(close) >= 4 else None

    # Each indicator casts a vote: +1 bullish / -1 bearish
    score = (1 if ema_bull else -1) + (1 if rsi_bull else -1)
    if macd_rising is not None:
        score += 1 if macd_rising else -1
    if mom_up is not None:
        score += 1 if mom_up else -1

    if score >= 2:
        bias = "BULLISH"
    elif score <= -2:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    signals = {
        "ema9": round(float(ema9.iloc[-1]), 2),
        "ema21": round(float(ema21.iloc[-1]), 2),
        "ema_bull": ema_bull,
        "rsi": round(rsi_val, 1),
        "macd_rising": macd_rising,
        "mom_up": mom_up,
        "score": score,
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

def _fetch_active_event() -> dict | None:
    """Return the KXBTC15M event that is currently open (soonest expiry)."""
    try:
        data = _kalshi_fetch(f"{_KALSHI_BASE}/events?series_ticker=KXBTC15M&limit=20&status=open")
    except Exception as e:
        print(f"[kalshi] fetch events error: {e}")
        return None

    now = datetime.now(UTC)
    future = []
    for e in data.get("events", []):
        exp_str = e.get("expiration_time") or e.get("close_time") or ""
        if not exp_str:
            continue
        try:
            exp = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if exp > now:
            future.append((exp, e))

    if not future:
        return None
    future.sort(key=lambda x: x[0])
    return future[0][1]


def _get_market_target(event_ticker: str) -> float | None:
    """Return floor_strike from the Kalshi market (the BTC price-to-beat)."""
    try:
        data = _kalshi_fetch(f"{_KALSHI_BASE}/markets?event_ticker={event_ticker}&limit=5")
        markets = data.get("markets", [])
        if markets:
            strike = markets[0].get("floor_strike") or markets[0].get("cap_strike")
            if strike:
                return float(strike)
    except Exception:
        pass
    return None


# ── Public: make / resolve / get ────────────────────────────────────────────

def make_prediction(db_path: Path | None = None) -> dict | None:
    """Analyse 15m bias and record a prediction for the current Kalshi event."""
    db = db_path or _DB_PATH
    _ensure_table(db)

    ev = _fetch_active_event()
    if not ev:
        return None

    ticker = ev["event_ticker"]
    exp_str = ev.get("expiration_time") or ev.get("close_time") or ""

    # Already recorded for this event?
    conn = sqlite3.connect(str(db))
    exists = conn.execute("SELECT id FROM kalshi_predictions WHERE event_ticker=?", (ticker,)).fetchone()
    conn.close()
    if exists:
        return None

    # Target price
    target = _get_market_target(ticker)
    btc = _btc_price()
    if target is None:
        target = round(btc, 2)

    # 15m technical bias
    try:
        df = _fetch_15m_candles(limit=100)
        bias_15m, signals = compute_15m_bias(df)
    except Exception as e:
        print(f"[kalshi] 15m analysis failed: {e}")
        return None

    # 4H EW bias for reference
    bias_4h = _get_4h_bias(db)

    if bias_15m == "NEUTRAL":
        print(f"[kalshi] NEUTRAL 15m bias — skip {ticker}")
        return None

    prediction = "UP" if bias_15m == "BULLISH" else "DOWN"
    now_str = datetime.now(UTC).isoformat()

    conn = sqlite3.connect(str(db))
    conn.execute("""
        INSERT INTO kalshi_predictions
            (event_ticker, target_price, ew_bias_15m, ew_bias_4h, signals_json,
             prediction, start_price, created_at, expires_at)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (ticker, target, bias_15m, bias_4h, json.dumps(signals), prediction, btc, now_str, exp_str))
    conn.commit()
    conn.close()

    print(f"[kalshi] Predicted {prediction} | {ticker} | 15m={bias_15m} 4H={bias_4h} | target=${target:,.0f}")
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
            exp = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
        except ValueError:
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
    """Return prediction history + win/loss stats."""
    db = db_path or _DB_PATH
    _ensure_table(db)

    conn = sqlite3.connect(str(db))
    rows = conn.execute("""
        SELECT event_ticker, target_price, ew_bias_15m, ew_bias_4h, prediction,
               start_price, end_price, kalshi_result, win, created_at, resolved_at, expires_at
        FROM kalshi_predictions
        ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()

    sr = conn.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN win=1 THEN 1 ELSE 0 END),
               SUM(CASE WHEN win=0 THEN 1 ELSE 0 END),
               SUM(CASE WHEN win IS NULL THEN 1 ELSE 0 END)
        FROM kalshi_predictions
    """).fetchone()
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
        },
    }


# ── Loop ────────────────────────────────────────────────────────────────────

def run_loop(db_path: Path | None = None, interval: int = 300) -> None:
    """Blocking prediction loop. Call from a daemon thread."""
    db = db_path or _DB_PATH
    print(f"[kalshi] Predictor started (interval={interval}s)")
    while True:
        try:
            resolve_predictions(db)
            make_prediction(db)
        except Exception as e:
            print(f"[kalshi] loop error: {e}")
        time.sleep(interval)
