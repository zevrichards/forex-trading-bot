# EUR/USD Bot — v1 Skeleton

This is the first real slice of code, not a prototype of everything.
It builds and tests every part of the trader's rules that doesn't depend on
an unresolved integration question, and clearly stubs the parts that do
(the ATS relay's Google Sheet setup, and the TradingView webhook) so
nothing about them is guessed at.

## What's built and tested (59 passing tests)

| Rule (the trader's words) | Module | Tested against |
|---|---|---|
| "$500 risk budget... Lot size = $500 / (stop pips x $10)" | `risk_sizing.py` | Every row of the trader's own lookup table, exactly |
| "BUY when price touches buy-side liquidity while below Value... SELL... above Value" | `decision_engine.py` | Clean buy/sell cases, wait cases, and a regression test that the two conditions are ANDed, not ORed |
| "Weekly + Daily bias must agree... Trend must agree with the bias" | `decision_engine.py` | Conflicting/neutral bias, trend disagreement |
| "Bullish trend = HH + HL. Bearish trend = LL + LH." | `bias.py` | Hand-built, hand-verified candle sequences for bullish, bearish, insufficient structure, and a genuinely conflicting (ambiguous) case |
| "Stop is outside the ATS Order Block Projection, with a small manually determined buffer" | `stop_placement.py` | LONG/SHORT stop calc, zero-buffer edge case — buffer is now a relayed value, not a placeholder constant |
| "Close 50% when opposite-side liquidity is touched, move remaining stop to breakeven" | `trade_manager.py` | Triggers correctly, doesn't fire early |
| "Exit the remaining 50% when price enters/touches a new ATS-identified Box" | `trade_manager.py` | Triggers only after partial close + a genuinely new box |
| "Never widen the stop" | `trade_manager.py` (`trail_stop`) | Enforced as a hard invariant on both long and short, independent of what proposes the new stop |
| "Trading days: Monday-Friday. Session: London only, fixed, no DST." | `filters.py` | Weekday/weekend, in/out of session |
| "News blackout: 15 min before, 30 min after" | `filters.py` | Before/after/outside the window |

Run the tests yourself: `pip install -r requirements.txt && pytest -v`

One real bug got caught during this build, worth knowing about: the
trader's own worked example (30 pips -> 1.67 lots) technically risks $501,
one dollar over the $500 budget, purely from rounding to the nearest
tradeable 0.01 lot. The risk-budget guard was originally too strict and
would have rejected their own example. Fixed by tolerating half a
lot-step's worth of unavoidable rounding — see the comment in
`risk_sizing.py` for the full reasoning. This is exactly the kind of thing
testing against their real numbers was for.

## What's live

**`relay_poller.py`** — reading the ATS Box/liquidity/OB-projection numbers.
Confirmed via live testing that these can't be read from ATS
programmatically (see the WhatsApp conversation history / plan docs for
the screen-share findings). `GoogleSheetRelaySource` reads the last row of
a manually-maintained Google Sheet (no Form, values are typed in directly)
via `gspread`, and has been run successfully end-to-end against the real
Sheet — see `docs/relay-setup.md` for the setup. `JSONFileRelaySource`
still works for offline/local testing (`RELAY_SOURCE=json`). The Sheet
currently holds placeholder/test values, not real ATS numbers yet.

## What's stubbed, and why

**`webhook_receiver.py`** — receiving ATS MTF Trend V1's bias signal, which
*is* confirmed live-readable. The endpoint works (tested). A companion Pine
Script now exists too (`pine/ats_trend_webhook.pine`), reading ATS MTF
Trend V1 via `input.source()` and firing `alertcondition()`s whose message
payload matches this endpoint's schema exactly. What's not done: the
script has never been compiled or run against the real indicator — see
`docs/pine-script-verification-checklist.md` for what's unconfirmed
(mainly whether ATS's plots behave the simple on/off way the script
assumes). Treat the payload schema
(`{"symbol": ..., "signal": "bullish_trend"}`) as provisional until that
checklist is done.

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

~~**Session hours.**~~ Resolved 2026-09-14: London session only (New York
dropped), fixed year-round with no DST shift. `filters.py` updated.

~~**Stop buffer size.**~~ Resolved 2026-09-15: rather than a fixed pip
constant, the trader's own source material (`docs/trader-strategy-source.md`
item 15: "not simply an arbitrary 10 or 20 pips... sits slightly below it
depending on structure") describes the buffer as structural/contextual, not
universal. So it's now a 6th manually-relayed value (`stop_buffer_pips`) —
see `relay_poller.py`, `models.MarketState`, `docs/relay-setup.md`. The
`DEFAULT_BUFFER_PIPS` constant is gone; `stop_placement.calculate_stop_price`
now requires `buffer_pips` explicitly.

1. **Swing-point detection for the real trailing-stop rule.** `bias.py`
   uses a standard fractal method (candle is a swing point if it's the
   most extreme of its 2 neighbors on each side) for weekly/daily trend
   classification, which is a Claude judgment call, not something the
   trader specified numerically. Asked the trader directly on 2026-09-14
   using "swing point" terminology — they didn't recognize the term
   ("Swing point? You mean liquidity?"), meaning this isn't a concept
   they use separately from liquidity/structure. `docs/trader-strategy-source.md`
   backs this up — every HH/HL/structure reference in his own write-up is
   tied to liquidity mechanics (sweeps, rejections, box breaks), never to
   raw candle geometry. He's since sent chart screenshots marking specific
   "order block" candles and measured leg distances between them (not
   simple circled highs/lows) — needs review against `bias.py`'s fractal
   method before `trade_manager._trail_stop()` gets built for real on top
   of it.
2. **News calendar source.** Needs an actual feed (a scraped calendar, a
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
pine/
  ats_trend_webhook.pine  companion Pine Script for webhook_receiver.py — drafted, unverified (see docs/pine-script-verification-checklist.md)
tests/                59 tests, one file per src module (except stop_placement)
```
