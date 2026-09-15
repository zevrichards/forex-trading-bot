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

    box_high / box_low / buy_liquidity / sell_liquidity / ob_projection_level /
    stop_buffer_pips / weekly_bias / daily_bias / structure_stop_level are all
    manually relayed (see relay_poller.py) — the trader reads all of them
    visually off ATS/his charts, so none of them are computed from raw candle
    data. stop_buffer_pips is relayed rather than a fixed constant because the
    stop buffer is structural/contextual, not one universal pip number.
    weekly_bias/daily_bias are relayed rather than computed because the
    trader's own rules describe them as a visual read of ATS's trend line +
    colored dots + structure, not a formula. structure_stop_level is the
    current higher-low (longs) / lower-high (shorts) the trader would trail
    the stop to, relayed the same way, since detecting that algorithmically
    turned out to be the same "ask him to explain a concept he doesn't think
    in those terms" problem as the others (see docs/trader-strategy-source.md
    and the 2026-09-15 conversation log). bias.py's candle-based classify_trend()
    predates this and is not wired into the live pipeline.

    trend comes from "ATS MTF Trend V1", which IS live-readable (see webhook_receiver.py)
    — the one field here that isn't manually relayed.
    """

    symbol: str
    timestamp: datetime
    current_price: float

    box_high: float
    box_low: float
    buy_liquidity: float   # blue dotted line
    sell_liquidity: float  # yellow dotted line
    ob_projection_level: float  # for stop placement
    stop_buffer_pips: float  # relayed per-trade, not a fixed constant — see stop_placement.py

    weekly_bias: Bias
    daily_bias: Bias
    trend: Trend

    structure_stop_level: float | None = None  # relayed; see trade_manager._trail_stop

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
