"""
Position sizing — the one part of the trader's rules that was already a
precise formula, not a chart-reading judgment call.

Rule, verbatim from their message:
    "Your account is $100,000. Your maximum risk per trade: 0.5%. Therefore:
    Maximum loss = $500. That's the number we protect. Not the lot size.
    Not the number of pips. $500 is the risk budget."

    "For EUR/USD, approximately: 1 standard lot = $10 per pip.
    Lot size = $500 / (stop-loss pips x $10)"

Every value in the trader's worked lookup table is reproduced as a test in
tests/test_risk_sizing.py — this file exists to match that table exactly,
not to approximate it.
"""

from __future__ import annotations

DEFAULT_RISK_PCT = 0.005  # 0.5%, "with no exceptions" per the trader's rules
DEFAULT_PIP_VALUE_PER_LOT = 10.0  # approx. USD per pip per standard lot on EUR/USD


def risk_amount(account_balance: float, risk_pct: float = DEFAULT_RISK_PCT) -> float:
    """The fixed dollar amount allowed to be lost on a single trade."""
    return account_balance * risk_pct


def calculate_lot_size(
    account_balance: float,
    stop_distance_pips: float,
    risk_pct: float = DEFAULT_RISK_PCT,
    pip_value_per_lot: float = DEFAULT_PIP_VALUE_PER_LOT,
) -> float:
    """Lot size = risk budget / (stop distance in pips x pip value per lot).

    Raises ValueError on a non-positive stop distance rather than silently
    returning something nonsensical — an invalid stop distance means the
    setup should be rejected upstream (see decision_engine's stop check),
    not sized.
    """
    if stop_distance_pips <= 0:
        raise ValueError("stop_distance_pips must be positive")

    lots = risk_amount(account_balance, risk_pct) / (stop_distance_pips * pip_value_per_lot)
    return round(lots, 2)


MIN_LOT_STEP = 0.01  # standard minimum lot increment most brokers support


def exceeds_risk_budget(
    account_balance: float,
    stop_distance_pips: float,
    proposed_lots: float,
    risk_pct: float = DEFAULT_RISK_PCT,
    pip_value_per_lot: float = DEFAULT_PIP_VALUE_PER_LOT,
    min_lot_step: float = MIN_LOT_STEP,
) -> bool:
    """'When your calculated lot size creates more than $500 risk' -> don't trade.

    Used as a final guard in the decision engine so a manually overridden or
    corrupted lot size can never silently exceed the risk budget.

    Tolerance note: this caught a real bug during testing. calculate_lot_size
    rounds to the nearest 0.01 lot (matching the trader's own table, e.g. 30
    pips -> 1.67 lots), but lots can only be sized in 0.01 steps at all, so
    hitting the risk budget exactly is generally impossible -- 1.67 lots on a
    30-pip stop is actually $501, one dollar over $500, purely from rounding
    to the nearest tradeable lot size. A near-zero float tolerance flagged
    that as "exceeds," which would reject their own worked example. The
    tolerance below is deliberately set to half a lot-step's worth of risk,
    so it accepts unavoidable rounding but still catches anything genuinely
    oversized (e.g. a stray extra lot).
    """
    actual_risk = proposed_lots * stop_distance_pips * pip_value_per_lot
    rounding_tolerance = 0.5 * min_lot_step * stop_distance_pips * pip_value_per_lot
    return actual_risk > risk_amount(account_balance, risk_pct) + rounding_tolerance
