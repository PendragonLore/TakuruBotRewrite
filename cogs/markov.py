import random
import typing

import aiofiles  # Using aiofiles because I'm way too lazy to rewrite this for DB integration.
from discord.ext import commands
from markovchain.text import MarkovText


class Markov(commands.Cog):
    """Markov memes lul."""

    def __init__(self, bot):
        self.bot = bot
        self.punctuation = ["!", ".", "?", "-"]

    @commands.Cog.listener()
    async def on_message(self, message):
        await self.markovlogging(message)

    async def markovlogging(self, message):
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return
        if message.author.bot:
            return
        if not message.content or message.guild.id not in self.bot.config.markov_guilds:
            return

        prefixes = [".", "f?", "h?", "!", ";", "=", "--", "%", "?"]
        if any(message.content.lower().startswith(prefix) for prefix in prefixes):
            return

        await self.do_log(message.clean_content)

    @commands.command(hidden=True)
    async def mlog(self, ctx, *, message: typing.Optional[str]):
        """Respond to a message with a Markov chain."""
        if ctx.guild.id not in self.bot.config.markov_guilds:
            raise commands.CheckFailure()

        if message:
            await self.do_log(await commands.clean_content().convert(ctx, message))

        await self.markovgen(ctx)

    async def markovgen(self, ctx):
        randomized_int = random.randint(1, 602)
        async with aiofiles.open(f"markov/markov ({randomized_int}).txt") as f:
            text = MarkovText()
            async for line in f:
                text.data(line, part=True)

        clean = await commands.clean_content(fix_channel_mentions=True).convert(ctx, text())
        await ctx.send(clean)

    async def do_log(self, msg):
        randomized_int = random.randint(1, 602)

        async with aiofiles.open(f"markov/markov ({randomized_int}).txt", "a+") as f:
            dot = "."
            if len(msg) <= 3 or any(punct in msg for punct in ["!", ".", "?", "-"]):
                dot = ""

            await f.write(f"{msg}{dot}\n")

    @mlog.error
    async def mlog_handler(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("This command is locked to a few selected guilds.")


def setup(bot):
    bot.add_cog(Markov(bot))
