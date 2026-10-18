"""
M1 skalping strategiyasini tarixiy ma'lumotda sinash.

Ishlatish:
    python scripts/backtest_m1.py --candles 129600          # ~90 kun M1
    python scripts/backtest_m1.py --candles 129600 --sweep  # parametr qidiruvi

Eslatma:
- Narx manbai: Binance PAXGUSDT (oltin bilan 1:1).
- Spread bir necha qiymatda sinaladi, chunki M1 da spread hal qiluvchi omil.
- Savdo maksimal `--bars` M1 shamcha ushlanadi (default 5 = 5 daqiqa).
- Natijalar o'tmishni ko'rsatadi, kelajakka kafolat emas.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import numpy as np  # noqa: E402

from services.m1_scalper import ScalpParams, m1_scalper_service  # noqa: E402
from services.market_data import fetch_history  # noqa: E402
from services.risk_calculator import risk_service  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
SPREADS = [0.0, 0.05, 0.10, 0.20, 0.30, 0.50]


def load_m1(candles: int, refresh: bool = False) -> pd.DataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"paxgusdt_m1_{candles}.pkl"
    if cache_file.exists() and not refresh:
        print(f"Keshdan o'qildi: {cache_file.name}")
        return pd.read_pickle(cache_file)
    print(f"Binance'dan {candles} ta M1 shamcha yuklanmoqda (taxminan {candles // 1440} kun)...")
    df = fetch_history("1m", candles)
    df.to_pickle(cache_file)
    print(f"Keshga saqlandi: {cache_file.name}")
    return df


def stats(res: pd.DataFrame, balance: float, risk_percent: float) -> dict:
    if res.empty:
        return {"n": 0}
    wins = res[res["r"] > 0]
    losses = res[res["r"] <= 0]
    gross_win = float(wins["r"].sum())
    gross_loss = float(abs(losses["r"].sum()))
    risk_usd = balance * (risk_percent / 100.0)
    total_r = float(res["r"].sum())

    lots = [
        risk_service.calculate_lot_size(balance, risk_percent, r.entry, r.sl, r.tp, r.tp, r.tp)["lot_size"]
        for r in res.itertuples()
    ]

    # Ketma-ket zararlar
    max_streak = streak = 0
    for r in res["r"]:
        if r <= 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    return {
        "n": len(res),
        "buy": int((res["action"] == "BUY").sum()),
        "sell": int((res["action"] == "SELL").sum()),
        "win_rate": len(wins) / len(res),
        "avg_r": res["r"].mean(),
        "total_r": total_r,
        "pf": (gross_win / gross_loss) if gross_loss else float("inf"),
        "tp": int((res["reason"] == "TP").sum()),
        "sl": int((res["reason"] == "SL").sum()),
        "time": int((res["reason"] == "TIME").sum()),
        "avg_win": wins["r"].mean() if len(wins) else 0.0,
        "avg_loss": losses["r"].mean() if len(losses) else 0.0,
        "max_loss_streak": max_streak,
        "avg_lot": sum(lots) / len(lots),
        "total_usd": total_r * risk_usd,
        "risk_usd": risk_usd,
    }


def fmt(label: str, s: dict) -> str:
    if s.get("n", 0) == 0:
        return f"{label:<14} signallar yo'q"
    return (
        f"{label:<14} n={s['n']:>6}  win={s['win_rate']:>5.1%}  avg={s['avg_r']:+.3f}R  "
        f"total={s['total_r']:>+8.1f}R  PF={s['pf']:.2f}  "
        f"TP/SL/TIME={s['tp']}/{s['sl']}/{s['time']}  lot~{s['avg_lot']:.2f}"
    )


def print_split(res: pd.DataFrame, balance: float, risk: float, spread: float) -> None:
    if res.empty:
        return
    split = int(len(res) * 0.7)
    print(f"\n=== In-Sample / Out-of-Sample (spread={spread:.2f}$) ===")
    for label, part in [("Jami", res), ("In-Sample 70%", res.iloc[:split]), ("Out-Sample 30%", res.iloc[split:])]:
        s = stats(part, balance, risk)
        line = fmt(label, s)
        if s.get("n"):
            line += f"  => {s['total_usd']:+.1f}$"
        print(line)


def run(candles: int, params: ScalpParams, balance: float, risk: float, spread: float, refresh: bool) -> None:
    df = load_m1(candles, refresh)
    print(f"Davr: {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}  ({len(df)} shamcha M1)\n")

    prepared = m1_scalper_service.prepare(df, params)

    action_counts = prepared["action"].value_counts()
    print(f"Signal shamchalari: BUY={action_counts.get('BUY', 0)}, SELL={action_counts.get('SELL', 0)}")
    print(f"Sozlamalar: max {params.max_bars} shamcha ushlash, SL={params.sl_atr_mult}ATR, TP={params.tp_atr_mult}ATR, "
          f"min_atr={params.min_atr}$, HTF={params.htf_rule}\n")

    print(f"Balans={balance:.0f}$, risk={risk:.1f}% (={balance * risk / 100:.2f}$/bitim)\n")
    print("=== Spreadga qarab natijalar ===")
    for sp in ([spread] if spread is not None else SPREADS):
        res = m1_scalper_service.simulate(prepared, params, spread=sp)
        s = stats(res, balance, risk)
        line = fmt(f"spread={sp:.2f}$", s)
        if s.get("n"):
            line += f"  => {s['total_usd']:+.1f}$"
        print(line)

    if spread is not None:
        print_split(m1_scalper_service.simulate(prepared, params, spread=spread), balance, risk, spread)


def _pf(r: pd.Series) -> float:
    gw = float(r[r > 0].sum())
    gl = float(abs(r[r <= 0].sum()))
    return (gw / gl) if gl else (99.0 if gw else 0.0)


def _mask(df: pd.DataFrame, min_atr: float = 0.0, session=None) -> pd.DataFrame:
    """Signal ustuniga min_atr/session filtrlarini qo'llaydi (qayta prepare qilmasdan)."""
    a = df["action"].to_numpy().copy()
    if min_atr and min_atr > 0:
        a[df["atr"].to_numpy(dtype=float) < min_atr] = "WAIT"
    if session:
        h = df["timestamp"].dt.hour.to_numpy()
        a[~((h >= session[0]) & (h <= session[1]))] = "WAIT"
    out = df.copy()
    out["action"] = a
    return out


