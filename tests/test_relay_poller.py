"""
JSONFileRelaySource is straightforward (read a file); the interesting
surface is GoogleSheetRelaySource._parse_rows, which is where a real bug
would live (wrong column order, header-only sheet, non-numeric cell). It's
tested directly with plain row data so these cases don't need a live Sheet
or real credentials. get_latest()'s gspread/Credentials wiring is tested
separately with those two calls monkeypatched.
"""

from datetime import datetime

import pytest

from src.relay_poller import (
    GoogleSheetRelaySource,
    JSONFileRelaySource,
    RelayValues,
    _parse_sheet_timestamp,
)

HEADER = [
    "Timestamp",
    "Box High",
    "Box Low",
    "Buy-side Liquidity",
    "Sell-side Liquidity",
    "OB Projection Level",
    "Stop Buffer (pips)",
]
VALID_ROW = ["9/9/2026 10:00:00", "1.16600", "1.16400", "1.16300", "1.16700", "1.16100", "3.0"]


def test_json_file_relay_source_reads_expected_fields(tmp_path):
    path = tmp_path / "relay_data.json"
    path.write_text(
        '{"box_high": 1.166, "box_low": 1.164, "buy_liquidity": 1.163, '
        '"sell_liquidity": 1.167, "ob_projection_level": 1.161, '
        '"stop_buffer_pips": 3.0, '
        '"relayed_at": "2026-09-09T10:00:00+00:00"}'
    )
    values = JSONFileRelaySource(path).get_latest()
    assert values.box_high == 1.166
    assert values.ob_projection_level == 1.161
    assert values.stop_buffer_pips == 3.0
    assert values.relayed_at == datetime.fromisoformat("2026-09-09T10:00:00+00:00")


def test_json_file_relay_source_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        JSONFileRelaySource(tmp_path / "nope.json").get_latest()


def test_parse_sheet_timestamp_with_seconds():
    assert _parse_sheet_timestamp("9/9/2026 10:00:00") == datetime(2026, 9, 9, 10, 0, 0)


def test_parse_sheet_timestamp_without_seconds():
    assert _parse_sheet_timestamp("9/9/2026 10:00") == datetime(2026, 9, 9, 10, 0, 0)


def test_parse_sheet_timestamp_iso_style():
    assert _parse_sheet_timestamp("2026-09-09 10:00:00") == datetime(2026, 9, 9, 10, 0, 0)


def test_parse_sheet_timestamp_unrecognized_raises():
    with pytest.raises(ValueError, match="doesn't match"):
        _parse_sheet_timestamp("not a date")


def test_parse_rows_reads_last_row():
    older_row = ["9/8/2026 09:00:00", "1.1", "1.0", "1.05", "1.15", "0.95", "2.0"]
    rows = [HEADER, older_row, VALID_ROW]

    values = GoogleSheetRelaySource._parse_rows(rows, source="sheet123")

    assert values == RelayValues(
        box_high=1.166,
        box_low=1.164,
        buy_liquidity=1.163,
        sell_liquidity=1.167,
        ob_projection_level=1.161,
        stop_buffer_pips=3.0,
        relayed_at=datetime(2026, 9, 9, 10, 0, 0),
    )


def test_parse_rows_header_only_raises():
    with pytest.raises(ValueError, match="no relayed rows yet"):
        GoogleSheetRelaySource._parse_rows([HEADER], source="sheet123")


def test_parse_rows_empty_sheet_raises():
    with pytest.raises(ValueError, match="no relayed rows yet"):
        GoogleSheetRelaySource._parse_rows([], source="sheet123")


def test_parse_rows_too_few_columns_raises():
    short_row = ["9/9/2026 10:00:00", "1.166", "1.164"]
    with pytest.raises(ValueError, match="expected"):
        GoogleSheetRelaySource._parse_rows([HEADER, short_row], source="sheet123")


def test_parse_rows_non_numeric_value_raises():
    bad_row = ["9/9/2026 10:00:00", "not-a-number", "1.164", "1.163", "1.167", "1.161", "3.0"]
    with pytest.raises(ValueError, match="non-numeric"):
        GoogleSheetRelaySource._parse_rows([HEADER, bad_row], source="sheet123")


def test_parse_rows_bad_timestamp_raises_with_clear_message():
    bad_row = ["not a date", "1.166", "1.164", "1.163", "1.167", "1.161", "3.0"]
    with pytest.raises(ValueError, match="unparseable Timestamp"):
        GoogleSheetRelaySource._parse_rows([HEADER, bad_row], source="sheet123")


def test_get_latest_wires_worksheet_rows_through_parse_rows(monkeypatch, tmp_path):
    """Confirms get_latest() actually calls get_all_values() on the worksheet
    it opens and feeds the result to _parse_rows — without touching real
    gspread auth or network calls."""
    creds_path = tmp_path / "creds.json"
    creds_path.write_text("{}")

    class FakeWorksheet:
        def get_all_values(self):
            return [HEADER, VALID_ROW]

    source = GoogleSheetRelaySource(sheet_id="sheet123", credentials_path=creds_path)
    monkeypatch.setattr(source, "_get_worksheet", lambda: FakeWorksheet())

    values = source.get_latest()

    assert values.box_high == 1.166


def test_get_latest_missing_credentials_file_raises(tmp_path):
    source = GoogleSheetRelaySource(
        sheet_id="sheet123", credentials_path=tmp_path / "missing-creds.json"
    )
    with pytest.raises(FileNotFoundError, match="credentials"):
        source._get_worksheet()
