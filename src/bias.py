"""
Weekly/Daily bias and trend classification — computed from plain candle data,
NOT from ATS. This is the one piece of "what is the chart telling us" that
doesn't depend on relayed numbers or a TradingView webhook at all; it just
needs OHLC history for the relevant timeframe (Weekly candles for weekly
bias, Daily candles for daily bias).

    "Bullish trend = HH + HL. Bearish trend = LL + LH."

This uses a standard fractal swing-point method (a candle whose high is the
highest of its `lookback` neighbors on each side counts as a swing high; low
is the mirror). It is a reasonable, common definition, but it is Claude's
implementation choice, not something Valentino specified numerically — flag
this to him and confirm it matches what he'd call a swing point by eye
before trusting it for live trading. See README "Open questions."
"""

from __future__ import annotations

from .models import Candle, Trend

DEFAULT_LOOKBACK = 2


def find_swing_highs(candles: list[Candle], lookback: int = DEFAULT_LOOKBACK) -> list[int]:
    """Returns the indices into `candles` that are swing highs."""
    highs = []
    for i in range(lookback, len(candles) - lookback):
        window = candles[i - lookback : i + lookback + 1]
        if candles[i].high == max(c.high for c in window):
            highs.append(i)
    return highs


def find_swing_lows(candles: list[Candle], lookback: int = DEFAULT_LOOKBACK) -> list[int]:
    """Returns the indices into `candles` that are swing lows."""
    lows = []
    for i in range(lookback, len(candles) - lookback):
        window = candles[i - lookback : i + lookback + 1]
        if candles[i].low == min(c.low for c in window):
            lows.append(i)
    return lows


def classify_trend(candles: list[Candle], lookback: int = DEFAULT_LOOKBACK) -> Trend:
    """Looks at the two most recent swing highs and two most recent swing
    lows and classifies the trend per Valentino's definition. Returns
    NEUTRAL if there isn't enough clean structure yet (fewer than two of
    either), or if highs and lows disagree (e.g. higher high but lower low —
    a genuinely ambiguous market the decision engine should sit out of
    rather than guess on).
    """
    swing_high_idx = find_swing_highs(candles, lookback)
    swing_low_idx = find_swing_lows(candles, lookback)

    if len(swing_high_idx) < 2 or len(swing_low_idx) < 2:
        return Trend.NEUTRAL

    last_high, prev_high = candles[swing_high_idx[-1]].high, candles[swing_high_idx[-2]].high
    last_low, prev_low = candles[swing_low_idx[-1]].low, candles[swing_low_idx[-2]].low

    higher_high = last_high > prev_high
    higher_low = last_low > prev_low
    lower_high = last_high < prev_high
    lower_low = last_low < prev_low

    if higher_high and higher_low:
        return Trend.BULLISH
    if lower_low and lower_high:
        return Trend.BEARISH
    return Trend.NEUTRAL
