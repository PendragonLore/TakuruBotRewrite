import contextlib
import itertools

import humanize

from . import image  # noqa: F401
from .better_timers import TimerManager as BetterTimerManager  # noqa: F401
from .checks import *  # noqa: F401
from .config import Config  # noqa: F401
from .context import RightSiderContext  # noqa: F401
from .converters import *  # noqa: F401
from .defaults import *  # noqa: F401
from .emotes import *  # noqa: F401
from .ezrequests import EasyRequests  # noqa: F401
from .formats import PaginationError, Paginator, Plural, Tabulator  # noqa: F401
from .nsfw_parser import Node, NSFWParser  # noqa: F401
from .waveobj import Player, Track  # noqa: F401


async def aioenumerate(iterator, start=0, step=1):
    counter = itertools.count(start=start, step=step)

    async for x in iterator:
        yield (next(counter), x)


def fmt_delta(date):
    return f"{humanize.naturaldate(date)} UTC ({humanize.naturaltime(date)})"


def trunc_text(text, maxlen, *, placeholder="..."):
    return text[:maxlen - len(placeholder)] + placeholder if len(text) > maxlen else text


def make_seed(string):
    return sum([ord(c) for c in string])


def fmt_uptime(delta):
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)

    return f"{days}d {hours}h {minutes}m {seconds}s"


def chunks(l, n):
    for i in range(0, len(l), n):
        yield l[i:i + n]


@contextlib.asynccontextmanager
async def acquire_transaction(db):
    async with db.acquire() as conn:
        async with conn.transaction():
            yield conn
