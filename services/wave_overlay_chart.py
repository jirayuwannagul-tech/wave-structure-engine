from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from data.market_data_fetcher import MarketDataFetcher
from services.trading_orchestrator import _load_runtime


SVG_WIDTH = 1400
SVG_HEIGHT = 860
PADDING_LEFT = 90
PADDING_RIGHT = 40
PADDING_TOP = 50
PADDING_BOTTOM = 70


@dataclass
class WavePoint:
    label: str
    timestamp: pd.Timestamp
    price: float


def _dataset_path(symbol: str, timeframe: str) -> Path:
    return Path(f"data/{symbol.upper()}_{timeframe.lower()}.csv")


def _load_timeframe_df(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    path = _dataset_path(symbol, timeframe)
    if path.exists():
        df = pd.read_csv(path)
        if "open_time" in df.columns:
            df["open_time"] = pd.to_datetime(df["open_time"], utc=True, errors="coerce")
        if "close" in df.columns:
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
        return df.tail(limit).copy()

    fetcher = MarketDataFetcher(symbol=symbol, interval=timeframe.lower(), limit=limit)
    return fetcher.fetch_ohlcv().tail(limit).copy()


def _extract_daily_wave_points(analysis: dict, df_1d: pd.DataFrame) -> list[WavePoint]:
    inprogress = analysis.get("inprogress")
    if inprogress is not None and getattr(inprogress, "is_valid", False):
        pivots = list(getattr(inprogress, "pivots", []) or [])
        points: list[WavePoint] = []
        for index, pivot in enumerate(pivots):
            label = "start" if index == 0 else str(index)
            points.append(WavePoint(label=label, timestamp=pivot.timestamp, price=float(pivot.price)))

        if not df_1d.empty:
            current_point = WavePoint(
                label=str(getattr(inprogress, "wave_number", "") or "now"),
                timestamp=pd.Timestamp(df_1d.iloc[-1]["open_time"]),
                price=float(analysis.get("current_price") or df_1d.iloc[-1]["close"]),
            )
            points.append(current_point)
        return points

    pattern = analysis.get("primary_pattern")
    if pattern is None:
        return []

    if all(hasattr(pattern, attr) for attr in ("a", "b", "c")):
        return [
            WavePoint("A", pattern.a.timestamp, float(pattern.a.price)),
            WavePoint("B", pattern.b.timestamp, float(pattern.b.price)),
            WavePoint("C", pattern.c.timestamp, float(pattern.c.price)),
        ]

    return []


def _extract_4h_wave_points(analysis: dict) -> list[WavePoint]:
    pattern = analysis.get("primary_pattern")
    if pattern is None:
        return []

    if all(hasattr(pattern, attr) for attr in ("a", "b", "c")):
        return [
            WavePoint("A", pattern.a.timestamp, float(pattern.a.price)),
            WavePoint("B", pattern.b.timestamp, float(pattern.b.price)),
            WavePoint("C", pattern.c.timestamp, float(pattern.c.price)),
        ]

    inprogress = analysis.get("inprogress")
    if inprogress is not None and getattr(inprogress, "is_valid", False):
        points: list[WavePoint] = []
        for index, pivot in enumerate(list(getattr(inprogress, "pivots", []) or [])):
            label = "start" if index == 0 else str(index)
            points.append(WavePoint(label=label, timestamp=pivot.timestamp, price=float(pivot.price)))
        return points

    return []


def _svg_x(timestamp: pd.Timestamp, min_ts: pd.Timestamp, max_ts: pd.Timestamp) -> float:
    total = max((max_ts - min_ts).total_seconds(), 1.0)
    current = (timestamp - min_ts).total_seconds()
    chart_width = SVG_WIDTH - PADDING_LEFT - PADDING_RIGHT
    return PADDING_LEFT + (current / total) * chart_width


def _svg_y(price: float, min_price: float, max_price: float) -> float:
    span = max(max_price - min_price, 1.0)
    chart_height = SVG_HEIGHT - PADDING_TOP - PADDING_BOTTOM
    return PADDING_TOP + (max_price - price) / span * chart_height


def _line_path(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    first_x, first_y = points[0]
    commands = [f"M {first_x:.2f} {first_y:.2f}"]
    for x_value, y_value in points[1:]:
        commands.append(f"L {x_value:.2f} {y_value:.2f}")
    return " ".join(commands)


def _render_price_axis(min_price: float, max_price: float) -> str:
    steps = 6
    chart_width = SVG_WIDTH - PADDING_LEFT - PADDING_RIGHT
    lines: list[str] = []
    for index in range(steps + 1):
        price = min_price + (max_price - min_price) * (index / steps)
        y_value = _svg_y(price, min_price, max_price)
        lines.append(
            f'<line x1="{PADDING_LEFT}" y1="{y_value:.2f}" x2="{PADDING_LEFT + chart_width}" y2="{y_value:.2f}" '
            'stroke="#1f2937" stroke-width="1" />'
        )
        lines.append(
            f'<text x="{PADDING_LEFT - 12}" y="{y_value + 4:.2f}" text-anchor="end" '
            'fill="#94a3b8" font-size="14" font-family="Menlo, Monaco, monospace">'
            f'{price:,.2f}</text>'
        )
    return "".join(lines)


def _render_time_labels(min_ts: pd.Timestamp, max_ts: pd.Timestamp) -> str:
    steps = 6
    lines: list[str] = []
    for index in range(steps + 1):
        ratio = index / steps
        ts = min_ts + (max_ts - min_ts) * ratio
        x_value = _svg_x(ts, min_ts, max_ts)
        lines.append(
            f'<text x="{x_value:.2f}" y="{SVG_HEIGHT - 24}" text-anchor="middle" '
            'fill="#94a3b8" font-size="14" font-family="Menlo, Monaco, monospace">'
            f'{ts.strftime("%Y-%m-%d")}</text>'
        )
    return "".join(lines)


def _render_wave(points: list[WavePoint], min_ts: pd.Timestamp, max_ts: pd.Timestamp, min_price: float, max_price: float, color: str, dashed: bool) -> str:
    if not points:
        return ""

    xy_points = [(_svg_x(point.timestamp, min_ts, max_ts), _svg_y(point.price, min_price, max_price)) for point in points]
    path = _line_path(xy_points)
    dash_attr = ' stroke-dasharray="12 8"' if dashed else ""
    parts = [
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="4"{dash_attr} />'
    ]

    for point, (x_value, y_value) in zip(points, xy_points):
        parts.append(f'<circle cx="{x_value:.2f}" cy="{y_value:.2f}" r="5" fill="{color}" />')
        parts.append(
            f'<text x="{x_value + 8:.2f}" y="{y_value - 8:.2f}" fill="{color}" '
            'font-size="15" font-family="Menlo, Monaco, monospace">'
            f'{point.label}</text>'
        )
    return "".join(parts)


def build_wave_overlay_svg(symbol: str = "BTCUSDT", output_path: str | Path | None = None) -> Path:
    runtime = _load_runtime(symbol.upper(), retries=1)
    analyses = {analysis["timeframe"]: analysis for analysis in runtime.analyses}
    analysis_1d = analyses["1D"]
    analysis_4h = analyses["4H"]

    df_1d = _load_timeframe_df(symbol, "1d", 90)
    df_4h = _load_timeframe_df(symbol, "4h", 180)

    wave_1d = _extract_daily_wave_points(analysis_1d, df_1d)
    wave_4h = _extract_4h_wave_points(analysis_4h)
    if not wave_1d or not wave_4h:
        raise ValueError(f"Unable to derive 1D/4H wave points for {symbol.upper()}")

    backdrop = pd.concat(
        [
            df_1d[["open_time", "close"]].rename(columns={"close": "price"}),
            df_4h[["open_time", "close"]].rename(columns={"close": "price"}),
        ],
        ignore_index=True,
    ).dropna(subset=["open_time", "price"])
    backdrop["open_time"] = pd.to_datetime(backdrop["open_time"], utc=True)
    backdrop["price"] = pd.to_numeric(backdrop["price"], errors="coerce")
    backdrop = backdrop.dropna(subset=["price"]).sort_values("open_time").reset_index(drop=True)

    all_points = wave_1d + wave_4h
    min_ts = min([backdrop["open_time"].min(), *(point.timestamp for point in all_points)])
    max_ts = max([backdrop["open_time"].max(), *(point.timestamp for point in all_points)])
    min_price = min([float(backdrop["price"].min()), *(point.price for point in all_points)])
    max_price = max([float(backdrop["price"].max()), *(point.price for point in all_points)])
    padding = max((max_price - min_price) * 0.08, 1.0)
    min_price -= padding
    max_price += padding

    backdrop_points = [
        (_svg_x(row.open_time, min_ts, max_ts), _svg_y(float(row.price), min_price, max_price))
        for row in backdrop.itertuples(index=False)
    ]
    backdrop_path = _line_path(backdrop_points)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{SVG_HEIGHT}" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}">
  <rect width="100%" height="100%" fill="#050816"/>
  <text x="{PADDING_LEFT}" y="28" fill="#e5e7eb" font-size="26" font-family="Menlo, Monaco, monospace">{symbol.upper()} 1D / 4H Wave Overlay</text>
  <text x="{PADDING_LEFT}" y="54" fill="#94a3b8" font-size="15" font-family="Menlo, Monaco, monospace">1D = white | 4H = dashed red</text>
  {_render_price_axis(min_price, max_price)}
  <path d="{backdrop_path}" fill="none" stroke="#334155" stroke-width="2" opacity="0.8" />
  {_render_wave(wave_1d, min_ts, max_ts, min_price, max_price, "#ffffff", dashed=False)}
  {_render_wave(wave_4h, min_ts, max_ts, min_price, max_price, "#ef4444", dashed=True)}
  {_render_time_labels(min_ts, max_ts)}
  <rect x="{PADDING_LEFT}" y="{PADDING_TOP}" width="{SVG_WIDTH - PADDING_LEFT - PADDING_RIGHT}" height="{SVG_HEIGHT - PADDING_TOP - PADDING_BOTTOM}" fill="none" stroke="#1f2937" stroke-width="1"/>
</svg>"""

    output = Path(output_path or f"charts/{symbol.upper()}_1d_4h_wave_overlay.svg")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")
    return output
