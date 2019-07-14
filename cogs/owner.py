from discord.ext import commands

from utils.emotes import FESTIVE, KAZ_HAPPY


class Owner(commands.Cog):
    """Owner only commands."""

    def cog_check(self, ctx):
        if not ctx.author.id == ctx.bot.owner_id:
            raise commands.NotOwner("You are not my owner.")

        return True

    @commands.command(name="blacklist", hidden=True)
    async def blacklist(self, ctx, thing: str, id_: int):
        s = getattr(ctx.bot, f"blacklisted_{thing}s")
        if id_ not in s:
            s.add(id_)
            await ctx.bot.redis("SADD", f"blacklisted_{thing}s", str(id_))
            await ctx.add_reaction(FESTIVE)
        else:
            s.remove(id_)
            await ctx.bot.redis("SREM", f"blacklister_{thing}s", str(id_))
            await ctx.add_reaction(KAZ_HAPPY)


def setup(bot):
    bot.add_cog(Owner())
