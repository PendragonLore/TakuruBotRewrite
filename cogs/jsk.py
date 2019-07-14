import asyncio
import importlib
import pathlib
import subprocess
import sys
import traceback

from discord.ext import commands, ui
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

        if not results:
            return await ctx.send("no results")

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
            ret = await ctx.bot.redis.execute(*args)
            await ctx.send(ret)
        except Exception as exc:
            await ctx.add_reaction(ARI_DERP)
            raise exc
        else:
            await ctx.add_reaction(KAZ_HAPPY)

    def check_module(self, module):
        if module.stem == "jsk":
            return False
        if module.stem.startswith("__"):
            return False
        if not module.suffix == ".py":
            return False
        return True

    def fetch_modules(self):
        utils_path = pathlib.Path("./utils")

        for util in utils_path.iterdir():
            if self.check_module(util):
                yield (True, f"{util.parent}.{util.stem}")

        cog_path = pathlib.Path("./cogs")

        for ext in cog_path.iterdir():
            if self.check_module(ext):
                yield (False, f"{ext.parent}.{ext.stem}")

    def reload_or_load_ext(self, module):
        try:
            self.bot.reload_extension(module)
        except commands.ExtensionNotLoaded:
            self.bot.load_extension(module)

    @jsk.command(name="reload-all")
    async def jsk_reload_all(self, ctx):
        try:
            resp = await ui.prompt(ctx, "Ya sure?", timeout=10)
        except asyncio.TimeoutError:
            return await ctx.send("Not doing it then.")
        else:
            if not resp.lower() == "ye":
                return await ctx.send("Not doing it then.")

        status = []
        for is_util, module in self.fetch_modules():
            if is_util:
                try:
                    actual = sys.modules[module]
                except KeyError:
                    status.append(f"\U0000274c **{module}**")
                else:
                    try:
                        importlib.reload(actual)
                    except Exception:
                        status.append(f"\U0000274c **{module}**")
                        traceback.print_exc()
                    else:
                        status.append(f"\U00002705 **{module}**")
            else:
                try:
                    self.reload_or_load_ext(module)
                except commands.ExtensionError:
                    status.append(f"\U0000274c **{module}**")
                else:
                    status.append(f"\U00002705 **{module}**")

        await self.bot.owner.send("\n".join(status))


def setup(bot):
    bot.add_cog(Jishaku(bot))
