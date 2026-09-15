"""
Where the manually-relayed ATS numbers come from.

Confirmed via live testing on the trader's TradingView (see README): Box
High/Low, buy/sell-side liquidity, and the OB Projection level cannot be
read programmatically from ATS Core / ATS V6 with OB Projections. Until
that changes (vendor adds an alert/webhook feature, or doesn't), these
values come from the trader manually, via whatever the simplest possible
relay mechanism turns out to be.

Three more values joined this relay for a different reason, not an ATS
API limitation but a "the trader reads this visually and can't reduce it
to a formula" one: stop_buffer_pips (2026-09-15, docs/trader-strategy-source.md
item 15), weekly_bias/daily_bias (2026-09-15 — never had a computation
path in code to begin with), and structure_stop_level (2026-09-15, for
trade_manager._trail_stop — asking the trader to define "swing point"
directly didn't work; see the 2026-09-15 conversation log).

This module defines one interface (RelaySource) so the rest of the system
never needs to know or care where the numbers physically come from. Two
implementations are provided:

- JSONFileRelaySource: reads a local JSON file. This is what to use for
  development and testing right now — no external accounts needed.
- GoogleSheetRelaySource: reads the last row of a Google Sheet the trader
  (or the developer, for now) types values into directly — no Google Form,
  just a plain sheet with one row per update. The code is implemented; the
  Sheet/service-account setup itself is a manual, one-time step — see
  docs/relay-setup.md.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import Bias


@dataclass(frozen=True)
class RelayValues:
    box_high: float
    box_low: float
    buy_liquidity: float
    sell_liquidity: float
    ob_projection_level: float
    stop_buffer_pips: float
    weekly_bias: Bias
    daily_bias: Bias
    relayed_at: datetime
    structure_stop_level: float | None = None  # optional; see models.MarketState


class RelaySource(ABC):
    @abstractmethod
    def get_latest(self) -> RelayValues:
        """Return the most recently relayed values. Should raise if none
        have ever been supplied — callers must not assume zeros are safe."""


class JSONFileRelaySource(RelaySource):
    """Reads {"box_high": ..., "box_low": ..., "buy_liquidity": ...,
    "sell_liquidity": ..., "ob_projection_level": ..., "stop_buffer_pips": ...,
    "weekly_bias": "bullish"|"bearish"|"neutral", "daily_bias": same,
    "relayed_at": "<ISO8601>", "structure_stop_level": <number, optional>}
    from a local file. Useful for local dev, testing, and as a manual
    stand-in before the real form/sheet exists — the trader (or you, for now)
    can literally hand-edit this file.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def get_latest(self) -> RelayValues:
        if not self.path.exists():
            raise FileNotFoundError(
                f"No relay file at {self.path} — nothing has been relayed yet."
            )
        data = json.loads(self.path.read_text())
        return RelayValues(
            box_high=data["box_high"],
            box_low=data["box_low"],
            buy_liquidity=data["buy_liquidity"],
            sell_liquidity=data["sell_liquidity"],
            ob_projection_level=data["ob_projection_level"],
            stop_buffer_pips=data["stop_buffer_pips"],
            weekly_bias=Bias(data["weekly_bias"]),
            daily_bias=Bias(data["daily_bias"]),
            relayed_at=datetime.fromisoformat(data["relayed_at"]),
            structure_stop_level=data.get("structure_stop_level"),
        )


