import asyncio
import logging
from typing import Callable, Optional, Tuple

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import views
from bot.access import AllowedUser
from bot.keyboards import (
    get_analysis_inline_kb,
    get_calc_keyboard,
    get_main_keyboard,
    get_signal_inline_kb,
)
from bot.state import get_settings, update_settings
from config import settings
from services.backtester import backtester_service
from services.journal import journal_service
from services.market_data import MarketDataError, market_service
from services.market_hours import is_market_open
from services.news_service import news_service

log = logging.getLogger(__name__)

router = Router()
router.message.filter(AllowedUser())
router.callback_query.filter(AllowedUser())

ERR_MARKET = "❌ Bozor ma'lumotlari vaqtincha olinmadi. Birozdan so'ng qayta urinib ko'ring."
ERR_GENERIC = "❌ Kutilmagan xatolik yuz berdi. Qayta urinib ko'ring."
PRICE_SANITY = (500.0, 20000.0)
MAX_OFFSET = 100.0
ALLOWED_DEPOSITS = {100.0, 300.0, 500.0, 1000.0, 2500.0, 5000.0}
ALLOWED_RISKS = {0.5, 1.0, 2.0}


async def _build(builder: Callable[..., str], *args) -> Tuple[str, bool]:
    """Sinxron quruvchini thread da ishga tushiradi (event loop bloklanmaydi)."""
    try:
        return await asyncio.to_thread(builder, *args), True
    except MarketDataError:
        log.exception("Bozor ma'lumotlari xatosi")
        return ERR_MARKET, False
    except Exception:
        log.exception("Handlerda kutilmagan xato")
        return ERR_GENERIC, False


async def _safe_edit(message: Message, text: str, kb: Optional[InlineKeyboardMarkup] = None) -> None:
    try:
        await message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


async def _answer_view(message: Message, loading: str, builder, args, kb_factory=None) -> None:
    status = await message.answer(loading)
    text, ok = await _build(builder, *args)
    kb = kb_factory() if (ok and kb_factory) else None
    await _safe_edit(status, text, kb)


async def _edit_view(callback: CallbackQuery, builder, args, kb_factory=None) -> None:
    text, ok = await _build(builder, *args)
    kb = kb_factory() if (ok and kb_factory) else None
    await _safe_edit(callback.message, text, kb)


def _valid_tf(tf: str) -> bool:
    return tf in settings.TIMEFRAMES


# --- Asosiy buyruqlar ---

@router.message(CommandStart())
async def cmd_start(message: Message):
    get_settings(message.from_user.id)
    text = (
        "👋 <b>XAUUSD (Oltin) tahlil va signal botiga xush kelibsiz!</b>\n\n"
        "Bot bozorni tahlil qilib, <b>kirish, Stop Loss, Take Profit va lot</b> bilan signal beradi. "
        "Zdelkani o'zingiz <b>Mobile MT5</b> da ochasiz.\n\n"
        "✨ <b>Imkoniyatlar:</b>\n"
        "• 🎯 Signal (BUY/SELL/WAIT) + yuqori timeframe tasdig'i\n"
        "• 📊 Texnik tahlil: EMA, RSI, MACD, ATR, Bollinger, kunlik pivot\n"
        "• 🧠 SMC: Order Block, FVG, BOS\n"
        "• 📰 AQSh yangiliklari va xavf filtri\n"
        "• 🛡 Lot kalkulyatori\n\n"
        "⚙️ <b>Muhim:</b> narx manbasi broker narxidan farq qilishi mumkin. MT5 dagi XAUUSD narxini "
        "<code>/price 4155.30</code> ko'rinishida yuboring - barcha daraja va signallar brokeringizga moslanadi.\n\n"
        "Pastdagi tugmalardan foydalaning 👇"
    )
    await message.answer(text, reply_markup=get_main_keyboard())


