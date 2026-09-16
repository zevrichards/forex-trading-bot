"""
ForexFactoryCalendarSource._parse is tested directly with plain dict data
matching the real feed's shape (confirmed live 2026-09-15, see module
docstring) — no network calls in the test suite. get_high_impact_events()'s
network wiring is tested separately with _fetch_raw() monkeypatched.
"""

from datetime import datetime, timezone

import pytest

from src.news_calendar import (
    ForexFactoryCalendarSource,
    HighImpactEvent,
    StaticNewsCalendarSource,
)

# A representative slice of the real feed's shape.
SAMPLE_RAW = [
    {
        "title": "CPI m/m",
        "country": "CAD",
        "date": "2026-09-14T08:30:00-04:00",
        "impact": "High",
        "forecast": "-0.1%",
        "previous": "0.5%",
    },
    {
        "title": "Core CPI m/m",
        "country": "USD",
        "date": "2026-09-16T08:30:00-04:00",
        "impact": "High",
        "forecast": "0.3%",
        "previous": "0.3%",
    },
    {
        "title": "ECB President Lagarde Speaks",
        "country": "EUR",
        "date": "2026-09-16T09:00:00-04:00",
        "impact": "High",
        "forecast": "",
        "previous": "",
    },
    {
        "title": "BusinessNZ Services Index",
        "country": "NZD",
        "date": "2026-09-13T18:30:00-04:00",
        "impact": "Low",
        "forecast": "",
        "previous": "50.6",
    },
    {
        "title": "German Manufacturing PMI",
        "country": "EUR",
        "date": "2026-09-16T04:00:00-04:00",
        "impact": "Medium",
        "forecast": "",
        "previous": "",
    },
]


def test_parse_keeps_only_high_impact_usd_eur_events():
    events = ForexFactoryCalendarSource._parse(SAMPLE_RAW)

    names = {e.name for e in events}
    assert names == {"Core CPI m/m", "ECB President Lagarde Speaks"}


def test_parse_excludes_non_high_impact_even_for_relevant_currency():
    events = ForexFactoryCalendarSource._parse(SAMPLE_RAW)
    assert "German Manufacturing PMI" not in {e.name for e in events}


def test_parse_excludes_high_impact_for_irrelevant_currency():
    events = ForexFactoryCalendarSource._parse(SAMPLE_RAW)
    assert "CPI m/m" not in {e.name for e in events}  # CAD, not USD/EUR


def test_parse_converts_to_utc():
    events = ForexFactoryCalendarSource._parse(SAMPLE_RAW)
    lagarde = next(e for e in events if e.name == "ECB President Lagarde Speaks")
    # 09:00 at UTC-04:00 -> 13:00 UTC
    assert lagarde.time == datetime(2026, 9, 16, 13, 0, tzinfo=timezone.utc)


def test_parse_skips_malformed_rows_without_crashing():
    raw = SAMPLE_RAW + [
        {"title": "Broken row", "country": "USD", "impact": "High"},  # missing "date"
        {"title": "Bad date", "country": "USD", "date": "not-a-date", "impact": "High"},
    ]
    events = ForexFactoryCalendarSource._parse(raw)
    # Still parses the two valid High-impact USD/EUR rows; malformed ones just vanish.
    assert {e.name for e in events} == {"Core CPI m/m", "ECB President Lagarde Speaks"}


def test_get_high_impact_events_wires_fetch_through_parse(monkeypatch):
    source = ForexFactoryCalendarSource()
    monkeypatch.setattr(source, "_fetch_raw", lambda: SAMPLE_RAW)

    events = source.get_high_impact_events()

    assert len(events) == 2
    assert all(isinstance(e, HighImpactEvent) for e in events)


def test_static_news_calendar_source_returns_provided_events():
    event = HighImpactEvent(
        name="Test Event",
        currency="USD",
        time=datetime(2026, 9, 16, 13, 0, tzinfo=timezone.utc),
        impact="High",
    )
    source = StaticNewsCalendarSource([event])
    assert source.get_high_impact_events() == [event]


def test_static_news_calendar_source_defaults_empty():
    assert StaticNewsCalendarSource().get_high_impact_events() == []


def test_static_news_calendar_source_returns_a_copy_not_the_internal_list():
    event = HighImpactEvent(
        name="Test Event",
        currency="USD",
        time=datetime(2026, 9, 16, 13, 0, tzinfo=timezone.utc),
        impact="High",
    )
    source = StaticNewsCalendarSource([event])

    first_call = source.get_high_impact_events()
    first_call.append("mutation shouldn't stick")  # type: ignore[arg-type]

    assert source.get_high_impact_events() == [event]
