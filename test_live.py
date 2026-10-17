import asyncio
import logging
from datetime import datetime
from services.market_data import market_service, MarketDataError
from services.signal_generator import signal_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

async def test_live():
    print("=== LIVE TEST BOSHLANDI ===")
    print("Iltimos, ushbu narxlarni MT5 bilan solishtiring.")
    print("Chiqish uchun Ctrl+C bosing.\n")
    
    while True:
        try:
            # Haqiqiy narxni olish
            live_price = await asyncio.to_thread(market_service.get_live_price)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Binance/Yahoo narxi: {live_price:.2f}")
            
            # 15m timeframe uchun signal olish
            sig = await asyncio.to_thread(
                signal_service.generate_signal, 
                "15m", 1000, 2, 0.0
            )
            
            if sig["action"] != "WAIT":
                print(f"!!! {sig['action']} SIGNALI ({sig['strength']}%) !!!")
                print(f"Kirish: {sig['entry_price']:.2f}, SL: {sig['stop_loss']:.2f}, TP1: {sig['tps'][0]:.2f}")
                print(f"Ovozlar: {sig.get('votes')}")
            
            print("-" * 40)
            await asyncio.sleep(60) # Har 1 daqiqada tekshiradi
            
        except MarketDataError as e:
            print(f"XATOLIK: Bozor ma'lumotlarini olib bo'lmadi ({e})")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"Kutilmagan xatolik: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(test_live())
    except KeyboardInterrupt:
        print("\nTest to'xtatildi.")
