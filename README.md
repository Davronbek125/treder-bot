# 🚀 XAUUSD (Oltin) Tahlil va Signal Telegram Boti

**Mobile MT5** foydalanuvchilari uchun. Kompyuterga MT5 o'rnatish shart emas: bot bozorni tahlil qilib, signalni Telegramga yuboradi, zdelkani esa o'zingiz telefondagi MT5 da ochasiz.

> ⚠️ **Halol ogohlantirish:** bot foyda kafolatlamaydi. "Signal kuchi" - indikatorlarning mosligi balli (0-100), g'alaba ehtimoli **emas**. Quyidagi backtest natijalariga qarang.

## 📊 Backtest natijalari (`scripts/backtest.py`)

**Metodika — jonli tizim bilan aynan bir xil sharoit:**

- Ma'lumot: Binance PAXGUSDT (oltin), **~1.4 yil** (12 000 soatlik shamcha, 2025-06 → 2026-10).
- Sozlash timeframe: **H1** + **H4** trend tasdig'i. Har bir qaror nuqtasida faqat **yopilgan 250 shamcha** tahlil qilinadi — jonli bot ham aynan shunday qiladi (hech qanday look-ahead yo'q).
- **Spread** modeli: SL/TP narxdan hisoblanadi, kirish esa spread miqdorida yomonlashtiriladi (har bir bitim spreadga "to'laydi").
- **Seans filtri:** faqat London/NY (08:00–22:00 UTC).
- Chiqish: TP1 (1.5R) yoki SL; bir shamchada ikkalasi tegsa — **SL** (konservativ); 24 soatdan keyin vaqt bo'yicha chiqish.
- Yangiliklar (fundamental) filtri tarixda qo'llanilmaydi.

| Spread | Bitimlar | G'alaba | Chiqish (TP/SL/Vaqt) | O'rtacha R | Jami R | PF | IS PF | OOS PF |
|--------|----------|---------|----------------------|------------|--------|-----|-------|--------|
| 0.20$ | 455 | 45.5% | 35% / 47% / 18% | +0.05 | **+24.0** | **1.11** | 1.14 | 1.04 |
| 0.35$ | 455 | 45.3% | 35% / 47% / 18% | +0.04 | +19.3 | 1.08 | 1.12 | 1.01 |
| 0.50$ | 455 | 45.3% | 35% / 47% / 18% | +0.03 | +14.7 | 1.06 | 1.10 | 0.99 |
| 0.80$ | 455 | 45.3% | 35% / 47% / 18% | +0.01 | +6.2 | 1.03 | 1.06 | 0.94 |

*(IS = In-Sample, dastlabki 70%; OOS = Out-of-Sample, oxirgi 30%.)*

**Halol xulosa:**

- Tizim **kuchsiz, lekin izchil musbat** ustunlikka ega (PF ~1.06–1.11). Ammo ustunlik **juda yupqa**: har bir bitim o'rtacha atigi **+0.01 … +0.05R**.
- Out-of-Sample (oxirgi 30%, taxminan 2026-04 → 2026-10) natija deyarli **breakeven** (PF 0.94–1.04) — ya'ni ustunlik **yaqin tarixda saqlanmadi**. Bu "mo'jiza" emas, kichik ustunlikning tabiiy ko'rinishi.
- Spread 0.80$ gacha ustunlik saqlanadi, biroq foyda deyarli yo'qoladi. Komissiya/slippage hisobga olinsa, real natija shu jadvaldan **yomonroq** bo'lishi mumkin.
- Oylik barqarorlik: 17 oydan **10 tasi musbat**, 7 tasi salbiy. Umumiy natijaning katta qismi bir necha oydan (+11.5R, +8.8R, +5.8R) kelgan, boshida esa 3 oy ketma-ket zarar (−22R) — egri chiziq **notekis**.

**Seans filtri nima beradi?** (0.50$ spreadda taqqoslash)

| Rejim | Bitimlar | PF | O'rtacha R | Jami R | OOS PF |
|-------|----------|-----|------------|--------|--------|
| Seans **ON** (08:00–22:00 UTC) | 455 | 1.06 | +0.03 | +14.7 | 0.99 |
| Seans **OFF** (24 soat) | 566 | 1.07 | +0.03 | +18.9 | 0.99 |

> Seans filtri **bitim boshiga kutilmani oshirmaydi** (R bir xil) — u shunchaki bitimlar sonini **~20% kamaytiradi**. Ammo tunda real spread modeldagidan (0.50$) **kengroq** bo'lgani uchun amalda tungi signallar foydali emas. Shu sababli filtr saqlanadi: kamroq bitim = kamroq xarajat va kamroq keraksiz xavf.

> ⚠️ Xulosa: bu "foyda mashinasi" emas. Kichik lot, qat'iy risk-menejment va **`/stats`** orqali real natijani kuzatish shart.

Qayta tekshirish:

```bash
python scripts/backtest.py --tf 1h --candles 12000 --spreads 0.20,0.35,0.50,0.80
python scripts/backtest.py --tf 1h --candles 12000 --spreads 0.20,0.35,0.50 --no-session   # seanssiz taqqoslash
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
- **🌊 Rejim va trend filtrlari:** ADX (trend/ranging), EMA200 (yo'nalish xavfsizligi), yuqori timeframe tasdig'i, yangilik (fundamental) vetosi.
- **📉 Halol kutilma:** har bir signal xabarida tizim **foyda kafolati emasligi** va natija broker **spreadiga** bog'liqligi ochiq ko'rsatiladi.
- **📈 `/stats` — real natijalar:** bot o'z signallarini jurnalda kuzatadi va haqiqiy Win Rate, **Profit Factor**, o'rtacha natija (expectancy) hamda BUY/SELL bo'yicha taqsimotni ko'rsatadi. Bu eng halol ko'rsatkich — o'z natijangizni o'zingiz kuzatasiz.

> 💡 20 tadan kam bitimda xulosa qilmang. Keng spreadli brokerda tizim ustunligi yo'qolishi mumkin.

## 🌟 Imkoniyatlar

- ⚡ **M1 Skalping** (eksperimental/demo): `/scalp` - maksimal 5 daqiqa ushlanadigan tez signal (SL/TP ATR asosida)
- 🎯 **Signal** (BUY/SELL/WAIT): kirish, Stop Loss (swing/ATR), TP1/TP2/TP3 (1.5R/2.5R/4R), lot, amal qilish vaqti
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
scripts/    backtest.py (H1+H4), backtest_m1.py (M1 skalping)
tests/      104 ta test (pytest)
```
