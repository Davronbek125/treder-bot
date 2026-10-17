import pytest
import pandas as pd
from services.smc_analysis import smc_service

def test_swing_points_detection():
    # Oddiy ekstremumlar bilan test ma'lumoti
    data = [10, 12, 15, 20, 14, 11, 8, 5, 7, 12, 18, 11]
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=len(data), freq="15min"),
        "open": data,
        "high": [x + 1 for x in data],
        "low": [x - 1 for x in data],
        "close": data,
        "volume": [500] * len(data)
    })
    swings = smc_service.find_swing_points(df, window=2)
    assert "swing_highs" in swings
    assert "swing_lows" in swings

def test_fvg_detection():
    # Bullish FVG yaratish:
    # Shamcha 1: High = 100
    # Shamcha 2: Katta o'sish
    # Shamcha 3: Low = 105 (Low > High(1) -> 5$ gap)
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=5, freq="15min"),
        "open": [95, 98, 106, 107, 108],
        "high": [100, 105, 110, 111, 112],
        "low": [94, 97, 105, 106, 107],
        "close": [98, 104, 109, 110, 111],
        "volume": [100] * 5
    })
    fvgs = smc_service.detect_fvg(df, min_gap_dollars=1.0)
    assert len(fvgs) >= 1
    assert fvgs[0]["type"] == "BULLISH_FVG"
    assert fvgs[0]["gap"] == 5.0

def test_order_block_detection():
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=6, freq="15min"),
        "open": [100, 102, 105, 101, 102, 115],
        "close": [102, 105, 101, 102, 115, 118],
        "high": [103, 106, 106, 103, 116, 119],
        "low": [99, 101, 100, 100, 101, 114],
        "volume": [100] * 6
    })
    obs = smc_service.detect_order_blocks(df)
    assert isinstance(obs, list)
