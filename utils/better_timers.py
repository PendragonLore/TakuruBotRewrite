import asyncio
import datetime

from discord.ext import tasks

try:
    import ujson as json
except ImportError:
    import json


class Timer:
    def __init__(self, id_, name, expires_at, kwargs):
        self.id = id_

        self.name = name
        self.expires_at = expires_at
        self.kwargs = kwargs

    @classmethod
    def from_record(cls, record):
        return cls(
            record["id"], record["name"], record["expires_at"], record["args"]
        )

    def __getitem__(self, item):
        return self.kwargs[item]

    def __repr__(self):
        return "<Timer name={0.name!r} expires_at={0.expires_at!r} kwargs={0.kwargs}>".format(self)


class TimerManager:
    def __init__(self, bot):
        self.bot = bot

        self.queue = asyncio.Queue(loop=bot.loop)

        self.fetch_timers.start()

    def cleanup(self):
        self.fetch_timers.cancel()

    @tasks.loop()
    async def fetch_timers(self):
        timer = await self.queue.get()

        self.queue.task_done()

        await self.dispatch(timer)

    @fetch_timers.before_loop
    async def before_fetch_timers(self):
        async with self.bot.db.acquire() as db:
            async with db.transaction():
                async for timer in db.cursor("SELECT * FROM times;"):
                    delta = (timer["expires_at"] - datetime.datetime.utcnow()).total_seconds()

                    obj = Timer.from_record(timer)
                    if delta <= 0:
                        await self.dispatch(obj)
                        continue

                    self.bot.loop.call_later(delta, lambda: self.queue.put_nowait(obj))

    async def dispatch(self, timer):
        self.bot.dispatch(f"{timer.name}_complete", timer)

        async with self.bot.db.acquire() as db:
            query = """
            DELETE FROM times
            WHERE id = $1;
            """

            await db.execute(query, timer.id)

    async def create_timer(self, name_, expire_at_, **kwargs):
        async with self.bot.db.acquire() as db:
            query = """
            INSERT INTO times (name, expires_at, args) 
            VALUES ($1, $2, $3::jsonb)
            RETURNING id;
            """

            timer_id = await db.fetchval(query, name_, expire_at_, json.dumps(kwargs))

        obj = Timer(timer_id, name_, expire_at_, kwargs)

        delta = (expire_at_ - datetime.datetime.utcnow()).total_seconds()

        if delta <= 0:
            await self.dispatch(obj)
            return

        self.bot.loop.call_later(delta, lambda: self.queue.put_nowait(obj))

        return obj
