"""
Where the manually-relayed ATS numbers come from.

Confirmed via live testing on Valentino's TradingView (see README): Box
High/Low, buy/sell-side liquidity, and the OB Projection level cannot be
read programmatically from ATS Core / ATS V6 with OB Projections. Until
that changes (vendor adds an alert/webhook feature, or doesn't), these
values come from Valentino manually, via whatever the simplest possible
relay mechanism turns out to be.

This module defines one interface (RelaySource) so the rest of the system
never needs to know or care where the numbers physically come from. Two
implementations are provided:

- JSONFileRelaySource: reads a local JSON file. This is what to use for
  development and testing right now — no external accounts needed.
- GoogleSheetRelaySource: a stub. The plan discussed was a Google Form
  feeding a Sheet Valentino fills in from his phone/laptop; this class is
  where that gets wired up once the Form/Sheet actually exists. NOT
  functional yet — raises NotImplementedError so it fails loudly rather
  than silently returning wrong data.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class RelayValues:
    box_high: float
    box_low: float
    buy_liquidity: float
    sell_liquidity: float
    ob_projection_level: float
    relayed_at: datetime


class RelaySource(ABC):
    @abstractmethod
    def get_latest(self) -> RelayValues:
        """Return the most recently relayed values. Should raise if none
        have ever been supplied — callers must not assume zeros are safe."""


class JSONFileRelaySource(RelaySource):
    """Reads {"box_high": ..., "box_low": ..., "buy_liquidity": ...,
    "sell_liquidity": ..., "ob_projection_level": ..., "relayed_at": "<ISO8601>"}
    from a local file. Useful for local dev, testing, and as a manual
    stand-in before the real form/sheet exists — Valentino (or you, for now)
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
            relayed_at=datetime.fromisoformat(data["relayed_at"]),
        )


class GoogleSheetRelaySource(RelaySource):
    """NOT YET IMPLEMENTED. Placeholder for reading the last row of a Google
    Sheet fed by a Google Form. Needs: a service account with read access to
    the Sheet, the Sheet ID, and the Form actually built and shared with
    Valentino. See README "Open questions: relay mechanism."
    """

    def __init__(self, sheet_id: str, credentials_path: str | Path):
        self.sheet_id = sheet_id
        self.credentials_path = credentials_path

    def get_latest(self) -> RelayValues:
        raise NotImplementedError(
            "Google Sheet relay isn't wired up yet — build the Form/Sheet first, "
            "then implement this against the gspread (or Google Sheets API) client."
        )
