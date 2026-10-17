import pytest
import pandas as pd
import numpy as np
from services.technical_analysis import technical_service

def create_synthetic_data(n=100):
    prices = [4000.0 + i * 0.5 + np.sin(i) * 3.0 for i in range(n)]
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="15min"),
        "open": prices,
        "high": [p + 2.0 for p in prices],
        "low": [p - 2.0 for p in prices],
        "close": prices,
        "volume": [1000] * n
    })
    return df

def test_ema_calculation():
    df = create_synthetic_data(50)
    ema20 = technical_service.calculate_ema(df["close"], 20)
    assert len(ema20) == 50
    assert not ema20.isna().all()
    assert ema20.iloc[-1] > 4000.0

def test_rsi_calculation():
    df = create_synthetic_data(60)
    rsi = technical_service.calculate_rsi(df["close"], 14)
    assert len(rsi) == 60
    last_rsi = rsi.iloc[-1]
    assert 0 <= last_rsi <= 100

def test_macd_calculation():
    df = create_synthetic_data(60)
    macd_res = technical_service.calculate_macd(df["close"])
    assert "macd" in macd_res
    assert "signal" in macd_res
    assert "hist" in macd_res
    assert len(macd_res["hist"]) == 60

def test_atr_calculation():
    df = create_synthetic_data(60)
    atr = technical_service.calculate_atr(df, 14)
    assert len(atr) == 60
    assert atr.iloc[-1] > 0

def test_technical_analyze():
    df = create_synthetic_data(80)
    res = technical_service.analyze(df)
    assert "current_price" in res
    assert "trend" in res
    assert "rsi" in res
    assert "pivots" in res
    assert res["pivots"]["r1"] >= res["pivots"]["pivot"]
    assert res["pivots"]["s1"] <= res["pivots"]["pivot"]
