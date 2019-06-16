import textwrap

from jishaku.help_command import MinimalPaginatorHelp


class TakuruHelpCommand(MinimalPaginatorHelp):
    def get_command_signature(self, command):
        return f"`{self.clean_prefix}{command.qualified_name} {command.signature}`"

    def add_subcommand_formatting(self, command):
        fmt = f"{command.qualified_name} - {command.short_doc}" if command.short_doc else command.qualified_name
        self.paginator.add_line(fmt)

    def add_bot_commands_formatting(self, commands, heading):
        if commands:
            joined = "\u2002".join(c.name for c in commands)
            self.paginator.add_line(f"__**{heading}**__")
            self.paginator.add_line(joined)

    def add_aliases_formatting(self, aliases):
        joined = textwrap.indent(" ".join(["`" + x + "`" for x in aliases]), prefix="    ")
        self.paginator.add_line(f"**{self.aliases_heading}**\n{joined}", empty=True)

    def add_command_formatting(self, command):
        if command.help:
            try:
                self.paginator.add_line(command.help, empty=True)
            except RuntimeError:
                for line in command.help.splitlines():
                    self.paginator.add_line(line)
                self.paginator.add_line()

        signature = textwrap.indent(self.get_command_signature(command), prefix="    ")
        self.paginator.add_line(f"**Usage**\n{signature}", empty=not command.aliases)

        if command.aliases:
            self.add_aliases_formatting(command.aliases)

    async def send_cog_help(self, cog):
        note = self.get_opening_note()
        if note:
            self.paginator.add_line(note, empty=True)

        filtered = await self.filter_commands(cog.get_commands(), sort=self.sort_commands)
        if filtered:
            self.paginator.add_line(f"**{cog.qualified_name} {self.commands_heading}**", empty=True)
            if cog.description:
                self.paginator.add_line(cog.description, empty=True)

            for command in filtered:
                self.add_subcommand_formatting(command)

        await self.send_pages()

    async def send_group_help(self, group):
        note = self.get_opening_note()
        if note:
            self.paginator.add_line(note, empty=True)

        self.add_command_formatting(group)

        filtered = await self.filter_commands(group.commands, sort=self.sort_commands)
        if filtered:
            self.paginator.add_line(f"**{self.commands_heading}**")
            for command in filtered:
                self.add_subcommand_formatting(command)

        await self.send_pages()
