import asyncio
import itertools
import logging
import os
import pathlib
from collections import Counter
from datetime import datetime

import aioredis
import async_cse
import asyncpg
import discord
import wavelink
from discord.ext import commands

import utils


class RightSiderContext(commands.Context):
    __slots__ = ("pages",)

    def __init__(self, **attrs):
        super().__init__(**attrs)

        self.pages = utils.Paginator(self)

    @property
    def db(self):
        return self.bot.db

    async def send(self, content=None, **kwargs):
        content = content or ""
        if len(content) > 1991 or content.count("\n") > 40:
            return await self.post_to_mystbin(content, "Content was too long so I put it here:")

        return await super().send(content, **kwargs)

    async def paginate(self):
        await self.pages.paginate()

    async def _request(self, __method: str, __url: str, **params):
        return await self.bot.ezr.request(__method, __url, **params)

    async def post(self, *args, **kwargs):
        return await self._request("POST", *args, **kwargs)

    async def get(self, *args, **kwargs):
        return await self._request("GET", *args, **kwargs)

    async def post_to_mystbin(self, content, ex="", **kwargs):
        try:
            haste = await self.post("https://mystb.in/documents", __data=content)
            url = f"https://mystb.in/{haste['key']}"
        except utils.ezrequests.WebException:
            raise commands.BadArgument("mystbin did not respond.")

        return await super().send(f"{ex} <{url}>", **kwargs)

    async def add_reaction(self, emote):
        try:
            return await self.message.add_reaction(emote)
        except discord.HTTPException:
            pass


class TakuruBot(commands.Bot):
    def __init__(self):
        self.prefixes = []
        super().__init__(command_prefix=self.get_custom_prefix,
                         activity=discord.Activity(type=discord.ActivityType.listening, name="positive delusions"),
                         owner_id=371741730455814145)
        self.init_time = INIT_TIME

        self.wavelink = wavelink.Client(self)
        config = utils.Config.from_file("config.json5")
        self.config = config

        self.prefix_dict = {}
        self.gateway_messages = Counter()

        self.http_headers = {"User-Agent": "Python/aiohttp"}

        self.init_cogs = [f"cogs.{ext.stem}" for ext in pathlib.Path("cogs/").glob("*.py")]

        self.db = None
        self._redis = None
        self.ezr = None
        self.pokeapi = None
        self.google_api_keys = itertools.cycle(config.tokens["apis"]["google_custom_search_api_keys"])
        self.google = async_cse.Search(api_key=next(self.google_api_keys))

        self.add_check(self.global_check)
        self.loop.create_task(self.load_init_cogs())

    @property
    def python_lines(self):
        total = 0
        file_amount = 0

        for path, _, _files in os.walk("."):
            for _name in _files:
                file_dir = str(pathlib.PurePath(path, _name))
                if not _name.endswith(".py") or "env" in file_dir:  # ignore env folder and non python files.
                    continue
                file_amount += 1
                with open(file_dir, "r", encoding="utf-8") as file:
                    for line in file:
                        if not line.strip().startswith("#"):
                            total += 1

        return total, file_amount

    @property
    def uptime(self):
        return datetime.utcnow() - INIT_TIME

    async def get_custom_prefix(self, _bot, message):
        return commands.when_mentioned_or(self.prefix_dict.get(message.guild.id, "kur "))(_bot, message)

    async def global_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()

        return True

    async def on_ready(self):
        LOG.info("Bot successfully booted up.")
        LOG.info("Total guilds: %s users: %s", len(self.guilds), len(self.users))

    async def on_message(self, message):
        if message.author.bot:
            return
        if message.content == self.user.mention:
            await message.add_reaction(utils.FESTIVE)

        ctx = await self.get_context(message, cls=RightSiderContext)
        await self.invoke(ctx)

    async def on_command(self, ctx):
        if ctx.guild is not None:
            LOG.info(
                "%s ran command %s in %s in #%s", ctx.message.author, ctx.command.qualified_name, ctx.guild, ctx.channel
            )

    async def on_guild_join(self, guild):
        LOG.info("Joined guild %s with %s members, owner: %s", guild, guild.member_count, guild.owner)

    async def on_guild_remove(self, guild):
        LOG.info("Removed from guild %s with %s members, owner: %s", guild, guild.member_count, guild.owner)

    async def login(self, *args, **kwargs):
        self._redis = await asyncio.wait_for(
            aioredis.create_pool(**self.config.dbs["redis"], loop=self.loop, encoding="utf-8"),
            timeout=20.0, loop=self.loop
        )

        LOG.info("Connected to Redis")
        self.db = await asyncpg.create_pool(**self.config.dbs["psql"], loop=self.loop)
        LOG.info("Connected to Postgres")

        # self.pokeapi = await async_pokepy.Client.connect(loop=self.loop)
        self.ezr = await utils.EasyRequests.start(self)
        LOG.info("Finished setting up API stuff")

        data = await self.db.fetch("SELECT * FROM prefixes;")

        for d in data:
            self.prefix_dict[d["guild_id"]] = d["prefix"]

        LOG.debug("Done fetching and inserting prefixes %s", self.prefix_dict)

        await super().login(*args, **kwargs)

    async def close(self):
        await self.ezr.close()
        # await self.pokeapi.close()
        await asyncio.wait_for(self.db.close(), timeout=20.0, loop=self.loop)
        self._redis.close()
        await self._redis.wait_closed()

        await super().close()

    async def load_init_cogs(self):
        await self.wait_until_ready()
        LOG.info("Loading cogs...")
        for cog in self.init_cogs:
            try:
                self.load_extension(cog)
                LOG.info("Successfully loaded %s", cog)
            except Exception as exc:
                LOG.exception("Failed to load %s [%s: %s]", cog, type(exc).__name__, exc)

    async def redis(self, *args, **kwargs):
        try:
            return await self._redis.execute(*args, **kwargs)
        except aioredis.errors.PoolClosedError:
            return


if __name__ == "__main__":
    INIT_TIME = datetime.utcnow()

    LOG = logging.getLogger("takuru")
    LOG.setLevel(logging.DEBUG)

    fmt = logging.Formatter("{asctime} | {levelname: <8} | {module}:{funcName}:{lineno} - {message}",
                            datefmt="%Y-%m-%d %H:%M:%S", style="{")
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)

    files = logging.FileHandler(filename=f"pokecom/takuru{INIT_TIME}.log", mode="w", encoding="utf-8")
    files.setFormatter(fmt)

    LOG.handlers = [files, stream]

    for name in ["utils.ezrequests"]:
        k = logging.getLogger(name)
        k.setLevel(logging.DEBUG)
        k.handlers = [files, stream]

    bot = TakuruBot()
    bot.loop.set_debug(True)

    try:
        bot.loop.run_until_complete(bot.start(bot.config.tokens["discord"]["kurusu"]))
    except KeyboardInterrupt:
        bot.loop.run_until_complete(bot.close())
    finally:
        bot.loop.close()
        LOG.info("Bot shut down.")
