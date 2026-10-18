import sqlite3
import json
import logging
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
import os
from contextlib import contextmanager

from config import settings

log = logging.getLogger(__name__)

class SignalJournal:
    def __init__(self, db_path="data/journal.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 10000;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._lock:
            with self._connection() as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS signals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        action TEXT,
                        timeframe TEXT,
                        entry_price REAL,
                        stop_loss REAL,
                        tp1 REAL,
                        strength INTEGER,
                        votes TEXT,
                        result TEXT, -- 'WIN', 'LOSS', 'PENDING', 'OPEN', 'OPEN_WARNED', 'EXPIRED'
                        pnl REAL
                    )
                ''')
                columns = [
                    "tp2 REAL", "tp3 REAL", "closed_at TEXT",
                    "user_id INTEGER", "lot_size REAL",
                    "price_offset REAL DEFAULT 0.0", "opened_at TEXT"
                ]
                for col in columns:
                    try:
                        conn.execute(f"ALTER TABLE signals ADD COLUMN {col}")
                    except sqlite3.OperationalError:
                        pass

    def log_signal(self, sig: Dict[str, Any], user_id: int = 0) -> int:
        if sig.get("action") not in ("BUY", "SELL"):
            return 0
            
        with self._lock:
            try:
                with self._connection() as conn:
                    cursor = conn.execute('''
                        INSERT INTO signals 
                        (timestamp, action, timeframe, entry_price, stop_loss, tp1, tp2, tp3, strength, votes, result, pnl, user_id, lot_size, price_offset)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 0.0, ?, ?, ?)
                    ''', (
                        sig["generated_at"].isoformat(),
                        sig["action"],
                        sig["timeframe"],
                        sig["entry_price"],
                        sig["stop_loss"],
                        sig["tps"][0] if sig.get("tps") else 0,
                        sig["tps"][1] if len(sig.get("tps", [])) > 1 else 0,
                        sig["tps"][2] if len(sig.get("tps", [])) > 2 else 0,
                        sig.get("strength", 0),
                        json.dumps(sig.get("votes", [])),
                        user_id,
                        sig.get("risk", {}).get("lot_size", 0.01),
                        sig.get("offset", 0.0)
                    ))
                    conn.commit()
                    return cursor.lastrowid
            except Exception:
                log.exception("Signal jurnalga yozishda xatolik yuz berdi")
                return 0

    def get_signal(self, signal_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            try:
                with self._connection() as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
                    return dict(row) if row else None
            except Exception:
                log.exception(f"Signalni ID bo'yicha olishda xatolik: {signal_id}")
                return None

    def mark_trade_open(self, signal_id: int, user_id: Optional[int] = None) -> bool:
        with self._lock:
            try:
                with self._connection() as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute("SELECT user_id, result FROM signals WHERE id = ?", (signal_id,)).fetchone()
                    if not row:
                        return False
                    if user_id is not None and row["user_id"] != user_id:
                        log.warning(f"Foydalanuvchi {user_id} boshqa userning signalini ({signal_id}) ochishga urindi")
                        return False
                    if row["result"] != "PENDING":
                        return False

                    now_str = datetime.now(ZoneInfo(settings.TIMEZONE)).isoformat()
                    conn.execute(
                        "UPDATE signals SET result = 'OPEN', opened_at = ? WHERE id = ?",
                        (now_str, signal_id)
                    )
                    conn.commit()
                    return True
            except Exception:
                log.exception(f"Signalni OPEN qilishda xatolik yuz berdi: {signal_id}")
                return False

    def mark_trade_warned(self, signal_id: int):
        with self._lock:
            try:
                with self._connection() as conn:
                    conn.execute("UPDATE signals SET result = 'OPEN_WARNED' WHERE id = ?", (signal_id,))
                    conn.commit()
            except Exception:
                log.exception(f"Signalni OPEN_WARNED qilishda xatolik yuz berdi: {signal_id}")

    def mark_trade_closed(self, signal_id: int, result: str, pnl: float = 0.0):
        with self._lock:
            try:
                with self._connection() as conn:
                    now_str = datetime.now(ZoneInfo(settings.TIMEZONE)).isoformat()
                    conn.execute(
                        "UPDATE signals SET result = ?, pnl = ?, closed_at = ? WHERE id = ?", 
                        (result, pnl, now_str, signal_id)
                    )
                    conn.commit()
            except Exception:
                log.exception(f"Signalni yopishda xatolik yuz berdi: {signal_id}")

    def mark_trade_tp1_hit(self, signal_id: int, stop_loss: float, partial_pnl: float):
        """TP1 urilganda: qisman foyda yoziladi. `stop_loss` - qolgan qism uchun amal qiladigan SL.

        DIQQAT: jonli mantiqda SL BE (kirish) ga SURILMAYDI - asl SL saqlanadi.
        Backtest (`scripts/backtest.py`, `half_hold`) BE ga surish foydani kamaytirishini ko'rsatdi.
        """
        with self._lock:
            try:
                with self._connection() as conn:
                    conn.execute(
                        "UPDATE signals SET result = 'TP1_HIT', stop_loss = ?, pnl = ? WHERE id = ?", 
                        (stop_loss, partial_pnl, signal_id)
                    )
                    conn.commit()
            except Exception:
                log.exception(f"Signalni TP1_HIT qilishda xatolik yuz berdi: {signal_id}")

    def get_open_trades(self) -> List[Dict[str, Any]]:
        try:
            with self._connection() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM signals WHERE result IN ('OPEN', 'OPEN_WARNED', 'TP1_HIT')"
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            log.exception("Ochiq bitimlarni o'qishda xatolik yuz berdi")
            return []

    def get_last_signal_time(self, user_id: int, timeframe: str, action: str) -> Optional[datetime]:
        try:
            with self._connection() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT timestamp FROM signals 
                    WHERE user_id = ? AND timeframe = ? AND action = ? 
                    ORDER BY id DESC LIMIT 1
                    """,
                    (user_id, timeframe, action)
                ).fetchone()
                if row:
                    return datetime.fromisoformat(row['timestamp'])
                return None
        except Exception:
            log.exception("Oxirgi signal vaqtini olishda xatolik")
            return None

    def get_stats(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        try:
            with self._connection() as conn:
                conn.row_factory = sqlite3.Row
                if user_id:
                    rows = conn.execute(
                        "SELECT * FROM signals WHERE result IN ('WIN', 'LOSS') AND user_id = ?",
                        (user_id,)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM signals WHERE result IN ('WIN', 'LOSS')"
                    ).fetchall()
                
                total = len(rows)
                wins = sum(1 for r in rows if r['result'] == 'WIN')
                losses = sum(1 for r in rows if r['result'] == 'LOSS')
                total_pnl = sum(r['pnl'] or 0.0 for r in rows)
                
                win_rate = (wins / total * 100) if total > 0 else 0
                
                return {
                    "total": total,
                    "wins": wins,
                    "losses": losses,
                    "win_rate": round(win_rate, 1),
                    "total_pnl": round(total_pnl, 2)
                }
        except Exception:
            log.exception("Statistikani olishda xatolik yuz berdi")
            return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl": 0.0}

    def get_detailed_stats(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Kengaytirilgan statistika: Profit Factor, o'rtacha natija, yo'nalish bo'yicha."""
        empty: Dict[str, Any] = {
            "total": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "total_pnl": 0.0, "profit_factor": 0.0, "avg_pnl": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "open_count": 0, "by_action": {},
        }
        try:
            with self._connection() as conn:
                conn.row_factory = sqlite3.Row
                where = "WHERE result IN ('WIN', 'LOSS')"
                params: tuple = ()
                if user_id:
                    where += " AND user_id = ?"
                    params = (user_id,)
                rows = conn.execute(f"SELECT result, action, pnl FROM signals {where}", params).fetchall()

                win_pnls = [r["pnl"] or 0.0 for r in rows if r["result"] == "WIN"]
                loss_pnls = [r["pnl"] or 0.0 for r in rows if r["result"] == "LOSS"]
                total = len(rows)
                gross_win = sum(w for w in win_pnls if w > 0)
                gross_loss = abs(sum(l for l in loss_pnls if l < 0))
                pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
                total_pnl = sum(win_pnls) + sum(loss_pnls)

                by_action: Dict[str, Dict[str, Any]] = {}
                for act in ("BUY", "SELL"):
                    sub = [r for r in rows if r["action"] == act]
                    n = len(sub)
                    sub_wins = sum(1 for r in sub if r["result"] == "WIN")
                    by_action[act] = {
                        "total": n,
                        "wins": sub_wins,
                        "losses": n - sub_wins,
                        "win_rate": round(sub_wins / n * 100, 1) if n else 0.0,
                        "pnl": round(sum(r["pnl"] or 0.0 for r in sub), 2),
                    }

                open_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM signals WHERE result IN ('OPEN', 'OPEN_WARNED', 'TP1_HIT')"
                ).fetchone()["c"]

            return {
                "total": total,
                "wins": len(win_pnls),
                "losses": len(loss_pnls),
                "win_rate": round(len(win_pnls) / total * 100, 1) if total else 0.0,
                "total_pnl": round(total_pnl, 2),
                "profit_factor": pf,
                "avg_pnl": round(total_pnl / total, 2) if total else 0.0,
                "avg_win": round(sum(win_pnls) / len(win_pnls), 2) if win_pnls else 0.0,
                "avg_loss": round(sum(loss_pnls) / len(loss_pnls), 2) if loss_pnls else 0.0,
                "open_count": open_count,
                "by_action": by_action,
            }
        except Exception:
            log.exception("Batafsil statistikani olishda xatolik yuz berdi")
            return empty

    def expire_stale_pending_signals(self, max_age_minutes: int = 60) -> int:
        with self._lock:
            try:
                with self._connection() as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute("SELECT id, timestamp FROM signals WHERE result = 'PENDING'").fetchall()
                    now = datetime.now(ZoneInfo(settings.TIMEZONE))
                    expired_ids = []
                    for r in rows:
                        sig_dt = datetime.fromisoformat(r['timestamp'])
                        diff_min = (now.replace(tzinfo=None) - sig_dt.replace(tzinfo=None)).total_seconds() / 60.0
                        if diff_min >= max_age_minutes:
                            expired_ids.append(r['id'])
                    
                    if expired_ids:
                        placeholders = ",".join("?" for _ in expired_ids)
                        conn.execute(f"UPDATE signals SET result = 'EXPIRED' WHERE id IN ({placeholders})", expired_ids)
                        conn.commit()
                    return len(expired_ids)
            except Exception:
                log.exception("Eskirgan PENDING signallarni tozalashda xatolik")
                return 0

journal_service = SignalJournal()
