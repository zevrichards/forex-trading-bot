"""
Ties everything together into one evaluation loop. This is DRY-RUN ONLY —
it decides what the bot *would* do and logs it; it does not place any
orders. Wiring this to a real broker (cTrader Open API per the plan) is
the next unit of work after this decision logic has been validated against
real relayed numbers and reviewed, not before.

Run it directly (`python -m src.orchestrator`) once relay_data.json exists
(see relay_poller.py) to see a single evaluation printed to the console.
A real deployment would call `evaluate_once()` on a timer (e.g. every
minute) instead.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import decision_engine, filters, trade_manager
from .models import Bias, MarketState, Trend
from .relay_poller import JSONFileRelaySource, RelaySource

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("orchestrator")

RELAY_FILE_PATH = "relay_data.json"
HIGH_IMPACT_NEWS_EVENTS: list[datetime] = []  # TODO: wire up a real economic calendar source


def build_market_state(
    relay_source: RelaySource,
    current_price: float,
    weekly_bias: Bias,
    daily_bias: Bias,
    trend: Trend,
    symbol: str = "EURUSD",
) -> MarketState:
    """Combines the three independent data sources into one MarketState:
    relayed ATS numbers, live current price, and bias/trend (computed via
    bias.py from candle history, or read from the webhook receiver's
    /trend/latest for `trend` once that's wired in — passed in explicitly
    here for now so this function stays easy to unit test).
    """
    relay = relay_source.get_latest()
    return MarketState(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc),
        current_price=current_price,
        box_high=relay.box_high,
        box_low=relay.box_low,
        buy_liquidity=relay.buy_liquidity,
        sell_liquidity=relay.sell_liquidity,
        ob_projection_level=relay.ob_projection_level,
        weekly_bias=weekly_bias,
        daily_bias=daily_bias,
        trend=trend,
    )


def evaluate_once(state: MarketState) -> None:
    can_trade, reason = filters.can_trade_now(state.timestamp, HIGH_IMPACT_NEWS_EVENTS)
    if not can_trade:
        logger.info("No-trade window: %s", reason)
        return

    decision = decision_engine.evaluate_entry(state)
    logger.info("Decision: %s — %s", decision.action, decision.reason)
    # Sizing/order placement happen from here once decision.action is BUY/SELL
    # and a broker integration exists (see README "Not yet built").


if __name__ == "__main__":
    # Manual smoke-test entry point. Requires relay_data.json to exist
    # (see relay_poller.JSONFileRelaySource) and hard-codes bias/trend/price
    # for now, since the candle-history fetch and webhook receiver aren't
    # wired into this loop yet.
    demo_state = build_market_state(
        relay_source=JSONFileRelaySource(RELAY_FILE_PATH),
        current_price=1.15700,
        weekly_bias=Bias.BULLISH,
        daily_bias=Bias.BULLISH,
        trend=Trend.BULLISH,
    )
    evaluate_once(demo_state)
