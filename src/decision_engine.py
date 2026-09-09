"""
Entry decision logic — the direct translation of the trader's rules:

    "BUY when price touches buy-side liquidity while below Value."
    "SELL when price touches sell-side liquidity while above Value."
    "Weekly + Daily bias must agree with the trade direction."
    "Trend must agree with the Weekly + Daily bias."

This module makes NO decision about position size or stop placement — that's
risk_sizing.py and stop_placement.py. It answers exactly one question: given
the current market state, is this a BUY, a SELL, or not a trade, and why.

Every branch below is commented with which of the trader's rules it
enforces, so this stays auditable against their written spec rather than a
black box — per their "no assumptions or approximations" instruction.
"""

from __future__ import annotations

from .models import Bias, EntryDecision, MarketState, Trend

WAIT = "WAIT"
NO_TRADE = "NO_TRADE"
BUY = "BUY"
SELL = "SELL"


def _combined_bias(state: MarketState) -> Bias | None:
    """'Weekly + Daily bias must agree with the trade direction.'
    Returns None if they conflict — caller treats that as NO_TRADE, not a guess.
    """
    if state.weekly_bias == state.daily_bias and state.weekly_bias != Bias.NEUTRAL:
        return state.weekly_bias
    return None


def evaluate_entry(state: MarketState) -> EntryDecision:
    bias = _combined_bias(state)
    if bias is None:
        return EntryDecision(
            NO_TRADE,
            f"Weekly ({state.weekly_bias}) and Daily ({state.daily_bias}) bias "
            "don't agree, or are neutral — 'Weekly + Daily bias must agree with "
            "the trade direction.'",
        )

    if bias == Bias.BULLISH:
        return _evaluate_long(state)
    else:
        return _evaluate_short(state)


def _evaluate_long(state: MarketState) -> EntryDecision:
    # "Trend must agree with the Weekly + Daily bias."
    if state.trend != Trend.BULLISH:
        return EntryDecision(
            NO_TRADE, f"Bias is bullish but trend is {state.trend}, not bullish (HH+HL)."
        )

    # "You want the long entry below value... Bias bullish -> price trades below
    # value -> liquidity is taken/price stabilizes -> bullish expansion -> enter long."
    if state.current_price >= state.value:
        return EntryDecision(
            WAIT, f"Price {state.current_price} is not below Value {state.value:.5f} yet."
        )

    # "BUY when price touches buy-side liquidity while below Value."
    if state.current_price <= state.buy_liquidity:
        return EntryDecision(
            BUY,
            f"Price {state.current_price} has touched buy-side liquidity "
            f"{state.buy_liquidity} while below Value {state.value:.5f}, "
            "with bullish bias+trend agreement.",
        )

    return EntryDecision(
        WAIT,
        f"Below Value but hasn't reached buy-side liquidity {state.buy_liquidity} yet.",
    )


def _evaluate_short(state: MarketState) -> EntryDecision:
    if state.trend != Trend.BEARISH:
        return EntryDecision(
            NO_TRADE, f"Bias is bearish but trend is {state.trend}, not bearish (LL+LH)."
        )

    # Mirror of the long case: "You want the short entry above value..."
    if state.current_price <= state.value:
        return EntryDecision(
            WAIT, f"Price {state.current_price} is not above Value {state.value:.5f} yet."
        )

    # "SELL when price touches sell-side liquidity while above Value."
    if state.current_price >= state.sell_liquidity:
        return EntryDecision(
            SELL,
            f"Price {state.current_price} has touched sell-side liquidity "
            f"{state.sell_liquidity} while above Value {state.value:.5f}, "
            "with bearish bias+trend agreement.",
        )

    return EntryDecision(
        WAIT,
        f"Above Value but hasn't reached sell-side liquidity {state.sell_liquidity} yet.",
    )
