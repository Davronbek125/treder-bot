"""Sinxron "view" quruvchilar: ma'lumot olib, tayyor matn qaytaradi (thread ichida chaqiriladi)."""
from typing import Any, Dict, Tuple

from bot.formatters import format_analysis, format_calc, format_performance, format_scalp_signal, format_smc
from services.market_data import market_service
from services.m1_scalper import m1_scalper_service
from services.risk_calculator import risk_service
from services.signal_generator import signal_service
from bot.formatters import format_signal
from services.smc_analysis import smc_service
from services.technical_analysis import technical_service
from services.journal import journal_service

SAMPLE_SL_DOLLARS = 5.0


def build_signal(cfg: Dict[str, Any], timeframe: str) -> Dict[str, Any]:
    """Signalni hisoblaydi, lekin jurnalga YOZMAYDI."""
    return signal_service.generate_signal(timeframe, cfg["balance"], cfg["risk_percent"], cfg["price_offset"])


def signal_text(cfg: Dict[str, Any], timeframe: str, user_id: int = 0) -> Tuple[str, int, str]:
    sig = build_signal(cfg, timeframe)
    
    signal_id = 0
    if sig["action"] in ("BUY", "SELL"):
        signal_id = journal_service.log_signal(sig, user_id)
        
    return format_signal(sig), signal_id, sig["action"]

def signal_text_only(cfg: Dict[str, Any], timeframe: str, user_id: int = 0) -> str:
    return signal_text(cfg, timeframe, user_id)[0]

def analysis_text(cfg: Dict[str, Any], timeframe: str) -> str:
    df = market_service.get_candles(timeframe, 250)
    daily = market_service.get_candles("1d", 30)
    tech = technical_service.analyze(df, pivot_df=daily)
    return format_analysis(tech, timeframe, cfg["price_offset"])


def smc_text(cfg: Dict[str, Any], timeframe: str) -> str:
    df = market_service.get_candles(timeframe, 250)
    price = market_service.get_live_price()
    return format_smc(smc_service.analyze(df), price, timeframe, cfg["price_offset"])


def scalp_text(cfg: Dict[str, Any]) -> str:
    """Eksperimental M1 skalping signali (jonli M1 ma'lumotdan)."""
    sig = m1_scalper_service.generate_signal(
        cfg["balance"], cfg["risk_percent"], cfg["price_offset"],
    )
    return format_scalp_signal(sig)


def performance_text(user_id: int) -> str:
    """Foydalanuvchining real, jurnalga yozilgan natijalari."""
    return format_performance(journal_service.get_detailed_stats(user_id))


def calc_text(cfg: Dict[str, Any]) -> str:
    price = round(market_service.get_live_price() + cfg["price_offset"], 2)
    risk = risk_service.calculate_lot_size(
        balance=cfg["balance"],
        risk_percent=cfg["risk_percent"],
        entry_price=price,
        stop_loss=price - SAMPLE_SL_DOLLARS,
        tp1=price + SAMPLE_SL_DOLLARS * 1.5,
        tp2=price + SAMPLE_SL_DOLLARS * 2.5,
        tp3=price + SAMPLE_SL_DOLLARS * 4.0,
    )
    return format_calc(cfg, price, risk)
