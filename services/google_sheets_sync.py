from __future__ import annotations

import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo


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
    "result",
    "win_score",
]


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
    return dt.astimezone(THAI_TZ).strftime("%Y-%m-%d")


def compute_sheet_result(signal_row) -> tuple[str, str]:
    status = (signal_row["status"] or "").upper()
    tp1_hit = bool(signal_row["tp1_hit_at"])
    tp2_hit = bool(signal_row["tp2_hit_at"])
    tp3_hit = bool(signal_row["tp3_hit_at"])

    if status == "TP3_HIT" or tp3_hit:
        return "TP3_HIT", "1.00"

    if status == "STOPPED":
        if tp2_hit:
            return "TP2_THEN_SL", "0.66"
        if tp1_hit:
            return "TP1_THEN_SL", "0.33"
        return "SL_HIT", "0.00"

    if status == "PARTIAL_TP2":
        return "TP2_ACTIVE", ""

    if status == "PARTIAL_TP1":
        return "TP1_ACTIVE", ""

    if status in {"PENDING_ENTRY", "ACTIVE", "INVALIDATED", "REPLACED"}:
        return status, ""

    return status or "UNKNOWN", ""


def build_signal_sheet_row(signal_row) -> list[str]:
    result, win_score = compute_sheet_result(signal_row)
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
        result,
        win_score,
    ]


def _build_identity_key(row_values: list[str]) -> tuple[str, ...]:
    return tuple(row_values[:9])


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
            self.worksheet.update("A1:K1", [SHEET_HEADERS])

    def upsert_signal(self, signal_row) -> None:
        row_values = build_signal_sheet_row(signal_row)
        identity = _build_identity_key(row_values)
        existing_row = self._find_row(identity)

        if existing_row is None:
            self.worksheet.append_row(row_values, value_input_option="USER_ENTERED")
            return

        self.worksheet.update(
            f"A{existing_row}:K{existing_row}",
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

    try:
        logger.upsert_signal(signal_row)
    except Exception as exc:
        print(f"Google Sheets sync skipped: {exc}")
