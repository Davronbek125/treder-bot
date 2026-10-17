"""
Signal mantiqini tarixiy ma'lumotda sinash (walk-forward backtest).

Ishlatish:
    python scripts/backtest.py --tf 1h --candles 8760
    python scripts/backtest.py --tf 15m --candles 35040 --spreads 0.20,0.35,0.50,0.80
    python scripts/backtest.py --tf 1h --candles 8760 --no-session

MUHIM (jonli tizim bilan aynan moslik):
- Har bir qaror nuqtasida FAQAT YOPILGAN shamchalar ishlatiladi (chala shamcha
  tashlab yuboriladi) - bu jonli `get_candles` xatti-harakati bilan bir xil.
- Sozlash timeframe'i va HTF (yuqori timeframe) alohida 250 shamchadan tahlil qilinadi.
- Look-ahead YO'Q: i shamchadan keyin qaror qabul qilinadi, SL/TP i+1 dan boshlab tekshiriladi.
- Spread: SL/TP xom close dan hisoblanadi, kirish esa spread miqdorida yomonlashtiriladi.
- Yangiliklar filtri tarixda qo'llanmaydi.

Natijalar o'tmishni ko'rsatadi, kelajakka kafolat EMAS.
"""
import argparse
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from config import settings  # noqa: E402
from services.market_data import fetch_history  # noqa: E402
from services.signal_generator import HTF_MAP, evaluate  # noqa: E402
from services.smc_analysis import smc_service  # noqa: E402
from services.technical_analysis import technical_service  # noqa: E402

BARS = 250            # Jonli tizim ham aynan 250 shamcha tahlil qiladi
MAX_HOLD_HOURS = 24   # Vaqt bo'yicha majburiy chiqish
DEFAULT_SPREADS = (0.20, 0.35, 0.50, 0.80)
TF_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
RESAMPLE = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}
NEWS_SAFE = {"safe_to_trade": True, "status_text": "SAFE", "recommendation": "", "calendar_ok": True}


def in_session(hour: int, session_start: Optional[int], session_end: Optional[int]) -> bool:
    if session_start is None or session_end is None:
        return True
    if session_start <= session_end:
        return session_start <= hour < session_end
    return hour >= session_start or hour < session_end


def simulate(df: pd.DataFrame, start: int, action: str, sl: float, tp1: float, spread: float, max_bars: int):
    """Konservativ: bitta shamchada ham SL, ham TP1 tegsa - SL hisoblanadi. Spread hisobga olingan."""
    last = min(start + max_bars, len(df) - 1)
    entry = df["close"].iloc[start]
    entry = entry + spread if action == "BUY" else entry - spread
    risk = abs(entry - sl)
    if risk <= 0:
        return -1.0, "SL", start

    for j in range(start + 1, last + 1):
        high, low = float(df["high"].iloc[j]), float(df["low"].iloc[j])
        hit_sl = low <= sl if action == "BUY" else high >= sl
        hit_tp = high >= tp1 if action == "BUY" else low <= tp1
        if hit_sl:
            return -1.0, "SL", j
        if hit_tp:
            pnl = (tp1 - entry) if action == "BUY" else (entry - tp1)
            return pnl / risk, "TP", j

    close = float(df["close"].iloc[last])
    pnl = (close - entry) if action == "BUY" else (entry - close)
    return pnl / risk, "TIME", last


def collect_candidates(df: pd.DataFrame, setup_tf: str, session_start, session_end) -> List[dict]:
    """
    Barcha shartli signallarni yig'adi (yopilishdan qat'i nazar).

    Jonli tizim bilan mos: sozlash TF 250 yopilgan shamcha, HTF 250 yopilgan shamcha.
    """
    htf_tf = HTF_MAP.get(setup_tf)
    htf_counts = None
    htf_bars = None
    if htf_tf:
        rule = RESAMPLE[htf_tf]
        htf_bars = (
            df.set_index("timestamp").resample(rule)
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna()
        )
        htf_times = htf_bars.index.values
        floor_htf = df["timestamp"].dt.floor(rule).to_numpy()
        # Yopilgan HTF shamchalar: joriy (chala) HTF shamchadan oldingilar
        htf_counts = np.searchsorted(htf_times, floor_htf, side="left")

    hours = df["timestamp"].dt.hour.to_numpy()
    closes = df["close"].to_numpy()
    candidates: List[dict] = []

    for i in range(BARS, len(df) - 1):
        if not in_session(int(hours[i]), session_start, session_end):
            continue

        setup_slice = df.iloc[i - BARS + 1: i + 1].reset_index(drop=True)
        tech = technical_service.analyze(setup_slice)
        smc = smc_service.analyze(setup_slice)

        # Tezlik: HTF trendi FAQAT veto sifatida ishlatiladi (ovoz emas). Shuning uchun
        # avval HTFsiz tekshiramiz; agar natija WAIT bo'lsa, HTF tahlili umuman kerak emas.
        sig = evaluate(tech, smc, None, NEWS_SAFE, float(closes[i]), setup_tf)
        if sig["action"] == "WAIT":
            continue

        htf_trend = None
        if htf_counts is not None:
            k = int(htf_counts[i])
            if k >= 200:
                htf_slice = htf_bars.iloc[max(0, k - BARS):k].reset_index(drop=True)
                htf_trend = technical_service.analyze(htf_slice)["trend"]
                sig = evaluate(tech, smc, htf_trend, NEWS_SAFE, float(closes[i]), setup_tf)

        if sig["action"] in ("BUY", "SELL") and sig["tps"]:
            candidates.append({
                "idx": i,
                "action": sig["action"],
                "sl": sig["stop_loss"],
                "tp1": sig["tps"][0],
                "strength": sig["strength"],
                "time": df["timestamp"].iloc[i],
            })
    return candidates


