import discord
from discord.ext import commands

import utils
from utils.emotes import ARI_DERP, KAZ_HAPPY


class Owner(commands.Cog):
    """Owner only commands."""

    def cog_check(self, ctx):
        if not ctx.author.id == ctx.bot.owner_id:
            raise commands.NotOwner("You are not my owner.")

        return True

    @commands.command(name="sql")
    async def sql(self, ctx, *, query: utils.Codeblock):
        """Run a SQL query."""
        is_not_select = query.lower().count("select") == 0
        async with ctx.db.acquire() as db:
            if is_not_select:
                request = db.execute
            else:
                request = db.fetch

            results = await request(query)

        if is_not_select:
            return await ctx.send(results)

        if not results:
            return await ctx.send("no results")

        headers = list(results[0].keys())
        table = utils.Tabulator()
        table.set_columns(headers)
        table.add_rows(list(r.values()) for r in results)
        render = table.render()

        fmt = f"```\n{render}\n```"

        try:
            await ctx.send(fmt)
        except discord.HTTPException:
            await ctx.post_to_mystbin(fmt, "u bad lol")

    # from Adventure! https://github.com/XuaTheGrate/Adventure xuadontkillmepleaseee
    @commands.command(name="redis")
    async def redis(self, ctx, *args):
        """Run a redis command."""
        try:
            ret = await ctx.bot.redis.execute(*args)
            await ctx.send(ret)
        except Exception as exc:
            await ctx.add_reaction(ARI_DERP)
            raise exc
        else:
            await ctx.add_reaction(KAZ_HAPPY)


def setup(bot):
    bot.add_cog(Owner())
