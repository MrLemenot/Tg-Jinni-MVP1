import asyncio
import contextlib

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1 import game, entities, tasks, shop, promotions
from app.database.database import engine, Base, SessionLocal
from app.database.models import models  # noqa: F401
from app.config.settings import get_settings

app = FastAPI(title="TG Jinni API", version="4.1.0")
app.include_router(game.router, prefix="/api/v1")
app.include_router(entities.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(shop.router, prefix="/api/v1")
app.include_router(promotions.router, prefix="/api/v1")

app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")

@app.get("/")
async def root():
    return FileResponse("frontend/index.html")

@app.get("/healthcheck")
async def healthcheck():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"status": "degraded", "database": "error"})


async def _run_bot_and_worker():
    from app.bot.bot import run_bot
    from app.tasks.worker import run_worker
    await asyncio.gather(run_bot(), run_worker())


@app.on_event("startup")
async def startup():
    # Creates tables for MVP bootstrap. Replace with Alembic migrations before multi-version production deploys.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.state.bot_task = asyncio.create_task(_run_bot_and_worker())


@app.on_event("shutdown")
async def shutdown():
    task = getattr(app.state, "bot_task", None)
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await engine.dispose()