def simulate_spread(df: pd.DataFrame, candidates: List[dict], spread: float, max_bars: int) -> pd.DataFrame:
    """Kandidatlarni ketma-ket sinaydi; bitta bitim ochiq bo'lganda yangisini olmaydi."""
    results: List[dict] = []
    next_allowed = 0
    for c in candidates:
        if c["idx"] < next_allowed:
            continue
        r, reason, exit_idx = simulate(df, c["idx"], c["action"], c["sl"], c["tp1"], spread, max_bars)
        results.append({
            "action": c["action"],
            "strength": c["strength"],
            "r": r,
            "reason": reason,
            "time": c["time"],
        })
        next_allowed = exit_idx + 1
    return pd.DataFrame(results)


def print_stats(title: str, res: pd.DataFrame) -> None:
    if res.empty:
        print(f"\n[{title}] Signallar yo'q.")
        return
    wins, losses = res[res["r"] > 0], res[res["r"] <= 0]
    gross_loss = abs(losses["r"].sum())
    gross_win = wins["r"].sum()
    pf = f"{gross_win / gross_loss:.2f}" if gross_loss else "cheksiz"
    tp = int((res["reason"] == "TP").sum())
    sl = int((res["reason"] == "SL").sum())
    tm = int((res["reason"] == "TIME").sum())
    print(f"\n--- {title} ---")
    print(f"Signallar soni:       {len(res)} (BUY {int((res.action == 'BUY').sum())}, SELL {int((res.action == 'SELL').sum())})")
    print(f"G'alaba (TP1) ulushi: {len(wins) / len(res):.1%}")
    print(f"Chiqish:              TP={tp} ({tp/len(res):.0%})  SL={sl} ({sl/len(res):.0%})  TIME={tm} ({tm/len(res):.0%})")
    print(f"O'rtacha natija:      {res['r'].mean():+.2f} R / bitim")
    print(f"Jami foyda/zarar:     {res['r'].sum():+.2f} R")
    print(f"Profit factor:        {pf}")


def monthly_breakdown(res: pd.DataFrame) -> None:
    if res.empty:
        return
    print("\n--- Oylik barqarorlik (R) ---")
    tmp = res.copy()
    tmp["month"] = pd.to_datetime(tmp["time"]).dt.to_period("M")
    for month, grp in tmp.groupby("month"):
        w = grp[grp["r"] > 0]
        print(f"  {month}: n={len(grp):>4}  win={len(w) / len(grp):>5.1%}  total={grp['r'].sum():>+7.1f}R")


def run(setup_tf: str, candles: int, spreads: tuple, session_start, session_end, refresh: bool = False) -> None:
    print(f"Ma'lumot yuklanmoqda: {candles} ta {setup_tf} shamcha...")
    df = fetch_history(setup_tf, candles, refresh=refresh)
    df = df.reset_index(drop=True)
    print(f"Davr: {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]} ({len(df)} shamcha)")

    htf = HTF_MAP.get(setup_tf)
    session_txt = "o'chirilgan" if session_start is None else f"{session_start:02d}:00-{session_end:02d}:00 UTC"
    max_bars = max(1, MAX_HOLD_HOURS * 60 // TF_MINUTES[setup_tf])
    print(f"Sozlamalar: setup={setup_tf}, HTF={htf}, {BARS} shamcha, maks. ushlash={MAX_HOLD_HOURS}h, seans: {session_txt}\n")

    print("Signallar yig'ilmoqda...")
    candidates = collect_candidates(df, setup_tf, session_start, session_end)
    print(f"Shartli signallar: {len(candidates)} (BUY {sum(c['action'] == 'BUY' for c in candidates)}, "
          f"SELL {sum(c['action'] == 'SELL' for c in candidates)})")

    for spread in spreads:
        res = simulate_spread(df, candidates, spread, max_bars)
        if res.empty:
            print(f"\n[spread={spread:.2f}$] Signallar yo'q.")
            continue
        split_idx = int(len(res) * 0.7)
        print_stats(f"spread={spread:.2f}$  UMUMIY", res)
        print_stats("   In-Sample 70%", res.iloc[:split_idx])
        print_stats("   Out-of-Sample 30%", res.iloc[split_idx:])

    ref = 0.50 if 0.50 in spreads else spreads[0]
    monthly_breakdown(simulate_spread(df, candidates, ref, max_bars))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XAUUSD signal backtest (jonli tizim bilan mos)")
    parser.add_argument("--tf", default=settings.DEFAULT_TIMEFRAME, choices=["15m", "1h", "4h"])
    parser.add_argument("--candles", type=int, default=8760, help="1h uchun 8760 = ~1 yil")
    parser.add_argument("--spread", type=float, default=None, help="Bitta spread (USD)")
    parser.add_argument("--spreads", default=None, help="Vergul bilan: 0.20,0.35,0.50,0.80")
    parser.add_argument("--session-start", type=int, default=settings.SESSION_START_HOUR)
    parser.add_argument("--session-end", type=int, default=settings.SESSION_END_HOUR)
    parser.add_argument("--no-session", action="store_true", help="Seans filtrini o'chirish")
    parser.add_argument("--refresh", action="store_true", help="Keshni e'tiborsiz qoldirib qayta yuklash")
    args = parser.parse_args()

    if args.spread is not None:
        chosen = (args.spread,)
    elif args.spreads:
        chosen = tuple(float(x) for x in args.spreads.split(","))
    else:
        chosen = DEFAULT_SPREADS

    run(
        args.tf, args.candles, chosen,
        None if args.no_session else args.session_start,
        None if args.no_session else args.session_end,
        refresh=args.refresh,
    )
