from services.news_service import NewsService


class _FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


class _FakeSession:
    """Tarmoqqa chiqmaydigan soxta sessiya (testlar uchun)."""

    def __init__(self, data=None, exc=None, status_code=200):
        self._data = data
        self._exc = exc
        self._status_code = status_code

    def get(self, url, timeout=10):
        if self._exc is not None:
            raise self._exc
        return _FakeResponse(self._data, self._status_code)


def test_fetch_calendar_parses_events(monkeypatch):
    news = NewsService()
    payload = [{
        "country": "USD", "impact": "High", "title": "Non-Farm Payrolls",
        "date": "2026-10-20T12:30:00-04:00", "forecast": "150K", "previous": "140K", "actual": "-",
    }]
    monkeypatch.setattr(news, "_get_session", lambda: _FakeSession(data=payload))

    events = news.fetch_calendar()
    assert isinstance(events, list)
    assert events[0]["title"] == "Non-Farm Payrolls"


def test_fetch_calendar_negative_cache_on_error(monkeypatch):
    """Xato bo'lganda negativ kesh ishlashi va tarmoqqa qayta chiqmasligi kerak."""
    news = NewsService()
    calls = {"n": 0}

    class _BoomSession:
        def get(self, url, timeout=10):
            calls["n"] += 1
            raise ConnectionError("network down")

    monkeypatch.setattr(news, "_get_session", lambda: _BoomSession())

    assert news.fetch_calendar() == []
    assert news.fetch_calendar() == []   # negativ kesh - yana urinmaydi
    assert calls["n"] == 1


def test_fetch_calendar_429_is_fast(monkeypatch):
    """429 javob berganda funksiya tez (qayta urinmasdan) qaytishi kerak."""
    import time

    news = NewsService()
    monkeypatch.setattr(news, "_get_session", lambda: _FakeSession(data={"error": "rate limited"}, status_code=429))

    start = time.time()
    result = news.fetch_calendar()
    elapsed = time.time() - start
    assert result == []
    assert elapsed < 2.0


def test_evaluate_trading_safety_safe_market(monkeypatch):
    news = NewsService()
    monkeypatch.setattr(news, "fetch_calendar", lambda force=False: [{"title": "x"}])
    monkeypatch.setattr(news, "get_usd_gold_events", lambda: [])

    safety = news.evaluate_trading_safety()
    assert safety["status"] == "SAFE"
    assert safety["safe_to_trade"] is True
    assert safety["calendar_ok"] is True


def test_evaluate_trading_safety_fails_closed_when_calendar_fails(monkeypatch):
    news = NewsService()
    monkeypatch.setattr(news, "fetch_calendar", lambda force=False: [])

    safety = news.evaluate_trading_safety()
    assert safety["status"] == "UNKNOWN_CAUTION"
    assert safety["calendar_ok"] is False
    assert safety["safe_to_trade"] is False


def _event(minutes_ahead, title="CPI", impact="High"):
    from datetime import datetime, timedelta, timezone
    return {
        "title": title, "impact": impact,
        "datetime": datetime.now(timezone.utc) + timedelta(minutes=minutes_ahead),
        "forecast": "-", "previous": "-", "actual": "-",
    }


def test_evaluate_trading_safety_danger_before_high_impact(monkeypatch):
    news = NewsService()
    monkeypatch.setattr(news, "fetch_calendar", lambda force=False: [{"title": "x"}])
    monkeypatch.setattr(news, "get_usd_gold_events", lambda: [_event(10)])

    safety = news.evaluate_trading_safety()
    assert safety["status"] == "DANGER"
    assert safety["safe_to_trade"] is False


def test_get_session_is_reused(monkeypatch):
    news = NewsService()
    assert news._get_session() is news._get_session()


def test_format_news_summary_escapes_external_html(monkeypatch):
    news = NewsService()
    monkeypatch.setattr(news, "fetch_calendar", lambda force=False: [{"title": "x"}])
    monkeypatch.setattr(news, "get_usd_gold_events", lambda: [_event(20, title="<b>Injected</b>")])

    text = news.format_news_summary_uz()
    assert "&lt;b&gt;Injected&lt;/b&gt;" in text
    assert "<b>Injected</b>" not in text

