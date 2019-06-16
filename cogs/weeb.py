import random
from datetime import datetime

import discord
from discord.ext import commands
from lxml import etree

import utils


class Weeb(commands.Cog, command_attrs=dict(cooldown=commands.Cooldown(1, 2.5, commands.BucketType.user))):
    """Fucking weeb."""

    def __init__(self, bot):
        self.bot = bot

        self.anilist_queries = {
            "media":
                """query ($search: String) {{ Media(search: $search, type: {type}) {{title {{romaji}}
                   id description episodes season meanScore isAdult siteUrl bannerImage chapters volumes duration
                   endDate {{year month day}} startDate {{year month day}} coverImage {{extraLarge color}}}}}}""",
            "char":
                """query ($search: String) { Character(search: $search) {
                   name {first last native} id siteUrl image {large} media {nodes {title {romaji}
                   coverImage {color}}} description favourites}}""",
        }

    @commands.command(name="osu")
    @utils.requires_config("tokens", "apis", "osu")
    async def osu(self, ctx, user):
        """Get info on a osu! user."""
        results = await ctx.get("https://osu.ppy.sh/api/get_user", k=ctx.bot.config.tokens["apis"]["osu"], u=user)
        try:
            d = results[0]
        except (IndexError, ValueError, TypeError):
            return await ctx.send("No results.")

        desc = f"**Total beatmaps**: {d['count300']} | **PP rank**: {d['pp_rank']} | **Level**: {d['level']}"
        embed = discord.Embed(
            title=f"{d['username']} - {d['user_id']}", description=desc, color=discord.Color(0x008CFF)
        )
        embed.add_field(name="`SS/SSH` country ranks", value=f"{d['count_rank_ss']}/{d['count_rank_ssh']}")
        embed.add_field(name="Total/Ranked", value=f"`{d['total_score']}/{d['ranked_score']}`")
        embed.add_field(name="Total seconds played", value=d["total_seconds_played"])
        embed.add_field(name="Country", value=d["country"])
        embed.set_thumbnail(url=f"https://a.ppy.sh/{d['user_id']}")
        joined_at = datetime.strptime(d["join_date"], "%Y-%m-%d %H:%M:%S")

        embed.add_field(
            name="Jointed at",
            value=utils.fmt_delta(joined_at),
        )
        if d["events"]:
            text = []
            for event in d["events"]:
                nodes = etree.fromstring(event["display_html"], etree.HTMLParser())
                k = "".join(nodes.xpath("//text()"))
                text.append(k)
            fin = "\n".join(text)
            embed.add_field(name="Events", value=f"``{fin}``")

        await ctx.send(embed=embed)

    async def build_anime_manga_embed(self, ctx, data, type_):
        if data["isAdult"] and not ctx.channel.is_nsfw():
            raise commands.BadArgument(f"This {type_.lower()} is adult only, consider searching it in NSFW channel.")

        c = data["coverImage"]["color"] or "#36393E"

        embed = discord.Embed(
            title=f"`{data['id']}` - {data['title']['romaji']}", color=int(c.lstrip("#"), 16), url=data["siteUrl"]
        )
        d = data["description"].replace("<br>", "")
        embed.description = utils.trunc_text(d, 2048)
        if data["bannerImage"]:
            embed.set_image(url=data["bannerImage"])

        embed.set_thumbnail(url=data["coverImage"]["extraLarge"])
        embed.add_field(name="Avarage Rating", value=f"{data['meanScore'] / 10}/10")
        embed.add_field(name="Is adult only?", value=data["isAdult"])

        dates = []
        if all(k for k in data.get("startDate", {}).values()):
            dates.append(f"Started on {utils.fmt_delta(datetime(**data['startDate']))}")
        if all(k for k in data.get("endDate", {}).values()):
            dates.append(f"Started on {utils.fmt_delta(datetime(**data['endDate']))}")

        embed.add_field(name="Dates", value="\n".join(dates) or "No dates available.")

        e = (
            f"{data['episodes']} total episodes, {data['duration']} minutes on average"
            if data["episodes"]
            else f"{data['volumes']} total volumes and {data['chapters']} total chapters"
        )
        embed.set_footer(text=f"Released in {str(data.get('season')).capitalize()} | {e}")

        await ctx.send(embed=embed)

    @commands.command(aliases=["anilist"])
    async def anime(self, ctx, *, name):
        """Search an anime on anilist.co."""
        var = {"search": name}
        result = await ctx.post(
            "https://graphql.anilist.co",
            __json={"query": self.anilist_queries["media"].format(type="ANIME"), "variables": var},
            cache=True,
        )

        data = result["data"]["Media"]

        await self.build_anime_manga_embed(ctx, data, "Anime")

    @commands.command(aliases=["anilistmanga"])
    async def manga(self, ctx, *, name):
        """Search a manga on anilist.co."""
        var = {"search": name}
        result = await ctx.post(
            "https://graphql.anilist.co",
            __json={"query": self.anilist_queries["media"].format(type="MANGA"), "variables": var},
            cache=True,
        )

        data = result["data"]["Media"]

        await self.build_anime_manga_embed(ctx, data, "Manga")

    @commands.command(aliases=["anilistchar"])
    async def animechar(self, ctx, *, name):
        """Search an anime or manga character on anilist.co."""
        var = {"search": name}
        result = await ctx.post(
            "https://graphql.anilist.co", __json={"query": self.anilist_queries["char"], "variables": var}, cache=True
        )

        data = result["data"]["Character"]
        n = data["name"]
        d = (data["description"] or "No description provided.").replace("<br>", "")

        try:
            c = int(data["media"]["nodes"][0]["coverImage"]["color"].lstrip("#"), 16)
        except (IndexError, KeyError, AttributeError, TypeError):
            c = discord.Colour.from_hsv(random.random(), 1, 1)

        embed = discord.Embed(
            title=f"`{data['id']}` - {n['last'] or ''} {n['first'] or ''} (Native: {n['native']})",
            url=data["siteUrl"],
            color=c,
            description=utils.trunc_text(d, 2048),
        )
        embed.set_thumbnail(url=data["image"]["large"])
        embed.add_field(
            name="Starred in",
            value=", ".join([c["title"]["romaji"] for c in data["media"]["nodes"]]) or "Nothing :thinking:",
        )
        embed.set_footer(text=f"Favorited by {data['favourites']} people")

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Weeb(bot))
