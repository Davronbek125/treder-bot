# 🚀 XAUUSD (Oltin) Tahlil va Signal Telegram Boti

**Mobile MT5** foydalanuvchilari uchun. Kompyuterga MT5 o'rnatish shart emas: bot bozorni tahlil qilib, signalni Telegramga yuboradi, zdelkani esa o'zingiz telefondagi MT5 da ochasiz.

> ⚠️ **Halol ogohlantirish:** bot foyda kafolatlamaydi. "Signal kuchi" - indikatorlarning mosligi balli (0-100), g'alaba ehtimoli **emas**. Quyidagi backtest natijalariga qarang.

## 📊 Backtest natijalari (`scripts/backtest.py`)

**Metodika — jonli tizim bilan aynan bir xil sharoit:**

- Ma'lumot: Binance PAXGUSDT (oltin), **~1.4 yil** (12 000 soatlik shamcha, 2025-06 → 2026-10).
- Sozlash timeframe: **H1** + **H4** trend tasdig'i. Har bir qaror nuqtasida faqat **yopilgan 250 shamcha** tahlil qilinadi — jonli bot ham aynan shunday qiladi (hech qanday look-ahead yo'q).
- **Spread** modeli: SL/TP narxdan hisoblanadi, kirish esa spread miqdorida yomonlashtiriladi (har bir bitim spreadga "to'laydi").
- **Seans filtri:** faqat London/NY (08:00–22:00 UTC).
- **SL joylashuvi:** kamida **3.5 × ATR**. Sabab: 24 soatlik ushlash gorizontida narxning tabiiy "shovqin zonasi" ≈ `ATR × √24 × 0.8 ≈ 3.9 × ATR`. Undan **torroq** stop shovqin bilan urilib ketadi (quyida isbot).
- **Chiqish menejmenti:** TP1 (1.5R) da pozitsiyaning **50% yopiladi, SL BE ga SURILMAYDI**; qolgani TP2 (2.5R) / TP3 (4R) ni nishonga oladi. Bir shamchada ham SL, ham TP tegsa — **SL** (konservativ). 24 soatdan keyin vaqt bo'yicha chiqish.
- Yangiliklar (fundamental) filtri tarixda qo'llanilmaydi.

| Spread | Bitimlar | G'alaba | O'rtacha R | Jami R | PF | IS PF | OOS PF |
|--------|----------|---------|------------|--------|-----|-------|--------|
| 0.20$ | 311 | 49.5% | +0.120 | **+37.5** | **1.46** | 1.62 | 1.18 |
| 0.35$ | 311 | 49.5% | +0.116 | +36.0 | 1.44 | 1.61 | 1.16 |
| 0.50$ | 311 | 49.5% | +0.111 | +34.6 | 1.42 | 1.59 | 1.14 |

*(IS = In-Sample, dastlabki 70%; OOS = Out-of-Sample, oxirgi 30%. Chiqish taqsimoti (0.50$): SL 22%, 24-soat vaqt 70%, TP1+ 9%.)*

**Nima o'zgartirildi va nima uchun (barqarorlik isboti):**

| Variant | Bitim | PF | O'rtacha R | Jami R | OOS PF |
|---------|-------|-----|------------|--------|--------|
| Eski: TP1 → SL **BE ga suriladi** | 419 | 1.03 | +0.015 | +6.4 | 0.85 |
| TP1 da 50%, SL o'zgarmaydi | 398 | 1.18 | +0.086 | +34.0 | 1.14 |
| Eski SL (1.1–1.5×ATR, SMC darajasi) | 455 | 1.06 | +0.032 | +14.7 | 0.99 |
| **Yakuniy: 50%/SL o'zgarmas + SL ≥ 3.5×ATR** | 311 | **1.42** | **+0.111** | **+34.6** | **1.14** |

