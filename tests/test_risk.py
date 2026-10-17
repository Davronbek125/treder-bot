import pytest
from services.risk_calculator import risk_service

def test_risk_calculator_lot_size():
    # 1000$ balans, 1% risk ($10), SL masofasi 5$
    # raw_lot = 10 / (5 * 100) = 10 / 500 = 0.02 lot
    res = risk_service.calculate_lot_size(
        balance=1000.0,
        risk_percent=1.0,
        entry_price=4140.0,
        stop_loss=4135.0,
        tp1=4147.5,
        tp2=4152.5,
        tp3=4160.0
    )
    assert res["lot_size"] == 0.02
    assert res["actual_sl_loss"] == 10.0
    assert res["tp1_profit"] == 15.0
    assert res["rr_tp1"] == "1:1.5"

def test_risk_calculator_minimum_lot():
    # 100$ kichik balans bo'lsa ham minimal 0.01 lot berishi kerak
    res = risk_service.calculate_lot_size(
        balance=100.0,
        risk_percent=1.0,
        entry_price=4140.0,
        stop_loss=4130.0,
        tp1=4150.0,
        tp2=4160.0,
        tp3=4170.0
    )
    assert res["lot_size"] >= 0.01
