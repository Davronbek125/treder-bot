# 🚀 XAUUSD (Oltin) Tahlil va Signal Telegram Boti

**Mobile MT5** foydalanuvchilari uchun. Kompyuterga MT5 o'rnatish shart emas: bot bozorni tahlil qilib, signalni Telegramga yuboradi, zdelkani esa o'zingiz telefondagi MT5 da ochasiz.

> ⚠️ **Halol ogohlantirish:** bot foyda kafolatlamaydi. "Signal kuchi" - indikatorlarning mosligi balli (0-100), g'alaba ehtimoli **emas**. Quyidagi backtest natijalariga qarang.

## 📊 Backtest natijalari (`scripts/backtest.py`)

**Metodika — jonli tizim bilan aynan bir xil sharoit:**

- Ma'lumot: Binance PAXGUSDT (oltin), **~1.4 yil** (12 000 soatlik shamcha, 2025-06 → 2026-10).
- Sozlash timeframe: **H1** + **H4** trend tasdig'i. Har bir qaror nuqtasida faqat **yopilgan 250 shamcha** tahlil qilinadi — jonli bot ham aynan shunday qiladi (hech qanday look-ahead yo'q).
- **Spread** modeli: SL/TP narxdan hisoblanadi, kirish esa spread miqdorida yomonlashtiriladi (har bir bitim spreadga "to'laydi").
- **Seans filtri:** faqat London/NY (08:00–22:00 UTC).
- **SL joylashuvi:** kamida `0.82 × ATR × √(ushlash shamchalari soni)` — **taymfreym va ushlash gorizontiga qarab avtomatik** (`services.signal_generator.sl_floor_atr`). 1h + 24 soatlik ushlash uchun bu **≈ 4.0 × ATR**. Sabab: ushlash gorizontida narxning tabiiy "shovqin zonasi" shu darajaga yetadi; undan **torroq** stop shovqin bilan urilib ketadi (quyida isbot).
- **Chiqish menejmenti:** TP1 (1.5R) da pozitsiyaning **50% yopiladi, SL BE ga SURILMAYDI**; qolgani TP2 (2.5R) / TP3 (4R) ni nishonga oladi. Bir shamchada ham SL, ham TP tegsa — **SL** (konservativ). 24 soatdan keyin vaqt bo'yicha chiqish.
- Yangiliklar (fundamental) filtri tarixda qo'llanilmaydi.

| Spread | Bitimlar | G'alaba | O'rtacha R | Jami R | PF | IS PF | OOS PF |
|--------|----------|---------|------------|--------|-----|-------|--------|
| 0.20$ | 308 | 50.3% | +0.128 | **+39.4** | **1.58** | 1.75 | 1.28 |
| 0.35$ | 308 | 50.3% | +0.124 | +38.1 | 1.56 | 1.73 | 1.26 |
| 0.50$ | 308 | 50.3% | +0.119 | +36.8 | **1.54** | 1.71 | 1.24 |

