from __future__ import annotations

import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from execution.settings import load_execution_config


THAI_TZ = ZoneInfo("Asia/Bangkok")
SHEET_HEADERS = [
    "date",
    "symbol",
    "timeframe",
    "side",
    "entry",
    "sl",
    "tp1",
    "tp2",
    "tp3",
    "rr_tp1",
    "rr_tp2",
    "rr_tp3",
    "tp1_mark",
    "tp2_mark",
    "tp3_mark",
    "sl_mark",
    "result",
    "realized_rr",
    "win_rate_pct",
]

SYNCABLE_SIGNAL_STATUSES = {
    "ACTIVE",
    "PARTIAL_TP1",
    "PARTIAL_TP2",
    "TP3_HIT",
    "STOPPED",
}


def _is_enabled() -> bool:
    return (os.getenv("GOOGLE_SHEETS_ENABLED", "false") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _normalize_price(value) -> str:
    if value is None:
        return ""
    value = round(float(value), 6)
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _signal_date(signal_row) -> str:
    raw = signal_row["created_at"]
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(THAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _tp_allocations() -> tuple[float, float, float]:
    config = load_execution_config()
    return (
        float(config.tp1_size_pct),
        float(config.tp2_size_pct),
        float(config.tp3_size_pct),
    )


def _fmt_marker(hit: bool, fail: bool = False) -> str:
    if hit:
        return "✓"
    if fail:
        return "✗"
    return ""


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _field(signal_row, key: str):
    if signal_row is None:
        return None
    if hasattr(signal_row, "keys"):
        try:
            if key in signal_row.keys():
                return signal_row[key]
        except Exception:
            pass
    if isinstance(signal_row, dict):
        return signal_row.get(key)
    try:
        return signal_row[key]
    except Exception:
        return None


def _normalize_metric(value: float | None) -> str:
    if value is None:
        return ""
    rounded = round(float(value), 4)
    text = f"{rounded:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _normalize_percentage(value: float | None) -> str:
    if value is None:
        return ""
    rounded = round(float(value), 2)
    return f"{rounded:.2f}"


def _weighted_realized_rr(signal_row) -> float | None:
    status = (_field(signal_row, "status") or "").upper()
    close_reason = (_field(signal_row, "close_reason") or "").upper()
    rr_tp1 = _to_float(_field(signal_row, "rr_tp1"))
    rr_tp2 = _to_float(_field(signal_row, "rr_tp2"))
    rr_tp3 = _to_float(_field(signal_row, "rr_tp3"))
    tp1_hit = bool(_field(signal_row, "tp1_hit_at"))
    tp2_hit = bool(_field(signal_row, "tp2_hit_at"))
    tp3_hit = bool(_field(signal_row, "tp3_hit_at"))
    w1, w2, w3 = _tp_allocations()

    realized_rr = 0.0
    realized_any = False

    if tp1_hit and rr_tp1 is not None:
        realized_rr += w1 * rr_tp1
        realized_any = True
    if tp2_hit and rr_tp2 is not None:
        realized_rr += w2 * rr_tp2
        realized_any = True
    if tp3_hit and rr_tp3 is not None:
        realized_rr += w3 * rr_tp3
        realized_any = True

    if status == "STOPPED":
        remaining_size = 1.0
        if tp1_hit:
            remaining_size -= w1
        if tp2_hit:
            remaining_size -= w2
        if tp3_hit:
            remaining_size -= w3
        remaining_size = max(remaining_size, 0.0)
        residual_rr = _residual_exit_rr(signal_row, close_reason)
        if residual_rr is not None:
            realized_rr += remaining_size * residual_rr
            realized_any = True

    if status == "TP3_HIT" and not realized_any:
        return None

    if status in {"PARTIAL_TP1", "PARTIAL_TP2", "TP3_HIT", "STOPPED"} and realized_any:
        return round(realized_rr, 4)

    return None


def _base_risk(signal_row) -> float | None:
    entry = _to_float(_field(signal_row, "entry_price"))
    tp1 = _to_float(_field(signal_row, "tp1"))
    rr_tp1 = _to_float(_field(signal_row, "rr_tp1"))
    stop_loss = _to_float(_field(signal_row, "stop_loss"))

    if entry is None:
        return None
    if tp1 is not None and rr_tp1 not in (None, 0.0):
        risk = abs(tp1 - entry) / abs(rr_tp1)
        if risk > 0:
            return risk
    if stop_loss is not None:
        risk = abs(entry - stop_loss)
        if risk > 0:
            return risk
    return None


def _rr_from_exit_price(signal_row, exit_price: float | None) -> float | None:
    entry = _to_float(_field(signal_row, "entry_price"))
    risk = _base_risk(signal_row)
    side = str(_field(signal_row, "side") or "").upper()

    if entry is None or exit_price is None or risk in (None, 0.0):
        return None

    direction = 1.0 if side == "LONG" else -1.0
    return round(((float(exit_price) - float(entry)) * direction) / float(risk), 4)


def _residual_exit_rr(signal_row, close_reason: str) -> float | None:
    close_reason = (close_reason or "").upper()
    if close_reason in {"TIME_STOP", "PROTECTIVE_EXIT", "OPPOSITE_STRUCTURE", "VOLATILITY_EXIT"}:
        return _rr_from_exit_price(signal_row, _to_float(_field(signal_row, "current_price")))
    if close_reason in {"STOP_LOSS", "STOP_LOSS_BEFORE_ENTRY"}:
        managed_stop = _to_float(_field(signal_row, "managed_stop_loss"))
        stop_price = managed_stop if managed_stop is not None else _to_float(_field(signal_row, "stop_loss"))
        return _rr_from_exit_price(signal_row, stop_price)
    return None


def compute_signal_tracking(signal_row) -> dict[str, str]:
    status = (_field(signal_row, "status") or "").upper()
    close_reason = (_field(signal_row, "close_reason") or "").upper()
    tp1_hit = bool(_field(signal_row, "tp1_hit_at"))
    tp2_hit = bool(_field(signal_row, "tp2_hit_at"))
    tp3_hit = bool(_field(signal_row, "tp3_hit_at"))
    stopped = status == "STOPPED"
    realized_rr_value = _weighted_realized_rr(signal_row)
    stopped_by_sl = stopped and close_reason in {"STOP_LOSS", "STOP_LOSS_BEFORE_ENTRY"}

    if status == "TP3_HIT" or tp3_hit:
        result = "TP3_HIT"
        win_rate_pct = _normalize_percentage(100.0)
    elif status == "STOPPED":
        if close_reason == "TIME_STOP":
            result = "TIME_STOP"
            if realized_rr_value is None:
                win_rate_pct = ""
            else:
                win_rate_pct = _normalize_percentage(100.0 if realized_rr_value > 0 else 0.0)
        elif close_reason == "OPPOSITE_STRUCTURE":
            result = "OPPOSITE_STRUCTURE_EXIT"
            if realized_rr_value is None:
                win_rate_pct = ""
            else:
                win_rate_pct = _normalize_percentage(100.0 if realized_rr_value > 0 else 0.0)
        elif close_reason == "VOLATILITY_EXIT":
            result = "VOLATILITY_EXIT"
            if realized_rr_value is None:
                win_rate_pct = ""
            else:
                win_rate_pct = _normalize_percentage(100.0 if realized_rr_value > 0 else 0.0)
        elif close_reason == "PROTECTIVE_EXIT":
            result = "PROTECTIVE_EXIT"
            if realized_rr_value is None:
                win_rate_pct = ""
            else:
                win_rate_pct = _normalize_percentage(100.0 if realized_rr_value > 0 else 0.0)
        elif tp2_hit:
            result = "TP2_THEN_SL"
            win_rate_pct = _normalize_percentage(66.67)
        elif tp1_hit:
            result = "TP1_THEN_SL"
            win_rate_pct = _normalize_percentage(33.33)
        else:
            result = "SL_HIT"
            win_rate_pct = _normalize_percentage(0.0)
    elif status == "PARTIAL_TP2":
        result = "TP2_ACTIVE"
        win_rate_pct = _normalize_percentage(66.67)
    elif status == "PARTIAL_TP1":
        result = "TP1_ACTIVE"
        win_rate_pct = _normalize_percentage(33.33)
    elif status in {"ACTIVE", "PENDING_ENTRY", "INVALIDATED", "REPLACED"}:
        result = status
        win_rate_pct = ""
    else:
        result = status or "UNKNOWN"
        win_rate_pct = ""

    return {
        "result": result,
        "tp1_mark": _fmt_marker(tp1_hit),
        "tp2_mark": _fmt_marker(tp2_hit),
        "tp3_mark": _fmt_marker(tp3_hit),
        "sl_mark": _fmt_marker(False, fail=stopped_by_sl),
        "realized_rr": _normalize_metric(realized_rr_value),
        "win_rate_pct": win_rate_pct,
    }


def compute_sheet_result(signal_row) -> tuple[str, str]:
    tracking = compute_signal_tracking(signal_row)
    return tracking["result"], tracking["win_rate_pct"]


def build_signal_sheet_row(signal_row) -> list[str]:
    tracking = compute_signal_tracking(signal_row)
    return [
        _signal_date(signal_row),
        str(signal_row["symbol"] or ""),
        str(signal_row["timeframe"] or ""),
        str(signal_row["side"] or ""),
        _normalize_price(signal_row["entry_price"]),
        _normalize_price(signal_row["stop_loss"]),
        _normalize_price(signal_row["tp1"]),
        _normalize_price(signal_row["tp2"]),
        _normalize_price(signal_row["tp3"]),
        _normalize_price(signal_row["rr_tp1"]),
        _normalize_price(signal_row["rr_tp2"]),
        _normalize_price(signal_row["rr_tp3"]),
        tracking["tp1_mark"],
        tracking["tp2_mark"],
        tracking["tp3_mark"],
        tracking["sl_mark"],
        tracking["result"],
        tracking["realized_rr"],
        tracking["win_rate_pct"],
    ]


def _normalize_identity_value(index: int, value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if index == 0:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).strftime(fmt)
            except ValueError:
                continue
    if index in {4, 5, 6, 7, 8}:
        try:
            return _normalize_price(text)
        except (TypeError, ValueError):
            return text
    return text


def _build_identity_key(row_values: list[str]) -> tuple[str, ...]:
    mode = (os.getenv("GOOGLE_SHEETS_DEDUPE_MODE", "full_plan") or "").strip().lower()
    # full_plan (default): keep separate rows for different SL/TP plans (date,symbol,timeframe,side,entry,sl,tp1,tp2,tp3)
    if mode in {"full_plan", "plan", "default", ""}:
        return tuple(_normalize_identity_value(idx, value) for idx, value in enumerate(row_values[:9]))
    # latest_per_symbol: one row per (symbol,timeframe,side) to avoid duplicates on sheet
    if mode in {"latest_per_symbol", "symbol_timeframe", "symbol_timeframe_side"}:
        return tuple(str(value or "").strip() for value in row_values[1:4])
    return tuple(_normalize_identity_value(idx, value) for idx, value in enumerate(row_values[:9]))


def should_sync_signal_to_sheet(signal_row) -> bool:
    row = signal_row
    try:
        # sqlite3.Row behaves like Mapping but has no .get
        if hasattr(row, "keys") and not isinstance(row, dict):
            row = {k: row[k] for k in row.keys()}
    except Exception:
        pass
    status = str((row or {}).get("status") or "").upper()
    if status in SYNCABLE_SIGNAL_STATUSES:
        return True
    if status == "INVALIDATED" and (row or {}).get("entry_triggered_at"):
        return True
    return False


class GoogleSheetsSignalLogger:
    def __init__(
        self,
        spreadsheet_id: str,
        credentials_path: str,
        worksheet_name: str = "wave_log",
        worksheet=None,
    ):
        self.spreadsheet_id = spreadsheet_id
        self.credentials_path = credentials_path
        self.worksheet_name = worksheet_name
        self.worksheet = worksheet or self._build_worksheet()
        self._ensure_headers()

    @classmethod
    def from_env(cls) -> GoogleSheetsSignalLogger | None:
        if not _is_enabled():
            return None

        spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID", "").strip()
        credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "").strip()
        worksheet_name = os.getenv("GOOGLE_SHEETS_TAB", "wave_log").strip() or "wave_log"

        if not spreadsheet_id or not credentials_path:
            return None

        return cls(
            spreadsheet_id=spreadsheet_id,
            credentials_path=credentials_path,
            worksheet_name=worksheet_name,
        )

    def _build_worksheet(self):
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = Credentials.from_service_account_file(self.credentials_path, scopes=scopes)
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(self.spreadsheet_id)
        try:
            return spreadsheet.worksheet(self.worksheet_name)
        except gspread.WorksheetNotFound:
            return spreadsheet.add_worksheet(title=self.worksheet_name, rows=1000, cols=len(SHEET_HEADERS))

    def _ensure_headers(self) -> None:
        header_row = self.worksheet.row_values(1)
        if header_row[: len(SHEET_HEADERS)] != SHEET_HEADERS:
            self.worksheet.update(self._row_range(1), [SHEET_HEADERS])

    def _row_range(self, row_number: int) -> str:
        return f"A{row_number}:{self._column_label(len(SHEET_HEADERS))}{row_number}"

    def _column_label(self, column_number: int) -> str:
        label = ""
        current = column_number
        while current > 0:
            current, remainder = divmod(current - 1, 26)
            label = chr(65 + remainder) + label
        return label

    def upsert_signal(self, signal_row) -> None:
        row_values = build_signal_sheet_row(signal_row)
        identity = _build_identity_key(row_values)
        existing_row = self._find_row(identity)

        if existing_row is None:
            self.worksheet.append_row(row_values, value_input_option="USER_ENTERED")
            return

        self.worksheet.update(
            self._row_range(existing_row),
            [row_values],
            value_input_option="USER_ENTERED",
        )

    def _find_row(self, identity: tuple[str, ...]) -> int | None:
        values = self.worksheet.get_all_values()
        for idx, row in enumerate(values[1:], start=2):
            padded = row + [""] * max(0, len(SHEET_HEADERS) - len(row))
            if _build_identity_key(padded) == identity:
                return idx
        return None


def safe_sync_signal(signal_row, logger: GoogleSheetsSignalLogger | None) -> None:
    if logger is None or signal_row is None:
        return
    row = signal_row
    try:
        if hasattr(row, "keys") and not isinstance(row, dict):
            row = {k: row[k] for k in row.keys()}
    except Exception:
        row = signal_row
    if not should_sync_signal_to_sheet(row):
        return

    try:
        logger.upsert_signal(row)
    except Exception as exc:
        print(f"Google Sheets sync skipped: {exc}")
