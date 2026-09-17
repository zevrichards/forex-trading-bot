"""
Trend classification — box-to-box comparison, per ATS's own "Master
Pattern" framework. Confirmed 2026-09-15 from trade ATS's own training
course (transcripts the trader sent, see docs/master-pattern-course-notes.md
for the distilled quotes/citations):

    "Contraction is identified as simultaneous lower highs and higher lows
    at the same time, which is a contracting of a price range... Trend is
    the price movement between the previous contraction point and a new
    contraction point established at higher or lower prices."

    "Bullish trend = HH + HL. Bearish trend = LL + LH." (the trader's own
    quantified rule, docs/trader-strategy-source.md Part 2)

An earlier version of this module tried to detect "swing points" from raw
candle data using a 5-candle fractal method. That was confirmed wrong-
shaped, not just unconfirmed: the trader doesn't think in isolated candle
peaks ("swing point? you mean liquidity?", 2026-09-15 conversation log),
and the course his own ATS indicator is built from defines structure in
terms of the Box (contraction), not individual candles. This version
instead compares the CURRENT box (box_high/box_low, already manually
relayed every update) against the PREVIOUS confirmed box
(prev_box_high/prev_box_low, relayed the same way, since both are visible
on the trader's chart at any moment) — no candle-history fetch or fractal
detection needed at all.
"""

from __future__ import annotations

from .models import Trend


def classify_trend_from_boxes(
    box_high: float,
    box_low: float,
    prev_box_high: float,
    prev_box_low: float,
) -> Trend:
    """'Bullish trend = HH + HL. Bearish trend = LL + LH.' Compares the
    current contraction box to the immediately preceding one. Returns
    NEUTRAL if the boxes are identical, or if high/low disagree (e.g. a
    higher high but a lower low) — a genuinely ambiguous market the
    decision engine should sit out of rather than guess on.
    """
    higher_high = box_high > prev_box_high
    higher_low = box_low > prev_box_low
    lower_high = box_high < prev_box_high
    lower_low = box_low < prev_box_low

    if higher_high and higher_low:
        return Trend.BULLISH
    if lower_low and lower_high:
        return Trend.BEARISH
    return Trend.NEUTRAL
