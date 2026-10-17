import html
import time
import requests
from datetime import datetime, timezone
import dateutil.parser
from typing import List, Dict, Any, Optional

import threading
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class NewsService:
    def __init__(self):
        # Oxirgi muvaffaqiyatli taqvim (yoki None)
        self._events: Optional[List[Dict[str, Any]]] = None
        self._last_success: float = 0.0
        # Oxirgi urinish vaqti (negativ kesh / backoff uchun)
        self._last_attempt: float = 0.0
        self.cache_ttl = 300       # Muvaffaqiyatli natija 5 daqiqa keshlanadi
        self.fail_backoff = 60     # Xato (tarmoq/429) bo'lsa 1 daqiqa qayta urinmaymiz
        self._lock = threading.Lock()
        self._local = threading.local()

    def _get_session(self) -> requests.Session:
        """Thread-safe: har bir ishchi oqimga alohida Session beriladi."""
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            # MUHIM: 429 ni qayta urinmaymiz. Cloudflare "Retry-After" bilan javob berganda
            # urllib3 uni hurmat qilib, ishchi oqimni o'nlab soniyaga bloklab qo'yadi.
            # Xato bo'lsa pastdagi negativ kesh orqali tez qaytamiz.
            retry_strategy = Retry(
                total=1,
                backoff_factor=0.3,
                status_forcelist=[500, 502, 503, 504],
                respect_retry_after_header=False,
                allowed_methods=frozenset(["GET"]),
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            self._local.session = session
        return session

    def fetch_calendar(self, force: bool = False) -> List[Dict[str, Any]]:
        """
        ForexFactory rasmiy taqvimidan joriy haftadagi iqtisodiy voqealarni oladi.

        Xato bo'lsa (tarmoq yoki 429) qisqa muddatli "negativ kesh" ishlatiladi -
        takroriy sekin urinishlarning oldini oladi. Muvaffaqiyatli natija 5 daqiqa keshlanadi.
        """
        now = time.time()
        with self._lock:
            # Yangi (muvaffaqiyatli) kesh hali amalda
            if not force and self._events is not None and (now - self._last_success < self.cache_ttl):
                return list(self._events)
            # Yaqinda urinib muvaffaqiyatsiz bo'lganmiz - backoff, eski keshni qaytaramiz
            if not force and self._last_attempt and (now - self._last_attempt < self.fail_backoff):
                return list(self._events or [])

        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        events: Optional[List[Dict[str, Any]]] = None
        try:
            r = self._get_session().get(url, timeout=10)
            if r.status_code == 200:
                events = r.json()
        except Exception:
            events = None

        with self._lock:
            self._last_attempt = now
            if events is not None:
                self._events = events
                self._last_success = now
                return list(events)
            # Xato: oxirgi muvaffaqiyatli kesh bo'lsa undan foydalanamiz
            return list(self._events or [])

    def get_usd_gold_events(self) -> List[Dict[str, Any]]:
        """
        Oltin (XAUUSD) ga bevosita ta'sir qiluvchi USD yangiliklarini filtrlaydi.
        """
        all_events = self.fetch_calendar()
        usd_events = []
        for event in all_events:
            # USD valyutasi va O'rta/Yuqori ta'sirli voqealar
            if event.get("country") == "USD" and event.get("impact") in ["High", "Medium"]:
                try:
                    event_dt = dateutil.parser.isoparse(event["date"])
                    usd_events.append({
                        "title": event.get("title", "Noma'lum voqea"),
                        "impact": event.get("impact", "Low"),
                        "datetime": event_dt,
                        "forecast": event.get("forecast", "-"),
                        "previous": event.get("previous", "-"),
                        "actual": event.get("actual", "-")
                    })
                except Exception:
                    continue
        return usd_events

    def evaluate_trading_safety(self) -> Dict[str, Any]:
        """
        Hozirgi vaqtda Oltinda savdo qilish xavfsizligini tekshiradi:
        - 30 daqiqa oldin va 15 daqiqa keyin yuqori xavfli hisoblanadi.
        """
        calendar_ok = bool(self.fetch_calendar())
        if not calendar_ok:
            return {
                "status": "UNKNOWN_CAUTION",
                "status_text": "⚪ Iqtisodiy taqvim bilan aloqa yo'q (Ehtiyotkorlik zarur)",
                "recommendation": "Iqtisodiy yangiliklar serveri bilan aloqa uzildi. Kutilmagan yangilik xavfi sababli yangi bitim ochish tavsiya etilmaydi.",
                "safe_to_trade": False,
                "calendar_ok": False,
                "upcoming": [],
                "recent": []
            }

        events = self.get_usd_gold_events()
        now = datetime.now(timezone.utc)

        upcoming_high = []
        recent_high = []

        for e in events:
            diff_minutes = (e["datetime"] - now).total_seconds() / 60.0

            # Keyingi 60 daqiqa ichidagi voqealar
            if 0 <= diff_minutes <= 60:
                upcoming_high.append({**e, "minutes_left": int(diff_minutes)})
            # Oxirgi 30 daqiqa ichida chiqqan voqealar
            elif -30 <= diff_minutes < 0:
                recent_high.append({**e, "minutes_ago": abs(int(diff_minutes))})

        # Xavf darajasini baholash
        if any(e["impact"] == "High" and 0 <= e["minutes_left"] <= 30 for e in upcoming_high):
            status = "DANGER"
            status_text = "🔴 YUQORI XAVF (Kuchli yangilik kutilmoqda)"
            recommendation = "Hozir yangi pozitsiya ochmang! Kuchli spayklar va sirpanishlar (slippage) bo'lishi mumkin."
            safe_to_trade = False
        elif any(e["impact"] == "High" and e["minutes_ago"] <= 15 for e in recent_high):
            status = "VOLATILE"
            status_text = "🟠 BOZOR BEQAROR (Yangilik endi e'lon qilindi)"
            recommendation = "Bozor yangilik reaksiyasini hazm qilmoqda. 10-15 daqiqa kutish tavsiya etiladi."
            safe_to_trade = False
        elif upcoming_high:
            status = "CAUTION"
            status_text = "🟡 DIQQAT (1 soat ichida voqea bor)"
            recommendation = "Qisqa muddatli savdolar mumkin, lekin Stop-Loss ni qat'iy nazorat qiling."
            safe_to_trade = True
        else:
            status = "SAFE"
            status_text = "🟢 XAVFSIZ (Tinch bozor)"
            recommendation = "Bozorda kuchli fundamental to'siqlar yo'q. Texnik va SMC signallari bo'yicha savdo qilish mumkin."
            safe_to_trade = True

        return {
            "status": status,
            "status_text": status_text,
            "recommendation": recommendation,
            "safe_to_trade": safe_to_trade,
            "calendar_ok": calendar_ok,
            "upcoming": upcoming_high[:3],
            "recent": recent_high[:2]
        }

    def format_news_summary_uz(self) -> str:
        """
        Telegram xabari uchun chiroyli o'zbek tilidagi tahliliy xulosa.
        """
        safety = self.evaluate_trading_safety()
        events = self.get_usd_gold_events()
        now = datetime.now(timezone.utc)

        lines = [
            "📰 <b>DUNYO IQTISODIY YANGILIKLARI VA FUNDAMENTAL TAHLIL</b>",
            f"⚡ <b>Holat:</b> {safety['status_text']}",
            f"💡 <b>Tavsiya:</b> {safety['recommendation']}",
            ""
        ]
        if not safety["calendar_ok"]:
            lines.insert(1, "⚪ <b>Diqqat:</b> iqtisodiy taqvim olinmadi, yangiliklar tekshirilmadi!")

        if safety["upcoming"]:
            lines.append("⏳ <b>Kutilayotgan muhim voqealar:</b>")
            for ev in safety["upcoming"]:
                impact_emoji = "🔴" if ev["impact"] == "High" else "🟠"
                lines.append(
                    f"• {impact_emoji} <b>{html.escape(str(ev['title']))}</b> (USD)\n"
                    f"  ⏱ Qoldi: {ev['minutes_left']} daqiqa\n"
                    f"  📊 Prognoz: {html.escape(str(ev['forecast']))} | "
                    f"Avvalgi: {html.escape(str(ev['previous']))}"
                )
            lines.append("")

        if safety["recent"]:
            lines.append("📢 <b>Yaqinda e'lon qilingan:</b>")
            for ev in safety["recent"]:
                lines.append(
                    f"• <b>{html.escape(str(ev['title']))}</b>: {ev['minutes_ago']} daqiqa oldin chiqdi\n"
                    f"  📊 Fakt: {html.escape(str(ev['actual']))} | "
                    f"Prognoz: {html.escape(str(ev['forecast']))}"
                )
            lines.append("")

        # Bugungi/Haftadagi eng muhim High impactlar
        future_highs = [e for e in events if e["datetime"] > now and e["impact"] == "High"]
        if future_highs and not safety["upcoming"]:
            lines.append("📅 <b>Keyingi muhim High-Impact voqea:</b>")
            next_ev = future_highs[0]
            local_time_str = next_ev["datetime"].strftime("%d-%b %H:%M UTC")
            lines.append(f"• 🔴 <b>{html.escape(str(next_ev['title']))}</b>: {local_time_str}")

        return "\n".join(lines)

news_service = NewsService()
