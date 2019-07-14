import random
from typing import Optional

import discord
from discord.ext import commands

import utils
from utils.emotes import BACKWARDS, FORWARD, POPULAR


class FunStuff(commands.Cog, name="Fun",
               command_attrs=dict(cooldown=commands.Cooldown(1, 2.5, commands.BucketType.user))):
    """Fun stuff, I think."""

    CHARS_MAP = {'a': ':regional_indicator_a:', 'b': ':regional_indicator_b:', 'c': ':regional_indicator_c:',
                 'd': ':regional_indicator_d:', 'e': ':regional_indicator_e:', 'f': ':regional_indicator_f:',
                 'g': ':regional_indicator_g:', 'h': ':regional_indicator_h:', 'i': ':regional_indicator_i:',
                 'j': ':regional_indicator_j:', 'k': ':regional_indicator_k:', 'l': ':regional_indicator_l:',
                 'm': ':regional_indicator_m:', 'n': ':regional_indicator_n:', 'o': ':regional_indicator_o:',
                 'p': ':regional_indicator_p:', 'q': ':regional_indicator_q:', 'r': ':regional_indicator_r:',
                 's': ':regional_indicator_s:', 't': ':regional_indicator_t:', 'u': ':regional_indicator_u:',
                 'v': ':regional_indicator_v:', 'w': ':regional_indicator_w:', 'x': ':regional_indicator_x:',
                 'y': ':regional_indicator_y:', 'z': ':regional_indicator_z:', '1': ':one:', '2': ':two:',
                 '3': ':three:', '4': ':four:', '5': ':five:', '6': ':six:', '7': ':seven:', '8': ':eight:',
                 '9': ':nine:', "#": ":hash:", "*": ":asterisk:"}

    @commands.command(name="emojitext")
    async def emojitext(self, ctx, *, text: commands.clean_content(fix_channel_mentions=True)):
        actual = []

        for char in text:
            maybe_emote = self.CHARS_MAP.get(char.lower())

            if maybe_emote is None:
                actual.append(char)
            else:
                actual.append(maybe_emote + "\u200b")
        try:
            await ctx.send("".join(actual))
        except discord.HTTPException:
            await ctx.send("Content too long, sorry.")

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
        """Make the bot rate something."""
        random.seed(utils.make_seed(thing))

        await ctx.send(f"I rate `{thing}` a **{random.randint(0, 10)} out of 10**.")

    @commands.command()
    async def mock(self, ctx, *, text: commands.clean_content):
        """Mock."""
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
