import asyncio
import datetime
import operator

from discord.ext import tasks

import utils

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

        self._lock = asyncio.Lock(loop=bot.loop)
        self._waiters = []

        self.fetch_timers.start()

    def cleanup(self):
        for _, waiter in self._waiters:
            waiter.cancel()
        self._waiters.clear()
        self.fetch_timers.cancel()

    @tasks.loop()
    async def fetch_timers(self):
        timer = await self.queue.get()

        self.queue.task_done()

        await self.dispatch(timer)

    @fetch_timers.before_loop
    async def before_fetch_timers(self):
        async with utils.acquire_transaction(self.bot.db) as db:
            async for timer in db.cursor("SELECT * FROM times;"):
                delta = (timer["expires_at"] - datetime.datetime.utcnow()).total_seconds()

                obj = Timer.from_record(timer)
                if delta <= 0:
                    await self.dispatch(obj)
                    continue

                waiter = self.bot.loop.call_later(delta, lambda: self.queue.put_nowait(obj))
                self._waiters.append((obj, waiter))

    async def dispatch(self, timer):
        self.bot.dispatch(f"{timer.name}_complete", timer)

        await self.delete_timer(timer.id)

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

        waiter = self.bot.loop.call_later(delta, lambda: self.queue.put_nowait(obj))

        self._waiters.append((obj, waiter))

        return obj

    async def delete_timer(self, timer_id):
        # idk if a race condition is possible but w/e.
        async with self._lock:
            for index, (timer, waiter) in enumerate(self._waiters):
                if timer.id == timer_id:
                    break
            else:
                raise TypeError("err err not found")

            if not waiter.cancelled():
                waiter.cancel()

            self._waiters.pop(index)
            async with self.bot.db.acquire() as db:
                query = """
                DELETE FROM times
                WHERE id = $1;
                """

                await db.execute(query, timer_id)

            return timer
