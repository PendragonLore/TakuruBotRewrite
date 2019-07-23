import asyncio
import logging

import aiohttp
from lru import LRU

try:
    import ujson as json
except ImportError:
    import json

LOG = logging.getLogger("utils.ezrequests")


class WebException(Exception):
    __slots__ = ("r", "status", "data")

    def __init__(self, response, data):
        self.r = response
        self.status = self.r.status
        self.data = data

        super().__init__(f"{self.r.method} {self.r.url} responded with HTTP status code {self.status}\n{self.data}")


class EasyRequests:
    __slots__ = ("bot", "loop", "session", "lock", "cache")

    def __init__(self, bot, session):
        self.bot = bot
        self.loop = bot.loop
        self.session = session

        self.lock = asyncio.Lock(loop=bot.loop)
        self.cache = LRU(64)

    @classmethod
    async def start(cls, bot):
        session = aiohttp.ClientSession(loop=bot.loop, headers=bot.http_headers, json_serialize=json.dumps)
        LOG.info("Session opened.")
        return cls(bot, session)

    def fmt_cache(self, m, url, param):
        p = ":".join([f"{k}:{v}" for k, v in param.items()])
        return f"{m}:{url}:{p}"

    def clear_cache(self, new_size=64):
        self.cache = LRU(new_size)

        LOG.info("Cleared cache, size set to %s", new_size)

    async def request(self, __method, __url, *, cache=False, **params):
        async with self.lock:
            check = self.cache.get(self.fmt_cache(__method, __url, params), None)
            if check and cache:
                LOG.debug("%s %s Got %s from cache", __method, __url, check)
                return check

            kwargs = {k.lstrip("_"): v for k, v in params.items() if k.startswith("__")}
            cache_params = params.copy()

            for key in cache_params.keys():
                if key.startswith("__"):
                    del params[key]

            async with self.session.request(__method, __url, params=params, **kwargs) as r:
                if "application/json" in r.headers["Content-Type"]:
                    data = await r.json(loads=json.loads)
                elif "text/" in r.headers["Content-Type"]:
                    data = await r.text("utf-8")
                else:
                    data = await r.read()

                request_fmt = f"{r.status} {r.method} {r.url}"

                LOG.debug("%s returned %s", request_fmt, data)

                if 300 > r.status >= 200 or __url == "https://www.zerochan.net/search":
                    LOG.info("%s succeeded", request_fmt)
                    if cache:
                        self.cache[self.fmt_cache(__method, __url, cache_params)] = data
                        LOG.debug("%s Inserted data into cache", request_fmt)
                    return data

                if r.status == 429:
                    LOG.warning("%s RATE LIMITED", request_fmt)
                    raise WebException(r, data)

                if r.status in {500, 502}:
                    LOG.warning("%s INTERNAL ERROR", request_fmt)
                    raise WebException(r, data)

                LOG.error("%s errored.", request_fmt)
                raise WebException(r, data)

    async def close(self):
        LOG.info("Session closed.")
        await self.session.close()
