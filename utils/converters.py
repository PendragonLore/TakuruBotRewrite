import inspect
import re

import parsedatetime
from dateutil.relativedelta import relativedelta
from discord.ext import commands


class Empty:
    pass


class Time(commands.Converter):
    __slots__ = (
        "arg",
        "date",
        "_past",
        "_converter"
        "_arg_required",
    )

    def __init__(self, *, arg_required=True, converter=commands.clean_content, greedy=False,
                 default=Empty, past_ok=False):
        self.date = None
        self.arg = None
        self.default = default
        self.past_ok = past_ok

        self._past = False
        self._arg_required = arg_required
        self._converter = converter
        self._greedy = greedy

    async def convert(self, ctx, argument):
        raise NotImplementedError("Must be implemented by subclasses")

    def check(self):
        if self._past and self.past_ok is False:
            raise commands.BadArgument("Time is in the past.")
        if not self._past and self.past_ok is None:
            raise commands.BadArgument("Time is in the future.")
        if self._arg_required and self.arg and self.default is not Empty:
            raise commands.BadArgument("Extra argument missing.")

        return True

    async def convert_extra_arg(self, ctx, arg):
        if not arg:
            if self.default is not Empty:
                self.arg = self.default
                return

            raise commands.BadArgument("Extra argument missing.")

        if self._converter:
            if inspect.isclass(self._converter):
                self._converter = self._converter()

            if self._greedy:
                args = []
                for line in arg.split():
                    try:
                        converted = await self._converter.convert(ctx, line)
                    except commands.BadArgument:
                        break
                    else:
                        args.append(converted)
                self.arg = args
            else:
                self.arg = await self._converter.convert(ctx, arg)
        else:
            self.arg = arg


class ShortTime(Time):
    REGEX = re.compile("""(?:(?P<years>[0-9]{1,4})(?:years?|y))?
                          (?:(?P<months>[0-9]{1,4})(?:months?|mo))?
                          (?:(?P<weeks>[0-9]{1,4})(?:weeks?|w))?
                          (?:(?P<days>[0-9]{1,4})(?:days?|d))?
                          (?:(?P<hours>[0-9]{1,4})(?:hours?|h))?
                          (?:(?P<minutes>[0-9]{1,4})(?:minutes?|m))?
                          (?:(?P<seconds>[0-9]{1,4})(?:seconds?|s))?""",
                       re.VERBOSE | re.IGNORECASE)

    async def convert(self, ctx, argument):
        match = self.REGEX.match(argument.strip())

        if not match or not match.group(0):
            raise commands.BadArgument("Invalid date passed.")

        now = ctx.message.created_at

        self.date = now + relativedelta(**{k: int(v) for k, v in match.groupdict(default=0).items()})
        self._past = now > self.date

        if self._arg_required:
            arg = argument[match.end():].strip()

            await self.convert_extra_arg(ctx, arg)

        self.check()

        return self


class DateTime(Time):
    calendar = parsedatetime.Calendar(version=parsedatetime.VERSION_CONTEXT_STYLE)

    async def convert(self, ctx, argument):
        now = ctx.message.created_at
        argument = argument.replace("from now", "").strip()

        try:
            date, pdt_ctx, start, end, _ = self.calendar.nlp(argument, sourceTime=now)[0]
        except (IndexError, TypeError):
            raise commands.BadArgument("Invalid date passed.")

        if not pdt_ctx.hasDateOrTime:
            raise commands.BadArgument("Invalid date passed.")

        if not pdt_ctx.hasTime:
            date = date.replace(hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond)

        if pdt_ctx.accuracy == parsedatetime.pdtContext.ACU_HALFDAY:
            date = date.replace(day=now.day + 1)

        self.date = date
        self._past = now > date

        if self._arg_required:
            if start in {0, 1}:
                if start == 1:
                    if argument[0] != "\"":
                        raise commands.BadArgument("Expected quote before time input.")

                    if not (end < len(argument) and argument[end] == "\""):
                        raise commands.BadArgument("If the time is quoted, you must unquote it.")

                    remaining = argument[end + 1:].lstrip(' ,.!')
                else:
                    remaining = argument[end:].lstrip(' ,.!')
            elif len(argument) == end:
                remaining = argument[:start].strip()

            await self.convert_extra_arg(ctx, remaining)

        self.check()

        return self


class HumanTime(DateTime):
    """A utility converter for human readable time.

    This takes both standard formats like YYYY-MM-DD,
    something more abstract like '3 hours from now' or
    more compact like 1h30m40s.

    All times are in UTC.

    Parameters
    ----------
    past_ok: Union[:class:`bool`, ``None``]
        A tribool to filter time.
        ``True`` will not filter anything.
        ``False`` will raise :exc:`~discord.ext.commands.BadArgument` if the time is in the past.
        ``None`` will raise :exc:`~discord.ext.commands.BadArgument` if the time is in the future.
    arg_required: :class:`bool`
        Whether if an extra argument is required or not.
    default
        The argument to use if none was provided.
        Ignored if :attr:`arg_required`` is ``False``.
    converter: :class:`~discord.ext.commands.Converter`
        A converter to use on the extra argument.
        Ignored if :attr:`arg_required`` is ``False``.
    greedy: :class:`bool`
        Wether or not to make the converter behave greedly.
        Ignore if :attr:`converter` is not provided.

    Attributes
    ----------
    date: :class:`~datetime.datetime`
        The date converted.
    arg: Optional
        The extra argument, is ``None`` if :attr:`arg_required` is ``False``."""
    __slots__ = (
        "_short",
    )

    def __init__(self, **kwargs):
        self._short = ShortTime(**kwargs)

        super().__init__(**kwargs)

    async def convert(self, ctx, argument):
        try:
            ret = await self._short.convert(ctx, argument)

            return ret
        except commands.BadArgument:
            ret = await super().convert(ctx, argument)

            return ret


class Codeblock(commands.Converter):
    __slots__ = (
        "pass_lang",
    )

    CODEBLOCK_REGEX = re.compile(r"^(?:```([A-Za-z0-9\-\\.]*)\n)?(.+?)(?:```)?$", re.S)

    def __init__(self, pass_lang=False):
        self.pass_lang = pass_lang

    async def convert(self, ctx, argument):
        match = self.CODEBLOCK_REGEX.match(argument)

        if not match or not match.group(0):
            raise commands.BadArgument("Invalid codeblock structure.")

        if self.pass_lang:
            return match.group(1), match.group(2)

        return match.group(2)
