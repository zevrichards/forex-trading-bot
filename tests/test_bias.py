"""
classify_trend_from_boxes() compares the current contraction box to the
immediately preceding one — see bias.py's module docstring for why this
replaced an earlier candle-fractal approach (confirmed wrong-shaped, not
just unconfirmed).
"""

from src.bias import classify_trend_from_boxes
from src.models import Trend


def test_higher_high_and_higher_low_is_bullish():
    trend = classify_trend_from_boxes(
        box_high=1.1700, box_low=1.1650, prev_box_high=1.1650, prev_box_low=1.1600
    )
    assert trend == Trend.BULLISH


def test_lower_low_and_lower_high_is_bearish():
    trend = classify_trend_from_boxes(
        box_high=1.1600, box_low=1.1550, prev_box_high=1.1650, prev_box_low=1.1600
    )
    assert trend == Trend.BEARISH


def test_identical_boxes_is_neutral():
    trend = classify_trend_from_boxes(
        box_high=1.1650, box_low=1.1600, prev_box_high=1.1650, prev_box_low=1.1600
    )
    assert trend == Trend.NEUTRAL


def test_higher_high_but_lower_low_is_neutral():
    # Range widened rather than shifted -- a genuinely ambiguous market,
    # not a clean trend either way.
    trend = classify_trend_from_boxes(
        box_high=1.1700, box_low=1.1550, prev_box_high=1.1650, prev_box_low=1.1600
    )
    assert trend == Trend.NEUTRAL


def test_lower_high_but_higher_low_is_neutral():
    # Range narrowed rather than shifted -- contraction, not a confirmed trend.
    trend = classify_trend_from_boxes(
        box_high=1.1640, box_low=1.1610, prev_box_high=1.1650, prev_box_low=1.1600
    )
    assert trend == Trend.NEUTRAL
