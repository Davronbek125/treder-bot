"""
Signal mantiqini tarixiy ma'lumotda sinash (walk-forward backtest + parametr sweep).

Ishlatish:
    python scripts/backtest.py --tf 1h --candles 12000                 # standart hisobot
    python scripts/backtest.py --tf 1h --candles 12000 --exit both     # tp1 va live exit
    python scripts/backtest.py --tf 1h --candles 12000 --sweep         # filtrlar taqqoslash
    python scripts/backtest.py --tf 1h --candles 12000 --refresh       # keshni yangilash

MUHIM (jonli tizim bilan aynan moslik):
- Har bir qaror nuqtasida FAQAT YOPILGAN shamchalar ishlatiladi (chala shamcha tashlanadi).
- Sozlash TF va HTF (yuqori TF) alohida 250 shamchadan tahlil qilinadi.
- Look-ahead YO'Q: i shamchadan keyin qaror, SL/TP i+1 dan boshlab tekshiriladi.
- Spread: SL/TP xom narxdan hisoblanadi, kirish esa spread miqdorida yomonlashtiriladi.
- Yangiliklar filtri tarixda qo'llanmaydi.

EXIT MODELLARI:
- `tp1`       : TP1 da to'liq yopiladi (konservativ pastki chegara).
- `live`      : ESKI jonli xatti-harakat - TP1 da 50%, SL BE ga suriladi (solishtirish uchun).
- `half_hold` : YANGI jonli xatti-harakat - TP1 da 50%, SL O'ZGARMAYDI, qolgani TP2/TP3/SL/TIME.

SL JOYLASHUVI:
- `--sl-atr K` : SL masofasi kamida K*ATR bo'ladi. Berilmasa — ishlab chiqarishdagi
  AVTOMATIK floor: K ~ 0.82*sqrt(ushlash shamchalari soni), ya'ni 1h/24h -> ~4.0 ATR,
  15m/24h -> ~8.0 ATR. Bu turli taymfreymlarda bir xil dollar SL beradi.
- Kesh toza bo'lishi uchun yig'ish vaqtida floor vaqtincha o'chiriladi (--refresh ham).

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
from services.signal_generator import HTF_MAP, TP_R_MULTIPLES, evaluate, sl_floor_atr  # noqa: E402
from services.smc_analysis import smc_service  # noqa: E402
from services.technical_analysis import technical_service  # noqa: E402

BARS = 250            # Jonli tizim ham aynan 250 shamcha tahlil qiladi
MAX_HOLD_HOURS = 24   # Vaqt bo'yicha majburiy chiqish
DEFAULT_SPREADS = (0.20, 0.35, 0.50, 0.80)
TF_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
RESAMPLE = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}
NEWS_SAFE = {"safe_to_trade": True, "status_text": "SAFE", "recommendation": "", "calendar_ok": True}
# Tanlangan (eng barqaror) konfiguratsiya: TP1 da 50% + SL O'ZGARMAYDI + SL masofasi >= 4.0*ATR (1h)
CHOSEN = {"exit": "half_hold", "sl_atr": 4.0}  # 1h/24h uchun ishlab chiqarish floor i
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"


def in_session(hour: int, session_start: Optional[int], session_end: Optional[int]) -> bool:
    if session_start is None or session_end is None:
        return True
    if session_start <= session_end:
        return session_start <= hour < session_end
    return hour >= session_start or hour < session_end


def simulate(
    df: pd.DataFrame,
    start: int,
    action: str,
    sl: float,
    tp1: float,
    spread: float,
    max_bars: int,
    tp2: Optional[float] = None,
    tp3: Optional[float] = None,
    exit_model: str = "tp1",
):
    """
    Bitta bitimni simulyatsiya qiladi.

    Konservativ: bir shamchada ham SL, ham TP tegsa - SL hisoblanadi.
    `tp2`/`tp3` berilmasa, TP1 dan TP_R_MULTIPLES nisbati bo'yicha tiklanadi.
    Qaytaradi: (R natija, chiqish sababi, chiqish indeksi).
    """
    last = min(start + max_bars, len(df) - 1)
    raw = float(df["close"].iloc[start])
    entry = raw + spread if action == "BUY" else raw - spread
    risk = abs(entry - sl)
    if risk <= 0:
        return -1.0, "SL", start
    sign = 1.0 if action == "BUY" else -1.0

    if tp2 is None or tp3 is None:
        sl_dist = abs(tp1 - raw) / TP_R_MULTIPLES[0]
        tp2 = raw + sign * sl_dist * TP_R_MULTIPLES[1]
        tp3 = raw + sign * sl_dist * TP_R_MULTIPLES[2]

    r1 = sign * (tp1 - entry) / risk
    r2 = sign * (tp2 - entry) / risk
    r3 = sign * (tp3 - entry) / risk

    def hit_stop(level: float, high: float, low: float) -> bool:
        """Stop (SL/BE) narxdan PASTDA (BUY) yoki TEPADA (SELL) - low/high bilan tekshiriladi."""
        return low <= level if action == "BUY" else high >= level

    def hit_target(level: float, high: float, low: float) -> bool:
        """Target (TP) narxdan TEPADA (BUY) yoki PASTDA (SELL) - high/low bilan tekshiriladi."""
        return high >= level if action == "BUY" else low <= level

    if exit_model == "tp1":
        for j in range(start + 1, last + 1):
            high, low = float(df["high"].iloc[j]), float(df["low"].iloc[j])
            if hit_stop(sl, high, low):
                return -1.0, "SL", j
            if hit_target(tp1, high, low):
                return r1, "TP1", j
        close = float(df["close"].iloc[last])
        return sign * (close - entry) / risk, "TIME", last

    if exit_model == "half_hold":
        # TP1 da 50% yopiladi, SL O'ZGARMAYDI, qolgani TP2/TP3/SL/TIME
        realized = 0.0
        hit_tp1 = False
        for j in range(start + 1, last + 1):
            high, low = float(df["high"].iloc[j]), float(df["low"].iloc[j])
            if not hit_tp1:
                if hit_stop(sl, high, low):
                    return -1.0, "SL", j
                if hit_target(tp1, high, low):
                    hit_tp1 = True
                    realized = 0.5 * r1
            else:
                if hit_stop(sl, high, low):
                    return realized - 0.5, "SL2", j
                if hit_target(tp3, high, low):
                    return realized + 0.5 * r3, "TP3", j
                if hit_target(tp2, high, low):
                    return realized + 0.5 * r2, "TP2", j
        close = float(df["close"].iloc[last])
        return realized + 0.5 * sign * (close - entry) / risk, "TIME", last

    # "live": TP1 da 50% + SL BE ga, qolgani TP2/TP3/BE
    realized = 0.0
    hit_tp1 = False
    for j in range(start + 1, last + 1):
        high, low = float(df["high"].iloc[j]), float(df["low"].iloc[j])
        if not hit_tp1:
            if hit_stop(sl, high, low):
                return -1.0, "SL", j
            if hit_target(tp1, high, low):
                hit_tp1 = True
                realized = 0.5 * r1
                if hit_stop(entry, high, low):  # o'sha shamchada BE ga qaytdi
                    return realized, "BE", j
        else:
            if hit_stop(entry, high, low):
                return realized, "BE", j
            if hit_target(tp3, high, low):
                return realized + 0.5 * r3, "TP3", j
            if hit_target(tp2, high, low):
                return realized + 0.5 * r2, "TP2", j

    close = float(df["close"].iloc[last])
    return realized + 0.5 * sign * (close - entry) / risk, "TIME", last


def collect_candidates(df: pd.DataFrame, setup_tf: str, session_start, session_end) -> List[dict]:
    """
    Barcha shartli signallarni (yopilishdan qat'i nazar) yig'adi + har biri uchun
    metama'lumot (ATR, RSI, ADX, strength, TP lar) saqlaydi - keyin filtrlab sweep qilish uchun.

    Jonli tizim bilan mos: sozlash TF 250 yopilgan shamcha, HTF 250 yopilgan shamcha.
    HTF trendi FAQAT veto bo'lgani uchun, avval HTFsiz tekshiriladi (tezlik).
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
        htf_counts = np.searchsorted(htf_times, floor_htf, side="left")

    hours = df["timestamp"].dt.hour.to_numpy()
    closes = df["close"].to_numpy()
    candidates: List[dict] = []

    # Sweep TOZA bo'lishi uchun: ishlab chiqarishdagi SL floor ni vaqtincha o'chiramiz.
    # Aks holda `--sl-atr` parametri hech narsa o'zgartirmaydi (floor allaqachon qo'llangan).
    # SL floor faqat simulyatsiya vaqtida (_transform) qo'llaniladi.
    prev_floor = getattr(settings, "MIN_SL_ATR_MULT", None)
    settings.MIN_SL_ATR_MULT = 0.0

    for i in range(BARS, len(df) - 1):
        if not in_session(int(hours[i]), session_start, session_end):
            continue

        setup_slice = df.iloc[i - BARS + 1: i + 1].reset_index(drop=True)
        tech = technical_service.analyze(setup_slice)
        smc = smc_service.analyze(setup_slice)

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
                "time": df["timestamp"].iloc[i],
                "action": sig["action"],
                "entry": float(closes[i]),
                "sl": float(sig["stop_loss"]),
                "tps": [float(t) for t in sig["tps"]],
                "atr": float(tech.get("atr") or 0.0),
                "rsi": float(tech.get("rsi") or 0.0),
                "adx": float(tech.get("adx") or 0.0),
                "strength": int(sig["strength"]),
                "htf_trend": htf_trend,
            })

    settings.MIN_SL_ATR_MULT = prev_floor
    return candidates


