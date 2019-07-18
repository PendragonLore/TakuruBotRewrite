import asyncio
import subprocess

from jishaku import cog
from jishaku.exception_handling import ReplResponseReactor, attempt_add_reaction, do_after_sleep, send_traceback

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


class Jishaku(cog.Jishaku):
    pass


def setup(bot):
    bot.add_cog(Jishaku(bot))
