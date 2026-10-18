from datetime import datetime, timedelta
from typing import Any, Dict
from zoneinfo import ZoneInfo

from config import settings
from services.m1_scalper import hold_text

LINE = "━━━━━━━━━━━━━━━━━━━━━━"
DISCLAIMER = (
    "⚠️ <i>Bu moliyaviy maslahat emas va foyda kafolati yo'q. "
    "Har doim Stop Loss ishlating va risk-menejmentga rioya qiling.</i>"
)
EXPECTANCY_NOTE = (
    "📉 <b>HALOL ESLATMA:</b> bu signal <b>kafolat emas</b>. ~1.4 yillik testda (5 bo'lakning "
    "hammasida musbat) tizim o'rtacha musbat: g'alaba ~50%, PF ~1.55, o'rtacha +0.12R/bitim. "
    "Biroq bitimlarning ~75% <b>24 soatlik vaqt chegarasida</b> yopiladi (trend davomida foyda, "
    "teskari davrda zarar) — ya'ni foyda <b>trend davrlariga bog'liq</b>. "
    "Real natijani /stats orqali kuzatib boring."
)


def _usd(value: float) -> str:
    return f"{value:.2f}$"


def _shift(value: float, offset: float) -> float:
    return round(value + offset, 2)


def format_signal(sig: Dict[str, Any]) -> str:
    action = sig["action"]
    badge = {
        "BUY": "🟢 <b>BUY (XARID)</b>",
        "SELL": "🔴 <b>SELL (SOTISH)</b>",
    }.get(action, "⏳ <b>WAIT (KUTISH)</b>")

    gen: datetime = sig["generated_at"]
    tz = ZoneInfo(settings.TIMEZONE)
    # signal_generator vaqtni settings.TIMEZONE da beradi; soatsiz (naive) bo'lsa o'sha zonada deb olamiz
    gen = gen.replace(tzinfo=tz) if gen.tzinfo is None else gen.astimezone(tz)
    valid_until = gen + timedelta(minutes=sig["valid_minutes"])
    news_icon = "🟢" if sig["news_safe"] else "🔴"

    strength_pct = sig.get("strength", 0)
    grade = "🅰️ KUCHLI" if strength_pct >= 90 else "🅱️ YAXSHI" if strength_pct >= 75 else "🅲 O'RTACHA" if strength_pct >= 60 else "🔴 PAST"

    lines = [
        LINE,
        f"🎯 <b>XAUUSD SAVDO SIGNALI</b> | <i>TF: {sig['timeframe'].upper()}</i>",
        LINE,
        f"⚡ <b>Harakat:</b> {badge}",
        f"📊 <b>Signal sifati:</b> <code>{strength_pct}%</code> <i>({grade})</i>",
    ]
    if sig["htf_timeframe"]:
        trend = (sig["htf_trend"] or "noma'lum").split(" ")[0]
        lines.append(f"🔭 <b>{sig['htf_timeframe'].upper()} trend:</b> {trend}")
    lines.extend([
        f"📰 <b>Yangiliklar:</b> {news_icon} {sig['news_status']}",
        f"💵 <b>Joriy narx:</b> <code>{_usd(sig['current_price'])}</code>",
        f"🕒 <b>Vaqt:</b> {gen:%H:%M} (amal qiladi: {valid_until:%H:%M} gacha) | Seans: London/NY",
        "",
    ])

    if not sig["news_calendar_ok"]:
        lines.append("⚪ <i>Iqtisodiy taqvim olinmadi - yangiliklar tekshirilmagan!</i>")
    if not sig["offset"]:
        lines.append("ℹ️ <i>Narx manbasi broker narxidan farq qilishi mumkin. "
                     "Moslash: /price &lt;MT5 dagi narx&gt;</i>")
    if not sig["news_calendar_ok"] or not sig["offset"]:
        lines.append("")

    if action in ("BUY", "SELL"):
        r = sig["risk"]
        tp1, tp2, tp3 = sig["tps"]
        lines.extend([
            "📍 <b>ZDELKA SOZLAMALARI:</b>",
            f"• Kirish: <code>{_usd(sig['entry_price'])}</code>",
            f"• Stop Loss: <code>{_usd(sig['stop_loss'])}</code> (masofa {_usd(r['sl_distance'])})",
            f"• TP1: <code>{_usd(tp1)}</code> [RR {r['rr_tp1']}]",
            f"• TP2: <code>{_usd(tp2)}</code> [RR {r['rr_tp2']}]",
            f"• TP3: <code>{_usd(tp3)}</code> [RR {r['rr_tp3']}]",
            "",
            "🛡 <b>RISK VA LOT:</b>",
            f"• Depozit: <b>{r['balance']}$</b> | Risk: <b>{r['risk_percent']}%</b>",
            f"• Tavsiya lot: <code>{r['lot_size']}</code>",
            f"• SL da zarar: <b>-{_usd(r['actual_sl_loss'])}</b>",
            f"• TP1 da foyda: <b>+{_usd(r['tp1_profit'])}</b>",
            f"• TP2 da foyda: <b>+{_usd(r['tp2_profit'])}</b>",
            f"• TP3 da foyda: <b>+{_usd(r['tp3_profit'])}</b>",
        ])
        if r["min_lot_exceeds_risk"]:
            lines.append(_risk_warning(r))
        lines.append("💡 <i>TP1 ga yetganda yarmini yoping, SL ni O'ZGARTIRMANG (BE ga surmang) — qolgani TP2/TP3 ni nishonga oladi.</i>")
        lines.append("")
        
        if "votes" in sig:
            lines.append("🗳 <b>STRATEGIYALAR OVOZI:</b>")
            for v in sig["votes"]:
                icon = "🟢" if v["vote"] == 1 else "🔴" if v["vote"] == -1 else "⚪"
                lines.append(f"{icon} <b>{v['name']}</b>: <i>{v['reason']}</i>")
            lines.append("")

        if sig["reasons"]:
            lines.append("🧠 <b>QO'SHIMCHA IZOH:</b>")
            lines.extend(f"• {reason}" for reason in sig["reasons"])
    else:
        lines.extend([
            f"📈 Xaridor ovozi: <code>{sig.get('buy_votes', 0)}/3</code>",
            f"📉 Sotuvchi ovozi: <code>{sig.get('sell_votes', 0)}/3</code>",
            "",
        ])
        if sig["reasons"]:
            lines.append("🧠 <b>SABAB:</b>")
            lines.extend(f"• {reason}" for reason in sig["reasons"])

    if action in ("BUY", "SELL"):
        lines.extend(["", EXPECTANCY_NOTE])

    lines.extend(["", DISCLAIMER, LINE])
    return "\n".join(lines)


