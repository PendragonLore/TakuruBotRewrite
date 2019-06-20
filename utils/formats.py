import asyncio
import functools

import discord
from discord.ext import commands


class PaginationError(Exception):
    pass


class Paginator:
    __slots__ = (
        "ctx",
        "bot",
        "user",
        "channel",
        "msg",
        "execute",
        "embed",
        "max_pages",
        "entries",
        "paginating",
        "current",
        "reactions",
    )

    def __init__(self, ctx, embed: bool = True):
        self.ctx = ctx
        self.bot = ctx.bot
        self.user = ctx.author
        self.channel = ctx.channel
        self.msg = ctx.message

        perms = self.channel.permissions_for(self.ctx.me)
        missing = [perm for perm, value in perms
                   if perm in {"add_reaction", "embed_links", "read_message_history"} and not value]
        if missing:
            raise commands.BotMissingPermissions(missing)

        self.execute = None
        self.entries = []
        self.embed = embed
        self.max_pages = None
        self.paginating = True
        self.current = 0
        self.reactions = [
            ("\N{BLACK LEFT-POINTING TRIANGLE}", self.backward),
            ("\N{BLACK RIGHT-POINTING TRIANGLE}", self.forward),
            ("\N{BLACK SQUARE FOR STOP}", functools.partial(self.stop, delete=True)),
            ("\N{INFORMATION SOURCE}", self.info),
        ]

    def add_entry(self, entry):
        self.entries.append(entry)

    async def setup(self):
        if not self.entries:
            e = PaginationError("No pagination entries.")
            raise commands.CommandInvokeError(e) from e

        if self.embed is False:
            try:
                self.msg = await self.channel.send(self.entries[0])
            except AttributeError:
                await self.channel.send(self.entries)
        else:
            for page, embed in enumerate(self.entries, 1):
                embed.set_author(name=f"Page {page} of {len(self.entries)}")
            try:
                self.msg = await self.channel.send(embed=self.entries[0])
            except (AttributeError, TypeError):
                await self.channel.send(embed=self.entries)

        if len(self.entries) == 1:
            return

        self.max_pages = len(self.entries) - 1

        for (r, _) in self.reactions:
            await self.msg.add_reaction(r)

    async def alter(self, page: int):
        try:
            await self.msg.edit(embed=self.entries[page])
        except (AttributeError, TypeError):
            await self.msg.edit(content=self.entries[page])

    async def backward(self):
        """takes you to the previous page or the last if used on the first one."""
        if self.current == 0:
            self.current = self.max_pages
            await self.alter(self.current)
        else:
            self.current -= 1
            await self.alter(self.current)

    async def forward(self):
        """takes you to the next page or the first if used on the last one."""
        if self.current == self.max_pages:
            self.current = 0
            await self.alter(self.current)
        else:
            self.current += 1
            await self.alter(self.current)

    async def stop(self, *, delete=False):
        """stops the paginator session."""
        try:
            if delete:
                await self.msg.delete()
            else:
                await self.msg.clear_reactions()
        except discord.HTTPException:
            pass
        finally:
            self.paginating = False

    async def info(self):
        """shows this page."""
        embed = discord.Embed(color=discord.Color(0x008CFF))

        embed.set_author(name="Instructions")

        embed.description = (
            "This is a reaction paginato,; when you react to one of the buttons below "
            "the message gets edited. Below you will find what the reactions do."
        )

        for emoji, func in self.reactions:
            embed.add_field(name=emoji, value=f"This reaction {func.__doc__}", inline=False)

        await self.msg.edit(embed=embed)

    def check(self, reaction, user):
        if user.id != self.user.id:
            return False

        if reaction.message.id != self.msg.id:
            return False

        for (emoji, func) in self.reactions:
            if reaction.emoji == emoji:
                self.execute = func
                return True
        return False

    async def paginate(self):
        await self.setup()

        while self.paginating:
            done, pending = await asyncio.wait(
                [
                    self.bot.wait_for("reaction_add", check=self.check),
                    self.bot.wait_for("reaction_remove", check=self.check),
                ],
                return_when=asyncio.FIRST_COMPLETED, timeout=120
            )

            try:
                exc = done.pop().exception()
            except KeyError:
                return await self.stop()
            else:
                if isinstance(exc, (discord.HTTPException, asyncio.TimeoutError)):
                    return await self.stop()

            for future in pending:
                future.cancel()

            await self.execute()


class Tabulator:
    __slots__ = ("_widths", "_columns", "_rows")

    def __init__(self):
        self._widths = []
        self._columns = []
        self._rows = []

    def set_columns(self, columns):
        self._columns = columns
        self._widths = [len(c) + 2 for c in columns]

    def add_row(self, row):
        rows = [str(r) for r in row]
        self._rows.append(rows)
        for index, element in enumerate(rows):
            width = len(element) + 2
            if width > self._widths[index]:
                self._widths[index] = width

    def add_rows(self, rows):
        for row in rows:
            self.add_row(row)

    def render(self):
        sep = "╬".join("═" * w for w in self._widths)
        sep = f"╬{sep}╬"

        to_draw = [sep]

        def get_entry(d):
            elem = "║".join(f"{e:^{self._widths[i]}}" for i, e in enumerate(d))
            return f"║{elem}║"

        to_draw.append(get_entry(self._columns))
        to_draw.append(sep)

        for row in self._rows:
            to_draw.append(get_entry(row))

        to_draw.append(sep)
        return "\n".join(to_draw)
