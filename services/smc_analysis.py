import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional

class SMCAnalysisService:
    @staticmethod
    def find_swing_points(df: pd.DataFrame, window: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """
        Swing High va Swing Low (lokal ekstremumlar) nuqtalarini topadi.
        """
        highs = df["high"].values
        lows = df["low"].values
        timestamps = df["timestamp"].values

        swing_highs = []
        swing_lows = []

        for i in range(window, len(df) - window):
            current_high = highs[i]
            current_low = lows[i]

            # Swing High tekshiruvi (atrofidagi window ta shamchadan baland)
            if all(current_high > highs[i - j] for j in range(1, window + 1)) and \
               all(current_high >= highs[i + j] for j in range(1, window + 1)):
                swing_highs.append({
                    "index": i,
                    "price": round(float(current_high), 2),
                    "timestamp": timestamps[i]
                })

            # Swing Low tekshiruvi (atrofidagi window ta shamchadan past)
            if all(current_low < lows[i - j] for j in range(1, window + 1)) and \
               all(current_low <= lows[i + j] for j in range(1, window + 1)):
                swing_lows.append({
                    "index": i,
                    "price": round(float(current_low), 2),
                    "timestamp": timestamps[i]
                })

        return {
            "swing_highs": swing_highs,
            "swing_lows": swing_lows
        }

    @staticmethod
    def detect_fvg(df: pd.DataFrame, min_gap_dollars: float = 1.0) -> List[Dict[str, Any]]:
        """
        Fair Value Gap (FVG / Imbalance - Bozor nomutanosibligi) ni aniqlaydi.
        3 ta shamcha orasidagi bo'shliq:
        - Bullish FVG: 1-shamcha Yuqorisi < 3-shamcha Pasti
        - Bearish FVG: 1-shamcha Pasti > 3-shamcha Yuqorisi
        """
        fvgs = []
        highs = df["high"].values
        lows = df["low"].values
        timestamps = df["timestamp"].values
        current_price = float(df["close"].iloc[-1])

        # Oxirgi 30 ta shamchani tekshirish
        start_idx = max(2, len(df) - 30)
        for i in range(start_idx, len(df)):
            c1_high = highs[i - 2]
            c1_low = lows[i - 2]
            c3_high = highs[i]
            c3_low = lows[i]

            # Bullish FVG
            if c3_low > c1_high:
                gap = c3_low - c1_high
                if gap >= min_gap_dollars:
                    is_filled = current_price < c1_high
                    fvgs.append({
                        "type": "BULLISH_FVG",
                        "top": round(float(c3_low), 2),
                        "bottom": round(float(c1_high), 2),
                        "gap": round(float(gap), 2),
                        "is_active": not is_filled,
                        "timestamp": timestamps[i]
                    })

            # Bearish FVG
            elif c1_low > c3_high:
                gap = c1_low - c3_high
                if gap >= min_gap_dollars:
                    is_filled = current_price > c1_low
                    fvgs.append({
                        "type": "BEARISH_FVG",
                        "top": round(float(c1_low), 2),
                        "bottom": round(float(c3_high), 2),
                        "gap": round(float(gap), 2),
                        "is_active": not is_filled,
                        "timestamp": timestamps[i]
                    })

        return fvgs

    @staticmethod
    def detect_order_blocks(df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Order Block (OB) zonalarini aniqlaydi:
        - Bullish OB: Kuchli impulsdan oldingi oxirgi qizil (bearish) shamcha
        - Bearish OB: Kuchli impulsdan oldingi oxirgi yashil (bullish) shamcha
        """
        obs = []
        opens = df["open"].values
        closes = df["close"].values
        highs = df["high"].values
        lows = df["low"].values
        timestamps = df["timestamp"].values

        # Oxirgi 25 ta shamchani tekshiramiz
        start_idx = max(3, len(df) - 25)
        for i in range(start_idx, len(df) - 1):
            body_size = abs(closes[i] - opens[i])
            next_body = abs(closes[i + 1] - opens[i + 1])

            # Kuchli o'sish impulsi (Bullish OB qidirish)
            if closes[i] < opens[i] and closes[i + 1] > opens[i + 1] and next_body > body_size * 2.0:
                obs.append({
                    "type": "BULLISH_OB",
                    "top": round(float(highs[i]), 2),
                    "bottom": round(float(lows[i]), 2),
                    "timestamp": timestamps[i],
                    "strength": "STRONG" if next_body > body_size * 3.0 else "MODERATE"
                })

            # Kuchli pasayish impulsi (Bearish OB qidirish)
            elif closes[i] > opens[i] and closes[i + 1] < opens[i + 1] and next_body > body_size * 2.0:
                obs.append({
                    "type": "BEARISH_OB",
                    "top": round(float(highs[i]), 2),
                    "bottom": round(float(lows[i]), 2),
                    "timestamp": timestamps[i],
                    "strength": "STRONG" if next_body > body_size * 3.0 else "MODERATE"
                })

        return obs

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        SMC (Smart Money Concepts) tahlil yakuniy hisoboti.
        """
        current_price = float(df["close"].iloc[-1])
        swings = self.find_swing_points(df)
        fvgs = self.detect_fvg(df)
        obs = self.detect_order_blocks(df)

        recent_highs = swings["swing_highs"][-3:] if swings["swing_highs"] else []
        recent_lows = swings["swing_lows"][-3:] if swings["swing_lows"] else []

        # Eng yaqin faol FVGlar
        active_bullish_fvg = [f for f in fvgs if f["type"] == "BULLISH_FVG" and f["is_active"]]
        active_bearish_fvg = [f for f in fvgs if f["type"] == "BEARISH_FVG" and f["is_active"]]

        nearest_bullish_ob = [o for o in obs if o["type"] == "BULLISH_OB" and o["top"] <= current_price]
        nearest_bearish_ob = [o for o in obs if o["type"] == "BEARISH_OB" and o["bottom"] >= current_price]

        # Bozor strukturasi (BOS)
        structure = "RANGE / CONSOLIDATION"
        if recent_highs and recent_lows:
            last_high = recent_highs[-1]["price"]
            last_low = recent_lows[-1]["price"]

            if current_price > last_high:
                structure = "BULLISH BOS (Break of Structure yuqoriga sindirildi)"
            elif current_price < last_low:
                structure = "BEARISH BOS (Break of Structure pastga sindirildi)"

        return {
            "structure": structure,
            "recent_highs": [h["price"] for h in recent_highs],
            "recent_lows": [l["price"] for l in recent_lows],
            "active_bullish_fvg": active_bullish_fvg[-2:] if active_bullish_fvg else [],
            "active_bearish_fvg": active_bearish_fvg[-2:] if active_bearish_fvg else [],
            "nearest_bullish_ob": nearest_bullish_ob[-1] if nearest_bullish_ob else None,
            "nearest_bearish_ob": nearest_bearish_ob[-1] if nearest_bearish_ob else None,
        }

smc_service = SMCAnalysisService()