def format_analysis(tech: Dict[str, Any], timeframe: str, offset: float = 0.0) -> str:
    p = lambda v: _usd(_shift(v, offset))  # noqa: E731
    pv = tech["pivots"]
    ema200_note = "" if tech.get("ema200_reliable") else " (taxminiy)"
    
    st_status = "🟢 O'sish" if tech.get('supertrend') == 1 else "🔴 Pasayish" if tech.get('supertrend') == -1 else "⚪ Neytral"

    return "\n".join([
        LINE,
        f"📊 <b>XAUUSD TEXNIK TAHLIL</b> | <i>TF: {timeframe.upper()}</i>",
        LINE,
        f"💵 <b>Narx:</b> <code>{p(tech['current_price'])}</code>",
        f"📈 <b>Trend:</b> <b>{tech['trend']}</b>",
        "",
        "📐 <b>TREND FILTRLARI:</b>",
        f"• EMA 20: <code>{p(tech['ema20'])}</code>",
        f"• EMA 50: <code>{p(tech['ema50'])}</code>",
        f"• EMA 200 (Asosiy qarshilik): <code>{p(tech['ema200'])}</code>{ema200_note}",
        "",
        "⚡ <b>ASOSIY INDIKATORLAR:</b>",
        f"• RSI (14) Pullback: <code>{tech['rsi']:.1f}</code>",
        f"• ADX (Bozor Rejimi): <code>{tech.get('adx', 0):.1f}</code>",
        f"• Supertrend (Yo'nalish): <b>{st_status}</b>",
        "",
        "🌊 <b>VOLATILLIK:</b>",
        f"• ATR (14) Stop Loss uchun: <code>{_usd(tech['atr'])}</code>",
        LINE,
    ])


