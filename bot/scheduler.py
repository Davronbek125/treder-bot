import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot

from config import settings
from bot.state import get_settings
from bot.views import build_signal
from bot.formatters import format_signal
from bot.keyboards import get_signal_inline_kb
from services.market_data import MarketDataError, market_service
from services.journal import journal_service
from services.market_hours import is_market_open


log = logging.getLogger(__name__)



async def _send_signal_alert(bot: Bot, user_id: int):
    try:
        cfg = get_settings(user_id)
        tf = cfg["timeframe"]
        
        # Signalni hisoblaymiz, lekin hali jurnalga yozmaymiz
        sig = await asyncio.to_thread(build_signal, cfg, tf)
        action = sig["action"]
        
        # If it's a BUY or SELL, send it. If it's WAIT, don't spam.
        if action in ("BUY", "SELL"):
            now = datetime.now(ZoneInfo(settings.TIMEZONE))
            
            # Dedup: oxirgi 1 soatda xuddi shu yo'nalishdagi signal bo'lsa - yubormaymiz.
            # MUHIM: tekshiruv log_signal dan OLDIN bo'lishi kerak, aks holda
            # yangi yozilgan signalning o'zi topilib, hech qachon yuborilmaydi.
            last_time = await asyncio.to_thread(journal_service.get_last_signal_time, user_id, tf, action)
            if last_time:
                # timezone muammosi bo'lmasligi uchun ikkalasini ham tz-naive qilib solishtiramiz
                last_time_naive = last_time.replace(tzinfo=None)
                now_naive = now.replace(tzinfo=None)
                if (now_naive - last_time_naive).total_seconds() < 3600:
                    return # Skip spam
            
            signal_id = await asyncio.to_thread(journal_service.log_signal, sig, user_id)
            text = format_signal(sig)
            await bot.send_message(
                user_id, 
                "🔔 <b>YANGI SIGNAL TAYYOR!</b>\n\n" + text,
                reply_markup=get_signal_inline_kb(tf, signal_id)
            )
            log.info(f"Signal alert sent to {user_id}")
    except MarketDataError:
        pass # Ignore network issues during automated checks
    except Exception as e:
        log.error(f"Error sending auto-signal to {user_id}: {e}")

async def auto_signal_task(bot: Bot):
    """Background task that checks for signals every 5 minutes."""
    log.info("Auto-signal scheduler started.")
    last_checked_minute = -1
    while True:
        try:
            now = datetime.now(ZoneInfo(settings.TIMEZONE))
            
            if now.minute % 5 == 0 and now.minute != last_checked_minute:
                last_checked_minute = now.minute

                # 1. Eskirgan PENDING signallarni tozalash (har 15 daqiqada)
                if now.minute % 15 == 0:
                    try:
                        await asyncio.to_thread(journal_service.expire_stale_pending_signals, 60)
                    except Exception as e:
                        log.warning(f"Error expiring stale signals: {e}")

                # 2. Dam olish kunlari (Forex/MT5 yopiq) tekshiruvi:
                if not is_market_open(now):
                    log.info("XAUUSD bozori yopiq (dam olish kuni). Avto-signal tekshiruvi o'tkazilmaydi.")
                else:
                    log.info("Checking for automated signals and open trades...")
                    tasks = []
                    for user_id in settings.allowed_user_ids:
                        tasks.append(asyncio.create_task(_send_signal_alert(bot, user_id)))
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                
                try:
                    await _check_open_trades(bot, now)
                except Exception as e:
                    log.error(f"Error checking open trades: {e}")
            
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            log.info("Auto-signal scheduler cancelled.")
            break
        except Exception as e:
            log.exception(f"Unexpected error in auto_signal_task loop: {e}")
            await asyncio.sleep(60)

