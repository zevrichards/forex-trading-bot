"""
Initial stop placement.

    "Stop is outside the ATS Order Block Projection, with a small manually
    determined buffer."

ob_projection_level is a relayed ATS value (see models.MarketState). The
buffer is a config value, not a chart-read one — Valentino called it
"manually determined," so it's exposed here as a parameter rather than
hard-coded, and should be confirmed with him directly (see README "Open
questions").
"""

from __future__ import annotations

from .models import Direction

DEFAULT_BUFFER_PIPS = 2.0  # PLACEHOLDER — confirm the real number with Valentino
PIP_SIZE = 0.0001  # EUR/USD; JPY pairs would use 0.01, not used here but noted for reuse


def calculate_stop_price(
    ob_projection_level: float,
    direction: Direction,
    buffer_pips: float = DEFAULT_BUFFER_PIPS,
) -> float:
    """Long: stop goes below the OB projection level, minus the buffer.
    Short: stop goes above the OB projection level, plus the buffer.
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
