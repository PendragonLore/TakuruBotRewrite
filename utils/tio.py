import zlib
from functools import partial

# Most of this is from RTFM (https://github.com/FrenchMasterSword/RTFMbot)
# mostly because I couldn't find actual documentation on this


class Tio:
    __slots__ = ("backend", "ctx", "request", "to_bytes")

    def __init__(self, ctx, language: str, code: str):
        self.backend = "https://tio.run/cgi-bin/run/api/"

        strings = {
            "lang": [language],
            ".code.tio": code,
            ".input.tio": "",
            "TIO_CFLAGS": [],
            "TIO_OPTIONS": [],
            "args": [],
        }

        bytes_ = b"".join(map(self._to_string, zip(strings.keys(), strings.values()))) + b"R"
        self.ctx = ctx

        self.request = zlib.compress(bytes_, 9)[2:-4]

        self.to_bytes = partial(bytes, encoding="utf-8")

    def _to_string(self, couple):
        name, obj = couple[0], couple[1]
        if not obj:
            return b""

        if isinstance(obj, list):
            content = [f"V{name}", str(len(obj))] + obj
            return self.to_bytes("\x00".join(content) + "\x00")

        return self.to_bytes(f"F{name}\x00{len(self.to_bytes(obj))}\x00{obj}\x00")

    async def send(self):
        data = await self.ctx.post(self.backend, __data=self.request)
        data = data.decode("utf-8")
        return data.replace(data[:16], "")
