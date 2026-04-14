import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import BOT_TOKEN
from app.storage import ensure_storage
from app.utils import set_commands, reminder_loop
from app.handlers.common import router as common_router
from app.handlers.subscription import router as subscription_router
from app.handlers.services import router as services_router
from app.handlers.admin import router as admin_router


async def main():
    ensure_storage()
    logging.basicConfig(level=logging.INFO)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(common_router)
    dp.include_router(subscription_router)
    dp.include_router(services_router)
    dp.include_router(admin_router)

    await set_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)

    reminder_task = asyncio.create_task(reminder_loop(bot))

    try:
        print("Bot is running...")
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())