@router.message(Command("help"))
@router.message(F.text == "⚙️ Sozlamalar & Yordam")
async def cmd_help(message: Message):
    cfg = get_settings(message.from_user.id)
    offset = cfg["price_offset"]
    offset_txt = f"{offset:+.2f}$" if offset else "o'rnatilmagan"
    text = (
        "⚙️ <b>SOZLAMALAR VA YORDAM</b>\n\n"
        f"💰 Depozit: <b>{cfg['balance']}$</b>\n"
        f"🛡 Risk: <b>{cfg['risk_percent']}%</b>\n"
        f"⏱ Timeframe: <b>{cfg['timeframe'].upper()}</b>\n"
        f"🔧 Broker narx farqi: <b>{offset_txt}</b>\n\n"
        "<b>Buyruqlar:</b>\n"
        "/signal - signal\n/analysis - texnik tahlil\n/smc - SMC zonalari\n"
        "/news - yangiliklar\n/calc - lot kalkulyatori\n"
        "/stats - haqiqiy natijalar (Win Rate, Profit Factor)\n"
        "/backtest - tezkor strategiya testi\n"
        "/scalp - ⚡ M1 skalping <i>(eksperimental/demo)</i>\n"
        "/price &lt;narx&gt; - MT5 narxiga moslash (<code>/price reset</code> - bekor qilish)\n\n"
        "⏸ <b>Seans:</b> signallar faqat <b>London/Nyu-York</b> (08:00–22:00 UTC) da beriladi "
        "(kechasi likvidlik past, spread keng).\n\n"
        "📱 <b>MT5 da zdelka:</b>\n"
        "1. Signal keldi - kirish, SL, TP va lotni ko'ring.\n"
        "2. MT5 da XAUUSD > yangi order, lotni yozing.\n"
        "3. SL va TP ni kiriting, BUY/SELL bosing.\n"
        "4. Signal amal qilish vaqti tugagan bo'lsa - yangisini oling.\n"
        "5. «✅ Bitim ochildi (Kuzatish)» tugmasini bosing - bot natijani o'zi kuzatadi (/stats)."
    )
    await message.answer(text)


@router.message(Command("price"))
async def cmd_price(message: Message, command: CommandObject):
    user_id = message.from_user.id
    arg = (command.args or "").strip().replace(",", ".")
    cfg = get_settings(user_id)

    if not arg:
        await message.answer(
            f"🔧 Hozirgi broker narx farqi: <b>{cfg['price_offset']:+.2f}$</b>\n\n"
            "MT5 dagi XAUUSD narxini yuboring: <code>/price 4155.30</code>\n"
            "Bekor qilish: <code>/price reset</code>"
        )
        return

    if arg.lower() in ("reset", "0"):
        update_settings(user_id, price_offset=0.0)
        await message.answer("✅ Narx farqi bekor qilindi.")
        return

    try:
        broker_price = float(arg)
    except ValueError:
        await message.answer("❌ Narx noto'g'ri. Misol: <code>/price 4155.30</code>")
        return
    if not PRICE_SANITY[0] < broker_price < PRICE_SANITY[1]:
        await message.answer("❌ Narx oltin uchun real emas. MT5 dagi XAUUSD narxini yuboring.")
        return

    try:
        feed_price = await asyncio.to_thread(market_service.get_live_price)
    except MarketDataError:
        await message.answer(ERR_MARKET)
        return

    offset = round(broker_price - feed_price, 2)
    if abs(offset) > MAX_OFFSET:
        await message.answer(f"❌ Farq juda katta ({offset:+.2f}$). Narxni tekshirib qayta yuboring.")
        return

    update_settings(user_id, price_offset=offset)
    await message.answer(
        f"✅ Moslandi! Manba: <code>{feed_price:.2f}$</code>, sizning broker: <code>{broker_price:.2f}$</code>\n"
        f"Farq: <b>{offset:+.2f}$</b> - endi barcha narxlar brokeringizga mos ko'rsatiladi.\n"
        "<i>Farq vaqt o'tishi bilan o'zgaradi - vaqti-vaqti bilan yangilab turing.</i>"
    )


# --- Signal ---

@router.message(F.text == "🎯 Aniq Savdo Signali")
@router.message(Command("signal"))
async def cmd_signal(message: Message):
    cfg = get_settings(message.from_user.id)
    tf = cfg["timeframe"]
    status = await message.answer("🔄 <i>Bozor va yangiliklar tahlil qilinmoqda...</i>")
    try:
        text, signal_id, _ = await asyncio.to_thread(views.signal_text, cfg, tf, message.from_user.id)
        if not is_market_open():
            text = "⚠️ <b>DIQQAT: Hozir MT5 (Forex) bozori yopiq (dam olish kuni). Bozor Dushanba kuni 03:00 da ochiladi.</b>\n\n" + text
        kb = get_signal_inline_kb(tf, signal_id)
        await _safe_edit(status, text, kb)
    except MarketDataError:
        await _safe_edit(status, ERR_MARKET)
    except Exception:
        log.exception("Handlerda kutilmagan xato")
        await _safe_edit(status, ERR_GENERIC)