def _candidates_cache_path(setup_tf: str, candles: int, session_start, session_end) -> Path:
    key = f"cand_{setup_tf}_{candles}_{session_start}_{session_end}"
    return CACHE_DIR / f"{key}.pkl"


def get_candidates(df, setup_tf, candles, session_start, session_end, refresh=False) -> List[dict]:
    path = _candidates_cache_path(setup_tf, candles, session_start, session_end)
    if not refresh and path.exists():
        try:
            cands = pd.read_pickle(path)
            print(f"Keshdan yuklandi: {path.name} ({len(cands)} signal)")
            return cands
        except Exception:
            pass
    print("Signallar yig'ilmoqda (H1/H4 tahlili)...")
    cands = collect_candidates(df, setup_tf, session_start, session_end)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        pd.to_pickle(cands, path)
        print(f"Keshga saqlandi: {path.name}")
    except Exception as exc:
        print(f"Keshga saqlanmadi: {exc}")
    return cands


def _transform(c: dict, sl_atr: float, tp_scale: float) -> dict:
    """SL masofasini kamida sl_atr*ATR qiladi va TP larni tp_scale ga ko'paytiradi."""
    if sl_atr <= 0 and tp_scale == 1.0:
        return c
    if c.get("entry") is None or c.get("atr") is None:
        return c
    raw = float(c["entry"])
    sign = 1.0 if c["action"] == "BUY" else -1.0
    sl_dist = abs(raw - float(c["sl"]))
    if sl_atr > 0:
        sl_dist = max(sl_dist, sl_atr * float(c["atr"]))
    sl = raw - sign * sl_dist
    tps = [raw + sign * sl_dist * m * tp_scale for m in TP_R_MULTIPLES]
    return {**c, "sl": sl, "tps": tps}


