import humanize

from .checks import *  # noqa: F401
from .config import Config  # noqa: F401
from .converters import *  # noqa: F401
from .defaults import *  # noqa: F401
from .emotes import *  # noqa: F401
from .ezrequests import EasyRequests  # noqa: F401
from .formats import PaginationError, Paginator, Tabulator  # noqa: F401
from .waveobj import Player, Track  # noqa: F401


def fmt_delta(date):
    return f"{humanize.naturaldate(date)} UTC ({humanize.naturaltime(date)})"


def trunc_text(text, maxlen):
    return text[:maxlen - 3] + "..." if len(text) > maxlen else text


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
