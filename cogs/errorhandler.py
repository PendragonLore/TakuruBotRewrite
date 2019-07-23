import datetime
import inspect
import math
import sys
import traceback

import discord
import sentry_sdk
from discord.ext import commands

from utils.emotes import ARI_DERP, YAM_SAD
from utils.ezrequests import WebException
from utils.formats import PaginationError, Plural


class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.wh = discord.Webhook.from_url(bot.config.wh_url, adapter=discord.AsyncWebhookAdapter(bot.ezr.session))

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return

        exc = getattr(error, "original", error)

        if isinstance(exc, commands.NoPrivateMessage):
            try:
                await ctx.add_reaction(ARI_DERP)
                await ctx.send("This bot is guild only.")
            except discord.HTTPException:
                pass

        elif isinstance(exc, commands.DisabledCommand):
            await ctx.add_reaction(YAM_SAD)
            await ctx.send(f"{ctx.command.qualified_name} has been disabled.")

        elif isinstance(exc, commands.NotOwner):
            await ctx.add_reaction(ARI_DERP)
            await ctx.send(f"You are not my owner.")

        elif isinstance(exc, commands.CommandOnCooldown):
            await ctx.add_reaction(ARI_DERP)
            await ctx.send(f"The command is currently on cooldown, retry in **{error.retry_after:.2f} seconds**.",
                           delete_after=math.ceil(error.retry_after))

        elif isinstance(error, commands.MissingPermissions):
            await ctx.add_reaction(ARI_DERP)

            perms, fmt = self.fmt_perms(error)

            await ctx.send(f"You lack the {perms} {fmt}.")

        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.add_reaction(YAM_SAD)

            perms, fmt = self.fmt_perms(error)

            await ctx.send(f"I lack the {perms} {fmt}.")

        elif isinstance(exc, commands.UserInputError):
            await ctx.add_reaction(ARI_DERP)
            await ctx.send(str(exc))

        elif isinstance(exc, commands.CheckFailure):
            return

        elif isinstance(exc, PaginationError):
            await ctx.add_reaction(ARI_DERP)
            await ctx.send("No pages to paginate.")

        elif isinstance(exc, discord.Forbidden):
            await ctx.add_reaction(YAM_SAD)
            try:
                await ctx.send("I don't have the necessary permissions to do that.")
            except discord.HTTPException:
                pass

        elif isinstance(exc, WebException):
            await ctx.add_reaction(YAM_SAD)
            await ctx.send("Not found or API did not respond.")

        else:
            if ctx.bot.sentry:
                def push_to_sentry():
                    with sentry_sdk.push_scope() as scope:
                        scope.set_tag("guild", f"{ctx.guild} ({ctx.guild.id})")
                        scope.set_tag("channel", f"#{ctx.channel} ({ctx.channel.id})")
                        scope.set_tag("command", ctx.command.qualified_name)
                        scope.set_tag("author", f"{ctx.author} ({ctx.author.id})")
                        sentry_sdk.capture_exception(exc)

                ctx.bot.loop.run_in_executor(None, push_to_sentry)

            traceback.print_exception(type(exc), exc, exc.__traceback__)

            stack = 6
            traceback_text = traceback.format_exception(type(exc), exc, exc.__traceback__, stack)

            embed = discord.Embed(title="Command Error", timestamp=datetime.datetime.utcnow(),
                                  color=discord.Color.red())

            embed.description = "```py\n" + "".join(traceback_text) + "```"
            embed.add_field(name="Metadata", value=(f"**Command**: `{ctx.command.qualified_name}`\n"
                                                    f"**Guild**: `{ctx.guild.id}`\n"
                                                    f"**Channel**: `{ctx.channel.id}`\n"
                                                    f"**Author**: `{ctx.author.id}`"))

            actual = ctx.args + list(ctx.kwargs.values())
            args = "\n".join([f"**{k}** = `{v}`" for k, v in
                              zip(inspect.signature(ctx.command.callback).parameters.keys(), actual)])
            embed.add_field(name="Args", value=f"{args}")
            await self.wh.send(embed=embed)

        # await ctx.send(f"An uncaught error occured in {ctx.command}")

    def fmt_perms(self, error):
        p = ", ".join([x.replace("_", " ") for x in error.missing_perms])
        f = format(Plural(len(error.missing_perms)), "permission").lstrip(" 0123456789")

        return p, f

    @commands.Cog.listener()
    async def on_error(self, event_name, *args, **kwargs):
        _, exc, _ = sys.exc_info()

        def push_to_sentry():
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("event_name", event_name)
                sentry_sdk.capture_exception(exc)

        await self.bot.loop.run_in_executor(None, push_to_sentry)

        embed = discord.Embed(title=event_name)
        embed.description = "".join(traceback.format_exc())
        embed.add_field(name="Args", value="\n".join([repr(x) for x in args]))
        embed.add_field(name="Args", value="\n".join([f"{k}={v!r}" for k, v in kwargs.items()]))

        await self.wh.send(embed=embed)


def setup(bot):
    bot.add_cog(ErrorHandler(bot))
