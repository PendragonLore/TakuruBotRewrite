import pickle
import random
from collections import Counter

from discord.ext import commands


class Markov(commands.Cog):
    """Markov memes lul."""

    def __init__(self, bot):
        self.bot = bot

        with open("markov.pack", "rb") as f:
            self.data = {}
            for k, v in pickle.load(f).items():
                del v[None]
                self.data.update({k: v})

    def cog_unload(self):
        with open("markov.pack", "wb+") as f:
            f.write(pickle.dumps(self.data))

    def cog_check(self, ctx):
        return ctx.guild in self.bot.config.markov_guilds

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.content or message.author.bot:
            return

        if message.guild is None or message.guild.id not in self.bot.config.markov_guilds:
            return

        before = None
        for word in message.content.split():
            actual = word.strip(" \n\r")
            if actual not in self.data:
                self.data[actual] = Counter()
            if before is not None:
                self.data[actual][before] += 1
            before = actual

    @commands.command(name="mlog")
    async def mlog(self, ctx):
        before = None
        maxlen = random.randint(5, 13)
        entries = []

        while len(entries) < maxlen:
            word = self.get_next_word(before).strip(" \n\r")

            before = word

            entries.append(word)

        result = " ".join(entries)
        await ctx.send(await self.normalize(ctx, result))

    async def normalize(self, ctx, phrase):
        phrase += ("." if not phrase.endswith((".", "!", "-", "?")) else "")

        cleaned = await commands.clean_content(use_nicknames=False).convert(ctx, phrase)

        cleaned = cleaned[0].upper() + cleaned[1:]

        return cleaned

    def get_next_word(self, before):
        elements = list(self.data[before].elements())
        if before not in self.data or not elements:
            rand = random.choice(list(self.data.keys()))
        else:
            rand = random.choice(elements)
        return rand


def setup(bot):
    bot.add_cog(Markov(bot))