def _zone(zone: Dict[str, Any], offset: float) -> str:
    return f"<code>{_usd(_shift(zone['bottom'], offset))} - {_usd(_shift(zone['top'], offset))}</code>"


def format_smc(smc: Dict[str, Any], price: float, timeframe: str, offset: float = 0.0) -> str:
    lines = [
        LINE,
        f"🧠 <b>SMART MONEY (SMC) TAHLILI</b> | <i>TF: {timeframe.upper()}</i>",
        LINE,
        f"💵 <b>Narx:</b> <code>{_usd(_shift(price, offset))}</code>",
        f"🏛 <b>Struktura:</b> <b>{smc['structure']}</b>",
        "",
    ]
    bull_ob, bear_ob = smc["nearest_bullish_ob"], smc["nearest_bearish_ob"]
    lines.append(f"🟢 <b>Xaridor OB:</b> {_zone(bull_ob, offset)} ({bull_ob['strength']})" if bull_ob
                 else "🟢 <b>Xaridor OB:</b> yaqin atrofda yo'q")
    lines.append(f"🔴 <b>Sotuvchi OB:</b> {_zone(bear_ob, offset)} ({bear_ob['strength']})" if bear_ob
                 else "🔴 <b>Sotuvchi OB:</b> yaqin atrofda yo'q")
    lines.append("")

    if smc["active_bullish_fvg"]:
        fvg = smc["active_bullish_fvg"][-1]
        lines.append(f"📦 <b>Bullish FVG:</b> {_zone(fvg, offset)} (gap {_usd(fvg['gap'])})")
    if smc["active_bearish_fvg"]:
        fvg = smc["active_bearish_fvg"][-1]
        lines.append(f"📦 <b>Bearish FVG:</b> {_zone(fvg, offset)} (gap {_usd(fvg['gap'])})")
    if smc["recent_highs"]:
        lines.append("🔺 <b>Swing High:</b> " + ", ".join(_usd(_shift(h, offset)) for h in smc["recent_highs"]))
    if smc["recent_lows"]:
        lines.append("🔻 <b>Swing Low:</b> " + ", ".join(_usd(_shift(l, offset)) for l in smc["recent_lows"]))

    lines.extend([
        "",
        "💡 <i>Narx OB yoki FVG zonasiga qaytganda (pullback) kirish ehtimoli yuqoriroq.</i>",
        LINE,
    ])
    return "\n".join(lines)


SCALP_WARNING = (
    "🧪 <b>Diqqat — ustunlik yupqa:</b>\n"
    "<i>1 yillik backtest: spread ≤0.40$ da 5 bo'lakning hammasi musbat, PF ~1.1. "
    "Spread 0.80$ ga yaqinlashsa ustunlik yo'qoladi — brokeringiz spreadini tekshiring. "
    "Kafolat yo'q.</i>"
)


def _risk_warning(r: Dict[str, Any]) -> str:
    """0.01 lot belgilangan riskdan katta bo'lsa — aniq foiz bilan qattiq ogohlantiradi."""
    loss = float(r.get("actual_sl_loss") or 0.0)
    balance = float(r.get("balance") or 0.0)
    pct = (loss / balance * 100.0) if balance > 0 else 0.0
    return (
        "🚨 <b>DIQQAT: 0.01 LOT RISKDAN ANCHA KATTA!</b>\n"
        f"<i>0.01 lot bilan SL da zarar <b>-{_usd(loss)}</b> = depozitning <b>{pct:.1f}%</b> "
        f"(belgilangan risk: {r['risk_percent']}%).\n"
        "Bu bitimni ochish juda xavfli. Depozitni ko'paytiring, aks holda signalni "
        "o'tkazib yuboring.</i>"
    )


