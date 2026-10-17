"""Ishonchlilik (reliability) qatlami testlari: seans filtri, kengaytirilgan statistika."""
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from bot.formatters import format_performance
from services.journal import SignalJournal
from services.signal_generator import in_session

ROOT = Path(__file__).resolve().parents[1]


# --- Seans filtri ---

def test_in_session_default_window():
    # Config: [8, 22) UTC
    assert in_session(datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)) is True
    assert in_session(datetime(2026, 1, 5, 21, 59, tzinfo=timezone.utc)) is True
    assert in_session(datetime(2026, 1, 5, 22, 0, tzinfo=timezone.utc)) is False
    assert in_session(datetime(2026, 1, 5, 3, 0, tzinfo=timezone.utc)) is False
    assert in_session(datetime(2026, 1, 5, 7, 59, tzinfo=timezone.utc)) is False


def test_in_session_wrap_around_window():
    # Tunni kesib o'tuvchi seans: [22, 6)
    assert in_session(datetime(2026, 1, 5, 23, 0, tzinfo=timezone.utc), start=22, end=6) is True
    assert in_session(datetime(2026, 1, 5, 5, 0, tzinfo=timezone.utc), start=22, end=6) is True
    assert in_session(datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc), start=22, end=6) is False


# --- Kengaytirilgan jurnal statistikasi ---

def test_get_detailed_stats(tmp_path):
    journal = SignalJournal(db_path=str(tmp_path / "j.db"))

    def add(action, result, pnl, uid=1):
        sig = {
            "generated_at": datetime.now(), "action": action, "timeframe": "M15",
            "entry_price": 2650.0, "stop_loss": 2645.0, "tps": [2660.0],
            "strength": 80, "votes": [],
        }
        sid = journal.log_signal(sig, user_id=uid)
        journal.mark_trade_closed(sid, result, pnl=pnl)

    add("BUY", "WIN", 10.0)
    add("BUY", "LOSS", -5.0)
    add("SELL", "LOSS", -5.0)

    stats = journal.get_detailed_stats(1)
    assert stats["total"] == 3
    assert stats["wins"] == 1 and stats["losses"] == 2
    assert stats["profit_factor"] == pytest.approx(1.0)
    assert stats["total_pnl"] == pytest.approx(0.0)
    assert stats["by_action"]["BUY"]["total"] == 2
    assert stats["by_action"]["SELL"]["total"] == 1


def test_get_detailed_stats_empty(tmp_path):
    journal = SignalJournal(db_path=str(tmp_path / "empty.db"))
    stats = journal.get_detailed_stats(42)
    assert stats["total"] == 0
    assert stats["profit_factor"] == 0.0


# --- Natijalar formatteri ---

def test_format_performance_empty():
    text = format_performance({"total": 0})
    assert "Hozircha yopilgan bitim yo'q" in text


def test_format_performance_with_data():
    stats = {
        "total": 30, "wins": 13, "losses": 17, "win_rate": 43.3,
        "total_pnl": 25.5, "profit_factor": 1.12, "avg_pnl": 0.85,
        "avg_win": 8.0, "avg_loss": -4.7, "open_count": 2,
        "by_action": {
            "BUY": {"total": 20, "wins": 9, "losses": 11, "win_rate": 45.0, "pnl": 18.0},
            "SELL": {"total": 10, "wins": 4, "losses": 6, "win_rate": 40.0, "pnl": 7.5},
        },
    }
    text = format_performance(stats)
    assert "Profit Factor: <b>1.12</b>" in text
    assert "43.3%" in text
    assert "Umumiy PnL: <b>+25.5$</b>" in text
    assert "BUY" in text and "SELL" in text


# --- Backtest simulyatsiyasi (scripts/backtest.py) ---

@pytest.fixture(scope="module")
def bt():
    spec = importlib.util.spec_from_file_location("bt_script", ROOT / "scripts" / "backtest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _candles(highs, lows, closes):
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=len(highs), freq="15min"),
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1.0] * len(highs),
    })


def test_simulate_buy_tp_after_spread(bt):
    # entry=100, spread=0.5 -> 100.5; SL=95 -> risk=5.5; TP1=110
    df = _candles([100, 106, 111, 100, 100], [100, 99, 100, 100, 100], [100, 105, 110, 100, 100])
    r, reason, idx = bt.simulate(df, 0, "BUY", 95.0, 110.0, 0.5, 10)
    assert reason == "TP"
    assert idx == 2
    assert r == pytest.approx((110.0 - 100.5) / 5.5, rel=1e-9)


def test_simulate_spread_reduces_r(bt):
    df = _candles([100, 106, 111, 100], [100, 99, 100, 100], [100, 105, 110, 100])
    r_no, _, _ = bt.simulate(df, 0, "BUY", 95.0, 110.0, 0.0, 10)
    r_sp, _, _ = bt.simulate(df, 0, "BUY", 95.0, 110.0, 0.5, 10)
    assert r_sp < r_no


def test_simulate_sl_takes_priority_over_tp(bt):
    # Bitta shamchada ham SL, ham TP -> konservativ: SL
    df = _candles([100, 106, 100], [100, 94, 100], [100, 100, 100])
    r, reason, idx = bt.simulate(df, 0, "BUY", 95.0, 105.0, 0.0, 10)
    assert reason == "SL"
    assert r == -1.0


def test_simulate_time_exit(bt):
    df = _candles([100, 100, 100, 100], [100, 100, 100, 99], [100, 100, 100, 99])
    r, reason, idx = bt.simulate(df, 0, "BUY", 95.0, 110.0, 0.0, 2)
    assert reason == "TIME"
    assert idx == 2


def test_simulate_spread_skips_overlapping_signals(bt):
    df = _candles([100, 106, 111, 120, 130], [100, 99, 100, 100, 100], [100, 105, 110, 120, 130])
    cands = [
        {"idx": 0, "action": "BUY", "sl": 95.0, "tp1": 110.0, "strength": 80, "time": df["timestamp"].iloc[0]},
        {"idx": 1, "action": "BUY", "sl": 95.0, "tp1": 110.0, "strength": 80, "time": df["timestamp"].iloc[1]},
    ]
    res = bt.simulate_spread(df, cands, 0.0, 10)
    # Birinchi bitim 2-shamchada yopiladi; idx=1 undan keyin joylashgani uchun tashlab yuboriladi
    assert len(res) == 1
