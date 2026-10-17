import numpy as np
import pandas as pd

from services.m1_scalper import M1ScalperService, ScalpParams
from services.market_data import MarketDataError


def _prepared(prices, highs=None, lows=None, action=None, atr=1.0):
    n = len(prices)
    highs = highs if highs is not None else [p + 0.5 for p in prices]
    lows = lows if lows is not None else [p - 0.5 for p in prices]
    acts = ["WAIT"] * n
    if action:
        idx, val = action
        acts[idx] = val
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="1min"),
        "open": prices, "high": highs, "low": lows, "close": prices, "volume": [1.0] * n,
        "action": acts, "atr": [atr] * n, "htf_trend": ["FLAT"] * n, "rsi": [50.0] * n,
    })


def _synthetic(n=600, seed=7):
    rng = np.random.default_rng(seed)
    close = 4000 + np.cumsum(rng.normal(0, 0.5, n))
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="1min"),
        "open": close, "high": close + 0.4, "low": close - 0.4,
        "close": close, "volume": rng.integers(1, 10, n).astype(float),
    })


def test_prepare_adds_indicator_and_signal_columns():
    df = M1ScalperService().prepare(_synthetic())
    for col in ["ema_fast", "ema_slow", "ema_trend", "rsi", "atr", "htf_trend", "action"]:
        assert col in df.columns
    assert set(df["action"].unique()).issubset({"BUY", "SELL", "WAIT"})
    assert set(df["htf_trend"].unique()).issubset({"BULLISH", "BEARISH", "FLAT"})


def test_simulate_requires_prepared_frame():
    df = _synthetic(50)[["timestamp", "open", "high", "low", "close", "volume"]]
    try:
        M1ScalperService().simulate(df)
        assert False, "prepare() qilinmagan df uchun xato kutilgan edi"
    except ValueError:
        pass


def test_stop_loss_gives_minus_one_r():
    df = _prepared([100, 98, 100, 100], action=(0, "BUY"))
    res = M1ScalperService().simulate(df, spread=0.0)
    assert len(res) == 1
    assert res.iloc[0]["reason"] == "SL"
    assert res.iloc[0]["r"] == -1.0


def test_take_profit_gives_tp_over_sl_r():
    p = ScalpParams(sl_atr_mult=1.0, tp_atr_mult=1.5)
    df = _prepared([100, 102, 100, 100], action=(0, "BUY"))
    res = M1ScalperService().simulate(df, p, spread=0.0)
    assert res.iloc[0]["reason"] == "TP"
    assert abs(res.iloc[0]["r"] - 1.5) < 1e-9


def test_spread_reduces_r_multiple():
    p = ScalpParams(sl_atr_mult=1.0, tp_atr_mult=1.5)
    df = _prepared([100, 102, 100, 100], action=(0, "BUY"))
    no_spread = M1ScalperService().simulate(df, p, spread=0.0).iloc[0]["r"]
    with_spread = M1ScalperService().simulate(df, p, spread=0.1).iloc[0]["r"]
    assert with_spread < no_spread


def test_time_exit_after_max_bars():
    p = ScalpParams(max_bars=5)
    # narx tekis — SL ham TP ham tegmaydi
    df = _prepared([100] * 10, action=(0, "BUY"))
    res = M1ScalperService().simulate(df, p, spread=0.0)
    assert res.iloc[0]["reason"] == "TIME"
    assert res.iloc[0]["bars"] == 5
    assert abs(res.iloc[0]["r"]) < 1e-9


def test_sl_has_priority_when_both_hit():
    # bitta shamchada ham TP, ham SL tegadi -> SL ustuvor
    highs = [100.5, 102.5, 100.5, 100.5]
    lows = [99.5, 97.5, 99.5, 99.5]
    df = _prepared([100, 100, 100, 100], highs=highs, lows=lows, action=(0, "BUY"))
    res = M1ScalperService().simulate(df, spread=0.0)
    assert res.iloc[0]["reason"] == "SL"


def test_no_overlapping_trades():
    df = _prepared([100] * 20, action=(0, "BUY"))
    df.loc[[1, 2, 3, 4, 5], "action"] = "BUY"  # bitim ichida takroriy signallar
    res = M1ScalperService().simulate(df, ScalpParams(max_bars=5), spread=0.0)
    # birinchi bitim 0-shамчadan boshlanib 5-shамчаda yopiladi, keyingisi undan keyin
    assert len(res) >= 1
    starts = list(res["bars"])
    assert starts[0] == 5


def test_sell_signal_direction():
    p = ScalpParams(sl_atr_mult=1.0, tp_atr_mult=1.5)
    df = _prepared([100, 98, 100, 100], action=(0, "SELL"))
    res = M1ScalperService().simulate(df, p, spread=0.0)
    assert res.iloc[0]["reason"] == "TP"
    assert abs(res.iloc[0]["r"] - 1.5) < 1e-9


def test_prepare_handles_ms_resolution_timestamps():
    # Binance ma'lumoti ms aniqlikda keladi; merge_asof dtype mosligini tekshiramiz
    df = _synthetic(400)
    df["timestamp"] = df["timestamp"].astype("datetime64[ms]")
    out = M1ScalperService().prepare(df)
    assert len(out) == len(df)
    assert set(out["htf_trend"].unique()).issubset({"BULLISH", "BEARISH", "FLAT"})


# --- Jonli signal (generate_signal) ---

def _trend_m1(n=3000, up=True):
    base = 4000.0
    step = 0.05 if up else -0.05
    close = [base + i * step + (0.5 if i % 3 == 0 else -0.5) for i in range(n)]
    close = np.array(close)
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="1min"),
        "open": close, "high": close + 0.4, "low": close - 0.4,
        "close": close, "volume": [5.0] * n,
    })


def test_generate_signal_structure(monkeypatch):
    monkeypatch.setattr("services.m1_scalper.fetch_history", lambda interval, total, **kw: _trend_m1())
    sig = M1ScalperService().generate_signal(balance=1000.0, risk_percent=1.0)

    assert sig["timeframe"] == "1m"
    assert sig["valid_minutes"] == 5
    assert sig["action"] in {"BUY", "SELL", "WAIT"}
    for key in ["current_price", "atr", "htf_trend", "rsi", "reasons", "params", "generated_at"]:
        assert key in sig

    if sig["action"] in ("BUY", "SELL"):
        assert sig["entry_price"] is not None
        assert sig["stop_loss"] is not None
        assert sig["tp"] is not None
        assert sig["risk"]["lot_size"] > 0
        if sig["action"] == "BUY":
            assert sig["stop_loss"] < sig["entry_price"] < sig["tp"]
        else:
            assert sig["tp"] < sig["entry_price"] < sig["stop_loss"]


def test_generate_signal_wait_on_flat_market(monkeypatch):
    flat = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=3000, freq="1min"),
        "open": [4000.0] * 3000, "high": [4000.0] * 3000, "low": [4000.0] * 3000,
        "close": [4000.0] * 3000, "volume": [1.0] * 3000,
    })
    monkeypatch.setattr("services.m1_scalper.fetch_history", lambda interval, total, **kw: flat)
    sig = M1ScalperService().generate_signal()
    assert sig["action"] == "WAIT"


def test_generate_signal_raises_on_short_data(monkeypatch):
    monkeypatch.setattr("services.m1_scalper.fetch_history", lambda interval, total, **kw: _trend_m1(100))
    try:
        M1ScalperService().generate_signal()
        assert False, "qisqa ma'lumotda MarketDataError kutilgan edi"
    except MarketDataError:
        pass
