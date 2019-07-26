import discord
from discord.ext import commands, flags

import utils


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


class FirstAttachmentOrSearchHistoryForImageAlsoMaybeDownloadItTooElseAuthorAvatarIsFine(flags.ParamDefault):
    async def default(self, ctx):
        def check(imdata):
            try:
                mime = discord.utils._get_mime_type_for_image(imdata)
            except discord.InvalidArgument:
                raise commands.BadArgument(f"Invalid attachment type.")

            if mime == "image/webp":
                raise commands.BadArgument("webp images are not supported.")

            return utils.image.ImageIO(imdata)

        try:
            return check(await ctx.message.attachments[0].read())
        except IndexError:
            pass

        maybe_attachments = await ctx.history(limit=20).filter(
            lambda x: x.attachments
        ).map(lambda x: x.attachments).flatten()

        if not maybe_attachments:
            return await utils.image.get_avatar(ctx.author)

        for att in maybe_attachments:
            try:
                return check(await att[0].read())
            except commands.BadArgument:
                pass

        return await utils.image.get_avatar(ctx.author)


class CurrentVoiceChannel(flags.ParamDefault):
    async def default(self, ctx):
        state = ctx.author.voice
        if state is not None:
            return state.channel
        raise commands.BadArgument("Not connected to a voice channel and none provided.")
