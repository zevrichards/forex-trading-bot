"""
Every row here is taken directly from the trader's own lookup table:

    Stop    Approx. lot size
    5 pips  10.00 lots
    10 pips 5.00 lots
    15 pips 3.33 lots
    20 pips 2.50 lots
    25 pips 2.00 lots
    30 pips 1.67 lots
    40 pips 1.25 lots
    50 pips 1.00 lot
    75 pips 0.67 lot
    100 pips 0.50 lot

on a $100,000 account at 0.5% risk. If any of these fail, the formula
implementation is wrong relative to what he actually specified — this is
not a test to "fix" by adjusting the expected values.
"""

import pytest

from src.risk_sizing import calculate_lot_size, exceeds_risk_budget, risk_amount

ACCOUNT_BALANCE = 100_000.0


@pytest.mark.parametrize(
    "stop_pips,expected_lots",
    [
        (5, 10.00),
        (10, 5.00),
        (15, 3.33),
        (20, 2.50),
        (25, 2.00),
        (30, 1.67),
        (40, 1.25),
        (50, 1.00),
        (75, 0.67),
        (100, 0.50),
    ],
)
def test_matches_traders_table(stop_pips, expected_lots):
    assert calculate_lot_size(ACCOUNT_BALANCE, stop_pips) == expected_lots


def test_risk_amount_is_half_percent():
    assert risk_amount(ACCOUNT_BALANCE) == 500.0


def test_zero_stop_distance_rejected():
    with pytest.raises(ValueError):
        calculate_lot_size(ACCOUNT_BALANCE, 0)


def test_negative_stop_distance_rejected():
    with pytest.raises(ValueError):
        calculate_lot_size(ACCOUNT_BALANCE, -10)


def test_exceeds_risk_budget_flags_oversized_lot():
    # 30 pips should size to 1.67 lots; manually forcing 5 lots on a 30 pip
    # stop would risk $1,500 — well over the $500 budget.
    assert exceeds_risk_budget(ACCOUNT_BALANCE, stop_distance_pips=30, proposed_lots=5.0)


def test_exceeds_risk_budget_passes_correctly_sized_lot():
    correctly_sized = calculate_lot_size(ACCOUNT_BALANCE, stop_distance_pips=30)
    assert not exceeds_risk_budget(
        ACCOUNT_BALANCE, stop_distance_pips=30, proposed_lots=correctly_sized
    )