- **SL ni BE (kirish narxi) ga surish foydani buzadi.** TP1 urilgach SL ni kirishga sursak, oddiy orqaga qaytishda qolgan yarmi yopiladi va TP2/TP3 imkoni yo'qoladi (OOS PF 0.85 → 1.14).
- **Tight (SMC asosidagi 1.1–1.5×ATR) stop shovqin bilan urilib ketadi.** SL masofasi 2.0 → 5.0×ATR oralig'ida sinov: `+avgR` 3.0–4.5×ATR da plateauga chiqadi (3.5–4.5 barqaror).
- **Qattiq barqarorlik testi:** 3 xil spread × 5 ta teng vaqt bo'lagi = **15/15 bo'lakda PF > 1** (eng yomon bo'lak PF 1.15). `--sweep` orqali tekshiriladi.

**Halol xulosa:**

- Tizim endi **o'rtacha musbat** (PF ~1.4, har bir bitim o'rtacha **+0.11R**) va OOS davrida ham musbat (PF 1.14) — ya'ni yangi sozlamada ustunlik **yaqin tarixda saqlanadi** (eski sozlamada OOS 0.85–0.99 edi).
- **Ammo:** bitimlarning **~70% 24-soatlik vaqt chegarasida** yopiladi — ya'ni bu asosan **trend yo'nalishida 24 soat ushlab turish** strategiyasi. Trend davrida foyda, teskari (teskari-trend) davrda zarar.
- Foyda **notekis**: 5 bo'lakdan 3-chisi (+21.5R) jami +36R ning yarmidan ko'pini beradi. Oylik: 17 oydan 5 tasi salbiy.
- **Keng SL → kichik lot.** 3.5×ATR stopda 1% risk uchun hisob (balans) kattaroq bo'lishi kerak; juda kichik hisobda minimal lot riskdan oshib ketishi mumkin (bot buni ogohlantiradi).
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
python scripts/backtest.py --tf 1h --candles 12000 --spreads 0.20,0.35,0.50,0.80
python scripts/backtest.py --tf 1h --candles 12000 --exit half_hold --sl-atr 3.5 --spreads 0.20,0.35,0.50
python scripts/backtest.py --tf 1h --candles 12000 --sweep --sweep-spread 0.35    # filtrlar/level taqqoslash
python scripts/backtest.py --tf 1h --candles 12000 --spreads 0.35 --no-session    # seanssiz taqqoslash
```

## ⚡ M1 Skalping (eksperimental — `scripts/backtest_m1.py`)

M1 (1 daqiqa) taymfreymida, **maksimal 5 daqiqa** ushlanadigan skalping tizimi (`services/m1_scalper.py`). Botda `/scalp` buyrug'i orqali ishlaydi.

1 yillik M1 backtest (525 600 shamcha, Binance PAXGUSDT, SL 1×ATR / TP 2.5×ATR / min ATR 1.2$, maks 5 daqiqa):

| Spread | Bitim | G'alaba | O'rtacha R | Jami R | Profit Factor |
|--------|-------|---------|------------|--------|---------------|
| 0.10$ | 8 287 | 41.0% | +0.068 | +564 | 1.13 |
| 0.20$ | 8 287 | 40.5% | +0.022 | +181 | 1.04 |
| 0.30$ | 8 287 | 39.7% | −0.020 | −166 | 0.96 |

⚠️ **Muhim / halol ogohlantirish:** M1 skalping **spreadga o'ta sezgir**. Foyda faqat **juda tor spread (≤0.20$)** da chiqadi; real broker spreadi (0.15–0.35$ + komissiya) da tizim chegarada yoki zararda. Shu sababli `/scalp` **EKSPERIMENTAL / DEMO** deb belgilangan — real pulda ishlatish tavsiya etilmaydi, faqat kuzatish/sinov uchun.

Qayta tekshirish: `python scripts/backtest_m1.py --candles 525600 --tp 2.5 --min-atr 1.2 --spread 0.20`

## 🛡 Ishonchlilik qatlami (Reliability)

Signal sifatini oshirish uchun qo'shilgan filtrlar va halollik funksiyalari:

- **⏸ Savdo seansi filtri (London/NY, 08:00–22:00 UTC):** kechasi (Osiyo sessiyasi) likvidlik past va spread keng bo'ladi — shu davrda signal berilmaydi. Backtest ham xuddi shu filtrni ishlatadi, ya'ni jonli tizim aynan test qilingan mantiqqa mos ishlaydi. *(Bu filtr bitim boshiga kutilmani oshirmaydi — faqat keraksiz tungi bitimlarni ~20% kamaytiradi.)*
- **🛡 SL "shovqin zonasidan" tashqarida (≥ 3.5 × ATR):** 24 soatlik ushlash gorizontida narxning tabiiy tebranishi ~3.9×ATR ga yetadi. Undan torroq stop shovqin bilan urilib ketadi — backtest buni isbotlaydi (PF 1.06 → 1.42). Sozlama: `config.MIN_SL_ATR_MULT`.
- **🎯 TP1 da SL BE ga surilmaydi:** qisman foyda (50%) qulflanadi, lekin Stop Loss **kirish narxiga o'tkazilmaydi** — qolgan yarmi TP2/TP3 ni nishonga oladi. *(BE ga surish backtestda OOS PF ni 1.14 → 0.85 ga tushirgan.)*
- **⏱ 24 soatlik ushlash chegarasi:** yopilmagan bitim 24 soatdan keyin avtomatik "eskirgan" deb belgilanadi (`config.MAX_TRADE_HOURS`) — backtestdagi bilan bir xil.
- **🌊 Rejim va trend filtrlari:** ADX (trend/ranging), EMA200 (yo'nalish xavfsizligi), yuqori timeframe tasdig'i, yangilik (fundamental) vetosi.
- **📉 Halol kutilma:** har bir signal xabarida tizim **foyda kafolati emasligi**, natija broker **spreadiga** bog'liqligi va bitimlarning ~70% 24-soat chegarasida yopilishi (ya'ni foyda **trend davrlariga** bog'liqligi) ochiq yozilgan.
- **📈 `/stats` — real natijalar:** bot o'z signallarini jurnalda kuzatadi va haqiqiy Win Rate, **Profit Factor**, o'rtacha natija (expectancy) hamda BUY/SELL bo'yicha taqsimotni ko'rsatadi. Bu eng halol ko'rsatkich — o'z natijangizni o'zingiz kuzatasiz.

> 💡 20 tadan kam bitimda xulosa qilmang. Keng spreadli brokerda tizim ustunligi yo'qolishi mumkin.

## 🌟 Imkoniyatlar

- ⚡ **M1 Skalping** (eksperimental/demo): `/scalp` - maksimal 5 daqiqa ushlanadigan tez signal (SL/TP ATR asosida)
- 🎯 **Signal** (BUY/SELL/WAIT): kirish, Stop Loss (≥3.5×ATR, shovqin zonasidan tashqarida), TP1/TP2/TP3 (1.5R/2.5R/4R), lot, amal qilish vaqti. TP1 da 50% yopiladi, SL o'zgarmaydi.
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
tests/      109 ta test (pytest)
```
