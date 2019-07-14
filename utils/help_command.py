import functools
import textwrap

from jishaku.help_command import MinimalPaginatorHelp


class TakuruHelpCommand(MinimalPaginatorHelp):
    def get_command_signature(self, command):
        return f"`{self.clean_prefix}{command.qualified_name} {command.signature}`"

    def add_subcommand_formatting(self, command):
        indent = functools.partial(textwrap.indent, prefix=" " * self.recursive_indent(command))
        fmt = indent(f"{command.qualified_name} - {command.short_doc}") \
            if command.short_doc else indent(command.qualified_name)
        self.paginator.add_line(fmt)

    def recursive_indent(self, command):
        total = 0
        while command.parent:
            command = command.parent
            total += 2
        return total

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

        filtered = await self.filter_commands(self.unique_walk_commands(cog), sort=self.sort_commands,
                                              key=self.recursive_indent)
        if filtered:
            self.paginator.add_line(f"**{cog.qualified_name} {self.commands_heading}**", empty=True)
            if cog.description:
                self.paginator.add_line(cog.description, empty=True)

            for command in filtered:
                self.add_subcommand_formatting(command)

        await self.send_pages()

    def unique_walk_commands(self, thing):
        yield from set(thing.walk_commands())

    async def send_group_help(self, group):
        note = self.get_opening_note()
        if note:
            self.paginator.add_line(note, empty=True)

        self.add_command_formatting(group)

        filtered = await self.filter_commands(self.unique_walk_commands(group),
                                              sort=self.sort_commands, key=self.recursive_indent)
        if filtered:
            self.paginator.add_line(f"**{self.commands_heading}**")
            for command in filtered:
                self.add_subcommand_formatting(command)

        await self.send_pages()
