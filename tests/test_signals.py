import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timezone

from services import signal_generator as sg
from services.market_data import MarketDataError


def synthetic_df(n=250, start=4000.0):
    rng = np.random.default_rng(7)
    close = start + np.cumsum(rng.normal(0.1, 1.5, n))
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="15min"),
        "open": close - 0.3,
        "high": close + 1.5,
        "low": close - 1.5,
        "close": close,
        "volume": np.full(n, 100.0),
    })


NEWS = {"safe_to_trade": True, "status_text": "SAFE", "recommendation": "", "calendar_ok": True,
        "status": "SAFE", "upcoming": [], "recent": []}


@pytest.fixture
def offline_services(monkeypatch):
    df = synthetic_df()
    monkeypatch.setattr(sg.market_service, "get_candles", lambda tf, limit=250: df)
    monkeypatch.setattr(sg.market_service, "get_live_price", lambda: float(df["close"].iloc[-1]))
    monkeypatch.setattr(sg.news_service, "evaluate_trading_safety", lambda: NEWS)


def test_generate_signal_structure(offline_services):
    sig = sg.signal_service.generate_signal("15m", balance=500.0, risk_percent=1.0)
    assert sig["symbol"] == "XAUUSD"
    assert sig["action"] in ("BUY", "SELL", "WAIT")
    assert 0 <= sig["strength"] <= 100
    assert len(sig["reasons"]) > 0
    if sig["action"] != "WAIT":
        assert sig["stop_loss"] is not None and len(sig["tps"]) == 3


def test_generate_signal_daily_has_no_htf(offline_services):
    sig = sg.signal_service.generate_signal("1d")
    assert sig["htf_timeframe"] is None


def test_market_failure_propagates_not_faked(monkeypatch):
    def boom(*a, **k):
        raise MarketDataError("offline")

    monkeypatch.setattr(sg.market_service, "get_candles", boom)
    with pytest.raises(MarketDataError):
        sg.signal_service.generate_signal("15m")


_FAKE_BUY = {
    "symbol": "XAUUSD", "timeframe": "15m", "htf_timeframe": "1h", "htf_trend": "BULLISH",
    "action": "BUY", "strength": 90, "buy_votes": 3, "sell_votes": 0, "votes": [],
    "current_price": 4000.0, "atr": 2.0, "reasons": ["setup"],
    "news_safe": True, "news_status": "SAFE", "news_calendar_ok": True,
    "offset": 0.0, "generated_at": datetime.now(timezone.utc),
    "valid_minutes": 30, "entry_price": 4000.0, "stop_loss": 3995.0,
    "tps": [4005.0, 4010.0, 4020.0], "risk": {"lot_size": 0.01},
}


def test_session_gate_blocks_outside_session(offline_services, monkeypatch):
    monkeypatch.setattr(sg, "evaluate", lambda *a, **k: dict(_FAKE_BUY))
    monkeypatch.setattr(sg, "in_session", lambda *a, **k: False)

    sig = sg.signal_service.generate_signal("15m")
    assert sig["action"] == "WAIT"
    assert sig.get("session_closed") is True
    assert sig["tps"] == [] and sig["risk"] is None
    assert any("seansidan tashqari" in r.lower() for r in sig["reasons"])


def test_session_gate_allows_inside_session(offline_services, monkeypatch):
    monkeypatch.setattr(sg, "evaluate", lambda *a, **k: dict(_FAKE_BUY))
    monkeypatch.setattr(sg, "in_session", lambda *a, **k: True)

    sig = sg.signal_service.generate_signal("15m")
    assert sig["action"] == "BUY"
    assert not sig.get("session_closed")
