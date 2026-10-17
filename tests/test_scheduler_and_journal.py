import pytest
import os
from datetime import datetime, timedelta
from services.journal import SignalJournal
from bot.scheduler import _process_open_trades

@pytest.fixture
def temp_journal(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_journal.db")
    journal = SignalJournal(db_path=db_file)
    # scheduler.py dagi journal_service ni ushbu test jurnaliga yo'naltiramiz
    monkeypatch.setattr("bot.scheduler.journal_service", journal)
    return journal

def test_journal_log_and_stats(temp_journal):
    sig = {
        "generated_at": datetime.now(),
        "action": "BUY",
        "timeframe": "M15",
        "entry_price": 2650.0,
        "stop_loss": 2642.0,
        "tps": [2660.0, 2670.0],
        "strength": 80,
        "votes": [],
    }
    sig_id = temp_journal.log_signal(sig, user_id=123)
    assert sig_id > 0
    
    # Dastlab statistikada WIN/LOSS yo'q
    stats = temp_journal.get_stats()
    assert stats["total"] == 0
    
    # WIN bilan yopamiz
    temp_journal.mark_trade_closed(sig_id, "WIN", pnl=10.0)
    stats = temp_journal.get_stats()
    assert stats["total"] == 1
    assert stats["wins"] == 1
    assert stats["losses"] == 0
    assert stats["win_rate"] == 100.0

def test_process_open_trades_buy_hit_sl(temp_journal):
    now = datetime.now()
    sig = {
        "generated_at": now - timedelta(minutes=15),
        "action": "BUY",
        "timeframe": "M15",
        "entry_price": 2650.0,
        "stop_loss": 2645.0,
        "tps": [2660.0, 2670.0, 2680.0],
        "strength": 80,
    }
    sig_id = temp_journal.log_signal(sig, user_id=999)
    temp_journal.mark_trade_open(sig_id)
    
    # Narx SL dan pastga tushdi (2644.0)
    notifs = _process_open_trades(now, current_price=2644.0)
    assert len(notifs) == 1
    user_id, msg = notifs[0]
    assert user_id == 999
    assert "LOSS" in msg
    assert "❌" in msg
    
    stats = temp_journal.get_stats()
    assert stats["total"] == 1
    assert stats["losses"] == 1

def test_process_open_trades_sell_hit_tp(temp_journal):
    now = datetime.now()
    sig = {
        "generated_at": now - timedelta(minutes=20),
        "action": "SELL",
        "timeframe": "M15",
        "entry_price": 2650.0,
        "stop_loss": 2655.0,
        "tps": [2640.0, 2630.0, 2620.0],
        "strength": 80,
    }
    sig_id = temp_journal.log_signal(sig, user_id=888)
    temp_journal.mark_trade_open(sig_id)
    
    # 1. TP1_HIT qilish uchun narxni 2640 ga tushiramiz (lekin tp2 ga emas)
    notifs = _process_open_trades(now, current_price=2640.0)
    assert len(notifs) == 1
    assert "TP1" in notifs[0][1]
    assert "Breakeven" in notifs[0][1]
    
    stats = temp_journal.get_stats()
    # Hali yopilmagan
    assert stats["total"] == 0 

    # 2. Keyin qolgani TP2 gacha tushib yopilsin (2625.0 < 2630.0, TP3 gacha bormaydi)
    notifs_2 = _process_open_trades(now, current_price=2625.0)
    assert len(notifs_2) == 1
    assert "WIN" in notifs_2[0][1]
    
    stats2 = temp_journal.get_stats()
    assert stats2["total"] == 1
    assert stats2["wins"] == 1

def test_process_open_trades_expired(temp_journal):
    now = datetime.now()
    sig = {
        "generated_at": now - timedelta(hours=13),
        "action": "BUY",
        "timeframe": "M15",
        "entry_price": 2650.0,
        "stop_loss": 2640.0,
        "tps": [2670.0, 2680.0, 2690.0],
        "strength": 80,
    }
    sig_id = temp_journal.log_signal(sig, user_id=777)
    temp_journal.mark_trade_open(sig_id)
    
    # Narx oraliqda (2652.0), lekin 13 soat o'tgan
    notifs = _process_open_trades(now, current_price=2652.0)
    assert len(notifs) == 1
    assert "eski" in notifs[0][1].lower() or "kuzatuvdan olindi" in notifs[0][1].lower()

def test_process_open_trades_wick_hit_tp(temp_journal):
    now = datetime.now()
    sig = {
        "generated_at": now - timedelta(minutes=10),
        "action": "BUY",
        "timeframe": "M15",
        "entry_price": 2650.0,
        "stop_loss": 2640.0,
        "tps": [2660.0, 2670.0, 2680.0],
        "strength": 80,
    }
    sig_id = temp_journal.log_signal(sig, user_id=555)
    temp_journal.mark_trade_open(sig_id)
    
    # current_price 2652.0 (oraliqda), lekin high_price 2681.0 (TP3=2680 urilgan)
    notifs = _process_open_trades(now, current_price=2652.0, high_price=2681.0, low_price=2648.0)
    assert len(notifs) == 1
    assert "WIN (TP3)" in notifs[0][1]
    assert "✅" in notifs[0][1]
    
    stats = temp_journal.get_stats()
    assert stats["wins"] == 1


def _open_buy(journal, user_id, hours_ago=0.0):
    sig = {
        "generated_at": datetime.now() - timedelta(hours=hours_ago),
        "action": "BUY",
        "timeframe": "M15",
        "entry_price": 2650.0,
        "stop_loss": 2645.0,
        "tps": [2660.0, 2670.0, 2680.0],
        "strength": 80,
        "risk": {"lot_size": 0.1},
    }
    sid = journal.log_signal(sig, user_id=user_id)
    journal.mark_trade_open(sid)
    return sid


def test_breakeven_after_tp1_counts_as_win_with_partial_profit(temp_journal):
    now = datetime.now()
    _open_buy(temp_journal, 321)
    notifs = _process_open_trades(now, current_price=2661.0)  # TP1
    assert "++" not in notifs[0][1]
    # Narx kirish narxiga qaytdi -> breakeven
    notifs = _process_open_trades(now, current_price=2650.0)
    assert len(notifs) == 1
    assert "Breakeven" in notifs[0][1]
    stats = temp_journal.get_stats()
    assert stats["losses"] == 0
    assert stats["wins"] == 1
    # 0.5 * 10$ * 100 * 0.1 lot = 50$
    assert stats["total_pnl"] == pytest.approx(50.0)


def test_expired_after_tp1_keeps_partial_profit(temp_journal):
    sid = _open_buy(temp_journal, 322, hours_ago=13)
    temp_journal.mark_trade_tp1_hit(sid, break_even_sl=2650.0, partial_pnl=50.0)
    _process_open_trades(datetime.now(), current_price=2655.0)
    with temp_journal._connection() as conn:
        result, pnl = conn.execute("SELECT result, pnl FROM signals WHERE id=?", (sid,)).fetchone()
    assert result == "EXPIRED"
    assert pnl == pytest.approx(50.0)

