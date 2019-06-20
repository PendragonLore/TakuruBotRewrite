import base64
import binascii
import io
import os
import re
import typing
import zlib
from datetime import datetime
from urllib.parse import quote as urlquote

import discord
from discord.ext import commands
from lxml import etree

from utils.checks import requires_config
from utils.converters import Codeblock
from utils.tio import Tio

try:
    import ujson as json
except ImportError:
    import json


# most rtfm stuff is from R. Danny https://github.com/Rapptz/RoboDanny/

class SphinxObjectFileReader:
    BUFSIZE = 16 * 1024

    def __init__(self, buffer):
        self.stream = io.BytesIO(buffer)

    def readline(self):
        return self.stream.readline().decode("utf-8")

    def skipline(self):
        self.stream.readline()

    def read_compressed_chunks(self):
        decompressor = zlib.decompressobj()
        while True:
            chunk = self.stream.read(self.BUFSIZE)
            if not chunk:
                break
            yield decompressor.decompress(chunk)
        yield decompressor.flush()

    def read_compressed_lines(self):
        buf = b""
        for chunk in self.read_compressed_chunks():
            buf += chunk
            pos = buf.find(b"\n")
            while pos != -1:
                yield buf[:pos].decode("utf-8")
                buf = buf[pos + 1:]
                pos = buf.find(b"\n")


