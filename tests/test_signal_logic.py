import pandas as pd
import pytest

from services.signal_generator import _levels, evaluate
from services.ensemble import ensemble_service

NEWS_SAFE = {"safe_to_trade": True, "status_text": "SAFE", "recommendation": "", "calendar_ok": True}
NEWS_DANGER = {"safe_to_trade": False, "status_text": "DANGER", "recommendation": "Yangilik kutilmoqda", "calendar_ok": True}


def make_tech(**over):
    base = {
        "current_price": 4140.0, "trend": "FLAT / SIDEWAYS", "ema20": 4139.0, "ema50": 4135.0,
        "ema200": 4100.0, "ema200_reliable": True, "above_ema200": True,
        "rsi": 52.0, "macd": 1.0, "macd_signal": 0.5, "macd_hist": 0.5, "atr": 4.0,
        "bb_lower": 4100.0, "bb_upper": 4200.0
    }
    return {**base, **over}


def make_smc(**over):
    base = {
        "structure": "RANGE", "recent_highs": [], "recent_lows": [],
        "active_bullish_fvg": [], "active_bearish_fvg": [],
    }
    return {**base, **over}


def bullish_setup():
    return (
        make_tech(trend="BULLISH (O'sish)", rsi=58.0, macd_hist=1.2, supertrend=1, adx=25, vwap=4100),
        make_smc(structure="BULLISH BOS", active_bullish_fvg=[{"top": 4138, "bottom": 4135, "gap": 3}]),
    )


def test_strong_bullish_alignment_gives_buy():
    tech, smc = bullish_setup()
    sig = evaluate(tech, smc, "BULLISH (O'sish)", NEWS_SAFE, 4140.0, "15m")
    assert sig["action"] == "BUY"
    assert sig["strength"] >= 60
    assert sig["stop_loss"] < sig["entry_price"] < sig["tps"][0] < sig["tps"][1] < sig["tps"][2]


def test_news_danger_forces_wait_even_with_strong_setup():
    tech, smc = bullish_setup()
    sig = evaluate(tech, smc, "BULLISH (O'sish)", NEWS_DANGER, 4140.0, "15m")
    assert sig["action"] == "WAIT"
    assert sig["stop_loss"] is None and sig["risk"] is None


def test_mixed_signals_give_wait():
    tech = make_tech(trend="BULLISH (O'sish)", rsi=40.0, macd_hist=-0.5)
    sig = evaluate(tech, make_smc(), "BEARISH (Pasayish)", NEWS_SAFE, 4140.0, "15m")
    assert sig["action"] == "WAIT"


def test_news_does_not_inflate_scores():
    tech, smc = bullish_setup()
    safe = ensemble_service.get_decision(tech, smc, "BULLISH (O'sish)", NEWS_SAFE)
    assert safe["strength"] <= 100


def test_sell_levels_are_mirrored():
    tech = make_tech(
        trend="BEARISH (Pasayish)", rsi=42.0, macd=-1.0, macd_signal=-0.5, macd_hist=-1.0, 
        ema20=4000, ema50=4050, ema200=4100, above_ema200=False,
        supertrend=-1, adx=25, vwap=4200, current_price=4050.0
    )
    smc = make_smc(structure="BEARISH BOS", active_bearish_fvg=[{"top": 4150, "bottom": 4145, "gap": 5}])
    sig = evaluate(tech, smc, "BEARISH (Pasayish)", NEWS_SAFE, 4140.0, "15m")
    assert sig["action"] == "SELL"
    assert sig["stop_loss"] > sig["entry_price"] > sig["tps"][0] > sig["tps"][1] > sig["tps"][2]


def test_offset_shifts_all_levels_equally():
    tech, smc = bullish_setup()
    base = evaluate(tech, smc, "BULLISH (O'sish)", NEWS_SAFE, 4140.0, "15m")
    shifted = evaluate(tech, smc, "BULLISH (O'sish)", NEWS_SAFE, 4140.0, "15m", offset=12.5)
    assert shifted["entry_price"] == pytest.approx(base["entry_price"] + 12.5)
    assert shifted["stop_loss"] == pytest.approx(base["stop_loss"] + 12.5)
    assert shifted["tps"][0] == pytest.approx(base["tps"][0] + 12.5)
    assert shifted["risk"]["sl_distance"] == pytest.approx(base["risk"]["sl_distance"])


def test_levels_risk_reward_ratios():
    lv = _levels("BUY", 4140.0, 4.0, make_smc())
    sl_dist = 4140.0 - lv["stop_loss"]
    # SMC daraja yo'q -> minimal SL: MIN_SL_ATR_MULT * ATR = 3.5 * 4
    assert sl_dist == pytest.approx(14.0)
    assert lv["tps"][0] - 4140.0 == pytest.approx(sl_dist * 1.5, abs=0.02)
    assert lv["tps"][2] - 4140.0 == pytest.approx(sl_dist * 4.0, abs=0.02)


def test_levels_stop_outside_noise_band():
    """SL hech qachon 3.5*ATR dan torroq bo'lmasligi kerak (shovqin zonasi)."""
    # Yaqin SMC daraja (1.5 ATR) -> floor qo'llaniladi
    near = _levels("BUY", 4140.0, 4.0, make_smc(recent_lows=[4134.0]))  # 6$ = 1.5 ATR
    assert 4140.0 - near["stop_loss"] == pytest.approx(14.0)

    # Uzoq SMC daraja (3.4 ATR) -> struktura hurmat qilinadi
    far = _levels("BUY", 4140.0, 4.0, make_smc(recent_lows=[4126.4]))  # 13.6$ = 3.4 ATR
    assert 4140.0 - far["stop_loss"] == pytest.approx(13.6 + 0.3 * 4.0)


def test_daily_without_htf_is_normalized():
    tech, smc = bullish_setup()
    with_htf = ensemble_service.get_decision(tech, smc, "BULLISH (O'sish)", NEWS_SAFE)["strength"]
    without = ensemble_service.get_decision(tech, smc, None, NEWS_SAFE)["strength"]
    assert without <= 100
    assert with_htf <= 100
