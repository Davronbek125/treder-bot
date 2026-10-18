from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Telegram Bot Token (@BotFather orqali olinadi)
    BOT_TOKEN: str = ""

    # Faqat shu Telegram ID lardagi foydalanuvchilar botdan foydalana oladi
    # (vergul bilan ajrating, masalan: 123456789,987654321). Bo'sh bo'lsa - hamma.
    ALLOWED_USER_IDS: str = ""

    # Asosiy savdo aktivi
    DEFAULT_SYMBOL: str = "XAUUSD"

    # Tahlil vaqt intervallari (Timeframes)
    TIMEFRAMES: list[str] = ["5m", "15m", "1h", "4h", "1d"]
    DEFAULT_TIMEFRAME: str = "1h"  # 1h eng barqaror (15m: PF 1.24 lekin 1 bo'lak zararli; scripts/backtest.py)

    # Signal kuchi chegarasi (0-100, indikatorlar mosligi balli).
    # DIQQAT: bu qiymat endi haqiqatda ishlaydi (services/ensemble.py).
    # 60% - backtest bilan sozlangan qiymat (2.7 / 4.5 ball). Oshirsangiz signal kamayadi.
    MIN_CONFIDENCE_THRESHOLD: int = 60
    # G'olib tomon raqibdan kamida shuncha ball (0-100) ko'p bo'lishi shart
    MIN_SIGNAL_MARGIN: int = 20

    # Savdo seansi (UTC soat). [start, end) oralig'ida signal beriladi.
    # 08:00-22:00 UTC = London + Nyu-York: eng likvid va eng tor spread davri.
    # Bu filtrlash backtestda ham qo'llaniladi (scripts/backtest.py).
    # Kechasi (Osiyo sessiyasi) likvidlik past, spread keng - signal sifati past.
    SESSION_START_HOUR: int = 8
    SESSION_END_HOUR: int = 22

    # SL (Stop Loss) masofasi uchun MINIMAL ATR ko'paytmasi.
    # None -> TAYMFREYM/GORIZONTGA QARAB AVTOMATIK (services.signal_generator.sl_floor_atr).
    # Son berilsa -> qat'iy qiymat (scripts/backtest.py shundan foydalanadi).
    #
    # NEGA AVTOMATIK? Ushlash gorizontidagi tabiiy "shovqin zonasi" ~ K*ATR*sqrt(N),
    # bu yerda N = ushlash shamchalari soni. Shu formula turli taymfreymlarda
    # BIR XIL dollar SL beradi: 15m (96 sham) ~ 8 ATR, 1h (24) ~ 4 ATR, 4h (6) ~ 2 ATR.
    MIN_SL_ATR_MULT: Optional[float] = None

    # Shovqin zonasi koeffitsienti: K ~ sqrt(2/pi) ~ 0.8.
    # 1h/24h -> 4.0 ATR, 15m/24h -> 8.0 ATR (backtest bo'yicha ikkalasi ham tasdiqlangan).
    SL_FLOOR_K: float = 0.82
    # Eng katta ruxsat etilgan floor (validatsiya qilingan eng keng qiymat).
    # 5m kabi juda kichik TF larda formulani cheksiz cho'zmaslik uchun.
    SL_FLOOR_MAX_ATR: float = 8.0

    # Ochiq bitim necha soatdan keyin eskigan (yopilmagan) hisoblanadi.
    # DIQQAT: backtestdagi MAX_HOLD_HOURS bilan bir xil bo'lishi kerak (scripts/backtest.py).
    MAX_TRADE_HOURS: float = 24.0

    # Backtest natijalari qaysi spread bilan hisoblangan (hujjat/halollik uchun).
    # Broker spreadi boshqacha bo'lsa: python scripts/backtest.py --spreads ...
    BACKTEST_SPREAD_USD: float = 0.50

    # Standart risk foizi
    DEFAULT_RISK_PERCENT: float = 1.0  # Har bir bitimda depozitning 1%

    # Kesh muddati (sekundda) - bozor ma'lumotlarini haddan tashqari tez-tez so'ramaslik uchun
    CACHE_EXPIRY_SECONDS: int = 30

    # Yangiliklar filtri
    NEWS_LOOKAHEAD_MINUTES: int = 60  # Keyingi 60 daqiqadagi yangiliklarni ogohlantirish
    NEWS_COOLDOWN_MINUTES: int = 30   # Yangilik chiqqandan keyingi 30 daqiqa

    # Xabarlarda ko'rsatiladigan vaqt zonasi
    TIMEZONE: str = "Asia/Tashkent"

    @property
    def allowed_user_ids(self) -> set[int]:
        ids: set[int] = set()
        for part in self.ALLOWED_USER_IDS.split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
        return ids

settings = Settings()
