import random
from typing import Optional

import discord
import numpy
from discord.ext import commands

import utils
from utils.emotes import BACKWARDS, FORWARD, POPULAR


class FunStuff(commands.Cog, name="Fun",
               command_attrs=dict(cooldown=commands.Cooldown(1, 2.5, commands.BucketType.user))):
    """Fun stuff, I think."""

    @commands.command(name="dog", aliases=["dogs", "doggos", "doggo"])
    async def dogs(self, ctx, amount: Optional[lambda x: min(int(x), 50)] = 1):
        """Get a random dog image, up to 50 per command."""
        dogs = await ctx.get(f"https://dog.ceo/api/breeds/image/random/{amount}")

        for dog in dogs["message"]:
            embed = discord.Embed(color=discord.Color(0x008CFF))
            embed.set_image(url=dog)

            ctx.pages.add_entry(embed)

        await ctx.paginate()

    @commands.command(name="cat", aliases=["cats"])
    @utils.requires_config("tokens", "apis", "catapi")
    async def cats(self, ctx, amount: Optional[lambda x: min(int(x), 100)] = 1):
        """Get a random cat image, up to 100 per command."""
        headers = (("x-api-key", ctx.bot.config.tokens.apis.catapi),)

        cats = await ctx.get("https://api.thecatapi.com/v1/images/search", limit=amount, __headers=headers)

        for cat in cats:
            embed = discord.Embed(color=discord.Color(0x008CFF))
            embed.set_image(url=cat["url"])

            ctx.pages.add_entry(embed)

        await ctx.paginate()

    @commands.command(name="lenny")
    async def lenny(self, ctx):
        """Get a random lenny."""
        lennies = [
            "( ͡° ͜ʖ ͡°)",
            "( ͡~ ͜ʖ ͡°)",
            "( ͡° ͜ʖ ͡ °)",
            "(˵ ͡~ ͜ʖ ͡°˵)ﾉ⌒♡*:･。.",
            "(∩ ͡° ͜ʖ ͡°)⊃━☆─=≡Σ((( つ◕ل͜◕)つ",
            "( ͡ ͡° ͡°  ʖ ͡° ͡°)",
            "ヽ(͡◕ ͜ʖ ͡◕)ﾉ",
            "(ಥ ͜ʖಥ)╭∩╮",
            "( ͡° ͜ʖ ͡°) ╯︵ ┻─┻",
            "┬──┬ ノ( ͡° ل͜ ͡°ノ)",
            "( ͡° ▽ ͡°)爻( ͡° ل͜ ͡° ☆)",
        ]
        await ctx.send(random.choice(lennies))

    @commands.command(name="8ball")
    async def eight_ball(self, ctx, *, question: commands.clean_content):
        """Answer questions."""
        possible_responses = ["no.", "maybe.", "dumb.", "yes.", "idk.", "meh."]

        random.seed(utils.make_seed(question))
        await ctx.send(
            f"**Question**: {question}\nAll signs point to\n\n"
            f"{FORWARD} **{random.choice(possible_responses):^14}** {BACKWARDS}"
        )

    @commands.command()
    async def choose(self, ctx, *choices):
        """Make the bot choose something."""
        if not choices or not all(s.strip() for s in choices):
            return await ctx.send("Not enough choices or some are empty.")

        await ctx.send(random.choice(choices))

    @commands.command()
    async def rate(self, ctx, *, thing: commands.clean_content):
        random.seed(utils.make_seed(thing))

        await ctx.send(f"I rate `{thing}` a **{random.randint(0, 10)} out of 10**.")

    @commands.command()
    async def owoify(self, ctx, *, text: commands.clean_content):
        """Owoify some text ~~*send help*~~."""
        owo_chars = ["w", "u", "owo", "uwu", "nya"]
        chars = []

        for x in text:
            if not x.strip():
                chars.append(x)
            else:
                chars.append(numpy.random.choice([x, random.choice(owo_chars)], replace=True,
                                                 p=[0.85, 0.15]))
        owod = "".join(chars)
        await ctx.send(owod)

    @commands.command()
    async def mock(self, ctx, *, text: commands.clean_content):
        """Mock text."""
        mocked = "".join(random.choice([m.upper(), m.lower()]) for m in text)

        await ctx.send(f"{POPULAR} *{mocked}* {POPULAR}")

    @commands.command(name="clap")
    async def clap(self, ctx, *, text: commands.clean_content):
        """:clap:"""
        clap = "\U0001f44f"
        clapped = clap.join(text.split())

        await ctx.send(f"{clap}{clapped}{clap}")


def setup(bot):
    bot.add_cog(FunStuff())
