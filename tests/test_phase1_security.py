import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from services.journal import SignalJournal
from bot.scheduler import _process_open_trades
from bot.handlers import cb_trade_opened, cb_calc_dep, cb_calc_risk

def test_journal_get_signal_and_safe_connection(tmp_path):
    db_file = str(tmp_path / "test_sec_journal.db")
    journal = SignalJournal(db_path=db_file)
    
    # Connection context manager to'g'ri ishlashini va yopilishini tekshirish
    with journal._connection() as conn:
        assert conn is not None
    
    sig = {
        "generated_at": datetime.now(),
        "action": "BUY",
        "timeframe": "15m",
        "entry_price": 2650.0,
        "stop_loss": 2640.0,
        "tps": [2665.0, 2675.0, 2690.0],
        "strength": 80,
        "votes": [],
        "offset": 1.5,
        "risk": {"lot_size": 0.05}
    }
    
    sig_id = journal.log_signal(sig, user_id=111)
    assert sig_id > 0
    
    fetched = journal.get_signal(sig_id)
    assert fetched is not None
    assert fetched["id"] == sig_id
    assert fetched["user_id"] == 111
    assert fetched["action"] == "BUY"
    assert fetched["result"] == "PENDING"
    assert fetched["price_offset"] == 1.5
    assert fetched["lot_size"] == 0.05

def test_journal_mark_trade_open_ownership_and_state(tmp_path):
    db_file = str(tmp_path / "test_sec_journal.db")
    journal = SignalJournal(db_path=db_file)
    
    sig = {
        "generated_at": datetime.now(),
        "action": "BUY",
        "timeframe": "15m",
        "entry_price": 2650.0,
        "stop_loss": 2640.0,
        "tps": [2665.0],
        "offset": 0.0,
    }
    sig_id = journal.log_signal(sig, user_id=111)
    
    # 1. Boshqa foydalanuvchi ochishga urinsa - rad etilishi kerak
    success = journal.mark_trade_open(sig_id, user_id=999)
    assert success is False
    assert journal.get_signal(sig_id)["result"] == "PENDING"
    
    # 2. O'z egasi ochsa - muvaffaqiyatli
    success = journal.mark_trade_open(sig_id, user_id=111)
    assert success is True
    opened_sig = journal.get_signal(sig_id)
    assert opened_sig["result"] == "OPEN"
    assert opened_sig.get("opened_at") is not None
    
    # 3. Allaqachon ochilgan bitimni qayta ochishga urinsa - rad etilishi kerak
    success_again = journal.mark_trade_open(sig_id, user_id=111)
    assert success_again is False

def test_scheduler_uses_stored_price_offset(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_offset_journal.db")
    journal = SignalJournal(db_path=db_file)
    monkeypatch.setattr("bot.scheduler.journal_service", journal)
    
    # Foydalanuvchining joriy sozlamasida offset = 5.0 bo'lsin
    monkeypatch.setattr("bot.scheduler.get_settings", lambda uid: {"price_offset": 5.0, "balance": 500.0, "risk_percent": 1.0})
    
    now = datetime.now()
    # Lekin signal paytida offset = 0.0 bo'lgan
    sig = {
        "generated_at": now,
        "action": "BUY",
        "timeframe": "15m",
        "entry_price": 2650.0,
        "stop_loss": 2640.0,
        "tps": [2660.0],
        "offset": 0.0,
        "risk": {"lot_size": 0.1}
    }
    sig_id = journal.log_signal(sig, user_id=777)
    journal.mark_trade_open(sig_id, user_id=777)
    
    # Agar joriy user offseti (5.0) ishlatilsa, u_low = 2638.0 + 5.0 = 2643.0 > sl(2640.0), demak SL urilmaydi.
    # Lekin signal offseti (0.0) ishlatilsa, u_low = 2638.0 <= 2640.0, demak LOSS uriladi!
    notifs = _process_open_trades(now, current_price=2638.0)
    assert len(notifs) == 1
    assert "LOSS" in notifs[0][1]

@pytest.mark.anyio
async def test_cb_trade_opened_security(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_cb_journal.db")
    journal = SignalJournal(db_path=db_file)
    monkeypatch.setattr("bot.handlers.journal_service", journal)

    sig = {
        "generated_at": datetime.now(),
        "action": "BUY",
        "timeframe": "15m",
        "entry_price": 2650.0,
        "stop_loss": 2640.0,
        "tps": [2665.0],
        "offset": 0.0,
    }
    sig_id = journal.log_signal(sig, user_id=123)

    # 1. Boshqa foydalanuvchi bosganda alert chiqishi
    cb_other = MagicMock()
    cb_other.data = f"trade_opened:{sig_id}"
    cb_other.from_user.id = 999
    cb_other.answer = AsyncMock()
    await cb_trade_opened(cb_other)
    assert "sizga tegishli emas" in cb_other.answer.call_args[0][0]

    # 2. O'z egasi bosganda muvaffaqiyatli
    cb_owner = MagicMock()
    cb_owner.data = f"trade_opened:{sig_id}"
    cb_owner.from_user.id = 123
    cb_owner.message.reply_markup = None
    cb_owner.answer = AsyncMock()
    await cb_trade_opened(cb_owner)
    assert "Bitim jurnalga ochiq" in cb_owner.answer.call_args[0][0]

    # 3. Qayta bosganda - allaqachon ochilganligi haqida xabar
    cb_owner_again = MagicMock()
    cb_owner_again.data = f"trade_opened:{sig_id}"
    cb_owner_again.from_user.id = 123
    cb_owner_again.answer = AsyncMock()
    await cb_trade_opened(cb_owner_again)
    assert "allaqachon ochilgan" in cb_owner_again.answer.call_args[0][0]

@pytest.mark.anyio
async def test_cb_calc_whitelist_validation():
    # calc_dep ruxsat etilmagan qiymat
    cb_dep = MagicMock()
    cb_dep.data = "calc_dep:99999"
    cb_dep.from_user.id = 123
    cb_dep.answer = AsyncMock()
    await cb_calc_dep(cb_dep)
    assert "Ruxsat etilmagan" in cb_dep.answer.call_args[0][0]

    # calc_risk ruxsat etilmagan qiymat
    cb_risk = MagicMock()
    cb_risk.data = "calc_risk:100.0"
    cb_risk.from_user.id = 123
    cb_risk.answer = AsyncMock()
    await cb_calc_risk(cb_risk)
    assert "Ruxsat etilmagan" in cb_risk.answer.call_args[0][0]