class GoogleSheetRelaySource(RelaySource):
    """Reads the most recent row of a manually-maintained Google Sheet.

    Expects a plain sheet with a header row and one data row per relayed
    update, columns in this exact order:

        Timestamp | Box High | Box Low | Buy-side Liquidity | Sell-side Liquidity | OB Projection Level | Stop Buffer (pips) | Weekly Bias | Daily Bias | Structure Stop Level

    Weekly Bias / Daily Bias are typed as "bullish", "bearish", or "neutral"
    (case-insensitive). Structure Stop Level is optional — leave the cell
    blank when there's no new higher-low/lower-high to trail the stop to yet;
    only fill it in when the trader would actually move the stop.

    Stop Buffer (pips), Weekly Bias, Daily Bias, and Structure Stop Level are
    all relayed rather than computed by the bot — see
    docs/trader-strategy-source.md and the 2026-09-15 conversation log for
    why: the trader reads all of these visually off his charts, and neither
    "swing point" nor a fixed buffer number translate to how he actually
    thinks about the chart.

    Column A (Timestamp) is typed in by whoever adds the row — see
    docs/relay-setup.md for the exact format. Building the Sheet and the
    service account is a manual, one-time setup step for a human with a
    Google account — see docs/relay-setup.md for the walkthrough. This
    class assumes that's already done and just reads from it.
    """

    _SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    def __init__(
        self,
        sheet_id: str,
        credentials_path: str | Path,
        worksheet_index: int = 0,
    ):
        self.sheet_id = sheet_id
        self.credentials_path = Path(credentials_path)
        self.worksheet_index = worksheet_index
        self._client = None

    def _get_worksheet(self):
        import gspread
        from google.oauth2.service_account import Credentials

        if self._client is None:
            if not self.credentials_path.exists():
                raise FileNotFoundError(
                    f"No service account credentials file at {self.credentials_path} "
                    "— see docs/relay-setup.md."
                )
            creds = Credentials.from_service_account_file(
                str(self.credentials_path), scopes=self._SCOPES
            )
            self._client = gspread.authorize(creds)
        spreadsheet = self._client.open_by_key(self.sheet_id)
        return spreadsheet.get_worksheet(self.worksheet_index)

    def get_latest(self) -> RelayValues:
        rows = self._get_worksheet().get_all_values()
        return self._parse_rows(rows, source=self.sheet_id)

    @staticmethod
    def _parse_rows(rows: list[list[str]], *, source: str) -> RelayValues:
        if len(rows) < 2:
            raise ValueError(
                f"Sheet {source} has no relayed rows yet (only a header, or "
                "empty) — nothing has been entered yet."
            )
        last_row = rows[-1]
        if len(last_row) < 9:
            raise ValueError(
                f"Sheet {source}'s last row has {len(last_row)} columns, expected "
                f"at least 9 (Timestamp, Box High/Low, Buy/Sell Liquidity, OB "
                f"Projection, Stop Buffer, Weekly/Daily Bias — Structure Stop "
                f"Level is an optional 10th): {last_row!r}"
            )
        timestamp_str = last_row[0]
        box_high, box_low, buy_liq, sell_liq, ob_proj, buffer_pips = last_row[1:7]
        weekly_bias_str, daily_bias_str = last_row[7:9]
        structure_stop_str = last_row[9] if len(last_row) > 9 else ""

        try:
            relayed_at = _parse_sheet_timestamp(timestamp_str)
        except ValueError as exc:
            raise ValueError(
                f"Sheet {source}'s last row has an unparseable Timestamp: {last_row!r}"
            ) from exc

        try:
            weekly_bias = _parse_bias(weekly_bias_str)
            daily_bias = _parse_bias(daily_bias_str)
        except ValueError as exc:
            raise ValueError(
                f"Sheet {source}'s last row has an invalid Weekly/Daily Bias "
                f"(must be bullish, bearish, or neutral): {last_row!r}"
            ) from exc

        try:
            return RelayValues(
                box_high=float(box_high),
                box_low=float(box_low),
                buy_liquidity=float(buy_liq),
                sell_liquidity=float(sell_liq),
                ob_projection_level=float(ob_proj),
                stop_buffer_pips=float(buffer_pips),
                weekly_bias=weekly_bias,
                daily_bias=daily_bias,
                relayed_at=relayed_at,
                structure_stop_level=_parse_optional_float(structure_stop_str),
            )
        except ValueError as exc:
            raise ValueError(
                f"Sheet {source}'s last row has a non-numeric value: {last_row!r}"
            ) from exc


_SHEET_TIMESTAMP_FORMATS = (
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


def _parse_sheet_timestamp(value: str) -> datetime:
    """Parses the hand-typed Timestamp column. Accepts a handful of common
    formats (e.g. "9/9/2026 10:00" or "2026-09-09 10:00:00") so whoever's
    entering rows doesn't have to match one exact pattern.

    Always naive (no timezone) — treated as UTC because docs/relay-setup.md
    has you set the Sheet's File > Settings timezone to UTC. If that setting
    ever changes, this will silently be wrong, since the string itself
    carries no timezone info.
    """
    for fmt in _SHEET_TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"Timestamp {value!r} doesn't match any known format "
        f"({', '.join(_SHEET_TIMESTAMP_FORMATS)})"
    )


def _parse_bias(value: str) -> Bias:
    """Case-insensitive parse of a hand-typed Weekly/Daily Bias cell."""
    normalized = value.strip().lower()
    for bias in Bias:
        if bias.value == normalized:
            return bias
    raise ValueError(f"{value!r} isn't one of bullish/bearish/neutral")


def _parse_optional_float(value: str) -> float | None:
    """Structure Stop Level is the one optional relayed value — an empty
    cell means nothing new to trail to yet, not zero."""
    stripped = value.strip()
    return float(stripped) if stripped else None
