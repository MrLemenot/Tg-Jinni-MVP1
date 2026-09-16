import asyncio
from aiogram import Bot
from app.config.settings import get_settings
from app.database.database import SessionLocal
from app.tasks.service import finalize_holds


async def run_worker():
    settings = get_settings()
    bot = Bot(settings.bot_token)
    try:
        while True:
            try:
                async with SessionLocal() as db:
                    await finalize_holds(db, bot)
            except Exception:
                # Keep the worker alive; Render logs the process-level failures through the API task.
                pass
            await asyncio.sleep(3600)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run_worker())
