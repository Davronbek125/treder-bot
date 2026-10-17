import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
from datetime import datetime

from bot.handlers import (
    cmd_start,
    cmd_help,
    cmd_price,
    cmd_signal,
    cb_signal,
    cmd_analysis,
    cb_analysis,
    cmd_smc,
    cmd_news,
    cmd_scalp,
    cmd_stats,
    cmd_backtest,
    cmd_calc,
    cb_open_calc,
)
from bot import views
from bot import keyboards

def sample_df(n=50):
    now = datetime.now()
    from datetime import timedelta
    return pd.DataFrame({
        "timestamp": [now + timedelta(minutes=15 * i) for i in range(n)],
        "open": [2650.0 + i * 0.1 for i in range(n)],
        "high": [2655.0 + i * 0.1 for i in range(n)],
        "low": [2645.0 + i * 0.1 for i in range(n)],
        "close": [2652.0 + i * 0.1 for i in range(n)],
        "volume": [500.0] * n,
    })

@pytest.mark.anyio
async def test_cmd_start():
    msg = MagicMock()
    msg.from_user.id = 12345
    msg.answer = AsyncMock()
    await cmd_start(msg)
    assert msg.answer.called
    assert "XAUUSD" in msg.answer.call_args[0][0]

@pytest.mark.anyio
async def test_cmd_help():
    msg = MagicMock()
    msg.from_user.id = 12345
    msg.answer = AsyncMock()
    await cmd_help(msg)
    assert msg.answer.called
    assert "SOZLAMALAR" in msg.answer.call_args[0][0]

@pytest.mark.anyio
async def test_cmd_price_various():
    msg = MagicMock()
    msg.from_user.id = 12345
    msg.answer = AsyncMock()

    # 1. No args
    cmd_obj = MagicMock()
    cmd_obj.args = ""
    await cmd_price(msg, cmd_obj)
    assert "Hozirgi broker narx farqi" in msg.answer.call_args[0][0]

    # 2. Reset
    cmd_obj.args = "reset"
    await cmd_price(msg, cmd_obj)
    assert "bekor qilindi" in msg.answer.call_args[0][0]

    # 3. Invalid float
    cmd_obj.args = "abc"
    await cmd_price(msg, cmd_obj)
    assert "noto'g'ri" in msg.answer.call_args[0][0]

    # 4. Out of range sanity
    cmd_obj.args = "100"
    await cmd_price(msg, cmd_obj)
    assert "real emas" in msg.answer.call_args[0][0]

    # 5. Valid price with mock feed
    with patch("services.market_data.market_service.get_live_price", return_value=2650.0):
        cmd_obj.args = "2652.5"
        await cmd_price(msg, cmd_obj)
        assert "Moslandi" in msg.answer.call_args[0][0]

@pytest.mark.anyio
async def test_cmd_signal_and_cb(monkeypatch):
    dummy_signal = {
        "symbol": "XAUUSD",
        "action": "BUY",
        "timeframe": "15m",
        "current_price": 2650.0,
        "entry_price": 2650.0,
        "stop_loss": 2640.0,
        "tps": [2660.0],
        "strength": 80,
        "votes": [],
        "reasons": ["Test"],
        "news_safe": True,
        "news_status": "OK",
        "offset": 0.0,
        "generated_at": datetime.now(),
        "valid_minutes": 30,
        "htf_timeframe": "1h",
        "htf_trend": "BULLISH",
        "risk": {"lot_size": 0.05, "balance": 500.0, "risk_amount_usd": 5.0, "actual_sl_loss": 5.0, "rr_tp1": "1:2.0", "tp1_profit": 10.0}
    }
    monkeypatch.setattr("bot.views.build_signal", lambda cfg, tf: dummy_signal)
    monkeypatch.setattr("services.journal.journal_service.log_signal", lambda sig, uid: 42)

    msg = MagicMock()
    msg.from_user.id = 12345
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=status_msg)

    await cmd_signal(msg)
    assert status_msg.edit_text.called

    cb = MagicMock()
    cb.data = "sig_tf:15m"
    cb.from_user.id = 12345
    cb.message = status_msg
    cb.answer = AsyncMock()
    await cb_signal(cb)
    assert cb.answer.called

