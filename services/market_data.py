import logging
import threading
import time
from typing import Any, Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import settings

log = logging.getLogger(__name__)

BINANCE_URL = "https://api.binance.com/api/v3"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
# Yangi ma'lumot olinmasa, eskirgan keshdan shuncha soniyagacha foydalanish mumkin
STALE_MAX_SECONDS = 900

_YAHOO_TF = {
    "5m": ("5m", "5d"),
    "15m": ("15m", "5d"),
    "1h": ("60m", "1mo"),
    "4h": ("60m", "3mo"),
    "1d": ("1d", "1y"),
}


class MarketDataError(RuntimeError):
    """Bozor ma'lumotlarini hech bir manbadan olib bo'lmaganda ko'tariladi."""


class MarketDataService:
    """
    Oltin narxi va shamchalari. Asosiy manba: Binance PAXGUSDT (oltin bilan 1:1 ta'minlangan),
    zaxira: Yahoo Finance GC=F. Hech qachon soxta/sintetik ma'lumot qaytarmaydi.
    """

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._local = threading.local()
        self.active_source: str = "binance"

    def _get_session(self) -> requests.Session:
        """Thread-safe: har bir ishchi oqimga o'z Session obyekti beriladi."""
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            retry_strategy = Retry(
                total=1,
                backoff_factor=0.2,
                status_forcelist=[500, 502, 503, 504],
                respect_retry_after_header=False,
                allowed_methods=frozenset(["GET"]),
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            self._local.session = session
        return session

    # --- kesh ---
    def _get_cache(self, key: str, max_age: float) -> Optional[Any]:
        with self._lock:
            entry = self._cache.get(key)
        if entry and time.time() - entry["ts"] < max_age:
            return entry["data"]
        return None

    def _set_cache(self, key: str, data: Any) -> None:
        with self._lock:
            self._cache[key] = {"ts": time.time(), "data": data}

    # --- narx ---
    def get_live_price(self) -> float:
        key = "live_price"
        cached = self._get_cache(key, settings.CACHE_EXPIRY_SECONDS)
        if cached is not None:
            return cached

        price = self._price_binance()
        if price is not None:
            self.active_source = "binance"
        else:
            price = self._price_yahoo()
            if price is not None:
                if self.active_source != "yahoo":
                    log.warning("Binance PAXG narxi olinmadi! Zaxira Yahoo Finance (GC=F Futures) ga o'tildi. Spot va Futures o'rtasida spred farqi bo'lishi mumkin.")
                self.active_source = "yahoo"

        if price is None:
            stale = self._get_cache(key, STALE_MAX_SECONDS)
            if stale is not None:
                log.warning("Jonli narx olinmadi, eskirgan keshdan foydalanildi")
                return stale
            raise MarketDataError("Oltin narxini hech bir manbadan olib bo'lmadi")

        self._set_cache(key, price)
        return price

    def get_latest_high_low(self) -> tuple[float, float, float]:
        """
        So'nggi 5m shamchaning (high, low, close) qiymatlarini qaytaradi.
        Wick (soya) orqali SL/TP ga tekkanini aniqroq tekshirish uchun xizmat qiladi.
        Shamcha bo'lmasa jonli narx qaytariladi.
        """
        try:
            df = self.get_candles("5m", limit=2)
            if not df.empty:
                last_row = df.iloc[-1]
                return float(last_row["high"]), float(last_row["low"]), float(last_row["close"])
        except Exception:
            pass
        p = self.get_live_price()
        return p, p, p

    def _price_binance(self) -> Optional[float]:
        try:
            r = self._get_session().get(f"{BINANCE_URL}/ticker/price", params={"symbol": "PAXGUSDT"}, timeout=10)
            r.raise_for_status()
            return float(r.json()["price"])
        except Exception as exc:
            log.warning("Binance narx xatosi: %s", exc)
            return None

    def _price_yahoo(self) -> Optional[float]:
        try:
            r = self._get_session().get(YAHOO_URL, params={"interval": "1m", "range": "1d"}, timeout=15)
            r.raise_for_status()
            return float(r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"])
        except Exception as exc:
            log.warning("Yahoo narx xatosi: %s", exc)
            return None

    # --- shamchalar ---
    def get_candles(self, timeframe: str = "15m", limit: int = 250) -> pd.DataFrame:
        if timeframe not in settings.TIMEFRAMES:
            raise ValueError(f"Qo'llab-quvvatlanmaydigan timeframe: {timeframe}")

        key = f"candles_{timeframe}_{limit}"
        cached = self._get_cache(key, settings.CACHE_EXPIRY_SECONDS)
        if cached is not None:
            return cached.copy()

        df = self._candles_binance(timeframe, limit)
        if df is None:
            df = self._candles_yahoo(timeframe, limit)
        if df is None or df.empty:
            stale = self._get_cache(key, STALE_MAX_SECONDS)
            if stale is not None:
                log.warning("Shamchalar olinmadi, eskirgan keshdan foydalanildi (%s)", timeframe)
                return stale.copy()
            raise MarketDataError(f"{timeframe} shamchalarini hech bir manbadan olib bo'lmadi")

        # Oxirgi shamcha odatda hali yopilmagan (chala) bo'ladi, tahlil barqarorligi uchun uni hisobga almaymiz
        df = df.iloc[:-1].reset_index(drop=True)

        self._set_cache(key, df)
        return df.copy()

    def _candles_binance(self, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        try:
            r = self._get_session().get(
                f"{BINANCE_URL}/klines",
                params={"symbol": "PAXGUSDT", "interval": timeframe, "limit": min(limit, 1000)},
                timeout=15,
            )
            r.raise_for_status()
            return klines_to_df(r.json())
        except Exception as exc:
            log.warning("Binance shamcha xatosi: %s", exc)
            return None

    def _candles_yahoo(self, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        try:
            interval, rng = _YAHOO_TF[timeframe]
            r = self._get_session().get(YAHOO_URL, params={"interval": interval, "range": rng}, timeout=20)
            r.raise_for_status()
            result = r.json()["chart"]["result"][0]
            quote = result["indicators"]["quote"][0]
            df = pd.DataFrame({
                "timestamp": pd.to_datetime(result["timestamp"], unit="s"),
                "open": quote["open"],
                "high": quote["high"],
                "low": quote["low"],
                "close": quote["close"],
                "volume": quote.get("volume") or [0] * len(result["timestamp"]),
            }).dropna().reset_index(drop=True)

            if timeframe == "4h":
                df = (
                    df.set_index("timestamp")
                    .resample("4h")
                    .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
                    .dropna()
                    .reset_index()
                )
            return df.tail(limit).reset_index(drop=True)
        except Exception as exc:
            log.warning("Yahoo shamcha xatosi: %s", exc)
            return None


def klines_to_df(raw: list) -> pd.DataFrame:
    """Binance klines javobini DataFrame ga aylantiradi (vektorlashtirilgan)."""
    return pd.DataFrame({
        "timestamp": pd.to_datetime([k[0] for k in raw], unit="ms"),
        "open": [float(k[1]) for k in raw],
        "high": [float(k[2]) for k in raw],
        "low": [float(k[3]) for k in raw],
        "close": [float(k[4]) for k in raw],
        "volume": [float(k[5]) for k in raw],
    })


def _history_cache_path(interval: str, total: int, symbol: str):
    from pathlib import Path

    from config import BASE_DIR

    directory = Path(BASE_DIR) / "data" / "cache"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"hist_{symbol}_{interval}_{total}.pkl"


def fetch_history(
    interval: str,
    total: int,
    symbol: str = "PAXGUSDT",
    timeout: int = 20,
    refresh: bool = False,
    retries: int = 3,
    cache: bool = True,
) -> pd.DataFrame:
    """
    Binance'dan `total` ta shamchani orqaga qarab sahifalab yuklaydi (backtest uchun).

    - `cache=True` (standart): natija `data/cache/` ga keshlanadi (backtest uchun tez).
    - `cache=False`: jonli foydalanish uchun - har doim yangi ma'lumot (kesh o'qilmaydi/saqlanmaydi).
    - Har bir so'rov `retries` marta takrorlanadi (tarmoq uzilishlariga chidamli).
    - To'liq yuklanmagan (qism) natija keshlanmaydi.
    """
    cache_path = _history_cache_path(interval, total, symbol)
    if cache and not refresh and cache_path.exists():
        try:
            cached = pd.read_pickle(cache_path)
            if len(cached) > 0:
                log.info("Tarix keshedan o'qildi: %s (%d shamcha)", cache_path.name, len(cached))
                return cached
        except Exception as exc:
            log.warning("Kesh o'qilmadi (%s): %s", cache_path.name, exc)

    frames: list[pd.DataFrame] = []
    end = None
    fetched = 0
    complete = True
    session = requests.Session()
    while fetched < total:
        params = {"symbol": symbol, "interval": interval, "limit": 1000}
        if end:
            params["endTime"] = end
        raw = None
        for attempt in range(1, retries + 1):
            try:
                resp = session.get(f"{BINANCE_URL}/klines", params=params, timeout=timeout)
                resp.raise_for_status()
                raw = resp.json()
                break
            except Exception as exc:
                log.warning("Binance so'rovi %d/%d muvaffaqiyatsiz: %s", attempt, retries, exc)
                time.sleep(1.5 * attempt)
        if not raw:
            if frames:
                log.warning("Sahifa olinmadi - mavjud %d shamcha bilan davom etamiz", fetched)
                complete = False
                break
            raise MarketDataError(f"Binance'dan {interval} tarixi olinmadi")
        frames.insert(0, klines_to_df(raw))
        fetched += len(raw)
        end = raw[0][0] - 1

    if not frames:
        raise MarketDataError(f"Binance'dan {interval} tarixi olinmadi")

    df = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
    df = df.tail(total).reset_index(drop=True)
    if complete and cache:
        try:
            df.to_pickle(cache_path)
        except Exception as exc:
            log.warning("Keshni saqlab bo'lmadi: %s", exc)
    return df


market_service = MarketDataService()
