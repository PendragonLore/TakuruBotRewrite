import io
import logging
import random
import typing
from datetime import datetime, timedelta
from html import unescape as htmlunescape

import aiohttp
import discord
from discord.ext import commands, flags, tasks

import utils

try:
    import ujson as json
except ImportError:
    import json

LOG = logging.getLogger("cogs.nsfw")


class NSFW(commands.Cog, command_attrs=dict(cooldown=commands.Cooldown(1, 2.5, commands.BucketType.user))):
    """Commands that can only be used in NSFW channels."""

    def __init__(self, bot):
        self.bot = bot
        self.mrm_url = "https://myreadingmanga.info/"
        self.token = None

        try:
            self.pixiv_data = self.bot.config.tokens.apis.pixiv
        except KeyError:
            LOG.warning("No pixiv data provided")
        else:
            self.pixiv_token.start()

    @tasks.loop(hours=1)
    async def pixiv_token(self):
        data = await self.bot.ezr.request(
            "POST", "https://oauth.secure.pixiv.net/auth/token", __data=self.pixiv_data
        )

        auth = data["response"]["token_type"].capitalize() + " " + data["response"]["access_token"]
        self.token = auth

    @commands.command(name="pixiv")
    @utils.requires_config("tokens", "apis", "pixiv")
    async def pixiv(self, ctx, *, query):
        await ctx.trigger_typing()
        data = await ctx.get(
            "https://app-api.pixiv.net/v1/search/illust",
            word=query,
            search_target="partial_match_for_tags",
            __headers={"Authorization": self.token},
            cache=True,
        )

        try:
            result = random.choice(data["illusts"][:10])
        except IndexError:
            raise commands.BadArgument("No results.")

        embed = discord.Embed(
            title=result["title"] or "No title.",
            color=discord.Color(0x008CFF),
            url=f"https://www.pixiv.net/member_illust.php?mode=medium&illust_id={result['id']}",
            timestamp=datetime.strptime(result["create_date"], "%Y-%m-%dT%H:%M:%S%z") + timedelta(hours=9),
        )

        author = result["user"]
        embed.set_author(name=author["name"], url=f"https://www.pixiv.net/member.php?id={author['id']}")
        embed.description = htmlunescape("\n".join(result["caption"].split("<br />"))) or "No description."
        tags = " | ".join([t["name"] for t in result["tags"]])
        embed.add_field(name="Tags", value=tags or "No tags.")
        embed.set_footer(text=f"Views: {result['total_view']} | Bookmarks {result['total_bookmarks']}")

        if result["meta_pages"]:
            url = result["meta_pages"][0]["image_urls"]["original"]
            embed.add_field(name="Type", value="Multiple Illustrations (Manga/Log)")
        else:
            url = result["meta_single_page"]["original_image_url"]
            embed.add_field(name="Type", value="Oneoff illustration")

        image = await ctx.get(url, __headers={"Referer": "https://app-api.pixiv.net/"})
        fp = io.BytesIO(image)
        fp.seek(0)
        embed.set_image(url="attachment://original.jpg")

        await ctx.send(embed=embed, file=discord.File(fp, "original.jpg"))

    def cog_unload(self):
        self.pixiv_token.cancel()

    def cog_check(self, ctx):
        return ctx.channel.is_nsfw()

    def xpath_ends_with(self, thing: str, string: str):
        return f"substring({thing}, string-length({thing}) - string-length('{string}') + 1) = '{string}'"

    @commands.command(name="mrm")
    async def my_reading_manga(self, ctx, *, query):
        """Search for BL content on My Reading Manga."""
        nodes = [
            utils.Node(f"//a[starts-with(@href, '{self.mrm_url}')]")[6:-8],
            utils.Node(f"//a[starts-with(@href, '{self.mrm_url}')]/@href")[6:-8],
            utils.Node(f"//img[{self.xpath_ends_with('@src', '.jpg')}]/@src"),
        ]

        parser = utils.NSFWParser(ctx, "https://myreadingmanga.info/search/",
                                  request_params={"search": query, "cache": True}, paths=nodes)

        async for title, url, image in parser.parse():
            embed = discord.Embed(color=discord.Color(0x008CFF), title=title.text)
            embed.set_thumbnail(url=image)
            embed.add_field(name="URL Link", value=url)

            ctx.pages.add_entry(embed)

        await ctx.paginate()

    @commands.command(name="nhentai", aliases=["nh"])
    async def nhentai(self, ctx, *, query):
        """Search for a doujin on nhentai."""
        nodes = [
            utils.Node("//div[@class='caption']"),
            utils.Node(f"//img[{self.xpath_ends_with('@src', '.jpg')}]/@src"),
            utils.Node("//a[@class='cover']/@href"),
        ]
        parser = utils.NSFWParser(ctx, "https://nhentai.net", request_params={"q": query, "cache": True}, paths=nodes)

        async for title, thumb, url in parser.parse():
            embed = discord.Embed(title=title.text, color=discord.Color(0x008CFF))
            embed.set_thumbnail(url=thumb)
            embed.description = "https://nhentai.net" + url

            ctx.pages.add_entry(embed)

        await ctx.paginate()

    @commands.command(name="zerochan", aliases=["zc"])
    async def zerochan(self, ctx, *, query):
        """Search for an image on Zerochan."""
        parser = utils.NSFWParser(ctx, "https://www.zerochan.net/search",
                                  request_params={"q": query, "cache": True},
                                  paths=[utils.Node("//img[@alt]/@src")[0::2]])
        async for image in parser.parse():
            embed = discord.Embed(color=discord.Color(0x008CFF), title=f"Search: {query}")

            embed.set_image(url=image.replace(".240.", ".full."))
            ctx.pages.add_entry(embed)

        await ctx.paginate()

    @commands.command(name="safebooru")
    async def safebooru(self, ctx, *, tags):
        data = json.loads(await ctx.get(
            "https://safebooru.org/index.php", page="dapi", s="post", q="index", json="1", tags=tags
        ))

        for post in data:
            embed = discord.Embed(color=discord.Color(0x008CFF))
            embed.set_image(url=f"https://safebooru.org//images/{post['directory']}/{post['image']}")
            embed.set_footer(text=", ".join(post['tags'].split()))

            ctx.pages.add_entry(embed)

        await ctx.paginate()

    @commands.command(name="sauce", aliases=["saucenao"], cls=flags.FlagCommand)
    @utils.requires_config("tokens", "apis", "saucenao")
    async def saucenao(self, ctx, *, url: typing.Optional[lambda x: x.strip("<>")]=utils.FirstAttachment):
        """Get the sauce of an image."""
        try:
            async with ctx.bot.ezr.session.get(url) as r:
                if "image/" not in r.headers["Content-Type"]:
                    raise TypeError()
        except (aiohttp.ClientError, TypeError):
            raise commands.BadArgument("You must either provide a valid attachment or image url.")

        sauce = await ctx.get(
            "https://saucenao.com/search.php",
            cache=True,
            db=999,
            output_type=2,
            numres=5,
            url=url,
            api_key=ctx.bot.config.tokens.apis.saucenao,
        )

        r = sauce["results"]

        for result in r:
            embed = discord.Embed(color=discord.Color(0x008CFF))
            embed.add_field(name="Sauce", value="\n".join(result["data"].get("ext_urls", ["No URLs."])))
            embed.description = "\n".join(
                [
                    f"**{k.replace('_', ' ').title()}:** {v}"
                    for k, v in result["data"].items()
                    if k not in {"data", "ext_urls"}
                ]
            )
            embed.set_thumbnail(url=result["header"]["thumbnail"])
            embed.set_footer(text=f"Similarity: {result['header']['similarity']}")

            ctx.pages.add_entry(embed)

        await ctx.paginate()


def setup(bot):
    bot.add_cog(NSFW(bot))
