import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from config import settings
from services.journal import SignalJournal
import bot.scheduler as scheduler


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, user_id, text, **kwargs):
        self.sent.append((user_id, text))


def _make_sig(action="BUY", minutes_ago=0):
    return {
        "generated_at": datetime.now(ZoneInfo(settings.TIMEZONE)) - timedelta(minutes=minutes_ago),
        "action": action,
        "timeframe": "15m",
        "entry_price": 2650.0,
        "stop_loss": 2645.0,
        "tps": [2657.5, 2662.5, 2670.0],
        "strength": 80,
        "votes": [],
        "risk": {"lot_size": 0.02},
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    journal = SignalJournal(db_path=str(tmp_path / "j.db"))
    monkeypatch.setattr(scheduler, "journal_service", journal)
    monkeypatch.setattr(scheduler, "get_settings", lambda uid: {
        "timeframe": "15m", "balance": 1000, "risk_percent": 1, "price_offset": 0.0,
    })
    monkeypatch.setattr(scheduler, "format_signal", lambda sig: "SIGNAL")
    monkeypatch.setattr(scheduler, "get_signal_inline_kb", lambda tf, sid: None)
    return journal


def _count_rows(journal):
    with journal._connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]


def test_first_signal_is_sent_and_logged_once(env, monkeypatch):
    monkeypatch.setattr(scheduler, "build_signal", lambda cfg, tf: _make_sig())
    bot = FakeBot()
    asyncio.run(scheduler._send_signal_alert(bot, 42))
    assert len(bot.sent) == 1
    assert _count_rows(env) == 1


def test_duplicate_within_hour_is_skipped_and_not_logged(env, monkeypatch):
    env.log_signal(_make_sig(minutes_ago=20), user_id=42)
    monkeypatch.setattr(scheduler, "build_signal", lambda cfg, tf: _make_sig())
    bot = FakeBot()
    asyncio.run(scheduler._send_signal_alert(bot, 42))
    assert bot.sent == []
    assert _count_rows(env) == 1  # yangi yozuv qo'shilmadi


def test_wait_signal_is_not_sent_or_logged(env, monkeypatch):
    monkeypatch.setattr(scheduler, "build_signal", lambda cfg, tf: _make_sig(action="WAIT"))
    bot = FakeBot()
    asyncio.run(scheduler._send_signal_alert(bot, 42))
    assert bot.sent == []
    assert _count_rows(env) == 0


def test_lot_size_is_stored(env):
    sid = env.log_signal(_make_sig(), user_id=1)
    with env._connection() as conn:
        lot = conn.execute("SELECT lot_size FROM signals WHERE id=?", (sid,)).fetchone()[0]
    assert lot == pytest.approx(0.02)
