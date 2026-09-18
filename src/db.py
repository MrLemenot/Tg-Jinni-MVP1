from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
from fastapi import Request


class Database:
    def __init__(self, env):
        self.env = env

    @property
    def hyperdrive(self):
        return self.env.HYPERDRIVE

    async def connect(self):
        hd = self.hyperdrive
        return await asyncpg.connect(
            host=hd.host,
            port=int(hd.port),
            user=hd.user,
            password=hd.password,
            database=hd.database,
            ssl=False,
            command_timeout=20,
        )

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[asyncpg.Connection]:
        conn = await self.connect()
        try:
            yield conn
        finally:
            await conn.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        conn = await self.connect()
        tx = conn.transaction()
        await tx.start()
        try:
            yield conn
        except Exception:
            await tx.rollback()
            raise
        else:
            await tx.commit()
        finally:
            await conn.close()


def db_from_request(request: Request) -> Database:
    return Database(request.scope["env"])