@router.callback_query(F.data.startswith("sig_tf:"))
@router.callback_query(F.data.startswith("sig_refresh:"))
async def cb_signal(callback: CallbackQuery):
    tf = callback.data.split(":")[1]
    if not _valid_tf(tf):
        await callback.answer("Noto'g'ri timeframe", show_alert=True)
        return
    cfg = update_settings(callback.from_user.id, timeframe=tf)
    await callback.answer(f"{tf.upper()} tahlil qilinmoqda...")
    try:
        text, signal_id, _ = await asyncio.to_thread(views.signal_text, cfg, tf, callback.from_user.id)
        if not is_market_open():
            text = "⚠️ <b>DIQQAT: Hozir MT5 (Forex) bozori yopiq (dam olish kuni). Bozor Dushanba kuni 03:00 da ochiladi.</b>\n\n" + text
        kb = get_signal_inline_kb(tf, signal_id)
        await _safe_edit(callback.message, text, kb)
    except MarketDataError:
        await _safe_edit(callback.message, ERR_MARKET)
    except Exception:
        log.exception("Handlerda kutilmagan xato")
        await _safe_edit(callback.message, ERR_GENERIC)


@router.callback_query(F.data.startswith("trade_opened:"))
async def cb_trade_opened(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 2 or not parts[1].isdigit():
        await callback.answer("Noto'g'ri signal ma'lumoti", show_alert=True)
        return

    signal_id = int(parts[1])
    sig = await asyncio.to_thread(journal_service.get_signal, signal_id)
    if not sig:
        await callback.answer("❌ Signal topilmadi yoki eskirgan.", show_alert=True)
        return
    if sig.get("user_id") and sig["user_id"] != callback.from_user.id:
        await callback.answer("❌ Bu signal sizga tegishli emas!", show_alert=True)
        return
    if sig.get("result") != "PENDING":
        await callback.answer("ℹ️ Bu bitim allaqachon ochilgan yoki yakunlangan.", show_alert=True)
        return

    success = await asyncio.to_thread(journal_service.mark_trade_open, signal_id, callback.from_user.id)
    if not success:
        await callback.answer("❌ Bitimni ochish imkoni bo'lmadi.", show_alert=True)
        return

    await callback.answer("✅ Bitim jurnalga ochiq (OPEN) sifatida qayd etildi! Bot uni kuzatib boradi.", show_alert=True)
    
    # Tugmani yo'qotish uchun klaviaturani qayta yuklaymiz (signal_id=0 bilan u tugma chiqmaydi)
    if callback.message.reply_markup:
        # Eski timeframe ni topib, klaviaturani usiz qayta yaratamiz (agar topolmasa default "15m")
        current_tf = "15m"
        for row in callback.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("sig_tf:"):
                    if "✅" in btn.text:
                        current_tf = btn.callback_data.split(":")[1]
        
        new_kb = get_signal_inline_kb(current_tf, signal_id=0)
        await callback.message.edit_reply_markup(reply_markup=new_kb)


# --- Texnik tahlil ---

@router.message(F.text == "📊 XAUUSD Bozor Tahlili")
@router.message(Command("analysis"))
async def cmd_analysis(message: Message):
    cfg = get_settings(message.from_user.id)
    tf = cfg["timeframe"]
    await _answer_view(
        message, "📊 <i>Indikatorlar hisoblanmoqda...</i>",
        views.analysis_text, (cfg, tf), lambda: get_analysis_inline_kb(tf),
    )


@router.callback_query(F.data.startswith("ana_tf:"))
@router.callback_query(F.data.startswith("ana_refresh:"))
async def cb_analysis(callback: CallbackQuery):
    tf = callback.data.split(":")[1]
    if not _valid_tf(tf):
        await callback.answer("Noto'g'ri timeframe", show_alert=True)
        return
    cfg = update_settings(callback.from_user.id, timeframe=tf)
    await callback.answer(f"{tf.upper()} yangilanmoqda...")
    await _edit_view(callback, views.analysis_text, (cfg, tf), lambda: get_analysis_inline_kb(tf))


# --- SMC ---

@router.message(F.text == "🧠 SMC & Order Block")
@router.message(Command("smc"))
async def cmd_smc(message: Message):
    cfg = get_settings(message.from_user.id)
    await _answer_view(
        message, "🧠 <i>SMC zonalari qidirilmoqda...</i>",
        views.smc_text, (cfg, cfg["timeframe"]),
    )


# --- M1 Skalping (Eksperimental) ---

@router.message(F.text == "⚡ M1 Skalping")
@router.message(Command("scalp"))
async def cmd_scalp(message: Message):
    cfg = get_settings(message.from_user.id)
    await _answer_view(
        message, "⚡ <i>M1 skalping tahlil qilinmoqda...</i>",
        views.scalp_text, (cfg,),
    )


# --- Yangiliklar ---

@router.message(F.text == "📰 Dunyo Yangiliklari")
@router.message(Command("news"))
async def cmd_news(message: Message):
    await _answer_view(
        message, "📰 <i>Iqtisodiy taqvim tekshirilmoqda...</i>",
        news_service.format_news_summary_uz, (),
    )


# --- Statistika ---

@router.message(F.text == "📊 Statistika")
@router.message(Command("stats"))
async def cmd_stats(message: Message):
    await _answer_view(
        message, "📊 <i>Natijalar hisoblanmoqda...</i>",
        views.performance_text, (message.from_user.id,),
    )


@router.message(Command("backtest"))
async def cmd_backtest(message: Message, command: CommandObject):
    tf = command.args.strip().lower() if command.args else settings.DEFAULT_TIMEFRAME
    if tf not in settings.TIMEFRAMES:
        tf = settings.DEFAULT_TIMEFRAME
        
    status = await message.answer(f"⏳ <b>XAUUSD ({tf.upper()})</b> bo'yicha tarixiy shamchalar tahlil qilinmoqda...")
    
    def _run():
        try:
            df = market_service.get_candles(tf, limit=250)
            res = backtester_service.run_backtest(df, timeframe=tf)
            return backtester_service.format_backtest_report(res, tf)
        except Exception:
            log.exception("Backtest bajarishda xatolik")
            return "❌ Backtestni amalga oshirib bo'lmadi. Birozdan so'ng qayta urinib ko'ring."
            
    report = await asyncio.to_thread(_run)
    await _safe_edit(status, report)


@router.message(F.text == "🛡 Lot Kalkulyatori")
@router.message(Command("calc"))
async def cmd_calc(message: Message):
    cfg = get_settings(message.from_user.id)
    await _answer_view(
        message, "🛡 <i>Hisoblanmoqda...</i>", views.calc_text, (cfg,), get_calc_keyboard,
    )


@router.callback_query(F.data == "open_calc")
async def cb_open_calc(callback: CallbackQuery):
    cfg = get_settings(callback.from_user.id)
    await callback.answer()
    text, ok = await _build(views.calc_text, cfg)
    await callback.message.answer(text, reply_markup=get_calc_keyboard() if ok else None)


@router.callback_query(F.data.startswith("calc_dep:"))
async def cb_calc_dep(callback: CallbackQuery):
    try:
        deposit = float(callback.data.split(":")[1])
    except ValueError:
        await callback.answer("Noto'g'ri qiymat", show_alert=True)
        return
    if deposit not in ALLOWED_DEPOSITS:
        await callback.answer("Ruxsat etilmagan depozit qiymati", show_alert=True)
        return
    cfg = update_settings(callback.from_user.id, balance=deposit)
    await callback.answer(f"Depozit: {int(deposit)}$")
    await _edit_view(callback, views.calc_text, (cfg,), get_calc_keyboard)


@router.callback_query(F.data.startswith("calc_risk:"))
async def cb_calc_risk(callback: CallbackQuery):
    try:
        risk = float(callback.data.split(":")[1])
    except ValueError:
        await callback.answer("Noto'g'ri qiymat", show_alert=True)
        return
    if risk not in ALLOWED_RISKS:
        await callback.answer("Ruxsat etilmagan risk qiymati", show_alert=True)
        return
    cfg = update_settings(callback.from_user.id, risk_percent=risk)
    await callback.answer(f"Risk: {risk}%")
    await _edit_view(callback, views.calc_text, (cfg,), get_calc_keyboard)
