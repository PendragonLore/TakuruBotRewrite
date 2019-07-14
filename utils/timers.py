import hashlib
import logging

import aioredis
from discord.ext import commands, tasks

LOG = logging.getLogger("utils.timers")


class TimerManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.channel = None

        db = self.bot.redis.db
        self._channel_fmt = f"__keyevent@{db}__:expired"

        self.fetch_timers.add_exception_type(aioredis.ChannelClosedError)
        self.fetch_timers.add_exception_type(aioredis.PoolClosedError)
        self.fetch_timers.start()

    @tasks.loop(reconnect=True)
    async def fetch_timers(self):
        key = await self.channel.get(encoding="utf-8")

        if key and str(key).startswith("timer-"):
            tr = self.bot.redis.multi_exec()

            tr.hgetall(f"lookup-{key}")
            tr.delete(f"lookup-{key}")

            kwargs, _ = await tr.execute()

            try:
                name = kwargs.pop("name")
            except KeyError:
                LOG.warning("Timer with args %s doesn't have a name field, discarding.", kwargs)
            else:
                LOG.info("Dispatching timer %s with args %s. SHA256: %s", name, kwargs, key.split(":")[-1])
                self.bot.dispatch(f"{name}_complete", kwargs)

    @fetch_timers.before_loop
    async def before_fetch_timers(self):
        await self.bot.wait_until_ready()

        self.channel = (await self.bot.redis.subscribe(self._channel_fmt))[0]

    @fetch_timers.after_loop
    async def after_fetch_timers(self):
        try:
            await self.bot.redis.unsubscribe(self._channel_fmt)
        except (aioredis.PoolClosedError, RuntimeError, aioredis.ConnectionForcedCloseError,
                aioredis.ChannelClosedError, aioredis.ConnectionClosedError):
            pass

    async def create_timer(self, name_, time_, **kwargs):
        h = self._gen_hash(kwargs)
        kwargs["name"] = name_

        tr = self.bot.redis.multi_exec()

        tr.hmset_dict(f"timer-{name_}:{h}", **kwargs)
        tr.hmset_dict(f"timer-lookup-{name_}:{h}", **kwargs)
        tr.expire(f"timer-{name_}:{h}", int(time_))

        try:
            ret = await tr.execute()
        except aioredis.MultiExecError:
            raise
        else:
            LOG.info("Created timers with args %s, waiting %d seconds. SHA256: %s", kwargs, int(time_), h)
            return ret

    async def delete_timer(self, name_, **kwargs):
        h = self._gen_hash(kwargs)

        tr = self.bot.redis.multi_exec()

        tr.delete(f"timer-{name_}:{h}")
        tr.delete(f"lookup-timer-{name_}:{h}")

        LOG.info("Deleted timers with args %s. SHA256: %s", kwargs, h)

        return await tr.execute()

    def _gen_hash(self, kwargs):
        return hashlib.sha256(":".join(f"{key}={value}" for key, value in kwargs.items()).encode()).hexdigest()

    def close(self):
        self.fetch_timers.cancel()
