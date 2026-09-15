"""
Initial stop placement.

    "Stop is outside the ATS Order Block Projection, with a small manually
    determined buffer."

ob_projection_level is a relayed ATS value (see models.MarketState). The
buffer is NOT a fixed constant — the trader's own source material describes
it as structural/contextual ("not simply an arbitrary 10 or 20 pips... sits
slightly below it depending on structure", docs/trader-strategy-source.md
item 15), so buffer_pips is a required, per-trade relayed value (see
models.MarketState.stop_buffer_pips / relay_poller.RelayValues), not a
module-level default.
"""

from __future__ import annotations

from .models import Direction

PIP_SIZE = 0.0001  # EUR/USD; JPY pairs would use 0.01, not used here but noted for reuse


def calculate_stop_price(
    ob_projection_level: float,
    direction: Direction,
    buffer_pips: float,
) -> float:
    """Long: stop goes below the OB projection level, minus the buffer.
    Short: stop goes above the OB projection level, plus the buffer.
    buffer_pips is required — see module docstring for why there's no default.
    """
    buffer_price = buffer_pips * PIP_SIZE
    if direction == Direction.LONG:
        return ob_projection_level - buffer_price
    else:
        return ob_projection_level + buffer_price


def stop_distance_pips(entry_price: float, stop_price: float) -> float:
    """Absolute distance between entry and stop, in pips. Sign-agnostic on
    purpose — risk_sizing only needs the magnitude."""
    return abs(entry_price - stop_price) / PIP_SIZE
