import pytest

from bot.formatters import format_calc, format_scalp_signal, format_signal
from services.m1_scalper import LIVE_PARAMS
from services.risk_calculator import risk_service
from services.signal_generator import evaluate
from tests.test_signal_logic import NEWS_DANGER, NEWS_SAFE, bullish_setup
from datetime import datetime


def test_format_buy_signal_contains_levels_and_disclaimer():
    tech, smc = bullish_setup()
    sig = evaluate(tech, smc, "BULLISH (O'sish)", NEWS_SAFE, 4140.0, "15m", balance=1000.0)
    text = format_signal(sig)
    assert "BUY" in text and "Stop Loss" in text and "TP3" in text
    assert "Signal sifati" in text
    assert "moliyaviy maslahat emas" in text
    assert "/price" in text  # offset o'rnatilmagani haqida eslatma


def test_format_wait_signal_has_no_levels():
    tech, smc = bullish_setup()
    sig = evaluate(tech, smc, "BULLISH (O'sish)", NEWS_DANGER, 4140.0, "15m")
    text = format_signal(sig)
    assert "WAIT" in text
    assert "ZDELKA SOZLAMALARI" not in text


def test_format_calc():
    risk = risk_service.calculate_lot_size(500.0, 1.0, 4140.0, 4135.0, 4147.5, 4152.5, 4160.0)
    text = format_calc({"balance": 500.0, "risk_percent": 1.0}, 4140.0, risk)
    assert "Tavsiya lot" in text


def test_min_lot_warning_flag():
    risk = risk_service.calculate_lot_size(100.0, 1.0, 4140.0, 4130.0, 4150.0, 4160.0, 4170.0)
    assert risk["lot_size"] == 0.01
    # 100$ * 1% = 1$ risk, lekin 0.01 lot va 10$ SL da zarar 10$ bo'ladi
    assert risk["min_lot_exceeds_risk"] is True
    ok = risk_service.calculate_lot_size(10000.0, 1.0, 4140.0, 4135.0, 4147.5, 4152.5, 4160.0)
    assert ok["min_lot_exceeds_risk"] is False
    tiny = risk_service.calculate_lot_size(50.0, 0.5, 4140.0, 4120.0, 4160.0, 4170.0, 4180.0)
    assert tiny["min_lot_exceeds_risk"] is True


def _scalp_sig(action="BUY"):
    risk = risk_service.calculate_lot_size(1000.0, 1.0, 4140.0, 4138.0, 4145.0, 4145.0, 4145.0)
    return {
        "action": action,
        "timeframe": "1m",
        "current_price": 4140.0,
        "atr": 2.0,
        "htf_trend": "BULLISH",
        "rsi": 55.0,
        "offset": 0.0,
        "generated_at": datetime.now(),
        "valid_minutes": 5,
        "reasons": ["Test sabab"],
        "params": LIVE_PARAMS,
        "entry_price": 4140.0,
        "stop_loss": 4138.0,
        "tp": 4145.0,
        "risk": risk,
    }


def test_format_scalp_signal_has_warning_and_levels():
    text = format_scalp_signal(_scalp_sig("BUY"))
    assert "M1 SKALPING" in text
    assert "EKSPERIMENTAL" in text
    assert "Stop Loss" in text and "Take Profit" in text
    assert "moliyaviy maslahat emas" in text


def test_format_scalp_signal_wait_has_no_levels():
    text = format_scalp_signal(_scalp_sig("WAIT"))
    assert "WAIT" in text
    assert "Take Profit" not in text
