"""
Shared data types for the EUR/USD bot.

Every field here traces back to a specific line in the trader's rules (see
README.md for the full mapping). Nothing in this file makes a trading
decision — it's just the shape of the data the rest of the system passes
around.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Bias(str, Enum):
    """Weekly/Daily directional bias. 'Weekly + Daily bias must agree with the trade direction.'"""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class Trend(str, Enum):
    """'Bullish trend = HH + HL. Bearish trend = LL + LH.' Neutral covers everything else
    (e.g. a clean trend hasn't formed yet) — treated as a no-trade condition."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class MarketState:
    """A snapshot of everything the decision engine needs, at one point in time.

    box_high / box_low / buy_liquidity / sell_liquidity / ob_projection_level are
    ATS Core / ATS V6 with OB Projections outputs. As of v1 these arrive via manual
    relay (see relay_poller.py) — the field names and meaning don't change if that
    later gets replaced with a live feed.

    trend comes from "ATS MTF Trend V1", which IS live-readable (see webhook_receiver.py).
    weekly_bias / daily_bias are computed independently from swing structure (see
    bias.py) and don't depend on ATS at all.
    """

    symbol: str
    timestamp: datetime
    current_price: float

    box_high: float
    box_low: float
    buy_liquidity: float   # blue dotted line
    sell_liquidity: float  # yellow dotted line
    ob_projection_level: float  # for stop placement

    weekly_bias: Bias
    daily_bias: Bias
    trend: Trend

    @property
    def value(self) -> float:
        """'Value is the middle of the Box.' Pure math — never relayed, always derived."""
        return (self.box_high + self.box_low) / 2.0


@dataclass(frozen=True)
class Candle:
    """One OHLC bar on whatever timeframe the caller is using (Weekly or
    Daily, for bias.py's purposes)."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class Position:
    """An open trade and everything needed to manage it per the trader's rules."""

    direction: Direction
    entry_price: float
    stop_price: float
    size_lots: float
    entry_box_high: float
    entry_box_low: float
    partial_closed: bool = False
    breakeven_moved: bool = False


@dataclass(frozen=True)
class EntryDecision:
    """Output of the entry decision engine. action is one of BUY / SELL / WAIT / NO_TRADE."""

    action: str
    reason: str


@dataclass(frozen=True)
class ManagementAction:
    """One instruction coming out of trade_manager.manage_position()."""

    kind: str  # "HOLD" | "PARTIAL_CLOSE" | "MOVE_STOP" | "FULL_CLOSE"
    reason: str
    new_stop_price: float | None = None
    close_fraction: float | None = None