class DevUtils(commands.Cog, name="Dev Utils",
               command_attrs=dict(cooldown=commands.Cooldown(1, 2.5, commands.BucketType.user))):
    """Utils for developers."""

    TOKEN_REGEX = re.compile(r"([a-zA-Z0-9]{24})\.([a-zA-Z0-9\-_]{6})\.([a-zA-Z0-9_\-]{27})")

    def __init__(self, bot):
        self.bot = bot

        self.page_types = {
            "python": "https://docs.python.org/3",
            "quart": "https://pgjones.gitlab.io/quart",
            "flask": "http://flask.pocoo.org/docs/dev",
            "py": "https://docs.python.org/3",
        }

        self.coliru_mapping = {
            "cpp": "g++ -std=c++1z -O2 -Wall -Wextra -pedantic -pthread main.cpp -lstdc++fs && ./a.out",
            "c": "mv main.cpp main.c && gcc -std=c11 -O2 -Wall -Wextra -pedantic main.c && ./a.out",
            "py": "python3 main.cpp",
            "python": "python3 main.cpp",
            "haskell": "runhaskell main.cpp",
        }

        with open("tiomap.json") as f:
            js = json.load(f)

        self.tio_quickmap = js["quick"]
        self.tio_not_quickmap = js["full"]

    def finder(self, text, collection, *, key=None, lazy=True):
        suggestions = []
        text = str(text)
        pat = ".*?".join(map(re.escape, text))
        regex = re.compile(pat, flags=re.IGNORECASE)
        for item in collection:
            to_search = key(item) if key else item
            r = regex.search(to_search)
            if r:
                suggestions.append((len(r.group()), r.start(), item))

        def sort_key(tup):
            if key:
                return tup[0], tup[1], key(tup[2])
            return tup

        if lazy:
            return (z for _, _, z in sorted(suggestions, key=sort_key))

        return [z for _, _, z in sorted(suggestions, key=sort_key)]

    def parse_object_inv(self, stream, url):
        result = {}

        inv_version = stream.readline().rstrip()

        if inv_version != "# Sphinx inventory version 2":
            raise commands.BadArgument("Invalid objects.inv file version.")

        projname = stream.readline().rstrip()[11:]
        _ = stream.readline().rstrip()[11:]

        line = stream.readline()
        if "zlib" not in line:
            raise commands.BadArgument("Invalid objects.inv file, not z-lib compatible.")

        entry_regex = re.compile(r"(?x)(.+?)\s+(\S*:\S*)\s+(-?\d+)\s+(\S+)\s+(.*)")
        for line in stream.read_compressed_lines():
            match = entry_regex.match(line.rstrip())
            if not match:
                continue

            name, directive, _, location, dispname = match.groups()
            domain, _, subdirective = directive.partition(":")
            if directive == "py:module" and name in result:
                continue

            if directive == "std:doc":
                subdirective = "label"

            if location.endswith("$"):
                location = location[:-1] + name

            key = name if dispname == "-" else dispname
            prefix = f"{subdirective}:" if domain == "std" else ""

            if projname == "discord.py":
                key = key.replace("discord.ext.commands.", "").replace("discord.", "")

            result[f"{prefix}{key}"] = os.path.join(url, location)

        return result

    async def build_rtfm_lookup_table(self):
        if not hasattr(self, "_rtfm_cache"):
            self._rtfm_cache = {}

        cache = {}
        for key, page in self.page_types.items():
            if key in self._rtfm_cache:
                continue
            cache[key] = {}

            out = await self.bot.ezr.request("GET", page + "/objects.inv")

            stream = SphinxObjectFileReader(out)
            cache[key] = self.parse_object_inv(stream, page)

        self._rtfm_cache.update(cache)

    async def do_rtfm(self, ctx, key, obj):
        key = key.replace(" ", "-").lower()

        if key not in self.page_types:
            self.page_types[key] = f"https://{key}.readthedocs.io/en/latest"

        if obj is None:
            await ctx.send(self.page_types[key])
            return

        if key not in getattr(self, "_rtfm_cache", {}):
            await ctx.trigger_typing()
            await self.build_rtfm_lookup_table()

        obj = re.sub(r"^(?:discord\.(?:ext\.)?)?(?:commands\.)?(.+)", r"\1", obj)

        if key == "discordpy":
            q = obj.lower()
            for name in dir(discord.abc.Messageable):
                if name[0] == "_":
                    continue
                if q == name:
                    obj = f"abc.Messageable.{name}"
                    break

        cache = list(self._rtfm_cache[key].items())

        matches = self.finder(obj, cache, key=lambda t: t[0], lazy=False)[:12]
        if not matches:
            return await ctx.send("No results.")

        e = discord.Embed(color=discord.Color(0x008CFF))

        e.description = "\n".join(f"[`{thing.replace(key + '.', '')}`]({url})" for thing, url in matches)
        await ctx.send(embed=e)

    @commands.command(aliases=["rtfd"])
    async def rtfm(self, ctx, key, *, obj=None):
        """Gives you documentation about stuff.

        The search is executed by ``https://{key.lower}.readthedocs.io/en/latest``
        Exceptions are: flask, quart and python, which all search to their custom URLs, (latest/dev).

        If nothing is found it will be ignored."""
        if not obj and key in self.page_types:
            return await ctx.send(self.page_types[key])
        await self.do_rtfm(ctx, key, obj)

    @commands.command(name="tio")
    async def tio(self, ctx, lang, *, code: Codeblock):
        """Run code on TIO.

        Most programming languages are supported."""
        if lang in self.tio_quickmap:
            lang = self.tio_quickmap[lang]
        if lang in self.tio_not_quickmap:
            lang = self.tio_not_quickmap[lang]

        runner = Tio(ctx, lang, code)

        result = await runner.send()

        zero = "\u200b"
        result = re.sub("```", f"{zero}`{zero}`{zero}`{zero}", result)

        if len(result) > 200 or result.count("\n") >= 40:
            return await ctx.post_to_mystbin(result)
        await ctx.send(f"```ph\n{result}```")

    @commands.command(name="http")
    async def http_status(self, ctx, *, code):
        """Get basic info about an HTTP status code."""
        try:
            html = await ctx.get("https://httpstatuses.com/{0}".format(urlquote(code)), cache=True)
        except Exception:
            return await ctx.send("404")

        nodes = etree.fromstring(html, etree.HTMLParser())
        embed = discord.Embed(
            title="{0} - {1}".format(nodes.xpath("//span/text()")[0].strip(), nodes.xpath("//h1/text()")[0].strip()),
            color=discord.Color(0x008CFF)
        )
        embed.description = nodes.xpath("//p/text()")[0].strip()
        embed.set_thumbnail(url="https://httpstatusdogs.com/img/{0}.jpg".format(code))

        await ctx.send(embed=embed)

    @commands.command(name="coliru", aliases=["run", "openeval"])
    async def coliru(self, ctx, lang, *, code: Codeblock):
        """Run code on coliru.

        Supports, and probably will only ever support, haskell, c, c++ and python 3.5.x
        You need to include a codeblock which denotes the language.
        Do not abuse this kthx."""
        if lang not in self.coliru_mapping.keys():
            return await ctx.send("Supported languages for code blocks are `py`, `python`, `c`, `cpp` and `haskell`.")

        payload = {"src": code, "cmd": self.coliru_mapping[lang]}

        data = json.dumps(payload)

        response = await ctx.post("http://coliru.stacked-crooked.com/compile", __data=data)
        clean = await commands.clean_content(use_nicknames=False).convert(ctx, response)

        await ctx.send(f"```{clean or 'No output.'}```")

    @commands.command(name="apm")
    @requires_config("tokens", "apis", "atom")
    async def apm(self, ctx, *, name):
        """Get an atom package's info."""
        auth = (("Authorization", ctx.bot.config.tokens.apis.atom),)
        package = await ctx.get(
            f"https://atom.io/api/packages/" f"{urlquote('-'.join(name.lower().split()), safe='')}", __headers=auth
        )

        embed = discord.Embed(title=package["name"], url=package["repository"]["url"], color=discord.Color(0x008CFF))
        embed.add_field(name="Description", value=package["metadata"]["description"] or "No description.")
        embed.add_field(
            name="Dependencies",
            value="\n".join(f"{d} ({v})" for d, v in package["metadata"]["dependencies"].items()) or "No dependencies.",
        )
        embed.set_thumbnail(url="https://cdn.freebiesupply.com/logos/large/2x/atom-4-logo-png-transparent.png")
        embed.set_footer(
            text=f"Stargazers: {package['stargazers_count']} | Downloads: {package['downloads']} "
            f"| Latest: {package['releases']['latest']}"
        )

        await ctx.send(embed=embed)

    @commands.command(name="pypi")
    async def pypi(self, ctx, *, name):
        """Get a pypi package's info."""
        data = await ctx.get(f"https://pypi.org/pypi/{urlquote(name, safe='')}/json")

        embed = discord.Embed(
            title=data["info"]["name"], url=data["info"]["package_url"], color=discord.Color(0x008CFF)
        )
        embed.set_author(name=data["info"]["author"])
        embed.description = data["info"]["summary"] or "No short description."
        embed.add_field(name="Classifiers", value="\n".join(data["info"]["classifiers"]) or "No classifiers.")
        embed.set_footer(
            text=f"Latest: {data['info']['version']} |" f" Keywords: {data['info']['keywords'] or 'No keywords.'}"
        )
        embed.set_thumbnail(url="https://cdn-images-1.medium.com/max/1200/1*2FrV8q6rPdz6w2ShV6y7bw.png")

        await ctx.send(embed=embed)

    @commands.command(name="rtfs", aliases=["rts", "readthesource", "readthefuckingsourcegoddamnit"])
    async def read_the_source(self, ctx, *, query: typing.Optional[str] = None):
        """Search the GitHub repo of discord.py."""
        if not query:
            return await ctx.send("https://github.com/Rapptz/discord.py")

        source = await ctx.get("https://rtfs.eviee.host/dpy/v1", search=query, limit=12)
        thing = []

        for result in source["results"]:
            thing.append(f"[{result['path'].replace('/', '.')}.{result['module']}.{result['object']}]({result['url']})")

        if not thing:
            return await ctx.send("No results.")

        embed = discord.Embed(
            color=discord.Color(0x008CFF), title=f"Results for `{query}`", description="\n".join(thing)
        )

        await ctx.send(embed=embed)

    @commands.command(name="parsetoken", aliases=["tokenparse"])
    async def parse_token(self, ctx, *, token):
        """Parse a Discord bot auth token."""
        match = self.TOKEN_REGEX.fullmatch(token)
        if not match or not match.group(0):
            return await ctx.send("Not a valid token.")

        enc_id, enc_time, hmac = match.groups()

        try:
            id_ = base64.standard_b64decode(enc_id).decode("utf-8")
            try:
                user = await ctx.bot.fetch_user(int(id_))
            except discord.HTTPException:
                user = None
        except binascii.Error:
            return await ctx.send("Failed to decode user ID.")

        try:
            token_epoch = 1293840000
            decoded = int.from_bytes(base64.standard_b64decode(enc_time + "=="), "big")
            timestamp = datetime.utcfromtimestamp(decoded)
            if timestamp.year < 2015:  # Usually if the year is less then 2015 it means that we must add the token epoch
                timestamp = datetime.utcfromtimestamp(decoded + token_epoch)
            date = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        except binascii.Error:
            return await ctx.send("Failed to decode timestamp.")

        fmt = (
            f"**Valid token.**\n\n**ID**: {id_}\n"
            f"**Created at**: {date}\n**Associated bot**: {user or '*Was not able to fetch it*.'}"
            f"\n**Cryptographic component**: {hmac}"
        )

        await ctx.send(fmt)


def setup(bot):
    bot.add_cog(DevUtils(bot))
