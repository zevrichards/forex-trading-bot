"""
buffer_pips is a required, relayed-per-trade value (see relay_poller.py /
models.MarketState.stop_buffer_pips) rather than a fixed constant — these
tests exercise calculate_stop_price with explicit buffer values on both
directions, plus stop_distance_pips.
"""

import pytest

from src.models import Direction
from src.stop_placement import PIP_SIZE, calculate_stop_price, stop_distance_pips


def test_long_stop_goes_below_ob_projection_minus_buffer():
    stop = calculate_stop_price(1.16100, Direction.LONG, buffer_pips=3.0)
    assert stop == pytest.approx(1.16100 - 3.0 * PIP_SIZE)


def test_short_stop_goes_above_ob_projection_plus_buffer():
    stop = calculate_stop_price(1.16100, Direction.SHORT, buffer_pips=3.0)
    assert stop == pytest.approx(1.16100 + 3.0 * PIP_SIZE)


def test_zero_buffer_places_stop_exactly_at_ob_projection():
    assert calculate_stop_price(1.16100, Direction.LONG, buffer_pips=0.0) == 1.16100


def test_stop_distance_pips_is_sign_agnostic():
    assert stop_distance_pips(1.16300, 1.16100) == pytest.approx(20.0)
    assert stop_distance_pips(1.16100, 1.16300) == pytest.approx(20.0)
