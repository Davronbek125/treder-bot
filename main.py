import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.handlers import router
from config import settings

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("TrederBot")

COMMANDS = [
    BotCommand(command="signal", description="🎯 Savdo signali"),
    BotCommand(command="analysis", description="📊 Texnik tahlil"),
    BotCommand(command="smc", description="🧠 SMC zonalari"),
    BotCommand(command="news", description="📰 Yangiliklar"),
    BotCommand(command="calc", description="🛡 Lot kalkulyatori"),
    BotCommand(command="scalp", description="⚡ M1 skalping (4 soatgacha ushlash)"),
    BotCommand(command="stats", description="📊 Statistika"),
    BotCommand(command="backtest", description="🧪 Strategiya backtesti"),
    BotCommand(command="price", description="🔧 MT5 narxiga moslash"),
    BotCommand(command="help", description="⚙️ Yordam"),
]


async def main():
    token = settings.BOT_TOKEN.strip()

    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("\n" + "=" * 65)
        print("⚠️  TELEGRAM BOT TOKEN TOPILMADI!")
        print("=" * 65)
        print("Botni ishga tushirish uchun quyidagi qadamlarni bajaring:")
        print("1. Telegramda @BotFather ga kiring va /newbot buyrug'i bilan yangi bot oching.")
        print("2. BotFather bergan API tokenni nusxalang.")
        print("3. Loyiha papkasidagi '.env' faylini oching va quyidagicha yozing:")
        print("   BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        print("4. So'ngra 'python main.py' buyrug'ini qayta ishga tushiring.")
        print("=" * 65 + "\n")
        sys.exit(1)

    if not settings.allowed_user_ids:
        print("\n" + "=" * 65)
        print("⚠️  XAVFSIZLIK OGOHLANTIRISHI: ALLOWED_USER_IDS bo'sh!")
        print("=" * 65)
        print("Bot begona odamlar ishlatmasligi uchun Telegram ID ngizni .env fayliga kiriting:")
        print("ALLOWED_USER_IDS=123456789")
        print("=" * 65 + "\n")
        sys.exit(1)

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    @dp.error()
    async def error_handler(event, exception):
        logger.exception("Global Telegram xatoligi: %s", exception)
        return True

    from bot.scheduler import auto_signal_task

    logger.info("🤖 XAUUSD Savdo va Tahlil Telegram Boti ishga tushmoqda...")
    bg_task = None
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_my_commands(COMMANDS)
        
        # Start background tasks
        bg_task = asyncio.create_task(auto_signal_task(bot))
        
        await dp.start_polling(bot)
    finally:
        if bg_task:
            bg_task.cancel()
            try:
                await bg_task
            except asyncio.CancelledError:
                pass
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