@pytest.mark.anyio
async def test_cmd_analysis_and_cb(monkeypatch):
    monkeypatch.setattr("services.market_data.market_service.get_candles", lambda tf, limit: sample_df())
    
    msg = MagicMock()
    msg.from_user.id = 12345
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=status_msg)

    await cmd_analysis(msg)
    assert status_msg.edit_text.called

    cb = MagicMock()
    cb.data = "ana_tf:1h"
    cb.from_user.id = 12345
    cb.message = status_msg
    cb.answer = AsyncMock()
    await cb_analysis(cb)
    assert cb.answer.called

@pytest.mark.anyio
async def test_cmd_smc_and_news(monkeypatch):
    monkeypatch.setattr("services.market_data.market_service.get_candles", lambda tf, limit: sample_df())
    monkeypatch.setattr("services.market_data.market_service.get_live_price", lambda: 2650.0)
    # Tarmoqqa chiqmaslik uchun yangiliklar xulosasini bloklaymiz
    monkeypatch.setattr("services.news_service.news_service.format_news_summary_uz", lambda: "📰 Test yangiliklar")
    monkeypatch.setattr("bot.handlers.news_service.format_news_summary_uz", lambda: "📰 Test yangiliklar")

    msg = MagicMock()
    msg.from_user.id = 12345
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=status_msg)

    await cmd_smc(msg)
    assert status_msg.edit_text.called

    await cmd_news(msg)
    assert status_msg.edit_text.called

@pytest.mark.anyio
async def test_cmd_scalp(monkeypatch):
    monkeypatch.setattr("bot.views.scalp_text", lambda cfg: "⚡ M1 SKALPING test signali")
    msg = MagicMock()
    msg.from_user.id = 12345
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=status_msg)

    await cmd_scalp(msg)
    assert status_msg.edit_text.called
    assert "M1 SKALPING" in status_msg.edit_text.call_args[0][0]


@pytest.mark.anyio
async def test_cmd_stats_and_backtest(monkeypatch):
    msg = MagicMock()
    msg.from_user.id = 12345
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=status_msg)

    await cmd_stats(msg)
    assert status_msg.edit_text.called

    cmd_obj = MagicMock()
    cmd_obj.args = "1h"
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=status_msg)
    monkeypatch.setattr("services.market_data.market_service.get_candles", lambda tf, limit: sample_df())

    await cmd_backtest(msg, cmd_obj)
    assert status_msg.edit_text.called

@pytest.mark.anyio
async def test_cmd_calc_and_views(monkeypatch):
    monkeypatch.setattr("services.market_data.market_service.get_live_price", lambda: 2650.0)
    cfg = {"balance": 500.0, "risk_percent": 1.0, "price_offset": 0.0, "timeframe": "15m"}
    
    msg = MagicMock()
    msg.from_user.id = 12345
    status_msg = MagicMock()
    status_msg.edit_text = AsyncMock()
    msg.answer = AsyncMock(return_value=status_msg)

    await cmd_calc(msg)
    assert status_msg.edit_text.called

    cb = MagicMock()
    cb.from_user.id = 12345
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    await cb_open_calc(cb)
    assert cb.message.answer.called

    # views check
    calc_res = views.calc_text(cfg)
    assert "LOT KALKULYATORI" in calc_res
    
    # keyboards check
    kb_main = keyboards.get_main_keyboard()
    assert kb_main is not None
    kb_sig = keyboards.get_signal_inline_kb("15m", signal_id=10)
    assert kb_sig is not None
    kb_ana = keyboards.get_analysis_inline_kb("1h")
    assert kb_ana is not None
    kb_calc = keyboards.get_calc_keyboard()
    assert kb_calc is not None
