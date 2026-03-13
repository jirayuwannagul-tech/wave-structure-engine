from services.google_sheets_sync import (
    SHEET_HEADERS,
    GoogleSheetsSignalLogger,
    build_signal_sheet_row,
    compute_sheet_result,
)


def _signal_row(
    status: str = "PENDING_ENTRY",
    tp1_hit_at=None,
    tp2_hit_at=None,
    tp3_hit_at=None,
):
    return {
        "created_at": "2026-03-12T00:15:00+00:00",
        "symbol": "BTCUSDT",
        "timeframe": "4H",
        "side": "SHORT",
        "entry_price": 68977.91,
        "stop_loss": 71321.0,
        "tp1": 68521.91,
        "tp2": 67760.55752,
        "tp3": 66792.07238,
        "rr_tp1": 0.195,
        "rr_tp2": 0.521,
        "rr_tp3": 0.934,
        "status": status,
        "tp1_hit_at": tp1_hit_at,
        "tp2_hit_at": tp2_hit_at,
        "tp3_hit_at": tp3_hit_at,
    }


class FakeWorksheet:
    def __init__(self):
        self.rows = [SHEET_HEADERS.copy()]

    def row_values(self, row_number: int):
        return self.rows[row_number - 1] if row_number <= len(self.rows) else []

    def update(self, target, values, value_input_option=None):
        if target == "A1:N1":
            self.rows[0] = list(values[0])
            return

        row_number = int(target.split(":")[0][1:])
        while len(self.rows) < row_number:
            self.rows.append([""] * len(SHEET_HEADERS))
        self.rows[row_number - 1] = list(values[0])

    def append_row(self, row_values, value_input_option=None):
        self.rows.append(list(row_values))

    def get_all_values(self):
        return [list(row) for row in self.rows]


def test_compute_sheet_result_closed_outcomes():
    assert compute_sheet_result(_signal_row(status="STOPPED")) == ("SL_HIT", "0.00")
    assert compute_sheet_result(_signal_row(status="STOPPED", tp1_hit_at="2026-03-12T01:00:00+00:00")) == (
        "TP1_THEN_SL",
        "0.33",
    )
    assert compute_sheet_result(
        _signal_row(
            status="STOPPED",
            tp1_hit_at="2026-03-12T01:00:00+00:00",
            tp2_hit_at="2026-03-12T02:00:00+00:00",
        )
    ) == ("TP2_THEN_SL", "0.66")
    assert compute_sheet_result(_signal_row(status="TP3_HIT", tp3_hit_at="2026-03-12T03:00:00+00:00")) == (
        "TP3_HIT",
        "1.00",
    )


def test_build_signal_sheet_row_formats_expected_columns():
    row = build_signal_sheet_row(_signal_row(status="PARTIAL_TP1", tp1_hit_at="2026-03-12T01:00:00+00:00"))

    assert row == [
        "2026-03-12",
        "BTCUSDT",
        "4H",
        "SHORT",
        "68977.91",
        "71321",
        "68521.91",
        "67760.55752",
        "66792.07238",
        "0.195",
        "0.521",
        "0.934",
        "TP1_ACTIVE",
        "",
    ]


def test_google_sheets_logger_upserts_existing_signal_row():
    worksheet = FakeWorksheet()
    logger = GoogleSheetsSignalLogger(
        spreadsheet_id="test",
        credentials_path="storage/credentials.json",
        worksheet_name="wave_log",
        worksheet=worksheet,
    )

    pending = _signal_row(status="PENDING_ENTRY")
    logger.upsert_signal(pending)

    assert len(worksheet.rows) == 2
    assert worksheet.rows[1][3] == "SHORT"
    assert worksheet.rows[1][9] == "0.195"
    assert worksheet.rows[1][12] == "PENDING_ENTRY"

    stopped = _signal_row(status="STOPPED", tp1_hit_at="2026-03-12T01:00:00+00:00")
    logger.upsert_signal(stopped)

    assert len(worksheet.rows) == 2
    assert worksheet.rows[1][12] == "TP1_THEN_SL"
    assert worksheet.rows[1][13] == "0.33"