def format_scalp_signal(sig: Dict[str, Any]) -> str:
    action = sig["action"]
    badge = {
        "BUY": "🟢 <b>BUY (XARID)</b>",
        "SELL": "🔴 <b>SELL (SOTISH)</b>",
    }.get(action, "⏳ <b>WAIT (KUTISH)</b>")

    gen: datetime = sig["generated_at"]
    tz = ZoneInfo(settings.TIMEZONE)
    gen = gen.replace(tzinfo=tz) if gen.tzinfo is None else gen.astimezone(tz)
    valid_until = gen + timedelta(minutes=sig["valid_minutes"])
    p = sig["params"]

    lines = [
        LINE,
        f"⚡ <b>M1 SKALPING SIGNALI</b> | <i>TF: M1</i> (ushlash maks {hold_text(p.max_bars)})",
        LINE,
        SCALP_WARNING,
        LINE,
        f"⚡ <b>Harakat:</b> {badge}",
        f"💵 <b>Joriy narx:</b> <code>{_usd(sig['current_price'])}</code>",
        f"🔭 <b>M5 trend:</b> {sig['htf_trend']} | 📊 <b>RSI:</b> <code>{sig['rsi']:.1f}</code>",
        f"🌊 <b>ATR:</b> <code>{_usd(sig['atr'])}</code>",
        f"🕒 <b>Vaqt:</b> {gen:%H:%M} (amal qiladi: {valid_until:%H:%M} gacha)",
        "",
    ]

    if action in ("BUY", "SELL"):
        r = sig["risk"]
        lines.extend([
            f"📍 <b>KIRISH ZONASI (tez, {sig['valid_minutes']} daqiqagacha):</b>",
            f"• Kirish: <code>{_usd(sig['entry_price'])}</code>",
            f"• Stop Loss: <code>{_usd(sig['stop_loss'])}</code> (masofa {_usd(r['sl_distance'])})",
            f"• Take Profit: <code>{_usd(sig['tp'])}</code> [RR {r['rr_tp1']}]",
            f"⏱ <b>Chiqish:</b> TP/SL tegmasa, <b>{hold_text(p.max_bars)}dan keyin</b> bozor narxida yoping.",
            "",
            "🛡 <b>RISK VA LOT:</b>",
            f"• Depozit: <b>{r['balance']}$</b> | Risk: <b>{r['risk_percent']}%</b>",
            f"• Tavsiya lot: <code>{r['lot_size']}</code>",
            f"• SL da zarar: <b>-{_usd(r['actual_sl_loss'])}</b>",
            f"• TP da foyda: <b>+{_usd(r['tp1_profit'])}</b>",
        ])
        if r["min_lot_exceeds_risk"]:
            lines.append(_risk_warning(r))
    else:
        lines.append("📈 <i>Hozircha aniq M1 skalping setupi yo'q. Birozdan so'ng qayta urinib ko'ring.</i>")

    if sig["reasons"]:
        lines.extend(["", "🧠 <b>SABAB:</b>"])
        lines.extend(f"• {reason}" for reason in sig["reasons"])

    lines.extend(["", DISCLAIMER, LINE])
    return "\n".join(lines)


