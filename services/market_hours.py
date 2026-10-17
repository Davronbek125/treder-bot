from datetime import datetime, timezone
from typing import Optional, Dict, Any

def is_market_open(dt: Optional[datetime] = None) -> bool:
    """
    XAUUSD (Xalqaro oltin bozori - Forex/MT5) ish vaqtini tekshiradi.
    Bozor Juma 22:00 UTC da yopiladi va Yakshanba 22:00 UTC da ochiladi.
    Hafta kunlari:
      0 = Dushanba, 1 = Seshanba, 2 = Chorshanba, 3 = Payshanba,
      4 = Juma, 5 = Shanba, 6 = Yakshanba.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    weekday = dt.weekday()
    hour = dt.hour
    minute = dt.minute

    # Shanba: to'liq yopiq
    if weekday == 5:
        return False

    # Yakshanba: 22:00 UTC gacha yopiq, 22:00 dan keyin ochiq
    if weekday == 6:
        return hour >= 22

    # Juma: 22:00 UTC dan keyin yopiladi
    if weekday == 4:
        return hour < 22

    # Dushanba, Seshanba, Chorshanba, Payshanba: ochiq
    return True

def get_market_status(dt: Optional[datetime] = None) -> Dict[str, Any]:
    """Bozor holati haqida batafsil ma'lumot qaytaradi."""
    open_now = is_market_open(dt)
    if open_now:
        return {
            "is_open": True,
            "status_text": "🟢 Oltin bozori (XAUUSD) ochiq",
            "message": "Bozor faol, savdo qilish mumkin."
        }
    return {
        "is_open": False,
        "status_text": "🔴 Oltin bozori (XAUUSD) yopiq (dam olish kuni)",
        "message": "Hozir xalqaro oltin bozori yopiq. Bozor Dushanba kuni 03:00 (Toshkent vaqti) da ochiladi."
    }
