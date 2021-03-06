import io
import logging
import random
import typing
from datetime import datetime, timedelta
from html import unescape as htmlunescape

import aiohttp
import discord
import lxml.etree as etree
from discord.ext import commands, flags, tasks

import utils

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

    async def get_mrm_search(self, ctx, query: str):
        html = await ctx.get("https://myreadingmanga.info/search/", search=query, cache=True)
        nodes = etree.fromstring(html, etree.HTMLParser())

        titles = tuple(t.text for t in nodes.xpath(f"//a[starts-with(@href, '{self.mrm_url}')]")[6:-8])
        urls = tuple(url for url in nodes.xpath(f"//a[starts-with(@href, '{self.mrm_url}')]/@href")[6:-8])
        thumbs = tuple(img for img in nodes.xpath(f"//img[{self.xpath_ends_with('@src', '.jpg')}]/@src"))

        result = tuple(zip(titles, urls, thumbs))

        return result

    @commands.command(name="mrm")
    async def my_reading_manga(self, ctx, *, query):
        """Search for BL content on My Reading Manga."""
        results = await self.get_mrm_search(ctx, query)

        for title, url, image in results:
            embed = discord.Embed(color=discord.Color(0x008CFF), title=title)
            embed.set_thumbnail(url=image)
            embed.add_field(name="URL Link", value=url)

            ctx.pages.add_entry(embed)

        await ctx.paginate()

    async def generate_reader_embed(self, ctx, images=None):
        for img in images:
            embed = discord.Embed(color=discord.Color(0x008CFF))
            embed.set_image(url=img)

            ctx.pages.add_entry(embed)

        await ctx.paginate()

    @commands.command(name="mreader")
    async def mrm_reader(self, ctx, *, search):
        """Get a paginated Embed view based of a My Reading Manga BL content.

        You can provide a MRM url or a search term."""
        html = await ctx.get(search, cache=True)
        nodes = etree.fromstring(html, etree.HTMLParser())
        images = tuple(img for img in nodes.xpath("//img/@data-lazy-src"))

        await self.generate_reader_embed(ctx, images)

    async def get_nh_search(self, ctx, query: str):
        html = await ctx.get("https://nhentai.net/search", q=query, cache=True)
        nodes = etree.fromstring(html, etree.HTMLParser())

        thumbs = tuple(img for img in nodes.xpath(f"//img[{self.xpath_ends_with('@src', '.jpg')}]/@src"))
        titles = tuple(div.text for div in nodes.xpath("//div[@class='caption']"))
        urls = tuple("https://nhentai.net" + a for a in nodes.xpath("//a[@class='cover']/@href"))

        result = tuple(zip(titles, thumbs, urls))

        return result

    @commands.command(name="nhentai", aliases=["nh"])
    async def nhentai(self, ctx, *, query):
        """Search for a doujin on nhentai."""
        results = await self.get_nh_search(ctx, query)

        for title, thumb, url in results:
            embed = discord.Embed(title=title, color=discord.Color(0x008CFF))
            embed.set_thumbnail(url=thumb)
            embed.description = url

            ctx.pages.add_entry(embed)

        await ctx.paginate()

    async def get_zerochan_search(self, ctx, query: str):
        html = await ctx.get("https://www.zerochan.net/search", q=query, cache=True)
        nodes = etree.fromstring(html, etree.HTMLParser())

        images = tuple(img.replace(".240.", ".full.") for img in nodes.xpath("//img[@alt]/@src")[0::2])

        return images

    @commands.command(name="zerochan", aliases=["zc"])
    async def zerochan(self, ctx, *, query):
        """Search for an image on Zerochan.

        While most, if not all, images on this image board can be considered SFW,
        some might be too much ecchi-ish for a guild's standard definition of NSFW,
        so it's in this extension for safety, might edit later."""
        images = await self.get_zerochan_search(ctx, query)

        for image in images:
            embed = discord.Embed(color=discord.Color(0x008CFF), title=f"Search: {query}")

            embed.set_image(url=image)
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

        try:
            sauce = await ctx.get(
                "https://saucenao.com/search.php",
                cache=True,
                db=999,
                output_type=2,
                numres=5,
                url=url,
                api_key=ctx.bot.config.tokens.apis.saucenao,
            )
        except Exception as e:
            raise e

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