*(IS = In-Sample, dastlabki 70%; OOS = Out-of-Sample, oxirgi 30%. Chiqish taqsimoti (0.50$): 24-soat vaqt 75%, SL 17%, TP2 6%, TP3 2%. Spread faqat bitim narxini yomonlashtiradi, signallar to'plami bir xil qoladi.)*

**Spreadga sezgirlik (nega keng SL muhim):** SL kengaytirilgach, spread xarajati riskning juda kichik qismiga aylanadi — natija barqaror qoladi.

| Spread | PF | O'rtacha R | Jami R | OOS PF |
|--------|-----|------------|--------|--------|
| 0.10$ | 1.60 | +0.131 | +40.3 | 1.30 |
| 0.15$ | 1.59 | +0.129 | +39.8 | 1.29 |
| 0.20$ | 1.58 | +0.128 | +39.4 | 1.28 |
| 0.30$ | 1.57 | +0.125 | +38.5 | 1.27 |
| 0.50$ | 1.54 | +0.119 | +36.8 | 1.24 |
| 0.80$ | 1.50 | +0.111 | +34.2 | **1.19** |

> Hatto **0.80$** (juda keng) spreadda ham OOS PF **1.19** — eski sozlama 0.80$ da deyarli nolga tushardi (OOS ~0.85–0.99).

**Nima o'zgartirildi va nima uchun (barqarorlik isboti, spread = 0.50$):**

| Variant | Bitim | PF | O'rtacha R | Jami R | OOS PF |
|---------|-------|-----|------------|--------|--------|
| Eski: TP1 → SL **BE ga suriladi** | 419 | 1.03 | +0.015 | +6.4 | 0.85 |
| TP1 da 50%, SL o'zgarmaydi (tor ~1.5×ATR SL) | 398 | 1.18 | +0.086 | +34.0 | 1.14 |
| Eski SL (1.1–1.5×ATR, SMC darajasi) | 455 | 1.06 | +0.032 | +14.7 | 0.99 |
| **Yakuniy: half_hold + SL ≥ 4.0×ATR** | 308 | **1.54** | **+0.119** | **+36.8** | **1.24** |

- **SL ni BE (kirish narxi) ga surish foydani buzadi.** TP1 urilgach SL ni kirishga sursak, oddiy orqaga qaytishda qolgan yarmi yopiladi va TP2/TP3 imkoni yo'qoladi (OOS PF 0.85 → 1.14).
- **Tight (SMC asosidagi 1.1–1.5×ATR) stop shovqin bilan urilib ketadi.** SL masofasi 2.0 → 5.0×ATR oralig'ida sinov: o'rtacha R 3.75–4.5×ATR da plateau beradi.
- **Qattiq barqarorlik testi:** 5 ta teng vaqt bo'lagida (spread 0.50$) PF = **1.21 / 1.43 / 3.00 / 1.40 / 1.22** — hammasi **> 1**, eng yomoni 1.21.

**Halol xulosa:**

- Tizim **o'rtacha musbat** (PF ~1.55, har bir bitim o'rtacha **+0.12R**) va OOS davrida ham musbat (PF 1.24) — ya'ni ustunlik **yaqin tarixda saqlanadi**.
- **Ammo:** bitimlarning **~75% 24-soatlik vaqt chegarasida** yopiladi — ya'ni bu asosan **trend yo'nalishida 24 soat ushlab turish** strategiyasi. Trend davrida foyda, teskari (teskari-trend) davrda zarar.
- Foyda **notekis**: 3-bo'lak (2026-01..03) +18.6R beradi (5 bo'lak jami +36.8R). Oylik: 17 oydan **15 tasi musbat**, 2 tasi salbiy (2025-06 −1.5R, 2026-10 −4.1R — oxirgisi chala oy).
- **Keng SL → kichik lot.** 4×ATR stopda 1% risk uchun hisob (balans) kattaroq bo'lishi kerak; juda kichik hisobda minimal lot riskdan oshib ketishi mumkin (bot buni ogohlantiradi).
- Komissiya/slippage hisobga olinsa, real natija shu jadvaldan **yomonroq** bo'ladi.

**Seans filtri nima beradi?** (bitim boshiga kutilmani ~oshirmaydi, balki tungi keng spreadli bitimlarni kamaytiradi)

| Rejim | Bitimlar | PF | O'rtacha R | Jami R | OOS PF |
|-------|----------|-----|------------|--------|--------|
| Seans **ON** (08:00–22:00 UTC) | 455 | 1.06 | +0.03 | +14.7 | 0.99 |
| Seans **OFF** (24 soat) | 566 | 1.07 | +0.03 | +18.9 | 0.99 |

