import discord
from discord.ext import commands

import utils


class RightSiderContext(commands.Context):
    __slots__ = (
        "pages",
    )

    def __init__(self, **attrs):
        super().__init__(**attrs)

        self.pages = utils.Paginator(self)

    @property
    def db(self):
        return self.bot.db

    @property
    def player(self):
        return self.bot.wavelink.get_player(self.guild.id, cls=utils.Player)

    async def paginate(self, *, embed: bool = True):
        await self.pages.paginate(embed=embed)

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

        return await self.send(f"{ex} <{url}>", **kwargs)

    async def add_reaction(self, emote):
        try:
            return await self.message.add_reaction(emote)
        except discord.HTTPException:
            pass
