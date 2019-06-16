import re

from discord.ext import commands


class Codeblock(commands.Converter):
    __slots__ = (
        "pass_lang",
    )

    CODEBLOCK_REGEX = re.compile("^(?:```([A-Za-z0-9\\-\\.]*)\n)?(.+?)(?:```)?$", re.S)

    def __init__(self, pass_lang=False):
        self.pass_lang = pass_lang

    async def convert(self, ctx, argument):
        match = self.CODEBLOCK_REGEX.match(argument)

        if not match or not match.group(0):
            raise commands.BadArgument("Invalid codeblock structure.")

        if self.pass_lang:
            return match.group(1), match.group(2)

        return match.group(2)