> (Jadval **eski** SL sozlamasi bilan olingan — filtrdan oldin/keyin farqni ko'rsatadi. Filtr saqlanadi: kamroq bitim = kamroq xarajat va kamroq keraksiz xavf.)

> ⚠️ Xulosa: bu "foyda mashinasi" emas. Kichik lot, qat'iy risk-menejment va **`/stats`** orqali real natijani kuzatish shart.

Qayta tekshirish:

```bash
python scripts/backtest.py --tf 1h --candles 12000 --exit half_hold --spreads 0.20,0.35,0.50,0.80
python scripts/backtest.py --tf 1h --candles 12000 --exit half_hold --sl-atr 4.0 --spreads 0.50   # floor ni qo'lda berish
python scripts/backtest.py --tf 1h --candles 12000 --sweep --sweep-spread 0.35    # filtrlar/level taqqoslash
python scripts/backtest.py --tf 15m --candles 35040 --exit half_hold --spreads 0.35   # 15m (floor avtomatik ~8.0 ATR)
python scripts/backtest.py --tf 1h --candles 12000 --spreads 0.35 --no-session    # seanssiz taqqoslash
```

> `--sl-atr` berilmasa skript **ishlab chiqarishdagi avtomatik floor** ni ishlatadi (1h → 4.02, 15m → 8.00 ATR). `--sl-atr 0` floor ni butunlay o'chiradi.

> **15m haqida halol izoh:** 15m ham xuddi shu dvigatel bilan ishlaydi (floor ~8.0 ATR, spread 0.35$ da PF 1.24, OOS 1.22). Lekin 5 ta bo'lakdan bittasi **zararli** (PF 0.77) va oylik natija beqaror (13 oydan 5 tasi musbat). Shu sababli standart taymfreym **1h** bo'lib qoladi.


## ⚡ M1 Skalping (`scripts/backtest_m1.py`)

M1 (1 daqiqa) taymfreymida ishlaydigan tizim (`services/m1_scalper.py`). Botda `/scalp` buyrug'i orqali ishlaydi.

**Asosiy g'oya:** M1 da bitta shamchaning harakati kichik, spread esa **qat'iy dollar xarajati**. Shuning uchun spread **riskning necha foizini** yeyishi hal qiluvchi:

| Sozlama | SL (dollarda) | Spread xarajati (0.20$) |
|---------|---------------|--------------------------|
| Eski: SL 1×ATR / TP 2.5×ATR / 5 daqiqa | ~2.9$ | ~7% risk |
| Yangi: SL 6×ATR / TP 3R / 4 soatgacha | ~14.2$ | ~1.4% risk |

Shu sababli **SL ni kengaytirish** va **TP ni uzoqqa qo'yish** M1 ni real spreadda ishlaydigan qildi.

1 yillik M1 backtest (525 600 shamcha, Binance PAXGUSDT, SL 6×ATR / TP 3R / min ATR 0.8$ / maks 240 daqiqa):

| Spread | Bitim | G'alaba | O'rtacha R | Jami R | PF | OOS PF | 5 bo'lak |
|--------|-------|---------|------------|--------|-----|--------|----------|
| 0.10$ | 1 926 | 35.0% | +0.081 | +156 | 1.13 | 1.14 | **5/5 > 1** |
| 0.15$ | 1 926 | 35.0% | +0.075 | +145 | 1.12 | 1.13 | **5/5 > 1** |
| 0.20$ | 1 926 | 35.0% | +0.070 | +134 | 1.12 | 1.12 | **5/5 > 1** |
| 0.30$ | 1 926 | 34.9% | +0.059 | +113 | 1.10 | 1.10 | **5/5 > 1** |
| 0.40$ | 1 926 | 34.9% | +0.048 | +92 | 1.08 | 1.08 | **5/5 > 1** |
| 0.50$ | 1 926 | 34.9% | +0.037 | +72 | 1.06 | 1.06 | 3/5 |
| 0.80$ | 1 926 | 34.8% | +0.007 | +14 | 1.01 | 1.01 | 2/5 |

**Taqqoslash (spread = 0.30$, real broker sharoiti):**

| Sozlama | Bitim | O'rtacha R | PF |
|---------|-------|------------|-----|
| Eski (SL 1×ATR / TP 2.5R / 5 daqiqa) | 8 287 | −0.020 | **0.96** (zarar) |
| **Yangi (SL 6×ATR / TP 3R / 4 soat)** | 1 926 | +0.059 | **1.10** |

**Halol izohlar:**

- Ustunlik **yupqa**: PF ~1.1, ya'ni har 100$ riskga ~10$ kutilma. Komissiya/slippage hisobga olinsa real natija **yomonroq** bo'ladi.
- G'alaba ulushi faqat **~35%** — bu **1:3 risk/foyda** strategiyasi, ya'ni ketma-ket zararlar normal.
- **Seans filtri M1 da zarar qiladi** (avgR +0.070 → +0.035), shuning uchun `/scalp` da seans filtri **o'chirilgan**.
- Kuniga ~5 ta signal; bitim **4 soatgacha** ushlanadi, SL dollarda keng (~14$) → lot kichik bo'ladi.
- `min_atr` sinaldi: 0.8 optimal, 1.2 deyarli bir xil, 2.0 ancha yomon — ya'ni tanlov **tor cho'qqiga bog'lanmagan**.

Qayta tekshirish:

```bash
python scripts/backtest_m1.py --candles 525600 --sl 6 --tp 18 --bars 240 --min-atr 0.8 --spread 0.30
python scripts/backtest_m1.py --candles 525600 --sweep --sweep-spread 0.20,0.30 --sweep-min-atr 0.8,1.2,1.6
```

## 🛡 Ishonchlilik qatlami (Reliability)

Signal sifatini oshirish uchun qo'shilgan filtrlar va halollik funksiyalari:

- **⏸ Savdo seansi filtri (London/NY, 08:00–22:00 UTC):** kechasi (Osiyo sessiyasi) likvidlik past va spread keng bo'ladi — shu davrda signal berilmaydi. Backtest ham xuddi shu filtrni ishlatadi, ya'ni jonli tizim aynan test qilingan mantiqqa mos ishlaydi. *(Bu filtr bitim boshiga kutilmani oshirmaydi — faqat keraksiz tungi bitimlarni ~20% kamaytiradi.)*
- **🛡 SL "shovqin zonasidan" tashqarida — taymfreymga qarab avtomatik:** floor = `0.82 × ATR × √(ushlash shamchalari soni)`, ya'ni **1h uchun ≈4.0×ATR**, 15m uchun ≈8.0×ATR. Bu turli taymfreymlarda **bir xil dollar SL** beradi. Undan torroq stop shovqin bilan urilib ketadi — backtest buni isbotlaydi (PF 1.06 → 1.56). Sozlamalar: `config.SL_FLOOR_K`, `config.SL_FLOOR_MAX_ATR`; `config.MIN_SL_ATR_MULT` ga son berilsa avtomatika bekor qilinadi (skript shundan foydalanadi).
- **🎯 TP1 da SL BE ga surilmaydi:** qisman foyda (50%) qulflanadi, lekin Stop Loss **kirish narxiga o'tkazilmaydi** — qolgan yarmi TP2/TP3 ni nishonga oladi. *(BE ga surish backtestda OOS PF ni 1.14 → 0.85 ga tushirgan.)*
- **⏱ 24 soatlik ushlash chegarasi:** yopilmagan bitim 24 soatdan keyin avtomatik "eskirgan" deb belgilanadi (`config.MAX_TRADE_HOURS`) — backtestdagi bilan bir xil.
- **🌊 Rejim va trend filtrlari:** ADX (trend/ranging), EMA200 (yo'nalish xavfsizligi), yuqori timeframe tasdig'i, yangilik (fundamental) vetosi.
- **📉 Halol kutilma:** har bir signal xabarida tizim **foyda kafolati emasligi**, natija broker **spreadiga** bog'liqligi va bitimlarning ~75% 24-soat chegarasida yopilishi (ya'ni foyda **trend davrlariga** bog'liqligi) ochiq yozilgan. Qisqacha: g'alaba ~50%, PF ~1.55, o'rtacha **+0.12R/bitim**.
- **📈 `/stats` — real natijalar:** bot o'z signallarini jurnalda kuzatadi va haqiqiy Win Rate, **Profit Factor**, o'rtacha natija (expectancy) hamda BUY/SELL bo'yicha taqsimotni ko'rsatadi. Bu eng halol ko'rsatkich — o'z natijangizni o'zingiz kuzatasiz.

> 💡 20 tadan kam bitimda xulosa qilmang. Keng spreadli brokerda tizim ustunligi yo'qolishi mumkin.

## 🌟 Imkoniyatlar

- ⚡ **M1 Skalping**: `/scalp` — M1 da kirish, **4 soatgacha** ushlash, SL 6×ATR / TP 3R (spread 0.10–0.40$ da 5/5 bo'lak musbat, PF ~1.1)
- 🎯 **Signal** (BUY/SELL/WAIT): kirish, Stop Loss (1h uchun ≈4.0×ATR — taymfreymga qarab avtomatik), TP1/TP2/TP3 (1.5R/2.5R/4R), lot, amal qilish vaqti. TP1 da 50% yopiladi, SL o'zgarmaydi.
- ⏸ **Seans filtri**: faqat London/NY (08:00–22:00 UTC) da signal
- 📈 **`/stats`**: haqiqiy Win Rate, Profit Factor, expectancy, BUY/SELL taqsimoti
- 🔭 **Yuqori timeframe tasdig'i** (M15→H1, H1→H4)
- 📊 **Texnik tahlil (Filtered):** SuperTrend, ADX (Bozor Rejimi/Regime Filter), RSI (Pullback) va EMA 200 (Qat'iy Trend Filtri).
- 🧠 **SMC (Smart Money Concepts):** Order Block, FVG, BOS (Asosiy qaror qabul qiluvchi)
- 📰 ForexFactory AQSh yangiliklari; xavfli paytda signal avtomatik **WAIT**
- 🛡 Lot kalkulyatori (minimal lot riskdan oshsa ogohlantiradi)
- 🔧 `/price` - broker narxiga moslash (manba narxi brokerdan 10-20$ farq qilishi mumkin)
- 🔒 `ALLOWED_USER_IDS` - botni faqat o'zingiz uchun yopish
- ❌ Ma'lumot olinmasa soxta signal **berilmaydi**

## ⚡ Ishga tushirish

1. [@BotFather](https://t.me/BotFather) da `/newbot` qiling, tokenni oling.
2. [@userinfobot](https://t.me/userinfobot) dan o'z Telegram ID ngizni oling.
3. Loyiha papkasida `.env` yarating va to'ldiring:
   ```env
   BOT_TOKEN=7845612345:AAH-xyz...
   ALLOWED_USER_IDS=123456789
   ```

### 💻 Option A: Mahalliy (Windows/Mac)
Oddiy kompyuterda ishlatish uchun:
```bash
pip install -r requirements.txt
python main.py
```
*(Yoki Windows da `run.bat` ni ishlating)*

### ☁️ Option B: VPS Serverda 24/7 (Docker) - Tavsiya etiladi
Bot sizning kompyuteringizdan mustaqil tunu-kun ishlashi uchun uni bitta buyruq bilan ishga tushiring:
```bash
docker compose up -d
```
*Loglarni ko'rish: `docker compose logs -f`*
*Avtomatik yangilash (kod o'zgarganda): `./deploy.sh`*

4. Bot yonganidan so'ng Telegramda `/start` va MT5 narxini kiritish uchun `/price 4155.30` buyruqlarini bering.

## 📱 MT5 Mobile da zdelka

1. 🎯 Signal oling (amal qilish vaqtiga qarang).
2. MT5 > XAUUSD > yangi order, tavsiya etilgan lotni yozing.
3. SL va TP ni kiriting, BUY/SELL bosing.

## 🧪 Testlar

```bash
python -m pytest tests/
```

## 📁 Struktura

```
config.py, main.py, run.bat, requirements.txt, .env
bot/        handlers, views, formatters, keyboards, state (sozlamalar saqlash), access (ruxsat)
services/   market_data, technical_analysis, smc_analysis, news_service, signal_generator, risk_calculator, m1_scalper
scripts/    backtest.py (H1+H4, sweep), backtest_m1.py (M1 skalping)
tests/      113 ta test (pytest)
```
