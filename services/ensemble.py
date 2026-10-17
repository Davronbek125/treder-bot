from typing import Dict, Any, List, Optional

from config import settings

class EnsembleVotingService:
    def _evaluate_strategies(self, tech: Dict[str, Any], smc: Dict[str, Any]) -> List[Dict[str, Any]]:
        votes = []
        adx = tech.get("adx", 0)
        
        # BOZOR REJIMI (REGIME FILTER)
        # Agar ADX > 20 bo'lsa bozor trendda, ADX < 20 bo'lsa Ranging (yonlama, konsolidatsiya)
        is_trending_market = adx > 20
        
        # 1. SMC (Structure) - Eng ishonchli darajalar (Vazn: 2.0)
        if "BULLISH BOS" in smc["structure"] or smc["active_bullish_fvg"]:
            votes.append({"name": "SMC", "vote": 1, "weight": 2.0, "reason": "SMC o'sish tuzilmasi (BOS/FVG)"})
        elif "BEARISH BOS" in smc["structure"] or smc["active_bearish_fvg"]:
            votes.append({"name": "SMC", "vote": -1, "weight": 2.0, "reason": "SMC pasayish tuzilmasi (BOS/FVG)"})
        else:
            votes.append({"name": "SMC", "vote": 0, "weight": 2.0, "reason": "SMC setup yo'q"})

        # 2. Trend & Momentum (Supertrend) (Vazn: 1.5 agar trend bo'lsa, 0 agar ranging bo'lsa)
        st = tech.get("supertrend", 0)
        trend_weight = 1.5 if is_trending_market else 0.0 # Regime filter
        
        if st == 1 and is_trending_market:
            votes.append({"name": "Trend", "vote": 1, "weight": trend_weight, "reason": f"O'sish trendi (ADX={adx:.1f})"})
        elif st == -1 and is_trending_market:
            votes.append({"name": "Trend", "vote": -1, "weight": trend_weight, "reason": f"Pasayish trendi (ADX={adx:.1f})"})
        else:
            votes.append({"name": "Trend", "vote": 0, "weight": trend_weight, "reason": "Yonlama bozor (Ranging), Trend inobatga olinmadi"})

        # 3. Pullback & Mean-Reversion (RSI) - Vazn: 1.0
        rsi = tech.get("rsi", 50)
        
        if is_trending_market:
            # Trend bo'lsa - Pullback
            if 50 <= rsi <= 68:
                votes.append({"name": "RSI", "vote": 1, "weight": 1.0, "reason": f"RSI pullback o'sish ({rsi:.1f})"})
            elif 32 <= rsi <= 50:
                votes.append({"name": "RSI", "vote": -1, "weight": 1.0, "reason": f"RSI pullback pasayish ({rsi:.1f})"})
            else:
                votes.append({"name": "RSI", "vote": 0, "weight": 1.0, "reason": f"RSI chegarada ({rsi:.1f})"})
        else:
            # Yonlama bozor bo'lsa - Mean reversion (teskari harakat)
            if rsi < 45:
                votes.append({"name": "RSI", "vote": 1, "weight": 1.0, "reason": f"RSI arzon (oversold) - mean-reversion ({rsi:.1f})"})
            elif rsi > 55:
                votes.append({"name": "RSI", "vote": -1, "weight": 1.0, "reason": f"RSI qimmat (overbought) - mean-reversion ({rsi:.1f})"})
            else:
                votes.append({"name": "RSI", "vote": 0, "weight": 1.0, "reason": f"RSI o'rtada ({rsi:.1f})"})
                
        return votes

    def get_decision(self, tech: Dict[str, Any], smc: Dict[str, Any], htf_trend: Optional[str], news: Dict[str, Any]) -> Dict[str, Any]:
        votes = self._evaluate_strategies(tech, smc)
        
        # Vaznga asoslangan baholash
        buy_score = sum(v["weight"] for v in votes if v["vote"] == 1)
        sell_score = sum(v["weight"] for v in votes if v["vote"] == -1)
        # Maksimal ball doim 4.5 (SMC 2.0 + Trend 1.5 + RSI 1.0)
        max_possible_score = 4.5 
        
        buy_votes = sum(1 for v in votes if v["vote"] == 1) # Statistika uchun
        sell_votes = sum(1 for v in votes if v["vote"] == -1)
        
        action = "WAIT"
        reasons = []
        strength = 0
        buy_strength = int((buy_score / max_possible_score) * 100)
        sell_strength = int((sell_score / max_possible_score) * 100)
        
        # 0. Fundamental Filtr
        if not news["safe_to_trade"]:
            reasons.append(f"VETO: Fundamental xavf: {news['recommendation']}")
            return {"action": "WAIT", "buy_votes": buy_votes, "sell_votes": sell_votes, "reasons": reasons, "strength": 0, "votes": votes}
            
        # 1. EMA 200 qat'iy filtri (Trend yo'nalishi xavfsizligi)
        price = tech.get("current_price", 0)
        ema200 = tech.get("ema200", 0)
        is_uptrend = price > ema200 if ema200 else True
        is_downtrend = price < ema200 if ema200 else True
        
        # Minimal kelishuv config orqali boshqariladi (settings.MIN_CONFIDENCE_THRESHOLD, %).
        required_score = max_possible_score * (settings.MIN_CONFIDENCE_THRESHOLD / 100.0)
        # G'olib tomon raqibdan kamida shuncha ball (0-100) ko'p bo'lishi shart.
        margin_ok_buy = (buy_strength - sell_strength) >= settings.MIN_SIGNAL_MARGIN
        margin_ok_sell = (sell_strength - buy_strength) >= settings.MIN_SIGNAL_MARGIN
        
        if buy_score >= required_score and margin_ok_buy:
            if not is_uptrend:
                reasons.append(f"VETO: EMA200 ({ema200:.1f}) dan past, BUY taqiqlangan.")
            elif htf_trend and htf_trend.startswith("BEARISH"):
                reasons.append("VETO: Katta taymfreym (HTF) trendiga qarshi BUY bekor qilindi.")
            else:
                action = "BUY"
                reasons = [v["reason"] for v in votes if v["vote"] == 1]
                strength = buy_strength
                
        elif sell_score >= required_score and margin_ok_sell:
            if not is_downtrend:
                reasons.append(f"VETO: EMA200 ({ema200:.1f}) dan yuqori, SELL taqiqlangan.")
            elif htf_trend and htf_trend.startswith("BULLISH"):
                reasons.append("VETO: Katta taymfreym (HTF) trendiga qarshi SELL bekor qilindi.")
            else:
                action = "SELL"
                reasons = [v["reason"] for v in votes if v["vote"] == -1]
                strength = sell_strength
        else:
            reasons.append(
                f"Yetarli kelishuv yo'q. BUY Ball: {buy_score:.1f}, SELL Ball: {sell_score:.1f} "
                f"(Talab: {required_score:.1f}, Marja: {settings.MIN_SIGNAL_MARGIN})"
            )
            
        return {
            "action": action,
            "buy_votes": buy_votes,
            "sell_votes": sell_votes,
            "reasons": reasons[:5],
            "strength": strength,
            "votes": votes
        }

ensemble_service = EnsembleVotingService()
