"""
No coverage existed for this endpoint at all before this file. The global
_latest_trend dict is reset before every test (autouse fixture) so tests
don't leak state into each other.
"""

import pytest
from fastapi.testclient import TestClient

from src import webhook_receiver
from src.models import Trend
from src.webhook_receiver import _parse_signal, app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_latest_trend():
    webhook_receiver._latest_trend.clear()
    yield
    webhook_receiver._latest_trend.clear()


def test_get_latest_trend_before_any_alert():
    response = client.get("/trend/latest")
    assert response.status_code == 200
    assert response.json() == {"status": "no data received yet"}


def test_receive_bullish_alert_updates_latest_trend():
    response = client.post(
        "/webhook/tradingview", json={"symbol": "EURUSD", "signal": "bullish_trend"}
    )
    assert response.status_code == 200
    assert response.json()["parsed_trend"] == Trend.BULLISH

    latest = client.get("/trend/latest").json()
    assert latest["symbol"] == "EURUSD"
    assert latest["trend"] == Trend.BULLISH
    assert "received_at" in latest


def test_receive_bearish_alert():
    response = client.post(
        "/webhook/tradingview", json={"symbol": "EURUSD", "signal": "bearish_trend"}
    )
    assert response.json()["parsed_trend"] == Trend.BEARISH


def test_receive_trend_end_maps_to_neutral():
    response = client.post(
        "/webhook/tradingview", json={"symbol": "EURUSD", "signal": "trend_end"}
    )
    assert response.json()["parsed_trend"] == Trend.NEUTRAL


def test_second_alert_overwrites_the_first():
    client.post("/webhook/tradingview", json={"symbol": "EURUSD", "signal": "bullish_trend"})
    client.post("/webhook/tradingview", json={"symbol": "EURUSD", "signal": "bearish_trend"})

    latest = client.get("/trend/latest").json()
    assert latest["trend"] == Trend.BEARISH


def test_missing_required_field_returns_422():
    response = client.post("/webhook/tradingview", json={"symbol": "EURUSD"})
    assert response.status_code == 422


def test_parse_signal_recognizes_all_expected_values():
    assert _parse_signal("bullish_trend") == Trend.BULLISH
    assert _parse_signal("bearish_trend") == Trend.BEARISH
    assert _parse_signal("trend_end") == Trend.NEUTRAL


def test_parse_signal_unrecognized_value_fails_safe_to_neutral(caplog):
    """Fails safe (NEUTRAL blocks entries in decision_engine.py) but must
    not fail silently -- a schema mismatch between the real Pine Script
    alert and this payload shape should be loud, not swallowed."""
    with caplog.at_level("WARNING"):
        result = _parse_signal("some_unexpected_value")

    assert result == Trend.NEUTRAL
    assert "Unrecognized TradingView signal" in caplog.text
    assert "some_unexpected_value" in caplog.text


def test_receive_alert_with_unrecognized_signal_still_returns_200():
    """The endpoint itself shouldn't reject an alert just because the
    signal string doesn't match -- it fails safe to NEUTRAL rather than
    erroring, since a webhook retry storm from TradingView is worse than
    logging and moving on."""
    response = client.post(
        "/webhook/tradingview", json={"symbol": "EURUSD", "signal": "unexpected_signal"}
    )
    assert response.status_code == 200
    assert response.json()["parsed_trend"] == Trend.NEUTRAL
