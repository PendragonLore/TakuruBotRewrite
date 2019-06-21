from discord.ext import commands, flags


class Author(flags.ParamDefault):
    async def default(self, ctx):
        return ctx.author


class CurrentTextChannel(flags.ParamDefault):
    async def default(self, ctx):
        return ctx.channel


class FirstAttachment(flags.ParamDefault):
    async def default(self, ctx):
        try:
            return ctx.message.attachments[0].url
        except IndexError:
            raise commands.BadArgument("No attachment or argument provided.")
