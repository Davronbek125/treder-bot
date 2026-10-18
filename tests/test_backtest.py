import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from services.backtester import backtester_service

def generate_sample_candles(n=120):
    np.random.seed(42)
    base_price = 2650.0
    prices = [base_price]
    for _ in range(n - 1):
        change = np.random.normal(0, 2.0)
        prices.append(prices[-1] + change)
        
    timestamps = [datetime(2026, 1, 1) + timedelta(minutes=15 * i) for i in range(n)]
    
    highs = [p + abs(np.random.normal(1.5, 0.5)) for p in prices]
    lows = [p - abs(np.random.normal(1.5, 0.5)) for p in prices]
    opens = [(highs[i] + lows[i]) / 2 for i in range(n)]
    closes = prices
    volumes = [np.random.randint(100, 1000) for _ in range(n)]
    
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })

def test_backtest_execution():
    df = generate_sample_candles(150)
    res = backtester_service.run_backtest(df, timeframe="15m", warmup=40)
    
    assert "total_bars" in res
    assert res["total_bars"] == 150
    assert "win_rate" in res
    assert "profit_factor" in res
    assert "max_drawdown_r" in res
    assert isinstance(res["trades"], list)
    
    # Format report tekshiruvi
    report = backtester_service.format_backtest_report(res, "15m")
    assert "BACKTEST NATIJALARI" in report
    assert "Win Rate:" in report

def test_backtest_short_df():
    df = generate_sample_candles(30)
    res = backtester_service.run_backtest(df, warmup=50)
    assert "error" in res


def test_backtester_tp1_does_not_move_sl_to_be(monkeypatch):
    """TP1 dan keyin SL BE (kirish) ga SURILMASLIGI kerak.

    Aks holda narx kirishga qaytishi bilan bitim yopilib, TP2/TP3 imkoni yo'qoladi.
    Backtest: BE ga surish PF ni ~1.20 dan ~1.05 ga tushirgan (scripts/backtest.py --sweep).
    """
    import services.backtester as bt

    monkeypatch.setattr(bt.technical_service, "analyze", lambda df: {"atr": 2.0})
    monkeypatch.setattr(bt.smc_service, "analyze", lambda df: {})
    monkeypatch.setattr(
        bt.ensemble_service, "get_decision",
        lambda **kw: {"action": "BUY", "strength": 90, "buy_votes": 3, "sell_votes": 0},
    )
    monkeypatch.setattr(
        bt, "_levels",
        lambda action, price, atr, smc, timeframe=None: {
            "stop_loss": price - 10.0,
            "tps": [price + 10.0, price + 20.0, price + 30.0],
        },
    )

    # idx 1: kirish (100) | idx 2: TP1 (110) | idx 3: kirishga qaytdi (95, SL=90 dan yuqori)
    # idx 4: TP2 (120) uriladi
    highs = [100, 100, 111, 100, 121, 120, 120, 120, 120, 120, 120, 120]
    lows = [100, 100, 105, 95, 100, 120, 120, 120, 120, 120, 120, 120]
    closes = [100, 100, 110, 96, 120, 120, 120, 120, 120, 120, 120, 120]
    df = pd.DataFrame({
        "timestamp": [datetime(2026, 1, 1, 8, 0) + timedelta(hours=i) for i in range(12)],
        "open": closes, "high": highs, "low": lows, "close": closes,
        "volume": [1.0] * 12,
    })

    res = backtester_service.run_backtest(
        df, timeframe="1h", warmup=1, max_holding_bars=10, cooldown_bars=10, spread=0.0
    )
    assert res["total_trades"] == 1
    trade = res["trades"][0]
    # BE da yopilgan bo'lsa "WIN (BE)" bo'lardi; to'g'ri natija - TP2 gacha ushlab turish
    assert trade["result"] == "WIN (TP2)"
    assert "BE" not in trade["result"]
    assert trade["pnl_r"] == pytest.approx(1.5)  # 0.5 (TP1) + 1.0 (TP2 ning yarmi)
