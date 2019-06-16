import asyncio
import subprocess

from jishaku import cog
from jishaku.exception_handling import ReplResponseReactor, attempt_add_reaction, do_after_sleep, send_traceback

import utils
from utils.emotes import ARI_DERP, FORWARD, KAZ_HAPPY, ONE_POUT, POPULAR


class AltReplReactor(ReplResponseReactor):
    async def __aenter__(self):
        self.handle = self.loop.create_task(do_after_sleep(1, attempt_add_reaction, self.message, FORWARD))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.handle:
            self.handle.cancel()
        if not exc_val:
            await attempt_add_reaction(self.message, KAZ_HAPPY)
            return
        self.raised = True
        if isinstance(exc_val, (asyncio.TimeoutError, subprocess.TimeoutExpired)):
            await attempt_add_reaction(self.message, POPULAR)
            await send_traceback(self.message.channel, 0, exc_type, exc_val, exc_tb)
        elif isinstance(exc_val, SyntaxError):
            await attempt_add_reaction(self.message, ARI_DERP)
            await send_traceback(self.message.channel, 0, exc_type, exc_val, exc_tb)
        else:
            await attempt_add_reaction(self.message, ONE_POUT)
            await send_traceback(self.message.author, 8, exc_type, exc_val, exc_tb)
        return True


cog.JISHAKU_RETAIN = True
cog.ReplResponseReactor = AltReplReactor


jsk = cog.Jishaku.jsk


class Jishaku(cog.Jishaku):
    @jsk.command(name="sql")
    async def jsk_sql(self, ctx, *, query: utils.Codeblock):
        """Run a SQL query."""
        is_not_select = query.count("SELECT") == 0
        async with ctx.db.acquire() as db:
            if is_not_select:
                request = db.execute
            else:
                request = db.fetch

            results = await request(query)

        if is_not_select:
            return await ctx.send(results)

        headers = list(results[0].keys())
        table = utils.Tabulator()
        table.set_columns(headers)
        table.add_rows(list(r.values()) for r in results)
        render = table.render()

        fmt = f"```\n{render}\n```"

        await ctx.send(fmt)

    # from Adventure! https://github.com/XuaTheGrate/Adventure xuadontkillmepleaseee
    @jsk.command(name="redis")
    async def jsk_redis(self, ctx, *args):
        """Run a redis command."""
        try:
            ret = await ctx.bot.redis(*args)
            await ctx.send(ret)
        except Exception as exc:
            await ctx.add_reaction(ARI_DERP)
            raise exc
        else:
            await ctx.add_reaction(KAZ_HAPPY)


def setup(bot):
    bot.add_cog(Jishaku(bot))
