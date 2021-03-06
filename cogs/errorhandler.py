import traceback

import discord
import sentry_sdk
from discord.ext import commands

from utils.emotes import ARI_DERP, YAM_SAD
from utils.ezrequests import WebException
from utils.formats import PaginationError


class CommandHandler(commands.Cog):
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
            await ctx.send(f"The command is currently on cooldown, retry in **{error.retry_after:.2f}** seconds.")

        elif isinstance(exc, (commands.UserInputError, commands.BotMissingPermissions, commands.MissingPermissions)):
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
                with sentry_sdk.push_scope() as scope:
                    scope.set_tag("guild", f"{ctx.guild} ({ctx.guild.id})")
                    scope.set_tag("channel", f"#{ctx.channel} ({ctx.guild.id})")
                    scope.set_tag("command", ctx.command.qualified_name)
                    scope.set_tag("author", f"{ctx.author} ({ctx.author.id})")
                    sentry_sdk.capture_exception(exc)
            traceback.print_exception(type(error), error, error.__traceback__)

            stack = 8
            traceback_text = traceback.format_exception(type(error), error, error.__traceback__, stack)
            paginator = commands.Paginator(prefix="```py", suffix="```", max_size=1990)

            for page in traceback_text:
                paginator.add_line(page.lstrip(" \n"))

            for page in paginator.pages:
                await ctx.bot.owner.send(page)

        # await ctx.send(f"An uncaught error occured in {ctx.command}")


def setup(bot):
    bot.add_cog(CommandHandler(bot))
