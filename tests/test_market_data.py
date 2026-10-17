import pytest

from services.market_data import MarketDataError, MarketDataService, klines_to_df


def failing_service(monkeypatch):
    svc = MarketDataService()
    monkeypatch.setattr(svc, "_price_binance", lambda: None)
    monkeypatch.setattr(svc, "_price_yahoo", lambda: None)
    monkeypatch.setattr(svc, "_candles_binance", lambda tf, limit: None)
    monkeypatch.setattr(svc, "_candles_yahoo", lambda tf, limit: None)
    return svc


def test_price_raises_when_all_sources_fail(monkeypatch):
    svc = failing_service(monkeypatch)
    with pytest.raises(MarketDataError):
        svc.get_live_price()


def test_candles_raise_when_all_sources_fail(monkeypatch):
    svc = failing_service(monkeypatch)
    with pytest.raises(MarketDataError):
        svc.get_candles("15m", 100)


def test_price_falls_back_to_yahoo(monkeypatch):
    svc = MarketDataService()
    monkeypatch.setattr(svc, "_price_binance", lambda: None)
    monkeypatch.setattr(svc, "_price_yahoo", lambda: 4123.4)
    assert svc.get_live_price() == 4123.4


def test_stale_cache_used_when_sources_fail(monkeypatch):
    svc = MarketDataService()
    monkeypatch.setattr(svc, "_price_binance", lambda: 4100.0)
    assert svc.get_live_price() == 4100.0
    svc._cache["live_price"]["ts"] -= 120  # kesh eskirdi, lekin stale chegarasida
    monkeypatch.setattr(svc, "_price_binance", lambda: None)
    monkeypatch.setattr(svc, "_price_yahoo", lambda: None)
    assert svc.get_live_price() == 4100.0


def test_invalid_timeframe_rejected():
    with pytest.raises(ValueError):
        MarketDataService().get_candles("3m")


def test_klines_to_df():
    raw = [[1700000000000, "1", "2", "0.5", "1.5", "10"]]
    df = klines_to_df(raw)
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert df["close"].iloc[0] == 1.5


def test_session_is_reused_per_thread():
    svc = MarketDataService()
    assert svc._get_session() is svc._get_session()