def format_calc(cfg: Dict[str, Any], price: float, risk: Dict[str, Any]) -> str:
    lines = [
        "🛡 <b>XAUUSD RISK VA LOT KALKULYATORI</b>",
        "",
        f"💵 <b>Narx:</b> <code>{_usd(price)}</code>",
        f"💰 <b>Depozit:</b> <b>{cfg['balance']}$</b>",
        f"🎯 <b>Risk:</b> <b>{cfg['risk_percent']}%</b>",
        "",
        "📊 <b>5$ li Stop-Loss uchun namuna:</b>",
        f"• Tavsiya lot: <code>{risk['lot_size']}</code>",
        f"• Zarar (SL da): <b>-{_usd(risk['actual_sl_loss'])}</b>",
        f"• TP1 foyda: <b>+{_usd(risk['tp1_profit'])}</b>",
        f"• TP2 foyda: <b>+{_usd(risk['tp2_profit'])}</b>",
        f"• TP3 foyda: <b>+{_usd(risk['tp3_profit'])}</b>",
    ]
    if risk.get("min_lot_exceeds_risk"):
        lines.extend(["", _risk_warning(risk)])
    lines.extend([
        "",
        "Depozit yoki riskni tanlang:",
    ])
    return "\n".join(lines)


def format_performance(stats: Dict[str, Any]) -> str:
    """Foydalanuvchining jonli jurnal statistikasi (halol ko'rsatkich: PF, expectancy)."""
    total = stats.get("total", 0)
    if total == 0:
        return "\n".join([
            LINE,
            "📈 <b>NATIJALARINGIZ (jonli jurnal)</b>",
            LINE,
            "Hozircha yopilgan bitim yo'q.",
            "",
            "Signal kelganda «✅ Bitim ochildi (Kuzatish)» tugmasini bosing — bot narxni kuzatib,",
            "TP/SL ga yetganda natijani avtomatik qayd etadi. Shundan so'ng bu yerda",
            "haqiqiy statistika paydo bo'ladi.",
            "",
            "💡 <i>10-20 ta bitim to'planmaguncha xulosa qilish erta.</i>",
            LINE,
        ])

    pnl = stats.get("total_pnl", 0.0)
    sign = "+" if pnl > 0 else ""
    icon = "💵" if pnl > 0 else "📉" if pnl < 0 else "➖"
    pf = stats.get("profit_factor", 0.0)

    lines = [
        LINE,
        "📈 <b>NATIJALARINGIZ (jonli jurnal)</b>",
        LINE,
        f"📌 Yopilgan bitimlar: <b>{total}</b> <i>(ochiq: {stats.get('open_count', 0)})</i>",
        f"✅ Foyda: <b>{stats.get('wins', 0)}</b> | ❌ Zarar: <b>{stats.get('losses', 0)}</b>",
        f"🎯 G'alaba ulushi: <b>{stats.get('win_rate', 0)}%</b>",
        f"⚖️ Profit Factor: <b>{pf}</b>",
        f"{icon} Umumiy PnL: <b>{sign}{pnl}$</b>",
        f"📈 O'rtacha / bitim: <b>{sign}{stats.get('avg_pnl', 0)}$</b>",
        f"• O'rtacha foyda: <b>+{stats.get('avg_win', 0)}$</b>",
        f"• O'rtacha zarar: <b>{stats.get('avg_loss', 0)}$</b>",
    ]

    by = stats.get("by_action") or {}
    rows = [act for act in ("BUY", "SELL") if (by.get(act) or {}).get("total")]
    if rows:
        lines.append("")
        lines.append("📊 <b>Yo'nalish bo'yicha:</b>")
        for act in rows:
            label = "🟢 BUY" if act == "BUY" else "🔴 SELL"
            row = by[act]
            lines.append(
                f"{label}: n={row['total']} | g'alaba {row.get('win_rate', 0)}% | PnL {row.get('pnl', 0):+.2f}$"
            )

    lines.append("")
    if total < 20:
        lines.append("⚠️ <i>Namuna kichik (20 tadan kam) — ishonchli xulosa uchun yetarli emas.</i>")
    else:
        lines.append("ℹ️ <i>Ochiq bitimlar narx TP/SL ga yetganda avtomatik yopiladi.</i>")
    lines.append(LINE)
    return "\n".join(lines)