def filter_candidates(cands: List[dict], min_strength: int = 0, min_atr: float = 0.0) -> List[dict]:
    if min_strength <= 0 and min_atr <= 0:
        return cands
    return [
        c for c in cands
        if c.get("strength", 0) >= min_strength and float(c.get("atr") or 0.0) >= min_atr
    ]


def simulate_spread(
    df: pd.DataFrame,
    candidates: List[dict],
    spread: float,
    max_bars: int,
    exit_model: str = "tp1",
    sl_atr: float = 0.0,
    tp_scale: float = 1.0,
) -> pd.DataFrame:
    """Kandidatlarni ketma-ket sinaydi; bitta bitim ochiq bo'lganda yangisini olmaydi."""
    results: List[dict] = []
    next_allowed = 0
    for c in candidates:
        if c["idx"] < next_allowed:
            continue
        c2 = _transform(c, sl_atr, tp_scale)
        tps = c2.get("tps") or [c2["tp1"]]
        tp1 = tps[0]
        tp2 = tps[1] if len(tps) > 1 else None
        tp3 = tps[2] if len(tps) > 2 else None
        r, reason, exit_idx = simulate(
            df, c2["idx"], c2["action"], c2["sl"], tp1, spread, max_bars, tp2, tp3, exit_model
        )
        results.append({
            "action": c2["action"],
            "strength": c2.get("strength", 0),
            "atr": c2.get("atr", 0.0),
            "r": r,
            "reason": reason,
            "time": c2["time"],
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
    counts = res["reason"].value_counts()
    exits = "  ".join(f"{k}={v} ({v / len(res):.0%})" for k, v in counts.items())
    print(f"\n--- {title} ---")
    print(f"Signallar soni:       {len(res)} (BUY {int((res.action == 'BUY').sum())}, SELL {int((res.action == 'SELL').sum())})")
    print(f"G'alaba ulushi:       {len(wins) / len(res):.1%}")
    print(f"Chiqish:              {exits}")
    print(f"O'rtacha natija:      {res['r'].mean():+.3f} R / bitim")
    print(f"Jami foyda/zarar:     {res['r'].sum():+.2f} R")
    print(f"Profit factor:        {pf}")


def _pf(res: pd.DataFrame) -> float:
    if res.empty:
        return 0.0
    gl = abs(res[res["r"] <= 0]["r"].sum())
    gw = res[res["r"] > 0]["r"].sum()
    return (gw / gl) if gl else float("inf")


def sweep(df, cands, spread, max_bars, configs) -> None:
    """Filtrlar/level/exit o'zgarishlarini IS/OOS + eng yomon bo'lak bo'yicha taqqoslaydi."""
    print(f"\n{'=' * 104}")
    print(f"SWEEP (spread={spread:.2f}$) - faqat OOS va eng yomon bo'lakda ham oqlanadiganini oling")
    print(f"{'=' * 104}")
    print(f"{'Konfiguratsiya':<30}{'n':>5}{'win%':>7}{'avgR':>8}{'totalR':>8}{'PF':>6}"
          f"{'IS PF':>7}{'OOS PF':>8}{'minFold':>9}{'f>1':>5}{'SL$':>7}{'SL/ATR':>8}")
    print("-" * 104)
    for name, cfg in configs:
        sub = filter_candidates(cands, cfg.get("min_strength", 0), cfg.get("min_atr", 0.0))
        transformed = [_transform(c, cfg.get("sl_atr", 0.0), cfg.get("tp_scale", 1.0)) for c in sub]
        ratios = [
            (abs(t["entry"] - t["sl"]) / t["atr"]) for t in transformed
            if t.get("atr") and t.get("entry") is not None
        ]
        avg_sl = np.mean([abs(t["entry"] - t["sl"]) for t in transformed]) if transformed else 0.0
        res = simulate_spread(
            df, sub, spread, max_bars, cfg.get("exit", "tp1"),
            cfg.get("sl_atr", 0.0), cfg.get("tp_scale", 1.0),
        )
        if res.empty:
            print(f"{name:<30}{'-':>5}")
            continue
        split = int(len(res) * 0.7)
        is_res, oos_res = res.iloc[:split], res.iloc[split:]
        size = max(1, len(res) // 5)
        fold_pfs = []
        for k in range(5):
            seg = res.iloc[k * size:(k + 1) * size] if k < 4 else res.iloc[k * size:]
            if not seg.empty:
                fold_pfs.append(_pf(seg))
        min_fold = min(fold_pfs) if fold_pfs else 0.0
        n_good = sum(1 for p in fold_pfs if p > 1.0)
        win = (res["r"] > 0).mean() * 100
        print(
            f"{name:<30}{len(res):>5}{win:>6.1f}%{res['r'].mean():>+8.3f}"
            f"{res['r'].sum():>+8.1f}{_pf(res):>6.2f}{_pf(is_res):>7.2f}{_pf(oos_res):>8.2f}"
            f"{min_fold:>9.2f}{n_good:>5}{avg_sl:>7.1f}{np.mean(ratios):>8.2f}"
        )


def walk_forward(df, cands, spread, max_bars, folds, cfg) -> None:
    """Tanlangan konfiguratsiyani teng bo'laklarga bo'lib PF barqarorligini ko'rsatadi."""
    sub = filter_candidates(cands, cfg.get("min_strength", 0), cfg.get("min_atr", 0.0))
    res = simulate_spread(
        df, sub, spread, max_bars, cfg.get("exit", "tp1"),
        cfg.get("sl_atr", 0.0), cfg.get("tp_scale", 1.0),
    )
    if res.empty:
        return
    print(f"\n--- Walk-forward ({folds} bo'lak, spread={spread:.2f}$, exit={cfg.get('exit')}, "
          f"sl_atr={cfg.get('sl_atr', 0)}) ---")
    size = max(1, len(res) // folds)
    for k in range(folds):
        seg = res.iloc[k * size:(k + 1) * size] if k < folds - 1 else res.iloc[k * size:]
        if seg.empty:
            continue
        w = pd.to_datetime(seg["time"].iloc[0]).strftime("%Y-%m")
        w2 = pd.to_datetime(seg["time"].iloc[-1]).strftime("%Y-%m")
        print(
            f"  {k + 1}-bo'lak ({w}..{w2}): n={len(seg):>4}  win={((seg['r'] > 0).mean()):>5.1%}  "
            f"total={seg['r'].sum():>+7.1f}R  PF={_pf(seg):.2f}"
        )


def monthly_breakdown(res: pd.DataFrame) -> None:
    if res.empty:
        return
    print("\n--- Oylik barqarorlik (R) ---")
    tmp = res.copy()
    tmp["month"] = pd.to_datetime(tmp["time"]).dt.to_period("M")
    for month, grp in tmp.groupby("month"):
        w = grp[grp["r"] > 0]
        print(f"  {month}: n={len(grp):>4}  win={len(w) / len(grp):>5.1%}  total={grp['r'].sum():>+7.1f}R")


def build_fine_sweep_configs(sl_grid=None) -> list:
    """SL floor ni nozik qadam bilan: barqaror platoni topish uchun."""
    ks = tuple(sl_grid) if sl_grid else (3.0, 3.25, 3.5, 3.75, 4.0, 4.5, 5.0)
    cfgs = []
    for k in ks:
        for ex in ("tp1", "half_hold"):
            cfgs.append((f"{ex} + sl>={k}ATR", {"exit": ex, "sl_atr": k}))
    return cfgs


def build_sweep_configs() -> list:
    return [
        ("tp1 exit (konservativ)", {"exit": "tp1"}),
        ("live exit (jonli model)", {"exit": "live"}),
        ("half_hold exit", {"exit": "half_hold"}),
        ("tp1 + sl>=2.0 ATR", {"exit": "tp1", "sl_atr": 2.0}),
        ("tp1 + sl>=2.5 ATR", {"exit": "tp1", "sl_atr": 2.5}),
        ("tp1 + sl>=3.0 ATR", {"exit": "tp1", "sl_atr": 3.0}),
        ("tp1 + sl>=3.5 ATR", {"exit": "tp1", "sl_atr": 3.5}),
        ("half_hold + sl>=2.5 ATR", {"exit": "half_hold", "sl_atr": 2.5}),
        ("half_hold + sl>=3.0 ATR", {"exit": "half_hold", "sl_atr": 3.0}),
        ("live + sl>=2.5 ATR", {"exit": "live", "sl_atr": 2.5}),
        ("live + sl>=3.0 ATR", {"exit": "live", "sl_atr": 3.0}),
        ("tp1 + sl>=2.5 + str>=70", {"exit": "tp1", "sl_atr": 2.5, "min_strength": 70}),
    ]


def run(setup_tf, candles, spreads, session_start, session_end, refresh, exit_models, do_sweep,
        sweep_spread: float = 0.50, sl_atr: Optional[float] = None, tp_scale: float = 1.0,
        max_hold_hours: float = MAX_HOLD_HOURS, sl_grid=None) -> None:
    print(f"Ma'lumot yuklanmoqda: {candles} ta {setup_tf} shamcha...")
    df = fetch_history(setup_tf, candles, refresh=refresh).reset_index(drop=True)
    print(f"Davr: {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]} ({len(df)} shamcha)")

    htf = HTF_MAP.get(setup_tf)
    session_txt = "o'chirilgan" if session_start is None else f"{session_start:02d}:00-{session_end:02d}:00 UTC"
    max_bars = max(1, int(max_hold_hours * 60 // TF_MINUTES[setup_tf]))
    # --sl-atr berilmasa: ishlab chiqarishdagi avtomatik floor (taymfreym/gorizonga qarab)
    if sl_atr is None:
        sl_atr = sl_floor_atr(setup_tf)
    print(f"Sozlamalar: setup={setup_tf}, HTF={htf}, {BARS} shamcha, maks. ushlash={max_hold_hours:g}h ({max_bars} sham), seans: {session_txt}")
    print(f"SL floor: {sl_atr:.2f} ATR (0 = o'chiq)")

    cands = get_candidates(df, setup_tf, candles, session_start, session_end, refresh=refresh)
    atr = np.array([c["atr"] for c in cands]) if cands else np.array([])
    print(f"Shartli signallar: {len(cands)} (BUY {sum(c['action'] == 'BUY' for c in cands)}, "
          f"SELL {sum(c['action'] == 'SELL' for c in cands)})")
    if len(atr):
        print(f"ATR (USD) taqsimoti: min={atr.min():.2f}  25%={np.percentile(atr, 25):.2f}  "
              f"50%={np.percentile(atr, 50):.2f}  75%={np.percentile(atr, 75):.2f}  max={atr.max():.2f}")
    if do_sweep:
        sweep(df, cands, sweep_spread, max_bars, build_fine_sweep_configs(sl_grid))
        return

    for spread in spreads:
        for em in exit_models:
            res = simulate_spread(df, cands, spread, max_bars, em, sl_atr, tp_scale)
            if res.empty:
                print(f"\n[spread={spread:.2f}$ exit={em}] Signallar yo'q.")
                continue
            split_idx = int(len(res) * 0.7)
            print_stats(f"spread={spread:.2f}$  exit={em}  sl_atr={sl_atr}  UMUMIY", res)
            print_stats("   In-Sample 70%", res.iloc[:split_idx])
            print_stats("   Out-of-Sample 30%", res.iloc[split_idx:])

    ref = 0.50 if 0.50 in spreads else spreads[0]
    detail_cfg = {"exit": exit_models[0], "sl_atr": sl_atr, "tp_scale": tp_scale}
    monthly_breakdown(simulate_spread(df, cands, ref, max_bars, exit_models[0], sl_atr, tp_scale))
    walk_forward(df, cands, ref, max_bars, 5, detail_cfg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XAUUSD signal backtest (jonli tizim bilan mos)")
    parser.add_argument("--tf", default=settings.DEFAULT_TIMEFRAME, choices=["15m", "1h", "4h"])
    parser.add_argument("--candles", type=int, default=8760, help="1h uchun 8760 = ~1 yil")
    parser.add_argument("--spread", type=float, default=None, help="Bitta spread (USD)")
    parser.add_argument("--spreads", default=None, help="Vergul bilan: 0.20,0.35,0.50,0.80")
    parser.add_argument("--exit", default="tp1", choices=["tp1", "live", "half_hold", "both"], help="Chiqish modeli")
    parser.add_argument("--sweep", action="store_true", help="Filtrlar/level o'zgarishlarini taqqoslash")
    parser.add_argument("--sweep-spread", type=float, default=0.50, help="Sweep uchun spread (USD)")
    parser.add_argument("--sl-atr", type=float, default=None,
                        help="SL masofasi uchun ATR floor (0 = o'chiq, berilmasa ishlab chiqarishdagi avtomatik)")
    parser.add_argument("--tp-scale", type=float, default=1.0, help="TP ko'paytmalarini masshtablash")
    parser.add_argument("--max-hold-hours", type=float, default=MAX_HOLD_HOURS,
                        help="Vaqt bo'yicha majburiy chiqish (soat). Standart 24.")
    parser.add_argument("--sl-grid", default=None,
                        help="Sweep uchun SL/ATR qiymatlari (vergul bilan), mas: 0,1,2,3,4,5,6")
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

    exit_models = ["tp1", "live"] if args.exit == "both" else [args.exit]

    run(
        args.tf, args.candles, chosen,
        None if args.no_session else args.session_start,
        None if args.no_session else args.session_end,
        refresh=args.refresh,
        exit_models=exit_models,
        do_sweep=args.sweep,
        sweep_spread=args.sweep_spread,
        sl_atr=args.sl_atr,
        tp_scale=args.tp_scale,
        max_hold_hours=args.max_hold_hours,
        sl_grid=([float(x) for x in args.sl_grid.split(",")] if args.sl_grid else None),
    )
