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