def _market(df: pd.DataFrame) -> dict:
    """ATR taqsimoti - M1 da harakat spreadga nisbatan yetarlimi ko'rish uchun."""
    atr = df["atr"].to_numpy(dtype=float)
    atr = atr[pd.notna(atr) & (atr > 0)]
    if not atr.size:
        return {}
    return {
        "min": float(atr.min()), "25": float(np.percentile(atr, 25)),
        "50": float(np.percentile(atr, 50)), "75": float(np.percentile(atr, 75)),
        "max": float(atr.max()), "mean": float(atr.mean()),
    }


def sweep(candles: int, base: ScalpParams, balance: float, risk: float, refresh: bool,
          spreads=None, bars_list=None, sl_list=None, tp_r_list=None,
          min_atr_list=None) -> None:
    """
    SL/TP/ushlash vaqtini birgalikda qidiradi va HAR BIR variant uchun
    IS/OOS + 5 bo'lak barqarorligini ko'rsatadi.

    MUHIM: M1 da SL "shovqin zonasidan" tashqarida bo'lishi kerak.
    Nazariy: floor ~ 0.8 * sqrt(max_bars) * ATR (masalan 5 daqiqa -> ~1.8 ATR).
    """
    df = load_m1(candles, refresh)
    print(f"Sweep davri: {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}\n")

    # prepare BIR MARTA (sl/tp/max_bars signal ustunlariga ta'sir qilmaydi) - juda tez.
    prepared = m1_scalper_service.prepare(
        df, ScalpParams(min_atr=0.0, session_start=None, session_end=None, htf_rule=base.htf_rule)
    )
    mkt = _market(prepared)
    if mkt:
        print(f"ATR (M1, USD): 25%={mkt['25']:.2f} 50%={mkt['50']:.2f} 75%={mkt['75']:.2f} "
              f"mean={mkt['mean']:.2f} max={mkt['max']:.2f}")
        print("(Spread ATR'ning qancha qismi - shu M1 ning asosiy muammosi)\n")

    spreads = spreads or (0.20, 0.30)
    bars_list = bars_list or (5, 15, 30, 60)
    sl_list = sl_list or (1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
    tp_r_list = tp_r_list or (1.0, 2.0)
    min_atr_list = min_atr_list or (base.min_atr,)
    session = (base.session_start, base.session_end) if base.session_start is not None else None
    print(f"{'ATR>':>5}{'bars':>6}{'SL':>5}{'TP_R':>6}{'spread':>8}{'n':>7}{'win%':>7}{'avgR':>8}"
          f"{'totalR':>9}{'PF':>6}{'IS':>6}{'OOS':>6}{'minF':>6}{'f>1':>5}{'TIME%':>7}{'SL$':>7}")
    print("-" * 108)
    for ma in min_atr_list:
        masked = _mask(prepared, ma, session)
        for bars in bars_list:
            for sl_mult in sl_list:
                for tp_r in tp_r_list:
                    params = ScalpParams(
                        sl_atr_mult=sl_mult, tp_atr_mult=sl_mult * tp_r, max_bars=bars,
                        min_atr=ma, session_start=base.session_start,
                        session_end=base.session_end, htf_rule=base.htf_rule,
                    )
                    for sp in spreads:
                        res = m1_scalper_service.simulate(masked, params, spread=sp)
                        if res.empty:
                            continue
                        r = res["r"]
                        split = int(len(res) * 0.7)
                        size = max(1, len(res) // 5)
                        fold_pfs = []
                        for k in range(5):
                            lo = k * size
                            hi = (k + 1) * size if k < 4 else len(res)
                            seg = res.iloc[lo:hi]
                            if not seg.empty:
                                fold_pfs.append(_pf(seg["r"]))
                        n_good = sum(1 for p in fold_pfs if p > 1.0)
                        sl_usd = float((res["entry"] - res["sl"]).abs().mean())
                        print(
                            f"{ma:>5.2f}{bars:>6}{sl_mult:>5.1f}{tp_r:>6.1f}{sp:>8.2f}{len(res):>7}"
                            f"{(r > 0).mean() * 100:>6.1f}%{r.mean():>+8.3f}{r.sum():>+9.1f}"
                            f"{_pf(r):>6.2f}{_pf(res.iloc[:split]['r']):>6.2f}{_pf(res.iloc[split:]['r']):>6.2f}"
                            f"{min(fold_pfs):>6.2f}{n_good:>5}"
                            f"{(res['reason'] == 'TIME').mean() * 100:>6.0f}%{sl_usd:>7.1f}"
                        )
    print("\nEslatma: ustunlik = avgR musbat VA OOS hamda minF (eng yomon bo'lak) > 1 bo'lishi.")
    print("M1 da spread katta qism bo'lgani uchun SL (dollarda) keng bo'lishi shart.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="M1 skalping backtest")
    parser.add_argument("--candles", type=int, default=129600, help="M1 shamchalar soni (129600 ~ 90 kun)")
    parser.add_argument("--bars", type=int, default=5, help="Maksimal ushlash (M1 shamchada)")
    parser.add_argument("--sl", type=float, default=1.0, help="SL (ATR ko'paytmasi)")
    parser.add_argument("--tp", type=float, default=1.5, help="TP (ATR ko'paytmasi)")
    parser.add_argument("--min-atr", type=float, default=0.0, help="Minimal ATR (USD) filtri")
    parser.add_argument("--session-start", type=int, default=None, help="Sessiya boshlanishi (UTC soat)")
    parser.add_argument("--session-end", type=int, default=None, help="Sessiya tugashi (UTC soat)")
    parser.add_argument("--balance", type=float, default=1000.0)
    parser.add_argument("--risk", type=float, default=1.0)
    parser.add_argument("--spread", type=float, default=None, help="Bitta spread qiymati (default: bir nechta)")
    parser.add_argument("--sweep", action="store_true", help="Parametr qidiruvi")
    parser.add_argument("--sweep-spreads", default="0.20,0.30",
                        help="Sweep uchun spreadlar (vergul bilan)")
    parser.add_argument("--sweep-bars", default=None, help="Sweep uchun ushlash (shamchada)")
    parser.add_argument("--sweep-sl", default=None, help="Sweep uchun SL (ATR ko'paytmasi)")
    parser.add_argument("--sweep-tp-r", default=None, help="Sweep uchun TP (R ko'paytmasi)")
    parser.add_argument("--sweep-min-atr", default=None, help="Sweep uchun min ATR (USD)")
    parser.add_argument("--refresh", action="store_true", help="Keshni yangilash")
    args = parser.parse_args()

    params = ScalpParams(
        sl_atr_mult=args.sl, tp_atr_mult=args.tp, max_bars=args.bars, min_atr=args.min_atr,
        session_start=args.session_start, session_end=args.session_end,
    )
    if args.sweep:
        _floats = lambda s: ([float(x) for x in s.split(",")] if s else None)
        sweep(
            args.candles, params, args.balance, args.risk, args.refresh,
            spreads=tuple(float(x) for x in args.sweep_spreads.split(",")),
            bars_list=([int(x) for x in args.sweep_bars.split(",")] if args.sweep_bars else None),
            sl_list=_floats(args.sweep_sl),
            tp_r_list=_floats(args.sweep_tp_r),
            min_atr_list=_floats(args.sweep_min_atr),
        )
    else:
        run(args.candles, params, args.balance, args.risk, args.spread, args.refresh)
