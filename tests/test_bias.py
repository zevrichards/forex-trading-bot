"""
Hand-built candle sequences with known, verified swing points, used to check
classify_trend() against the trader's definition:

    "Bullish trend = HH + HL. Bearish trend = LL + LH."

Each sequence below has exactly two swing highs and two swing lows under the
default lookback=2 fractal method (verified by hand when written — see
bias.py for how swing points are found). If bias.py's swing-detection logic
changes, these fixtures may need rebuilding, not just the assertions.
"""

from datetime import datetime, timedelta, timezone

from src.bias import classify_trend
from src.models import Candle, Trend

START = datetime(2026, 9, 1, tzinfo=timezone.utc)

# Highs/lows only — open/close aren't used by classify_trend, set equal to
# the midpoint for simplicity.
_BULLISH_HL = [
    (1.1080, 1.1060),
    (1.1060, 1.1020),
    (1.1040, 1.0950),  # swing low L1 = 1.0950
    (1.1070, 1.1000),
    (1.1090, 1.1020),
    (1.1110, 1.1040),
    (1.1130, 1.1060),
    (1.1150, 1.1080),  # swing high H1 = 1.1150
    (1.1120, 1.1060),
    (1.1100, 1.1040),
    (1.1080, 1.1020),
    (1.1060, 1.1010),
    (1.1050, 1.1000),  # swing low L2 = 1.1000 (> L1 -> higher low)
    (1.1080, 1.1020),
    (1.1110, 1.1040),
    (1.1140, 1.1070),
    (1.1170, 1.1100),
    (1.1200, 1.1130),  # swing high H2 = 1.1200 (> H1 -> higher high)
    (1.1160, 1.1100),
    (1.1130, 1.1070),
]


def _build_candles(highs_lows: list[tuple[float, float]]) -> list[Candle]:
    return [
        Candle(
            timestamp=START + timedelta(days=i),
            open=(h + l) / 2,
            high=h,
            low=l,
            close=(h + l) / 2,
        )
        for i, (h, l) in enumerate(highs_lows)
    ]


def test_higher_highs_and_higher_lows_classify_bullish():
    candles = _build_candles(_BULLISH_HL)
    assert classify_trend(candles) == Trend.BULLISH


def test_lower_lows_and_lower_highs_classify_bearish():
    # Reversing the bullish sequence in time turns "higher high then higher
    # low" into "lower high then lower low" -- see file docstring in
    # test_bias.py history / the plan doc for why this mirroring is valid:
    # classify_trend only looks at high/low values, never timestamp order
    # beyond most-recent-first.
    reversed_hl = list(reversed(_BULLISH_HL))
    candles = _build_candles(reversed_hl)
    assert classify_trend(candles) == Trend.BEARISH


def test_insufficient_structure_is_neutral():
    # Only the first 10 bars -- just one clean swing high/low pair forms,
    # not the two-of-each classify_trend needs.
    candles = _build_candles(_BULLISH_HL[:10])
    assert classify_trend(candles) == Trend.NEUTRAL


def test_conflicting_higher_high_but_lower_low_is_neutral():
    conflicting = list(_BULLISH_HL)
    # Drop the second swing low well below the first -> higher high, but a
    # LOWER low -- a genuinely ambiguous market, not a clean trend either way.
    conflicting[12] = (1.1050, 1.0900)
    candles = _build_candles(conflicting)
    assert classify_trend(candles) == Trend.NEUTRAL
