import pytest
from datetime import datetime, timezone
from services.market_hours import is_market_open, get_market_status
from services.news_service import NewsService
from services.journal import SignalJournal

def test_market_hours_weekdays_and_weekend():
    # Chorshanba 14:00 UTC - Bozor ochiq
    wednesday = datetime(2026, 10, 14, 14, 0, tzinfo=timezone.utc)
    assert is_market_open(wednesday) is True
    
    # Shanba 10:00 UTC - Bozor yopiq
    saturday = datetime(2026, 10, 17, 10, 0, tzinfo=timezone.utc)
    assert is_market_open(saturday) is False
    
    # Yakshanba 15:00 UTC - Hali ochilmagan (22:00 UTC da ochiladi)
    sunday_before = datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc)
    assert is_market_open(sunday_before) is False

    # Yakshanba 22:30 UTC - Bozor ochilgan
    sunday_open = datetime(2026, 10, 18, 22, 30, tzinfo=timezone.utc)
    assert is_market_open(sunday_open) is True

    # Juma 21:30 UTC - Bozor ochiq
    friday_open = datetime(2026, 10, 16, 21, 30, tzinfo=timezone.utc)
    assert is_market_open(friday_open) is True

    # Juma 22:15 UTC - Bozor yopilgan
    friday_closed = datetime(2026, 10, 16, 22, 15, tzinfo=timezone.utc)
    assert is_market_open(friday_closed) is False

def test_news_safety_fails_closed_when_calendar_fails(monkeypatch):
    news = NewsService()
    # Taqvim serveriga ulanish uzildi deb hisoblaymiz
    monkeypatch.setattr(news, "fetch_calendar", lambda: [])
    
    safety = news.evaluate_trading_safety()
    assert safety["calendar_ok"] is False
    # Xavfsizlik qoidasi: ma'lumot bo'lmasa, DANGER yoki noaniqlik bilan safe_to_trade=False bo'lishi kerak
    assert safety["safe_to_trade"] is False
    assert "aloqa yo'q" in safety["status_text"].lower() or "uzildi" in safety["status_text"].lower()

def test_expire_stale_pending_signals(tmp_path):
    db_file = str(tmp_path / "test_expire.db")
    journal = SignalJournal(db_path=db_file)
    
    # 2 soat oldingi signal
    from datetime import timedelta
    old_time = datetime.now() - timedelta(minutes=120)
    sig_old = {
        "generated_at": old_time,
        "action": "BUY",
        "timeframe": "15m",
        "entry_price": 2650.0,
        "stop_loss": 2640.0,
        "tps": [2665.0],
        "offset": 0.0,
    }
    id_old = journal.log_signal(sig_old, user_id=1)
    
    # 5 daqiqa oldingi yangi signal
    recent_time = datetime.now() - timedelta(minutes=5)
    sig_recent = {
        "generated_at": recent_time,
        "action": "SELL",
        "timeframe": "15m",
        "entry_price": 2650.0,
        "stop_loss": 2660.0,
        "tps": [2635.0],
        "offset": 0.0,
    }
    id_recent = journal.log_signal(sig_recent, user_id=1)
    
    # 30 daqiqadan oshgan PENDING signallarni EXPIRED qilish
    expired_count = journal.expire_stale_pending_signals(max_age_minutes=30)
    assert expired_count == 1
    
    assert journal.get_signal(id_old)["result"] == "EXPIRED"
    assert journal.get_signal(id_recent)["result"] == "PENDING"
