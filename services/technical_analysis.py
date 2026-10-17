import pandas as pd
import numpy as np
from typing import Dict, Any

class TechnicalAnalysisService:
    @staticmethod
    def calculate_ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        return {"macd": macd_line, "signal": signal_line, "hist": macd_line - signal_line}

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high, low, close_prev = df["high"], df["low"], df["close"].shift(1)
        tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    @staticmethod
    def calculate_bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0) -> Dict[str, pd.Series]:
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        return {"upper": sma + (std * num_std), "middle": sma, "lower": sma - (std * num_std)}

    @staticmethod
    def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Dict[str, pd.Series]:
        lowest_low = df["low"].rolling(window=k_period).min()
        highest_high = df["high"].rolling(window=k_period).max()
        k = 100 * (df["close"] - lowest_low) / (highest_high - lowest_low + 1e-10)
        d = k.rolling(window=d_period).mean()
        return {"k": k, "d": d}

    @staticmethod
    def calculate_cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
        tp = (df["high"] + df["low"] + df["close"]) / 3
        sma_tp = tp.rolling(window=period).mean()
        # Mad function definition to work around pandas Series limitations
        def mad(x):
            return np.abs(x - np.mean(x)).mean()
        mean_dev = tp.rolling(window=period).apply(mad, raw=True)
        return (tp - sma_tp) / (0.015 * mean_dev + 1e-10)

    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> Dict[str, pd.Series]:
        up_move = df["high"] - df["high"].shift(1)
        down_move = df["low"].shift(1) - df["low"]
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        
        atr = TechnicalAnalysisService.calculate_atr(df, period)
        
        plus_di = 100 * (pd.Series(plus_dm).ewm(alpha=1.0/period, adjust=False).mean() / (atr + 1e-10))
        minus_di = 100 * (pd.Series(minus_dm).ewm(alpha=1.0/period, adjust=False).mean() / (atr + 1e-10))
        
        dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10))
        adx = dx.ewm(alpha=1.0/period, adjust=False).mean()
        return {"adx": adx, "plus_di": plus_di, "minus_di": minus_di}

    @staticmethod
    def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> Dict[str, pd.Series]:
        atr = TechnicalAnalysisService.calculate_atr(df, period)
        hl2 = (df["high"] + df["low"]) / 2

        # numpy massivlarda hisoblaymiz: pandas .iloc[] har bir qadamda juda sekin.
        # Natija eski implementatsiya bilan aynan bir xil (bir xil taqqoslashlar).
        n = len(df)
        close = df["close"].to_numpy(dtype=float)
        basic_ub = (hl2 + (multiplier * atr)).to_numpy(dtype=float)
        basic_lb = (hl2 - (multiplier * atr)).to_numpy(dtype=float)

        final_ub = np.zeros(n, dtype=float)
        final_lb = np.zeros(n, dtype=float)
        trend = np.ones(n, dtype=int)  # 1: uptrend, -1: downtrend

        for i in range(1, n):
            if basic_ub[i] < final_ub[i - 1] or close[i - 1] > final_ub[i - 1]:
                final_ub[i] = basic_ub[i]
            else:
                final_ub[i] = final_ub[i - 1]

            if basic_lb[i] > final_lb[i - 1] or close[i - 1] < final_lb[i - 1]:
                final_lb[i] = basic_lb[i]
            else:
                final_lb[i] = final_lb[i - 1]

            if trend[i - 1] == 1 and close[i] <= final_lb[i]:
                trend[i] = -1
            elif trend[i - 1] == -1 and close[i] >= final_ub[i]:
                trend[i] = 1
            else:
                trend[i] = trend[i - 1]

        return {
            "trend": pd.Series(trend, index=df.index),
            "lower": pd.Series(final_lb, index=df.index),
            "upper": pd.Series(final_ub, index=df.index),
        }

    @staticmethod
    def calculate_vwap(df: pd.DataFrame) -> pd.Series:
        # Hozircha oddiy cumulative VWAP
        if "volume" not in df:
            return pd.Series(0.0, index=df.index)
        tp = (df["high"] + df["low"] + df["close"]) / 3
        return (tp * df["volume"]).cumsum() / (df["volume"].cumsum() + 1e-10)

    @staticmethod
    def calculate_pivot_points(df: pd.DataFrame) -> Dict[str, float]:
        high = float(df["high"].iloc[-2]) if len(df) > 1 else float(df["high"].iloc[-1])
        low = float(df["low"].iloc[-2]) if len(df) > 1 else float(df["low"].iloc[-1])
        close = float(df["close"].iloc[-2]) if len(df) > 1 else float(df["close"].iloc[-1])

        pivot = (high + low + close) / 3.0
        r1, s1 = 2 * pivot - low, 2 * pivot - high
        r2, s2 = pivot + (high - low), pivot - (high - low)
        r3, s3 = high + 2 * (pivot - low), low - 2 * (high - pivot)

        return {"pivot": round(pivot, 2), "r1": round(r1, 2), "s1": round(s1, 2), "r2": round(r2, 2), "s2": round(s2, 2), "r3": round(r3, 2), "s3": round(s3, 2)}

    def analyze(self, df: pd.DataFrame, pivot_df: pd.DataFrame | None = None) -> Dict[str, Any]:
        if len(df) < 30:
            raise ValueError("Tahlil uchun kamida 30 ta shamcha kerak")

        close = df["close"]
        current_price = float(close.iloc[-1])

        ema20 = float(self.calculate_ema(close, 20).iloc[-1])
        ema50 = float(self.calculate_ema(close, 50).iloc[-1])
        ema200 = float(self.calculate_ema(close, min(200, len(df))).iloc[-1])

        rsi = float(self.calculate_rsi(close).iloc[-1])
        macd_data = self.calculate_macd(close)
        
        atr = float(self.calculate_atr(df).iloc[-1])
        bb = self.calculate_bollinger_bands(close)
        
        stoch = self.calculate_stochastic(df)
        cci = float(self.calculate_cci(df).iloc[-1])
        adx_data = self.calculate_adx(df)
        st = self.calculate_supertrend(df)
        vwap = float(self.calculate_vwap(df).iloc[-1])
        
        pivots = self.calculate_pivot_points(pivot_df if pivot_df is not None and len(pivot_df) > 1 else df)

        trend = "BULLISH" if current_price > ema20 > ema50 else "BEARISH" if current_price < ema20 < ema50 else "FLAT"
        
        return {
            "current_price": current_price,
            "trend": trend,
            "ema20": ema20, "ema50": ema50, "ema200": ema200, "ema200_reliable": len(df) >= 200,
            "above_ema200": current_price > ema200,
            "rsi": rsi,
            "macd": float(macd_data["macd"].iloc[-1]), "macd_signal": float(macd_data["signal"].iloc[-1]), "macd_hist": float(macd_data["hist"].iloc[-1]),
            "atr": atr,
            "bb_upper": float(bb["upper"].iloc[-1]), "bb_lower": float(bb["lower"].iloc[-1]), "bb_mid": float(bb["middle"].iloc[-1]),
            "stoch_k": float(stoch["k"].iloc[-1]), "stoch_d": float(stoch["d"].iloc[-1]),
            "cci": cci,
            "adx": float(adx_data["adx"].iloc[-1]), "adx_plus": float(adx_data["plus_di"].iloc[-1]), "adx_minus": float(adx_data["minus_di"].iloc[-1]),
            "supertrend": int(st["trend"].iloc[-1]), # 1 or -1
            "vwap": vwap,
            "pivots": pivots
        }

technical_service = TechnicalAnalysisService()
