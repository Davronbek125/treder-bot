import pytest
from services.ensemble import ensemble_service

def make_base_data():
    tech = {
        "current_price": 2650.0,
        "atr": 4.0,
        "ema20": 2655.0,
        "ema50": 2645.0,
        "ema200": 2630.0,
        "supertrend": 1,
        "adx": 25.0,
        "rsi": 58.0,
        "macd": 2.5,
        "macd_signal": 1.5,
        "macd_hist": 1.0,
        "stoch_k": 65.0,
        "cci": 80.0,
        "pivots": {"s1": 2640.0, "s2": 2630.0, "r1": 2670.0, "r2": 2680.0},
        "bb_lower": 2635.0,
        "bb_upper": 2665.0,
        "vwap": 2645.0,
    }
    smc = {
        "structure": "BULLISH BOS",
        "active_bullish_fvg": [{"top": 2648.0, "bottom": 2645.0}],
        "active_bearish_fvg": [],
        "recent_highs": [2660.0],
        "recent_lows": [2640.0],
    }
    news = {
        "safe_to_trade": True,
        "recommendation": "Normal bozor",
    }
    return tech, smc, news

def test_ensemble_buy_consensus():
    tech, smc, news = make_base_data()
    # Narx bb_lower ga yaqinlashtirib pivotes s1 ga yaqinlashtiramiz
    tech["current_price"] = 2641.0  # s1=2640 ga yaqin, bb_lower=2635 (+2=2637)
    decision = ensemble_service.get_decision(tech, smc, htf_trend="BULLISH", news=news)
    
    assert decision["action"] == "BUY"
    assert decision["buy_votes"] >= 2
    assert decision["strength"] >= 60
    assert len(decision["reasons"]) > 0

def test_ensemble_veto_by_news():
    tech, smc, news = make_base_data()
    news["safe_to_trade"] = False
    news["recommendation"] = "FOMC foiz stavkasi e'lon qilinmoqda"
    
    decision = ensemble_service.get_decision(tech, smc, htf_trend="BULLISH", news=news)
    assert decision["action"] == "WAIT"
    assert decision["strength"] == 0
    assert any("VETO: Fundamental xavf" in r for r in decision["reasons"])

def test_ensemble_veto_by_counter_htf():
    tech, smc, news = make_base_data()
    # Barcha indikatorlar BUY beradi, lekin HTF BEARISH
    decision = ensemble_service.get_decision(tech, smc, htf_trend="BEARISH", news=news)
    assert decision["action"] == "WAIT"
    assert any("VETO: Katta taymfreym (HTF) trendiga qarshi" in r for r in decision["reasons"])

def test_ensemble_sell_consensus():
    tech, smc, news = make_base_data()
    # Hamma indikatorlarni pasayish (SELL) ga sozlaymiz
    tech["ema20"] = 2620.0
    tech["ema50"] = 2640.0
    tech["ema200"] = 2660.0
    tech["supertrend"] = -1
    tech["adx"] = 28.0
    tech["rsi"] = 42.0
    tech["macd"] = -3.0
    tech["macd_signal"] = -1.5
    tech["macd_hist"] = -1.5
    tech["stoch_k"] = 35.0
    tech["cci"] = -90.0
    tech["vwap"] = 2660.0
    tech["current_price"] = 2655.0
    tech["pivots"] = {"r1": 2656.0, "s1": 2620.0}
    tech["bb_upper"] = 2656.0
    tech["bb_lower"] = 2630.0
    
    smc["structure"] = "BEARISH BOS"
    smc["active_bullish_fvg"] = []
    smc["active_bearish_fvg"] = [{"top": 2658.0, "bottom": 2654.0}]
    
    decision = ensemble_service.get_decision(tech, smc, htf_trend="BEARISH", news=news)
    assert decision["action"] == "SELL"
    assert decision["sell_votes"] >= 2
    assert decision["strength"] >= 60

def test_ensemble_insufficient_consensus():
    tech, smc, news = make_base_data()
    # Neytral holat
    tech["ema20"] = 2645.0
    tech["ema50"] = 2648.0
    tech["ema200"] = 2640.0 # aralash
    tech["adx"] = 12.0 # zaif
    tech["rsi"] = 75.0 # ekstremum
    tech["macd_hist"] = 0.0
    tech["stoch_k"] = 52.0
    tech["cci"] = 10.0
    smc["structure"] = "NEUTRAL"
    smc["active_bullish_fvg"] = []
    smc["active_bearish_fvg"] = []
    
    decision = ensemble_service.get_decision(tech, smc, htf_trend=None, news=news)
    assert decision["action"] == "WAIT"
    assert any("Yetarli kelishuv yo'q" in r for r in decision["reasons"])
