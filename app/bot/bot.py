import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from app.config.settings import get_settings
from app.bot.routers.start import router as start_router
from app.bot.routers.tasks import router as tasks_router


async def run_bot():
    settings = get_settings()
    bot = Bot(settings.bot_token)
    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(tasks_router)
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Открыть ТГ-Джинни"),
            BotCommand(command="tasks", description="Задания"),
        ])
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


async def main():
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
