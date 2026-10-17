import logging
from typing import Dict, Any, List, Optional
import pandas as pd

from config import settings
from services.technical_analysis import technical_service
from services.smc_analysis import smc_service
from services.ensemble import ensemble_service
from services.signal_generator import _levels

log = logging.getLogger(__name__)


class BacktesterService:
    """
    XAUUSD strategiyasini (Ensemble ovozlar, SMC, Texnik tahlil, ATR SL/TP)
    tarixiy shamchalar bo'yicha sinovdan o'tkazuvchi (Backtest) tizim.

    Spread va savdo seansi `scripts/backtest.py` bilan mos modellashtiriladi,
    shuning uchun bu yerdagi natijalar konservativ va halol bo'ladi.
    """

    def run_backtest(
        self,
        df: pd.DataFrame,
        timeframe: str = "15m",
        warmup: int = 50,
        max_holding_bars: int = 48,  # M15 da 48 bar = 12 soat
        cooldown_bars: int = 4,      # Signal berilgach kamida 4 bar yangi signal ochilmaydi
        spread: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Berilgan DataFrame shamchalari bo'yicha ketma-ket simulyatsiya qiladi.

        - Spread: kirish narxi spread miqdorida yomonlashtiriladi (har bir bitim to'laydi).
        - Seans: faqat London/NY (config) oralig'ida signal ochiladi.
        """
        if len(df) < warmup + 10:
            return {"error": f"Shamchalar soni yetarli emas (kamida {warmup + 10} ta kerak)."}

        spread = settings.BACKTEST_SPREAD_USD if spread is None else spread
        session_start = settings.SESSION_START_HOUR
        session_end = settings.SESSION_END_HOUR

        trades: List[Dict[str, Any]] = []
        open_trade: Optional[Dict[str, Any]] = None
        last_signal_idx = -cooldown_bars

        news_dummy = {
            "safe_to_trade": True,
            "recommendation": "Backtest simulyatsiyasi",
            "status_text": "OK",
        }

        def pnl_r(trade: Dict[str, Any], exit_price: float, portion: float = 1.0) -> float:
            diff = (exit_price - trade["entry"]) if trade["action"] == "BUY" else (trade["entry"] - exit_price)
            return round(diff / trade["risk"] * portion, 2)

        # Simulyatsiya qadamma-qadam
        for i in range(warmup, len(df)):
            curr_row = df.iloc[i]
            curr_high = float(curr_row["high"])
            curr_low = float(curr_row["low"])
            curr_close = float(curr_row["close"])
            curr_time = curr_row.get("timestamp", str(i))

            # 1. Ochiq savdo holatini tekshirish
            if open_trade is not None:
                action = open_trade["action"]
                sl = open_trade["sl"]
                tp1 = open_trade["tp1"]
                tp2 = open_trade.get("tp2", tp1)
                state = open_trade.get("state", "OPEN")
                bars_held = i - open_trade["entry_idx"]

                closed = False
                result = None
                exit_price = curr_close

                if action == "BUY":
                    if state == "OPEN":
                        if curr_low <= sl:
                            result, exit_price, closed = "LOSS", sl, True
                        elif curr_high >= tp2:
                            result, exit_price, closed = "WIN (TP2)", tp2, True
                        elif curr_high >= tp1:
                            # TP1 urildi: yarmi yopiladi, qolgani uchun SL breakevenga suriladi
                            open_trade["state"] = "TP1_HIT"
                            open_trade["partial_r"] = pnl_r(open_trade, tp1, 0.5)
                            open_trade["sl"] = open_trade["entry"]
                            sl = open_trade["sl"]
                    elif state == "TP1_HIT":
                        if curr_low <= sl:
                            result, exit_price, closed = "WIN (BE)", sl, True
                        elif curr_high >= tp2:
                            result, exit_price, closed = "WIN (TP2)", tp2, True

                elif action == "SELL":
                    if state == "OPEN":
                        if curr_high >= sl:
                            result, exit_price, closed = "LOSS", sl, True
                        elif curr_low <= tp2:
                            result, exit_price, closed = "WIN (TP2)", tp2, True
                        elif curr_low <= tp1:
                            open_trade["state"] = "TP1_HIT"
                            open_trade["partial_r"] = pnl_r(open_trade, tp1, 0.5)
                            open_trade["sl"] = open_trade["entry"]
                            sl = open_trade["sl"]
                    elif state == "TP1_HIT":
                        if curr_high >= sl:
                            result, exit_price, closed = "WIN (BE)", sl, True
                        elif curr_low <= tp2:
                            result, exit_price, closed = "WIN (TP2)", tp2, True

                # Vaqt limiti (masalan 12 soat o'tganda)
                if not closed and bars_held >= max_holding_bars:
                    result, exit_price, closed = "EXPIRED", curr_close, True

                if closed:
                    if open_trade.get("state") == "TP1_HIT":
                        final_r = round(open_trade.get("partial_r", 0.0) + pnl_r(open_trade, exit_price, 0.5), 2)
                    else:
                        final_r = pnl_r(open_trade, exit_price)
                    open_trade.update({
                        "exit_idx": i,
                        "exit_time": curr_time,
                        "exit_price": exit_price,
                        "result": result,
                        "pnl_r": final_r,
                        "bars_held": bars_held,
                    })
                    trades.append(open_trade)
                    open_trade = None

            # 2. Agar savdo ochiq bo'lmasa, yangi signal izlash
            if open_trade is None and (i - last_signal_idx) >= cooldown_bars:
                hour = getattr(curr_time, "hour", None)
                if hour is None or (session_start <= hour < session_end):
                    slice_df = df.iloc[:i + 1]
                    try:
                        tech = technical_service.analyze(slice_df)
                        smc = smc_service.analyze(slice_df)
                        decision = ensemble_service.get_decision(
                            tech=tech,
                            smc=smc,
                            htf_trend=None,  # Backtestda ichki trend tahlili yetarli
                            news=news_dummy,
                        )
                        action = decision["action"]
                        if action in ("BUY", "SELL"):
                            atr = max(tech["atr"], 1.0)
                            lv = _levels(action, curr_close, atr, smc)
                            tps = lv.get("tps", [curr_close, curr_close])
                            # Spread kirish narxini yomonlashtiradi
                            entry = curr_close + spread if action == "BUY" else curr_close - spread
                            risk = abs(entry - lv["stop_loss"])
                            if risk > 0:
                                open_trade = {
                                    "id": len(trades) + 1,
                                    "entry_idx": i,
                                    "entry_time": curr_time,
                                    "action": action,
                                    "entry": entry,
                                    "risk": risk,
                                    "sl": lv["stop_loss"],
                                    "tp1": tps[0],
                                    "tp2": tps[1] if len(tps) > 1 else tps[0],
                                    "state": "OPEN",
                                    "strength": decision["strength"],
                                    "buy_votes": decision["buy_votes"],
                                    "sell_votes": decision["sell_votes"],
                                }
                                last_signal_idx = i
                    except Exception as e:
                        log.warning(f"Backtest bar {i} da tahlil xatosi: {e}")

        # Natijalarni hisoblash
        total_trades = len(trades)
        wins = sum(1 for t in trades if "WIN" in str(t.get("result", "")))
        losses = sum(1 for t in trades if t["result"] == "LOSS")
        expired = sum(1 for t in trades if t["result"] == "EXPIRED")

        decided_trades = wins + losses
        win_rate = (wins / decided_trades * 100) if decided_trades > 0 else 0.0

        total_r = sum(t["pnl_r"] for t in trades)
        gross_profit_r = sum(t["pnl_r"] for t in trades if t["pnl_r"] > 0)
        gross_loss_r = abs(sum(t["pnl_r"] for t in trades if t["pnl_r"] < 0))
        profit_factor = (gross_profit_r / gross_loss_r) if gross_loss_r > 0 else (99.0 if gross_profit_r > 0 else 0.0)

        # Drawdown hisoblash (R larda)
        cum_r = 0.0
        peak_r = 0.0
        max_dd_r = 0.0
        for t in trades:
            cum_r += t["pnl_r"]
            if cum_r > peak_r:
                peak_r = cum_r
            dd = peak_r - cum_r
            if dd > max_dd_r:
                max_dd_r = dd

        return {
            "total_bars": len(df),
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "expired": expired,
            "win_rate": round(win_rate, 1),
            "total_r": round(total_r, 2),
            "avg_r": round(total_r / total_trades, 2) if total_trades > 0 else 0.0,
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_r": round(max_dd_r, 2),
            "spread": spread,
            "trades": trades,
        }

    def format_backtest_report(self, res: Dict[str, Any], timeframe: str = "15m") -> str:
        if "error" in res:
            return f"❌ Backtest xatosi: {res['error']}"

        trades = res.get("trades", [])
        last_5_text = ""
        if trades:
            last_5 = trades[-5:]
            last_5_text = "\n\n<b>Oxirgi savdolar:</b>\n"
            for t in last_5:
                icon = "✅" if "WIN" in str(t['result']) else ("❌" if t['result'] == "LOSS" else "⚠️")
                last_5_text += f"{icon} #{t['id']} {t['action']} | {t['result']} | {t['pnl_r']:+0.1f}R\n"

        spread = res.get("spread", settings.BACKTEST_SPREAD_USD)
        return (
            f"🧪 <b>STRATEGIYA BACKTEST NATIJALARI ({timeframe.upper()})</b>\n\n"
            f"📊 Jami shamchalar: <b>{res['total_bars']}</b>\n"
            f"📌 Jami signallar: <b>{res['total_trades']}</b>\n"
            f"✅ G'alabalar (TP): <b>{res['wins']}</b>\n"
            f"❌ Zararlar (SL): <b>{res['losses']}</b>\n"
            f"⏳ Muddati o'tganlar: <b>{res['expired']}</b>\n"
            f"🎯 <b>Win Rate: {res['win_rate']}%</b>\n"
            f"💰 <b>Jami daromad: {res['total_r']:+.2f} R</b>\n"
            f"⚖️ Profit Factor: <b>{res['profit_factor']}</b>\n"
            f"📉 Max Drawdown: <b>-{res['max_drawdown_r']} R</b>\n"
            f"📈 O'rtacha bitta savdoga: <b>{res['avg_r']:+.2f} R</b>\n"
            f"💸 Spread: <b>{spread:.2f}$</b> | ⏸ Seans: London/NY (hisobga olingan)"
            f"{last_5_text}\n\n"
            "<i>Eslatma: bu tezkor tekshiruv - HTF (yuqori timeframe) filtri qo'llanilmagan va "
            "namuna kichik. To'liq 1 yillik test: <code>python scripts/backtest.py</code>.</i>"
        )


backtester_service = BacktesterService()
