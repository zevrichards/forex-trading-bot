# EUR/USD Bot — v1 Skeleton

This is the first real slice of code, not a prototype of everything.
It builds and tests every part of Valentino's rules that doesn't depend on
an unresolved integration question, and clearly stubs the two that do
(the ATS relay, and the TradingView webhook) so nothing about them is
guessed at.

## What's built and tested (45 passing tests)

| Rule (his words) | Module | Tested against |
|---|---|---|
| "$500 risk budget... Lot size = $500 / (stop pips x $10)" | `risk_sizing.py` | Every row of his own lookup table, exactly |
| "BUY when price touches buy-side liquidity while below Value... SELL... above Value" | `decision_engine.py` | Clean buy/sell cases, wait cases, and a regression test that the two conditions are ANDed, not ORed |
| "Weekly + Daily bias must agree... Trend must agree with the bias" | `decision_engine.py` | Conflicting/neutral bias, trend disagreement |
| "Bullish trend = HH + HL. Bearish trend = LL + LH." | `bias.py` | Hand-built, hand-verified candle sequences for bullish, bearish, insufficient structure, and a genuinely conflicting (ambiguous) case |
| "Stop is outside the ATS Order Block Projection, with a small manually determined buffer" | `stop_placement.py` | Not yet unit tested — buffer size is a placeholder, see Open Questions |
| "Close 50% when opposite-side liquidity is touched, move remaining stop to breakeven" | `trade_manager.py` | Triggers correctly, doesn't fire early |
| "Exit the remaining 50% when price enters/touches a new ATS-identified Box" | `trade_manager.py` | Triggers only after partial close + a genuinely new box |
| "Never widen the stop" | `trade_manager.py` (`trail_stop`) | Enforced as a hard invariant on both long and short, independent of what proposes the new stop |
| "Trading days: Monday-Friday. Sessions: London and New York." | `filters.py` | Weekday/weekend, in/out of session |
| "News blackout: 15 min before, 30 min after" | `filters.py` | Before/after/outside the window |

Run the tests yourself: `pip install -r requirements.txt && pytest -v`

One real bug got caught during this build, worth knowing about: his own
worked example (30 pips -> 1.67 lots) technically risks $501, one dollar
over the $500 budget, purely from rounding to the nearest tradeable 0.01
lot. The risk-budget guard was originally too strict and would have
rejected his own example. Fixed by tolerating half a lot-step's worth of
unavoidable rounding — see the comment in `risk_sizing.py` for the full
reasoning. This is exactly the kind of thing testing against his real
numbers was for.

## What's stubbed, and why

**`relay_poller.py`** — reading the ATS Box/liquidity/OB-projection numbers.
Confirmed via live testing that these can't be read from ATS
programmatically (see the WhatsApp conversation history / plan docs for
the screen-share findings). `JSONFileRelaySource` works today for local
testing. `GoogleSheetRelaySource` is a real interface with no
implementation yet — build the Google Form + Sheet, then wire this up.

**`webhook_receiver.py`** — receiving ATS MTF Trend V1's bias signal, which
*is* confirmed live-readable. The endpoint works (tested), but the
Pine Script companion indicator that reads ATS MTF Trend V1 via
`input.source()` and defines the alert that posts here doesn't exist yet.
The payload schema (`{"symbol": ..., "signal": "bullish_trend"}`) is a
reasonable proposal, not a confirmed format — finalize it once the Pine
script's actual alert message template exists.

**Not started at all:**
- Order execution (cTrader Open API integration) — nothing places a real
  order yet; `orchestrator.py` only logs what it *would* do.
- Candle history fetch for `bias.py` to run on live data (it's tested with
  hand-built fixtures, not wired to a real data source yet).
- The actual trailing-stop rule ("after a new higher-low forms, move stop
  below it") — `trade_manager._trail_stop()` is a deliberate no-op stub;
  see Open Questions below.
- An economic calendar feed for the news blackout filter — `filters.py`
  takes a plain list of event times; nothing populates that list yet.

## Open questions to resolve before this goes further

1. **Swing-point detection for the real trailing-stop rule.** `bias.py`
   uses a standard fractal method (candle is a swing point if it's the
   most extreme of its 2 neighbors on each side) for weekly/daily trend
   classification, which is a Claude judgment call, not something
   Valentino specified numerically. Worth confirming with him that this
   matches what he'd call a swing point by eye, especially before
   `trade_manager._trail_stop()` gets built for real on top of it.
2. **Session hours.** `filters.py`'s London (07:00-16:00 UTC) and New York
   (12:00-21:00 UTC) windows are standard placeholders, not confirmed with
   him, and don't account for daylight saving shifts on either side.
3. **Stop buffer size.** `stop_placement.py`'s `DEFAULT_BUFFER_PIPS = 2.0`
   is a placeholder for what he called a "small manually determined
   buffer" — get an actual number (or a rule for choosing one) from him.
4. **Relay mechanism.** Google Form -> Sheet was the plan; not built yet.
5. **News calendar source.** Needs an actual feed (a scraped calendar, a
   paid API) to populate the blackout list — nothing chosen yet.

## Project layout

```
src/
  models.py          shared data types (MarketState, Position, etc.)
  risk_sizing.py      position sizing from the 0.5% risk rule
  decision_engine.py  entry logic (BUY/SELL/WAIT/NO_TRADE)
  stop_placement.py   initial stop from the OB projection level
  trade_manager.py    partial close / breakeven / full close / never-widen
  bias.py             weekly/daily bias + trend from swing structure
  filters.py          trading day / session / news blackout gate
  relay_poller.py     where the manually-relayed ATS numbers come from
  webhook_receiver.py FastAPI endpoint for ATS MTF Trend V1 alerts
  orchestrator.py     ties it together, dry-run only (no order placement)
tests/                45 tests, one file per src module (except stop_placement)
```
