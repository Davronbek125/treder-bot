"""
M1 skalping strategiyasi — qisqa muddatli, maksimal 5 daqiqa ushlanadigan tizim.

Mavjud M15/H1 tizimidan (signal_generator + ensemble) ALOHIDA ishlaydi:
- Kirish M1 shamchada (EMA pullback + momentum)
- Yuqori TF (M5) trend filtri
- SL/TP ATR asosida
- Savdo maksimal `max_bars` ta M1 shamcha (default 5 = 5 daqiqa) ushlanadi,
  so'ng bozor narxida yopiladi.

Indikatorlar vektorlashtirilgan (butun seriya bo'yicha bir marta hisoblanadi),
shuning uchun yuz minglab shamchani ham tez qayta ishlaydi va backtestda
har bir shamcha uchun qayta hisoblash shart bo'lmaydi.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from config import settings
from services.market_data import MarketDataError, fetch_history
from services.risk_calculator import risk_service
from services.technical_analysis import technical_service


@dataclass
class ScalpParams:
    """M1 skalping strategiyasi parametrlari."""

    # Trend (EMA) — M1
    ema_fast: int = 9
    ema_slow: int = 21
    ema_trend: int = 50

    # Indikatorlar
    rsi_period: int = 14
    atr_period: int = 14

    # SL/TP (ATR ko'paytmasi)
    sl_atr_mult: float = 1.0
    tp_atr_mult: float = 1.5

    # Maksimal ushlash (M1 shamchada). 5 = 5 daqiqa.
    max_bars: int = 5

    # RSI kirish oynasi (pullback)
    rsi_buy_low: float = 45.0
    rsi_buy_high: float = 68.0
    rsi_sell_low: float = 32.0
    rsi_sell_high: float = 55.0

    # Yuqori TF trend filtri (M5). None bo'lsa o'chiriladi.
    htf_rule: Optional[str] = "5min"
    htf_fast: int = 50
    htf_slow: int = 200

    # Sessiya filtri (UTC soat). None bo'lsa filtr yo'q.
    session_start: Optional[int] = None
    session_end: Optional[int] = None

    # Faqat ATR shu qiymatdan (USD) katta bo'lganda savdo qilamiz.
    # Spreadga nisbatan harakat katta bo'lishi uchun (M1 uchun muhim).
    min_atr: float = 0.0

    # Narx EMA_fast ga tegishi shartmi (pullback touch)
    pullback_touch: bool = True


class M1ScalperService:
    """M1 skalping signalini tayyorlaydi va tarixiy simulyatsiya qiladi."""

    # --- indikatorlar ---
    def _htf_trend_series(self, df: pd.DataFrame, params: ScalpParams) -> np.ndarray:
        """
        Yuqori TF (masalan M5) trendini M1 shamchalarga xavfsiz (look-ahead yo'q)
        tarzda joylashtiradi: M5 shamcha yopilgandan keyingina ma'lum bo'ladi.
        """
        rule = params.htf_rule
        if not rule:
            return np.array(["FLAT"] * len(df), dtype=object)

        htf = (
            df.set_index("timestamp")
            .resample(rule)
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna()
        )
        if htf.empty:
            return np.array(["FLAT"] * len(df), dtype=object)

        ema_f = htf["close"].ewm(span=params.htf_fast, adjust=False).mean()
        ema_s = htf["close"].ewm(span=params.htf_slow, adjust=False).mean()
        trend = pd.Series("FLAT", index=htf.index, dtype=object)
        trend[(htf["close"] > ema_f) & (ema_f > ema_s)] = "BULLISH"
        trend[(htf["close"] < ema_f) & (ema_f < ema_s)] = "BEARISH"

        right = pd.DataFrame(
            {"available_at": htf.index + pd.Timedelta(rule), "htf_trend": trend.to_numpy()}
        ).sort_values("available_at")
        left = df[["timestamp"]].sort_values("timestamp").copy()
        # merge_asof ikkala kalitning bir xil dtype bo'lishini talab qiladi
        left["timestamp"] = left["timestamp"].astype("datetime64[ns]")
        right["available_at"] = right["available_at"].astype("datetime64[ns]")
        merged = pd.merge_asof(left, right, left_on="timestamp", right_on="available_at", direction="backward")
        return merged["htf_trend"].fillna("FLAT").to_numpy()

    def prepare(self, df: pd.DataFrame, params: Optional[ScalpParams] = None) -> pd.DataFrame:
        """Indikatorlar va signal ustunlarini qo'shadi (vektorlashtirilgan)."""
        p = params or ScalpParams()
        out = df.copy()
        close = out["close"].astype(float)

        out["ema_fast"] = close.ewm(span=p.ema_fast, adjust=False).mean()
        out["ema_slow"] = close.ewm(span=p.ema_slow, adjust=False).mean()
        out["ema_trend"] = close.ewm(span=p.ema_trend, adjust=False).mean()
        out["rsi"] = technical_service.calculate_rsi(close, p.rsi_period)
        out["atr"] = technical_service.calculate_atr(out, p.atr_period)
        out["htf_trend"] = self._htf_trend_series(out, p)
        out["action"] = self._signals(out, p)
        return out

    def _signals(self, df: pd.DataFrame, p: ScalpParams) -> np.ndarray:
        close = df["close"]
        ema_f, ema_s, ema_t = df["ema_fast"], df["ema_slow"], df["ema_trend"]
        rsi = df["rsi"]

        trend_up = (ema_f > ema_s) & (ema_s > ema_t)
        trend_dn = (ema_f < ema_s) & (ema_s < ema_t)

        if p.pullback_touch:
            pull_up = (df["low"] <= ema_f) & (close >= ema_f)
            pull_dn = (df["high"] >= ema_f) & (close <= ema_f)
        else:
            pull_up = close < ema_f
            pull_dn = close > ema_f

        rsi_up = (rsi >= p.rsi_buy_low) & (rsi <= p.rsi_buy_high)
        rsi_dn = (rsi >= p.rsi_sell_low) & (rsi <= p.rsi_sell_high)

        if p.htf_rule:
            htf = df["htf_trend"]
            htf_up = (htf == "BULLISH").to_numpy()
            htf_dn = (htf == "BEARISH").to_numpy()
        else:
            htf_up = np.ones(len(df), dtype=bool)
            htf_dn = np.ones(len(df), dtype=bool)

        buy = (trend_up & pull_up & rsi_up).to_numpy() & htf_up
        sell = (trend_dn & pull_dn & rsi_dn).to_numpy() & htf_dn

        if p.min_atr > 0:
            vol_ok = (df["atr"] >= p.min_atr).to_numpy()
            buy &= vol_ok
            sell &= vol_ok

        if p.session_start is not None and p.session_end is not None:
            hours = df["timestamp"].dt.hour.to_numpy()
            sess = (hours >= p.session_start) & (hours <= p.session_end)
            buy &= sess
            sell &= sess

        return np.where(buy, "BUY", np.where(sell, "SELL", "WAIT"))

    # --- simulyatsiya ---
    def simulate(
        self,
        df: pd.DataFrame,
        params: Optional[ScalpParams] = None,
        spread: float = 0.0,
        start_index: int = 0,
    ) -> pd.DataFrame:
        """
        Tayyorlangan df (`prepare` dan keyin) ustida savdolarni simulyatsiya qiladi.
        Har bir bitim maksimal `max_bars` M1 shamcha ushlanadi; SL/TP tegsa oldinroq yopiladi.
        Spread kirish narxiga yomonlashtirib qo'shiladi. Ikki tomonga tegishda SL ustuvor.
        """
        p = params or ScalpParams()
        needed = {"action", "atr", "htf_trend", "rsi"}
        if not needed.issubset(df.columns):
            raise ValueError("simulate() dan oldin prepare() chaqirilishi kerak")

        n = len(df)
        close = df["close"].to_numpy(dtype=float)
        high = df["high"].to_numpy(dtype=float)
        low = df["low"].to_numpy(dtype=float)
        atr = df["atr"].to_numpy(dtype=float)
        action = df["action"].to_numpy()
        ts = df["timestamp"].to_numpy()

        trades: list[Dict[str, Any]] = []
        i = start_index
        while i < n - 1:
            act = action[i]
            if act == "WAIT":
                i += 1
                continue

            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                i += 1
                continue

            # SL/TP darajalari BOZOR narxidan hisoblanadi (spreaddan oldin),
            # kirish narxi esa spread bilan yomonlashtiriladi. Shuning uchun spread
            # real savdodagidek foydani kamaytiradi.
            if act == "BUY":
                sl = close[i] - p.sl_atr_mult * a
                tp = close[i] + p.tp_atr_mult * a
                entry = close[i] + spread
            else:
                sl = close[i] + p.sl_atr_mult * a
                tp = close[i] - p.tp_atr_mult * a
                entry = close[i] - spread

            risk = abs(entry - sl)
            if risk <= 0:
                i += 1
                continue

            last = min(i + p.max_bars, n - 1)
            outcome: Optional[float] = None
            exit_idx = last
            reason = "TIME"

            for j in range(i + 1, last + 1):
                if act == "BUY":
                    if low[j] <= sl:
                        outcome, exit_idx, reason = -1.0, j, "SL"
                        break
                    if high[j] >= tp:
                        outcome, exit_idx, reason = (tp - entry) / risk, j, "TP"
                        break
                else:
                    if high[j] >= sl:
                        outcome, exit_idx, reason = -1.0, j, "SL"
                        break
                    if low[j] <= tp:
                        outcome, exit_idx, reason = (entry - tp) / risk, j, "TP"
                        break

            if outcome is None:
                px = close[last]
                outcome = ((px - entry) if act == "BUY" else (entry - px)) / risk

            trades.append({
                "time": ts[i],
                "action": act,
                "entry": entry,
                "sl": round(sl, 2),
                "tp": round(tp, 2),
                "r": outcome,
                "reason": reason,
                "bars": int(exit_idx - i),
            })
            i = exit_idx + 1

        return pd.DataFrame(trades)

    # --- jonli signal ---
    def generate_signal(
        self,
        balance: float = 500.0,
        risk_percent: float = 1.0,
        offset: float = 0.0,
        params: Optional[ScalpParams] = None,
    ) -> Dict[str, Any]:
        """
        Jonli M1 skalping signalini shakllantiradi (oxirgi yopilgan M1 shamcha bo'yicha).

        DIQQAT: eksperimental. Backtest shuni ko'rsatadiki foyda faqat juda tor
        spread'da (<=0.20$) bo'ladi. Real pulda xavfli.
        """
        p = params or LIVE_PARAMS
        try:
            # cache=False: jonli signal har doim ENG YANGI ma'lumotni olishi shart.
            df = fetch_history("1m", LIVE_HISTORY_BARS, cache=False)
        except Exception as exc:  # tarmoq / Binance xatosi
            raise MarketDataError(f"M1 ma'lumot olinmadi: {exc}") from exc
        if df is None or len(df) < 250:
            raise MarketDataError("M1 ma'lumot yetarli emas")

        prepared = self.prepare(df, p)
        last = prepared.iloc[-1]
        action = str(last["action"])
        atr = float(last["atr"]) if pd.notna(last["atr"]) else 0.0
        raw_price = float(last["close"])
        price = round(raw_price + offset, 2)

        reasons = [
            f"EMA{p.ema_fast}/EMA{p.ema_slow}/EMA{p.ema_trend}: "
            f"{last['ema_fast']:.2f} / {last['ema_slow']:.2f} / {last['ema_trend']:.2f}",
            f"Yuqori TF ({p.htf_rule}) trend: {last['htf_trend']}",
            f"RSI({p.rsi_period}): {float(last['rsi']):.1f}",
            f"ATR({p.atr_period}): {atr:.2f}$ (min filtr: {p.min_atr}$)",
        ]

        sig: Dict[str, Any] = {
            "symbol": settings.DEFAULT_SYMBOL,
            "timeframe": "1m",
            "action": action,
            "current_price": price,
            "atr": round(atr, 2),
            "htf_trend": str(last["htf_trend"]),
            "rsi": round(float(last["rsi"]), 1),
            "offset": offset,
            "generated_at": datetime.now(ZoneInfo(settings.TIMEZONE)),
            "valid_minutes": p.max_bars,
            "reasons": reasons,
            "params": p,
            "entry_price": None,
            "stop_loss": None,
            "tp": None,
            "risk": None,
        }

        if action in ("BUY", "SELL") and atr > 0:
            sign = 1 if action == "BUY" else -1
            entry = round(raw_price + offset, 2)
            sl = round(raw_price - sign * p.sl_atr_mult * atr + offset, 2)
            tp = round(raw_price + sign * p.tp_atr_mult * atr + offset, 2)
            sig.update({
                "entry_price": entry,
                "stop_loss": sl,
                "tp": tp,
                "risk": risk_service.calculate_lot_size(balance, risk_percent, entry, sl, tp, tp, tp),
            })
            sig["reasons"].append(
                f"Kirish: M1 pullback + momentum ({p.sl_atr_mult}ATR SL / {p.tp_atr_mult}ATR TP, "
                f"maks {p.max_bars} daqiqa)"
            )
        return sig


# Jonli /scalp uchun standart sozlamalar (1 yillik backtest: eng chidamlisi)
LIVE_HISTORY_BARS = 3000
LIVE_PARAMS = ScalpParams(tp_atr_mult=2.5, min_atr=1.2, max_bars=5, htf_rule="5min")

m1_scalper_service = M1ScalperService()