def _process_open_trades(
    now: datetime, 
    current_price: float, 
    high_price: float = None, 
    low_price: float = None
) -> list:
    """
    Ochiq bitimlarni SL va TP darajalari bo'yicha tekshiradi.
    high_price va low_price berilsa (shamcha soyasi), narx sakrab o'tgan bo'lsa ham aniq ushlaydi.
    """
    notifications = []
    high = high_price if high_price is not None else current_price
    low = low_price if low_price is not None else current_price
    
    rows = journal_service.get_open_trades()
    for r in rows:
        try:
            user_id = r.get('user_id', 0)
            if not user_id: continue
            
            cfg = get_settings(user_id)
            # Signal paytida qayd etilgan offset ishlatiladi (mavjud bo'lmasa userning joriy offseti)
            offset = r.get("price_offset") if r.get("price_offset") is not None else cfg.get("price_offset", 0.0)
            
            # Narxlarni tegishli offsetga moslaymiz
            u_high = high + offset
            u_low = low + offset
            u_close = current_price + offset
            
            sig_id = r['id']
            action = r['action']
            entry = r.get('entry_price', u_close)
            sl = r['stop_loss']
            tp1 = r['tp1']
            tp2 = r.get('tp2', 0) or tp1
            tp3 = r.get('tp3', 0) or tp1
            
            trade_time = datetime.fromisoformat(r['timestamp'])
            diff_hours = (now.replace(tzinfo=None) - trade_time.replace(tzinfo=None)).total_seconds() / 3600.0
            
            hit_result = None
            pnl = 0.0
            target_price = 0.0
            
            # DB da log_signal da yozilgan lot bo'lsa, o'shani ishlatamiz. Yo'qsa, user config orqali taxminan topamiz.
            db_lot = r.get('lot_size')
            if db_lot and db_lot > 0:
                lot_size = db_lot
            else:
                risk_usd = (cfg["balance"] * cfg["risk_percent"]) / 100.0
                sl_distance = abs(entry - sl)
                calc_lot = risk_usd / (sl_distance * 100) if sl_distance > 0 else 0.01 
                lot_size = max(0.01, round(calc_lot, 2))
            
            # Oldindan yozilgan (masalan TP1 hit) foydani hisobga olamiz
            existing_pnl = r.get('pnl') or 0.0
            trade_state = r.get('result', 'OPEN')
            
            def calc_pnl(exit_p: float, portion: float = 1.0) -> float:
                diff = (exit_p - entry) if action == "BUY" else (entry - exit_p)
                return round(diff * 100 * lot_size * portion, 2)
            
            if action == "BUY":
                if u_low <= sl:
                    hit_result = "LOSS"
                    target_price = sl
                elif u_high >= tp3:
                    hit_result = "WIN (TP3)"
                    target_price = tp3
                elif u_high >= tp2:
                    hit_result = "WIN (TP2)"
                    target_price = tp2
                elif u_high >= tp1 and trade_state != 'TP1_HIT':
                    hit_result = "TP1_HIT"
                    target_price = tp1
            elif action == "SELL":
                if u_high >= sl:
                    hit_result = "LOSS"
                    target_price = sl
                elif u_low <= tp3:
                    hit_result = "WIN (TP3)"
                    target_price = tp3
                elif u_low <= tp2:
                    hit_result = "WIN (TP2)"
                    target_price = tp2
                elif u_low <= tp1 and trade_state != 'TP1_HIT':
                    hit_result = "TP1_HIT"
                    target_price = tp1
            
            if hit_result == "TP1_HIT":
                partial_pnl = calc_pnl(target_price, portion=0.5)
                journal_service.mark_trade_tp1_hit(sig_id, break_even_sl=entry, partial_pnl=partial_pnl)
                notifications.append((
                    user_id, 
                    f"✅ <b>TP1 Urib O'tildi! (Foyda qulflanmoqda)</b>\n"
                    f"#{sig_id} {action} bitimi TP1 ga yetdi ({target_price}$).\n"
                    f"👉 Pozitsiya yarmi (0.5 yopildi): <b>{partial_pnl:+.2f}$</b>\n"
                    f"🛡 Qolgan qismi uchun Stop Loss kirish narxiga ({entry}$) o'tkazildi (Breakeven)!"
                ))
                continue
                
            elif hit_result:
                # Qolgan yoki butun pnl ni hisoblaymiz
                portion_left = 0.5 if trade_state == 'TP1_HIT' else 1.0
                final_pnl = existing_pnl + calc_pnl(target_price, portion=portion_left)
                is_breakeven = trade_state == 'TP1_HIT' and hit_result == "LOSS"
                # Breakeven: TP1 dagi qisman foyda saqlangan, demak natija WIN (yoki 0 bo'lsa LOSS emas)
                if is_breakeven:
                    db_result = "WIN" if final_pnl > 0 else "LOSS"
                else:
                    db_result = "WIN" if "WIN" in hit_result else "LOSS"
                journal_service.mark_trade_closed(sig_id, db_result, pnl=final_pnl)
                
                icon = "🛡" if is_breakeven else "✅✅" if db_result == "WIN" else "❌"
                txt_status = "Breakeven bilan yopildi" if is_breakeven else f"{hit_result} bilan yakunlandi"
                
                notifications.append((
                    user_id, 
                    f"{icon} <b>Bitim to'liq yopildi!</b>\n"
                    f"#{sig_id} {action} bitimi <b>{txt_status}</b>.\n"
                    f"🎯 Chiqish narxi: {target_price}$\n"
                    f"📊 Yakuniy Sof Foyda/Zarar: <b>{final_pnl:+.2f}$</b> <i>(Asosiy Lot: {lot_size})</i>"
                ))
                continue
            
            # 12 soatdan oshsa eskiradi
            if diff_hours >= 12.0:
                # TP1 da olingan qisman foyda yo'qolmasligi kerak
                journal_service.mark_trade_closed(sig_id, "EXPIRED", pnl=existing_pnl)
                notifications.append((
                    user_id, 
                    f"⚠️ <b>Bitim eskirgan!</b>\n#{sig_id} {action} bitimi 12 soatdan oshdi va yopilmagan deb topildi."
                ))
            # 4 soatdan oshsa ogohlantirish
            elif diff_hours >= 4.0 and r.get('result') == 'OPEN':
                journal_service.mark_trade_warned(sig_id)
                notifications.append((
                    user_id, 
                    f"⚠️ <b>DIQQAT!</b> Sizning #{sig_id} {action} bitimingiz {diff_hours:.1f} soatdan beri ochiq (hali na TP va na SL ni urmagan)."
                ))
                
        except Exception as e:
            log.error(f"Error processing trade {r.get('id')}: {e}")
            
    return notifications

async def _check_open_trades(bot: Bot, now: datetime):
    try:
        high, low, close = await asyncio.to_thread(market_service.get_latest_high_low)
    except Exception as e:
        log.warning(f"Failed to get price for open trade check: {e}")
        return
    
    try:
        notifications = await asyncio.to_thread(_process_open_trades, now, close, high, low)
        for user_id, msg in notifications:
            if user_id:
                try:
                    await bot.send_message(user_id, msg)
                except Exception as e:
                    log.warning(f"Could not send trade notification to {user_id}: {e}")
    except Exception as e:
        log.error(f"Error checking open trades: {e}")
