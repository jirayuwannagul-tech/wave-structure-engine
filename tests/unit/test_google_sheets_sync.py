from services.google_sheets_sync import (
    SHEET_HEADERS,
    GoogleSheetsSignalLogger,
    build_signal_sheet_row,
    compute_sheet_result,
    compute_signal_tracking,
    safe_sync_signal,
    should_sync_signal_to_sheet,
)


def _signal_row(
    status: str = "PENDING_ENTRY",
    tp1_hit_at=None,
    tp2_hit_at=None,
    tp3_hit_at=None,
    close_reason=None,
    current_price=None,
    managed_stop_loss=None,
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
        "close_reason": close_reason if close_reason is not None else ("STOP_LOSS" if status == "STOPPED" else None),
        "current_price": current_price if current_price is not None else 68977.91,
        "managed_stop_loss": managed_stop_loss,
    }


class FakeWorksheet:
    def __init__(self):
        self.rows = [SHEET_HEADERS.copy()]

    def row_values(self, row_number: int):
        return self.rows[row_number - 1] if row_number <= len(self.rows) else []

    def update(self, target, values, value_input_option=None):
        row_number = int(target.split(":")[0][1:])
        while len(self.rows) < row_number:
            self.rows.append([""] * len(SHEET_HEADERS))
        self.rows[row_number - 1] = list(values[0])

    def append_row(self, row_values, value_input_option=None):
        self.rows.append(list(row_values))

    def get_all_values(self):
        return [list(row) for row in self.rows]


def _column(name: str) -> int:
    return SHEET_HEADERS.index(name)


def test_compute_sheet_result_closed_outcomes():
    assert compute_sheet_result(_signal_row(status="STOPPED")) == ("SL_HIT", "0.00")
    assert compute_sheet_result(_signal_row(status="STOPPED", tp1_hit_at="2026-03-12T01:00:00+00:00")) == (
        "TP1_THEN_SL",
        "33.33",
    )
    assert compute_sheet_result(
        _signal_row(
            status="STOPPED",
            tp1_hit_at="2026-03-12T01:00:00+00:00",
            tp2_hit_at="2026-03-12T02:00:00+00:00",
        )
    ) == ("TP2_THEN_SL", "66.67")
    assert compute_sheet_result(_signal_row(status="TP3_HIT", tp3_hit_at="2026-03-12T03:00:00+00:00")) == (
        "TP3_HIT",
        "100.00",
    )


def test_compute_signal_tracking_marks_targets_and_stop_loss():
    tracking = compute_signal_tracking(
        _signal_row(
            status="STOPPED",
            tp1_hit_at="2026-03-12T01:00:00+00:00",
        )
    )

    assert tracking == {
        "result": "TP1_THEN_SL",
        "tp1_mark": "✓",
        "tp2_mark": "",
        "tp3_mark": "",
        "sl_mark": "✗",
        "realized_rr": "-0.5232",
        "win_rate_pct": "33.33",
    }


def test_compute_signal_tracking_uses_managed_stop_loss_without_rewriting_plan():
    tracking = compute_signal_tracking(
        _signal_row(
            status="STOPPED",
            tp1_hit_at="2026-03-12T01:00:00+00:00",
            managed_stop_loss=68977.91,
        )
    )

    assert tracking["result"] == "TP1_THEN_SL"
    assert tracking["realized_rr"] == "0.078"
    assert tracking["win_rate_pct"] == "33.33"


def test_build_signal_sheet_row_formats_trade_journal_columns():
    row = build_signal_sheet_row(
        _signal_row(
            status="PARTIAL_TP1",
            tp1_hit_at="2026-03-12T01:00:00+00:00",
        )
    )

    assert row == [
        "2026-03-12 07:15:00",
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
        "✓",
        "",
        "",
        "",
        "TP1_ACTIVE",
        "0.078",
        "33.33",
    ]


def test_google_sheets_logger_upserts_existing_signal_row():
    worksheet = FakeWorksheet()
    logger = GoogleSheetsSignalLogger(
        spreadsheet_id="test",
        credentials_path="storage/credentials.json",
        worksheet_name="wave_log",
        worksheet=worksheet,
    )

    active = _signal_row(status="ACTIVE")
    logger.upsert_signal(active)

    assert len(worksheet.rows) == 2
    assert worksheet.rows[1][_column("side")] == "SHORT"
    assert worksheet.rows[1][_column("rr_tp1")] == "0.195"
    assert worksheet.rows[1][_column("result")] == "ACTIVE"

    stopped = _signal_row(status="STOPPED", tp1_hit_at="2026-03-12T01:00:00+00:00")
    logger.upsert_signal(stopped)

    assert len(worksheet.rows) == 2
    assert worksheet.rows[1][_column("tp1_mark")] == "✓"
    assert worksheet.rows[1][_column("sl_mark")] == "✗"
    assert worksheet.rows[1][_column("result")] == "TP1_THEN_SL"
    assert worksheet.rows[1][_column("realized_rr")] == "-0.5232"
    assert worksheet.rows[1][_column("win_rate_pct")] == "33.33"


def test_compute_signal_tracking_time_stop_without_sl_mark():
    tracking = compute_signal_tracking(
        _signal_row(
            status="STOPPED",
            close_reason="TIME_STOP",
            current_price=68800.0,
        )
    )

    assert tracking["result"] == "TIME_STOP"
    assert tracking["sl_mark"] == ""
    assert tracking["realized_rr"] != ""


def test_compute_signal_tracking_opposite_structure_exit_without_sl_mark():
    tracking = compute_signal_tracking(
        _signal_row(
            status="STOPPED",
            close_reason="OPPOSITE_STRUCTURE",
            current_price=68850.0,
        )
    )

    assert tracking["result"] == "OPPOSITE_STRUCTURE_EXIT"
    assert tracking["sl_mark"] == ""
    assert tracking["realized_rr"] != ""


def test_should_sync_signal_to_sheet_only_after_real_entry():
    assert should_sync_signal_to_sheet(_signal_row(status="PENDING_ENTRY")) is False
    assert should_sync_signal_to_sheet(_signal_row(status="INVALIDATED")) is False
    assert should_sync_signal_to_sheet(_signal_row(status="REPLACED")) is False
    assert should_sync_signal_to_sheet(_signal_row(status="ACTIVE")) is True
    assert should_sync_signal_to_sheet(_signal_row(status="PARTIAL_TP1")) is True
    assert should_sync_signal_to_sheet(_signal_row(status="STOPPED")) is True


def test_safe_sync_signal_skips_pending_entry_and_appends_on_active():
    worksheet = FakeWorksheet()
    logger = GoogleSheetsSignalLogger(
        spreadsheet_id="test",
        credentials_path="storage/credentials.json",
        worksheet_name="wave_log",
        worksheet=worksheet,
    )

    safe_sync_signal(_signal_row(status="PENDING_ENTRY"), logger)
    assert worksheet.rows == [SHEET_HEADERS.copy()]

    safe_sync_signal(_signal_row(status="ACTIVE"), logger)
    assert len(worksheet.rows) == 2
    assert worksheet.rows[1][_column("result")] == "ACTIVE"
    assert worksheet.rows[1][_column("realized_rr")] == ""
