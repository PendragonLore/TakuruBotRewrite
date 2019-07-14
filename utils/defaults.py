from discord.ext import commands, flags


class Author(flags.ParamDefault):
    async def default(self, ctx):
        return ctx.author


class CurrentTextChannel(flags.ParamDefault):
    async def default(self, ctx):
        return ctx.channel


class FirstAttachment(flags.ParamDefault):
    def __init__(self, with_filename=False):
        self.with_name = with_filename

    async def default(self, ctx):
        try:
            att = ctx.message.attachments[0]

            if self.with_name:
                return att.url, att.filename
            return att.url
        except IndexError:
            raise commands.BadArgument("No attachment or argument provided.")


class CurrentVoiceChannel(flags.ParamDefault):
    async def default(self, ctx):
        state = ctx.author.voice
        if state is not None:
            return state.channel
        raise commands.BadArgument("Not connected to a voice channel and none provided.")
