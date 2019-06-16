import random
from typing import Optional

import discord
from discord.ext import commands
from numpy.random import choice

import utils
from utils.emotes import BACKWARDS, FORWARD, POPULAR


class FunStuff(commands.Cog, name="Fun",
               command_attrs=dict(cooldown=commands.Cooldown(1, 2.5, commands.BucketType.user))):
    """Fun stuff, I think."""

    @commands.command(name="dog", aliases=["dogs", "doggos", "doggo"])
    async def dogs(self, ctx, amount: Optional[int] = 1):
        """Get a random dog image, up to 50 per command."""
        if amount > 50:
            return await ctx.send("You can only get up to 50 dog pics at a time.")

        dogs = await ctx.get(f"https://dog.ceo/api/breeds/image/random/{amount}")

        for dog in dogs["message"]:
            embed = discord.Embed(color=discord.Color(0x008CFF))
            embed.set_image(url=dog)

            ctx.pages.add_entry(embed)

        await ctx.paginate()

    @commands.command(name="cat", aliases=["cats"])
    @utils.requires_config("tokens", "apis", "catapi")
    async def cats(self, ctx, amount: Optional[int] = 1):
        """Get a random cat image, up to 100 per command."""
        if amount > 100:
            return await ctx.send("You can only get up to 100 cat pics at a time.")

        headers = (("x-api-key", ctx.bot.config.tokens["apis"]["catapi"]),)

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
            f"**Question**: {question}\nAll signs point to "
            f"{FORWARD} **{random.choice(possible_responses)}** {BACKWARDS}"
        )

    @commands.command(name="owoify")
    async def owoify(self, ctx, *, text: commands.clean_content):
        """Owoify some text ~~*send help*~~."""
        owo_chars = ["w", "u", "owo", "uwu", "ww", "n", "nya"]
        owod = "".join(choice([x, random.choice(owo_chars)], replace=True, p=[0.80, 0.20]) for x in text)
        await ctx.send(owod)

    @commands.command(name="mock")
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
