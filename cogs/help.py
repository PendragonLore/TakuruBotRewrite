from discord.ext import commands

from utils.help_command import TakuruHelpCommand


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._original_help_command = bot.help_command
        bot.help_command = TakuruHelpCommand(
            verify_checks=True,
            show_hidden=False,
            aliases_heading="Aliases",
            command_attrs=dict(
                cooldown=commands.Cooldown(1, 2.5, commands.BucketType.user),
                hidden=True
            ),
            paginator=commands.Paginator(max_size=1000, prefix=None, suffix=None)
        )
        self.bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._original_help_command


def setup(bot):
    bot.add_cog(Help(bot))
