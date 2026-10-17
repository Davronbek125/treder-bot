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


def sweep(candles: int, base: ScalpParams, balance: float, risk: float, refresh: bool) -> None:
    df = load_m1(candles, refresh)
    print(f"Sweep davri: {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}\n")

    print(f"{'SL/TP/maxBars':<18} {'spread':>7} {'n':>6} {'win':>6} {'avgR':>8} {'totalR':>9} {'PF':>6}")
    best = None
    for tp_mult in (1.0, 1.5, 2.0, 2.5, 3.0):
        for bars in (5, 10, 15):
            params = ScalpParams(
                sl_atr_mult=base.sl_atr_mult, tp_atr_mult=tp_mult, max_bars=bars,
                min_atr=base.min_atr, session_start=base.session_start, session_end=base.session_end,
            )
            prepared = m1_scalper_service.prepare(df, params)
            for sp in (0.10, 0.20, 0.30):
                res = m1_scalper_service.simulate(prepared, params, spread=sp)
                s = stats(res, balance, risk)
                if s.get("n", 0) == 0:
                    continue
                print(f"SL{params.sl_atr_mult} TP{tp_mult} b{bars:<4} {sp:>7.2f} {s['n']:>6} {s['win_rate']:>5.1%} "
                      f"{s['avg_r']:>+8.3f} {s['total_r']:>+9.1f} {s['pf']:>6.2f}")
                if best is None or s["total_r"] > best[0]["total_r"]:
                    best = (s, f"SL{params.sl_atr_mult} TP{tp_mult} b{bars} spread={sp}")
    if best:
        print(f"\nEng yaxshi (total R bo'yicha): {best[1]} -> {best[0]['total_r']:+.1f}R, PF={best[0]['pf']:.2f}")


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
    parser.add_argument("--refresh", action="store_true", help="Keshni yangilash")
    args = parser.parse_args()

    params = ScalpParams(
        sl_atr_mult=args.sl, tp_atr_mult=args.tp, max_bars=args.bars, min_atr=args.min_atr,
        session_start=args.session_start, session_end=args.session_end,
    )
    if args.sweep:
        sweep(args.candles, params, args.balance, args.risk, args.refresh)
    else:
        run(args.candles, params, args.balance, args.risk, args.spread, args.refresh)
