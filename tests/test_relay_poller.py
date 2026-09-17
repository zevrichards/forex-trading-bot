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

from src.models import Bias
from src.relay_poller import (
    GoogleSheetRelaySource,
    JSONFileRelaySource,
    RelayValues,
    _parse_bias,
    _parse_optional_float,
    _parse_sheet_timestamp,
)

HEADER = [
    "Timestamp",
    "Box High",
    "Box Low",
    "Previous Box High",
    "Previous Box Low",
    "Buy-side Liquidity",
    "Sell-side Liquidity",
    "OB Projection Level",
    "Stop Buffer (pips)",
    "Weekly Bias",
    "Daily Bias",
    "Structure Stop Level",
]
VALID_ROW = [
    "9/9/2026 10:00:00",
    "1.16600",
    "1.16400",
    "1.16500",
    "1.16300",
    "1.16300",
    "1.16700",
    "1.16100",
    "3.0",
    "bullish",
    "bullish",
    "",
]


def test_json_file_relay_source_reads_expected_fields(tmp_path):
    path = tmp_path / "relay_data.json"
    path.write_text(
        '{"box_high": 1.166, "box_low": 1.164, "prev_box_high": 1.165, '
        '"prev_box_low": 1.163, "buy_liquidity": 1.163, '
        '"sell_liquidity": 1.167, "ob_projection_level": 1.161, '
        '"stop_buffer_pips": 3.0, "weekly_bias": "bullish", '
        '"daily_bias": "bearish", "structure_stop_level": 1.15900, '
        '"relayed_at": "2026-09-09T10:00:00+00:00"}'
    )
    values = JSONFileRelaySource(path).get_latest()
    assert values.box_high == 1.166
    assert values.prev_box_high == 1.165
    assert values.prev_box_low == 1.163
    assert values.ob_projection_level == 1.161
    assert values.stop_buffer_pips == 3.0
    assert values.weekly_bias == Bias.BULLISH
    assert values.daily_bias == Bias.BEARISH
    assert values.structure_stop_level == 1.15900
    assert values.relayed_at == datetime.fromisoformat("2026-09-09T10:00:00+00:00")


def test_json_file_relay_source_structure_stop_level_defaults_to_none(tmp_path):
    path = tmp_path / "relay_data.json"
    path.write_text(
        '{"box_high": 1.166, "box_low": 1.164, "prev_box_high": 1.165, '
        '"prev_box_low": 1.163, "buy_liquidity": 1.163, '
        '"sell_liquidity": 1.167, "ob_projection_level": 1.161, '
        '"stop_buffer_pips": 3.0, "weekly_bias": "bullish", '
        '"daily_bias": "bullish", '
        '"relayed_at": "2026-09-09T10:00:00+00:00"}'
    )
    values = JSONFileRelaySource(path).get_latest()
    assert values.structure_stop_level is None


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


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("bullish", Bias.BULLISH),
        ("Bullish", Bias.BULLISH),
        ("  BEARISH  ", Bias.BEARISH),
        ("neutral", Bias.NEUTRAL),
    ],
)
def test_parse_bias_case_insensitive(raw, expected):
    assert _parse_bias(raw) == expected


def test_parse_bias_invalid_raises():
    with pytest.raises(ValueError, match="isn't one of"):
        _parse_bias("sideways")


def test_parse_optional_float_blank_is_none():
    assert _parse_optional_float("") is None
    assert _parse_optional_float("   ") is None


def test_parse_optional_float_parses_number():
    assert _parse_optional_float("1.15900") == 1.15900


def test_parse_rows_reads_last_row():
    older_row = [
        "9/8/2026 09:00:00",
        "1.1",
        "1.0",
        "1.08",
        "0.98",
        "1.05",
        "1.15",
        "0.95",
        "2.0",
        "bearish",
        "bearish",
        "1.09000",
    ]
    rows = [HEADER, older_row, VALID_ROW]

    values = GoogleSheetRelaySource._parse_rows(rows, source="sheet123")

    assert values == RelayValues(
        box_high=1.166,
        box_low=1.164,
        prev_box_high=1.165,
        prev_box_low=1.163,
        buy_liquidity=1.163,
        sell_liquidity=1.167,
        ob_projection_level=1.161,
        stop_buffer_pips=3.0,
        weekly_bias=Bias.BULLISH,
        daily_bias=Bias.BULLISH,
        relayed_at=datetime(2026, 9, 9, 10, 0, 0),
        structure_stop_level=None,
    )


def test_parse_rows_structure_stop_level_populated():
    row_with_level = VALID_ROW[:11] + ["1.15900"]
    values = GoogleSheetRelaySource._parse_rows([HEADER, row_with_level], source="sheet123")
    assert values.structure_stop_level == 1.15900


def test_parse_rows_structure_stop_level_column_missing_entirely():
    """11-column row (no 12th column at all) — gspread can drop a trailing
    empty column rather than returning it as ''. Must still parse."""
    row_without_12th = VALID_ROW[:11]
    values = GoogleSheetRelaySource._parse_rows([HEADER, row_without_12th], source="sheet123")
    assert values.structure_stop_level is None


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
    bad_row = VALID_ROW.copy()
    bad_row[1] = "not-a-number"
    with pytest.raises(ValueError, match="non-numeric"):
        GoogleSheetRelaySource._parse_rows([HEADER, bad_row], source="sheet123")


def test_parse_rows_bad_timestamp_raises_with_clear_message():
    bad_row = VALID_ROW.copy()
    bad_row[0] = "not a date"
    with pytest.raises(ValueError, match="unparseable Timestamp"):
        GoogleSheetRelaySource._parse_rows([HEADER, bad_row], source="sheet123")


def test_parse_rows_invalid_bias_raises_with_clear_message():
    bad_row = VALID_ROW.copy()
    bad_row[9] = "sideways"
    with pytest.raises(ValueError, match="invalid Weekly/Daily Bias"):
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
    assert values.weekly_bias == Bias.BULLISH


def test_get_latest_missing_credentials_file_raises(tmp_path):
    source = GoogleSheetRelaySource(
        sheet_id="sheet123", credentials_path=tmp_path / "missing-creds.json"
    )
    with pytest.raises(FileNotFoundError, match="credentials"):
        source._get_worksheet()
