import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

from config import settings
from services.market_data import market_service
from services.news_service import news_service
from services.risk_calculator import risk_service
from services.smc_analysis import smc_service
from services.technical_analysis import technical_service

log = logging.getLogger(__name__)

# Yuqori timeframe (trend tasdig'i uchun)
HTF_MAP: Dict[str, Optional[str]] = {"5m": "1h", "15m": "1h", "1h": "4h", "4h": "1d", "1d": None}
# Signal necha daqiqa davomida dolzarb hisoblanadi
VALID_MINUTES: Dict[str, int] = {"5m": 10, "15m": 30, "1h": 90, "4h": 240, "1d": 720}

SL_ATR_MULT = 1.5
# Minimal SL masofasi (ATR ko'paytmasi). Shovqin zonasidan tashqarida bo'lishi uchun
# (config.MIN_SL_ATR_MULT, standart 3.5). Backtest: --sweep ga qarang.
MIN_SL_ATR_MULT = 3.5
# TP lar Risk (SL masofasi) ning ko'paytmalari sifatida: 1.5R, 2.5R, 4R
TP_R_MULTIPLES: Tuple[float, float, float] = (1.5, 2.5, 4.0)


from services.ensemble import ensemble_service

def _levels(action: str, price: float, atr: float, smc: Dict[str, Any]) -> Dict[str, Any]:
    """SL (SMC zonalari va ATR asosida) va R-ko'paytmali TP larni hisoblaydi."""
    sign = 1 if action == "BUY" else -1
    sl_dist = atr * SL_ATR_MULT

    candidates = []
    if action == "BUY":
        candidates.extend(smc.get("recent_lows", []))
        ob = smc.get("nearest_bullish_ob")
        if ob: candidates.append(ob["bottom"])
        for fvg in smc.get("active_bullish_fvg", []):
            candidates.append(fvg["bottom"])
    else:
        candidates.extend(smc.get("recent_highs", []))
        ob = smc.get("nearest_bearish_ob")
        if ob: candidates.append(ob["top"])
        for fvg in smc.get("active_bearish_fvg", []):
            candidates.append(fvg["top"])

    # Saralash (narxga eng yaqindan uzoqqa)
    candidates = sorted(list(set(candidates)), key=lambda x: abs(price - x))

    for level in candidates:
        dist = (price - level) if action == "BUY" else (level - price)
        # 0.8*ATR dan 3.5*ATR gacha masofada bo'lgan birinchi SMC zonani tanlaymiz
        if 0.8 * atr <= dist <= 3.5 * atr:
            sl_dist = dist + 0.3 * atr  # Likvidlik (Stop hunt) dan himoya
            break

    # Shovqin zonasidan himoya: SL kamida MIN_SL_ATR_MULT * ATR masofada bo'lsin
    min_sl = atr * getattr(settings, "MIN_SL_ATR_MULT", MIN_SL_ATR_MULT)
    if sl_dist < min_sl:
        sl_dist = min_sl

    return {
        "stop_loss": round(price - sign * sl_dist, 2),
        "tps": [round(price + sign * sl_dist * r, 2) for r in TP_R_MULTIPLES],
    }


def in_session(now_utc: Optional[datetime] = None, start: Optional[int] = None, end: Optional[int] = None) -> bool:
    """London/Nyu-York seansi (config: SESSION_START_HOUR..SESSION_END_HOUR, UTC)."""
    h = (now_utc or datetime.now(timezone.utc)).hour
    start = settings.SESSION_START_HOUR if start is None else start
    end = settings.SESSION_END_HOUR if end is None else end
    if start <= end:
        return start <= h < end
    return h >= start or h < end  # tunni kesib o'tuvchi seans


def evaluate(
    tech: Dict[str, Any],
    smc: Dict[str, Any],
    htf_trend: Optional[str],
    news: Dict[str, Any],
    price: float,
    timeframe: str,
    balance: float = 500.0,
    risk_percent: float = 1.0,
    offset: float = 0.0,
) -> Dict[str, Any]:
    """
    Vaznli ensemble ovoziga asoslangan signal qarori (SMC 2.0, Trend 1.5, RSI 1.0).
    """
    decision = ensemble_service.get_decision(tech, smc, htf_trend, news)
    action = decision["action"]
    atr = max(tech["atr"], 1.0)

    sig: Dict[str, Any] = {
        "symbol": settings.DEFAULT_SYMBOL,
        "timeframe": timeframe,
        "htf_timeframe": HTF_MAP.get(timeframe),
        "htf_trend": htf_trend,
        "action": action,
        "strength": decision["strength"],
        "buy_votes": decision["buy_votes"],
        "sell_votes": decision["sell_votes"],
        "votes": decision["votes"],
        "current_price": round(price + offset, 2),
        "atr": round(atr, 2),
        "reasons": decision["reasons"],
        "news_safe": news["safe_to_trade"],
        "news_status": news["status_text"],
        "news_calendar_ok": news.get("calendar_ok", True),
        "offset": offset,
        "generated_at": datetime.now(ZoneInfo(settings.TIMEZONE)),
        "valid_minutes": VALID_MINUTES.get(timeframe, 30),
        "entry_price": None,
        "stop_loss": None,
        "tps": [],
        "risk": None,
    }

    if action in ("BUY", "SELL"):
        lv = _levels(action, price, atr, smc)
        entry = round(price + offset, 2)
        sl = round(lv["stop_loss"] + offset, 2)
        tps = [round(t + offset, 2) for t in lv["tps"]]
        sig.update({
            "entry_price": entry,
            "stop_loss": sl,
            "tps": tps,
            "risk": risk_service.calculate_lot_size(balance, risk_percent, entry, sl, *tps),
        })
    return sig


class SignalGeneratorService:
    def generate_signal(
        self,
        timeframe: str = "15m",
        balance: float = 500.0,
        risk_percent: float = 1.0,
        offset: float = 0.0,
    ) -> Dict[str, Any]:
        """Jonli ma'lumotlarni olib, to'liq tahlil asosida signal shakllantiradi."""
        df = market_service.get_candles(timeframe, 250)
        price = market_service.get_live_price()

        htf_trend = None
        htf_tf = HTF_MAP.get(timeframe)
        if htf_tf:
            try:
                htf_trend = technical_service.analyze(market_service.get_candles(htf_tf, 250))["trend"]
            except Exception as exc:  # yuqori TF bo'lmasa ham signal beramiz, lekin ballar kamayadi
                log.warning("Yuqori timeframe tahlili olinmadi: %s", exc)

        tech = technical_service.analyze(df)
        smc = smc_service.analyze(df)
        news = news_service.evaluate_trading_safety()
        sig = evaluate(tech, smc, htf_trend, news, price, timeframe, balance, risk_percent, offset)

        # Savdo seansi filtri: seansdan tashqarida signal BERILMAYDI.
        # (Backtest faqat shu seansda ishlaydi - jonli tizim ham aynan mos bo'lishi kerak.)
        if sig["action"] in ("BUY", "SELL") and not in_session():
            sig.update({
                "action": "WAIT",
                "strength": 0,
                "entry_price": None,
                "stop_loss": None,
                "tps": [],
                "risk": None,
                "session_closed": True,
                "reasons": [
                    "⏸ Savdo seansidan tashqari (faqat "
                    f"{settings.SESSION_START_HOUR:02d}:00-{settings.SESSION_END_HOUR:02d}:00 UTC). "
                    "Past likvidlik va keng spread sababli signal berilmadi."
                ] + list(sig["reasons"]),
            })
        return sig


signal_service = SignalGeneratorService()
