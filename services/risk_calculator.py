from typing import Dict, Any

class RiskCalculatorService:
    @staticmethod
    def calculate_lot_size(
        balance: float,
        risk_percent: float,
        entry_price: float,
        stop_loss: float,
        tp1: float,
        tp2: float,
        tp3: float
    ) -> Dict[str, Any]:
        """
        Oltin (XAUUSD) uchun to'g'ri Lot hajmi va risk kalkulyatsiyasi.
        Formula:
        XAUUSD da 1.00 Lot = 100 unsiya oltin.
        Narx 1$ yursa, 1 lotda foyda/zarar = 100$.
        0.01 lotda 1$ yurish = 1$ foyda/zarar.
        """
        if balance <= 0:
            balance = 100.0
        if risk_percent <= 0:
            risk_percent = 1.0

        sl_distance = abs(entry_price - stop_loss)
        if sl_distance <= 0.01:
            sl_distance = 1.0  # Minimal xavfsiz masofa

        # Depozitdan ruxsat etilgan maksimal yo'qotish (USD)
        risk_amount_usd = balance * (risk_percent / 100.0)

        # Kerakli Lot hajmi:
        # risk_amount = lot * (sl_distance * 100)
        raw_lot = risk_amount_usd / (sl_distance * 100.0)

        # Broker cheklovlari: min 0.01, max 10.0, 2 xona aniqlik
        lot_size = min(10.0, max(0.01, round(raw_lot, 2)))

        # Haqiqiy Stop Loss yo'qotilishi (lot yaxlitlangani hisobiga)
        actual_sl_loss = round(lot_size * sl_distance * 100.0, 2)

        # TP darajalaridagi kutilayotgan sof foyda (USD)
        tp1_distance = abs(tp1 - entry_price)
        tp2_distance = abs(tp2 - entry_price)
        tp3_distance = abs(tp3 - entry_price)

        tp1_profit = round(lot_size * tp1_distance * 100.0, 2)
        tp2_profit = round(lot_size * tp2_distance * 100.0, 2)
        tp3_profit = round(lot_size * tp3_distance * 100.0, 2)

        # Risk / Reward nisbati
        rr_tp1 = round(tp1_distance / sl_distance, 2)
        rr_tp2 = round(tp2_distance / sl_distance, 2)
        rr_tp3 = round(tp3_distance / sl_distance, 2)

        return {
            "balance": balance,
            "risk_percent": risk_percent,
            "risk_amount_usd": round(risk_amount_usd, 2),
            "lot_size": lot_size,
            "sl_distance": round(sl_distance, 2),
            "actual_sl_loss": actual_sl_loss,
            "min_lot_exceeds_risk": actual_sl_loss > risk_amount_usd * 1.05,
            "tp1_profit": tp1_profit,
            "tp2_profit": tp2_profit,
            "tp3_profit": tp3_profit,
            "rr_tp1": f"1:{rr_tp1}",
            "rr_tp2": f"1:{rr_tp2}",
            "rr_tp3": f"1:{rr_tp3}"
        }

risk_service = RiskCalculatorService()
