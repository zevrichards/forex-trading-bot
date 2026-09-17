# EUR/USD Bot — v1 Skeleton

This is the first real slice of code, not a prototype of everything.
It builds and tests every part of the trader's rules that doesn't depend on
an unresolved integration question, and clearly stubs the parts that do
(the TradingView webhook, and the Google Sheet's newest columns) so
nothing about them is guessed at.

## What's built and tested (112 passing tests)

| Rule (the trader's words) | Module | Tested against |
|---|---|---|
| "$500 risk budget... Lot size = $500 / (stop pips x $10)" | `risk_sizing.py` | Every row of the trader's own lookup table, exactly |
| "BUY when price touches buy-side liquidity while below Value... SELL... above Value" | `decision_engine.py` | Clean buy/sell cases, wait cases, and a regression test that the two conditions are ANDed, not ORed |
| "Weekly + Daily bias must agree... Trend must agree with the bias" | `decision_engine.py` | Conflicting/neutral bias, trend disagreement. `weekly_bias`/`daily_bias` are now relayed (see below), not computed |
| "Bullish trend = HH + HL. Bearish trend = LL + LH." | `bias.py` | Box-to-box comparisons: higher-high+higher-low, lower-low+lower-high, identical boxes, and both disagreement cases (range widened / range narrowed) |
| "Stop is outside the ATS Order Block Projection, with a small manually determined buffer" | `stop_placement.py` | LONG/SHORT stop calc, zero-buffer edge case — buffer is now a relayed value, not a placeholder constant |
| "Close 50% when opposite-side liquidity is touched, move remaining stop to breakeven" | `trade_manager.py` | Triggers correctly, doesn't fire early |
| "Exit the remaining 50% when price enters/touches a new ATS-identified Box" | `trade_manager.py` | Triggers only after partial close + a genuinely new box |
| "Never widen the stop" | `trade_manager.py` (`trail_stop`) | Enforced as a hard invariant on both long and short, independent of what proposes the new stop |
| "Trading days: Monday-Friday. Session: London only, fixed, no DST." | `filters.py` | Weekday/weekend, in/out of session |
| "News blackout: 15 min before, 30 min after" | `filters.py` | Before/after/outside the window |
| *(no direct quote — this is plumbing, not a rule)* | `orchestrator.py` | Full pipeline wiring: BUY/SELL -> stop -> lot size -> order, and that WAIT/NO_TRADE/filtered-out cases never reach the order executor |
| *(no direct quote — cTrader Open API's own message format)* | `order_execution.py` | Request-building tested against the real installed `ctrader-open-api` package, not a mock — see note below |

Run the tests yourself: `pip install -r requirements.txt && pytest -v`

**`bias.py` note (updated 2026-09-17):** rewritten from scratch. The
original version tried to compute trend from raw candles via a fractal
"swing point" method — confirmed the wrong shape entirely (not just
unconfirmed/unwired), per `docs/master-pattern-course-notes.md` and the
trader's own responses. It's now `classify_trend_from_boxes()`, a
box-to-box comparison (current box vs. the immediately preceding one,
both manually relayed), and **is** wired into `orchestrator.py`'s
`build_market_state()` as the default source for `trend` — no longer
dead code. Still overridable (e.g. once the ATS MTF Trend V1 webhook is
verified, or for testing).

**`order_execution.py` note (2026-09-15):** `_build_new_order_proto()` —
the code that turns a BUY/SELL decision into a cTrader order request — is
real, and tested against the actual installed `ctrader-open-api` PyPI
package's protobuf message shapes (field names, `MARKET`/`BUY`/`SELL`
enum values, volume units, stopLoss/takeProfit semantics), confirmed
2026-09-15 by installing the package and introspecting it directly plus
cross-checking help.ctrader.com — not guessed from memory. What's
genuinely not done: `place_market_order()` itself, i.e. actually sending
anything over the wire. That needs a live cTrader demo account (client
ID/secret from an app registered at openapi.ctrader.com, an OAuth access
token, and a broker-specific symbolId for EURUSD) which doesn't exist —
raises `NotImplementedError` rather than guessing at connection-lifecycle
code that can't be tested. `orchestrator.py` defaults to
`LoggingOrderExecutor` (dry-run), consistent with "nothing places a real
order yet."

One real bug got caught during this build, worth knowing about: the
trader's own worked example (30 pips -> 1.67 lots) technically risks $501,
one dollar over the $500 budget, purely from rounding to the nearest
tradeable 0.01 lot. The risk-budget guard was originally too strict and
would have rejected their own example. Fixed by tolerating half a
lot-step's worth of unavoidable rounding — see the comment in
`risk_sizing.py` for the full reasoning. This is exactly the kind of thing
testing against their real numbers was for.

A second real bug (2026-09-15): `manage_position()` returned `[]` before
the first partial close but `[HOLD]` after it, for the same "nothing to do
right now" situation — an inconsistent API that only showed up once
`tests/test_trade_manager_lifecycle.py` started running a full position
lifecycle through multiple `manage_position()` calls in sequence instead of
testing each call in isolation. Fixed by restructuring the function to one
exit path with a single "fall back to HOLD" check. Single-call tests
couldn't have caught this by construction — worth keeping the lifecycle
test file around as its own category, not folding it into `test_trade_manager.py`.

## What's live

**`relay_poller.py`** — reading the ATS Box/liquidity/OB-projection numbers,
plus (as of 2026-09-15) stop buffer, weekly/daily bias, and the trailing-
stop's structure level, plus the previous confirmed contraction box (for
trend classification, see the `bias.py` note above) — see Open Questions
history below for why these joined the relay instead of being computed.
Confirmed via live testing that the ATS numbers can't be read
programmatically (see the WhatsApp conversation history / plan docs for
the screen-share findings). `GoogleSheetRelaySource` reads the last row
of a manually-maintained Google Sheet (no Form, values are typed in
directly) via `gspread` — see `docs/relay-setup.md` for the setup and the
current full 12-column schema. **The live Sheet is 2 columns behind the
code** (needs Previous Box High/Low added), and its Weekly Bias/Daily
Bias cells currently hold a placeholder ("1") rather than
bullish/bearish/neutral, which the parser correctly rejects rather than
guessing — swap in real values (or "bullish"/"bearish"/"neutral" test
values) to get the orchestrator running end-to-end again.
`JSONFileRelaySource` still works for offline/local testing
(`RELAY_SOURCE=json`).

**`news_calendar.py`** (added 2026-09-15) — populates `filters.py`'s news
blackout list. `ForexFactoryCalendarSource` reads a free, no-signup JSON
mirror of the ForexFactory calendar (confirmed live), filtered to
High-impact USD/EUR events. Not an official API and rate-limited — a
second fetch within the same minute during testing got 403 then 429 — so
`orchestrator.py` fails open (warns, proceeds with an empty blackout list)
rather than blocking evaluation on it. Fine for now; cache/throttle this
once it runs on a real timer instead of a one-shot script (see module
docstring).

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
- The actual network side of order execution — see `order_execution.py`
  note above. `orchestrator.py` defaults to `LoggingOrderExecutor`, so
  nothing places a real order yet.

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

~~**Swing-point detection for the real trailing-stop rule.**~~ Resolved in
two stages. Stage 1 (2026-09-15): asking the trader directly for a "swing
point" definition didn't land twice ("Swing point? You mean liquidity?",
then chart screenshots marking order-block legs instead of circled
highs/lows) — rather than keep pushing, `weekly_bias`/`daily_bias`/
`structure_stop_level` became manually-relayed values. Stage 2
(2026-09-17): the trader, pushed further, pointed to trade ATS's own
training course instead of a definition; the transcripts turned out to
contain an actual mechanical definition — trend is a **box-to-box**
comparison (current contraction box vs. the previous one), not a
candle-fractal one. `bias.py` was rewritten around this
(`classify_trend_from_boxes()`) and is now genuinely wired into
`orchestrator.py`, no longer dead code — see
`docs/master-pattern-course-notes.md` for the distilled course quotes
this is grounded in. Needed two new relayed values, `prev_box_high`/
`prev_box_low` (both already visible on the trader's chart).

That same course research also surfaced a real ambiguity worth recording:
the course defines "Order Block Projection" as a *far* 100%-range profit
target, which would contradict the trader's stop rule ("stop outside the
ATS Order Block Projection") if taken literally — his real stops are
tight (5-100 pips), nowhere near a 100%-range target. Resolved via a
direct follow-up message where he described his stop as "outside the
framework" without using that term at all, read alongside a real chart
screenshot (stop clustered near the box, a clearly separate far target
line elsewhere on the chart) — understood to mean the order-block zone,
not the far projection line. `ob_projection_level` needed no code change;
see `docs/master-pattern-course-notes.md` for the full reasoning.

~~**News calendar source.**~~ Resolved 2026-09-15: `news_calendar.py`'s
`ForexFactoryCalendarSource` populates the blackout list from a free,
no-signup community feed, filtered to High-impact USD/EUR events. Not an
official API and rate-limited (see `news_calendar.py`), so treat it as
"good enough for now," not a permanent choice — swap for a paid API later
without touching `filters.py`, same swappable-source pattern as the relay.

No open questions remain that need the trader's input right now.

## Project layout

```
src/
  models.py          shared data types (MarketState, Position, etc.)
  risk_sizing.py      position sizing from the 0.5% risk rule
  decision_engine.py  entry logic (BUY/SELL/WAIT/NO_TRADE)
  stop_placement.py   initial stop from the OB projection level
  trade_manager.py    partial close / breakeven / full close / never-widen / trailing
  bias.py             box-to-box trend classification — real, tested, and wired into orchestrator.py
  filters.py          trading day / session / news blackout gate
  relay_poller.py     where the manually-relayed ATS numbers come from
  news_calendar.py    populates the news blackout list (ForexFactory feed)
  webhook_receiver.py FastAPI endpoint for ATS MTF Trend V1 alerts
  order_execution.py  builds real cTrader order requests; sending them is NOT done (see note above)
  orchestrator.py     full pipeline: filters -> decision -> stop -> size -> order (dry-run by default)
pine/
  ats_trend_webhook.pine  companion Pine Script for webhook_receiver.py — drafted, unverified (see docs/pine-script-verification-checklist.md)
tests/                112 tests, one file per src module, plus test_trade_manager_lifecycle.py and test_orchestrator.py
```
