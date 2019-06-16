import hmac
from base64 import b64encode as b64
from datetime import datetime

from discord.ext import commands
from passlib.hash import pbkdf2_sha256


class Trench(commands.Cog, name="Trench Utils"):
    """Utils for the trenchapp server."""

    def __init__(self, bot):
        self.bot = bot

        self.genhash = pbkdf2_sha256.using(salt_size=64, rounds=150000)

    async def cog_check(self, ctx):
        return ctx.guild.id == 583797080510824472

    @commands.command()
    async def newauth(self, ctx, *, password):
        parts = list()
        parts.append(b64(str(ctx.author.id).encode()))
        parts.append(
            b64(str((ctx.author.id >> 10) - datetime.utcnow().timestamp()).encode()).decode().rstrip("=").encode()
        )
        parts.append(
            b64(
                hmac.new(
                    b"\xd6\xd3o\x80\xc5\xe7KW\xb6Kqy\xea\xe2F\x83\x0c\xecx\xc80I\xb0\x9f\xb7\xe5\xf1\xa3\xd3\x95\xfad"
                    b"\xa5+\n\xda\xd7\xcfk\x04D\x10\xff\x9a\xb25_O\x96\x07\xc0\xed\xa7\x8a\xcc\x1f\xb1D\x94\x15"
                    b"<\xfd\xaa\x1e",
                    msg=self.genhash.hash(password.encode()).encode(),
                    digestmod="sha256",
                ).digest()
            )
        )
        await ctx.send(":".join([a.decode() for a in parts]))


def setup(bot):
    bot.add_cog(Trench(bot))
