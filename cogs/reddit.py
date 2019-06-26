import html
from collections import deque
from datetime import datetime
from urllib.parse import quote as urlquote
from urllib.parse import urlparse

import discord
from discord.ext import commands
from lru import LRU

import utils


class PostType(discord.Enum):
    TEXT = 0
    LINK = 1
    IMAGE = 2
    VIDEO = 3
    EMBED = 4


class Post:
    __slots__ = (
        "title",
        "subreddit",
        "thumbnail",
        "created_at",
        "url",
        "author",
        "text",
        "crossposts_count",
        "comments_count",
        "flair",
        "nsfw",
        "link",
        "type",
        "e_title",
        "e_desc",
        "e_thumbnail",
        "e_author_name",
        "e_author_url",
    )

    def __init__(self, data):
        self.title = html.unescape(data["title"])
        self.subreddit = data["subreddit_name_prefixed"]
        self.thumbnail = data["thumbnail"]
        self.created_at = datetime.utcfromtimestamp(data["created_utc"])
        self.url = "https://www.reddit.com" + data["permalink"]
        self.author = data["author_flair_text"]
        self.text = html.unescape(data["selftext"]).replace("&#x200b;", "")
        self.crossposts_count = data["num_crossposts"]
        self.comments_count = data["num_comments"]
        self.flair = data["link_flair_type"]
        self.link = data["url"]
        self.nsfw = data["over_18"]
        embed_check = data.get("secure_media")

        if urlparse(self.link).path.lower().endswith((".gif", ".jpeg", ".jpg", ".png", ".gifv")):
            self.type = PostType.IMAGE
        elif embed_check:
            self.type = PostType.EMBED
            e = embed_check.get("oembed", {})

            self.e_title = e.get("title")
            self.e_desc = e.get("description")
            self.e_thumbnail = e.get("thumbnail_url")
            self.e_author_name = e.get("author_name")
            self.e_author_url = e.get("author_url")
        elif not self.link == self.url:
            self.type = PostType.LINK
        elif data["is_video"]:
            self.type = PostType.VIDEO
        else:
            self.type = PostType.TEXT


class Reddit(commands.Cog, command_attrs=dict(cooldown=commands.Cooldown(1, 2.5, commands.BucketType.user))):
    """Reddit commands."""

    BASE = "https://www.reddit.com"

    def __init__(self, bot):
        self.bot = bot
        self.user_agent = "Python:TakuruBot:0.1 (by u/Pendragon_Lore)"
        self.headers = {"User-Agent": self.user_agent}

        self._post_cache = LRU(64)

    @commands.group(name="reddit", aliases=["r"], invoke_without_command=True, case_insensitive=True)
    async def reddit(self, ctx):
        await ctx.send_help(ctx.command)

    @reddit.command(name="search", aliases=["s"])
    async def reddit_search(self, ctx, *, query):
        """Search up a post on reddit.

        This basically searches r/all."""
        await self.do_post(ctx, "/search.json", q=query, limit=20)

    @reddit.command(name="subreddit", aliases=["sr"])
    async def subreddit_search(self, ctx, subreddit, *, query):
        """Search up a post on a subreddit."""
        await self.do_post(ctx, f"/r/{urlquote(subreddit, safe='')}/search.json", q=query, limit=20, restrict_sr="true")

    @reddit.command(name="subsort", aliases=["ss"])
    async def subreddit_search_sorted(self, ctx, subreddit, sort_type: lambda x: x.lower()="hot"):
        """Get a random post from a subreddit.

        You can optionally sort by `hot`, `new`, `rising`, `top` or `controversial`.
        Default is `hot`."""
        if sort_type not in {"hot", "new", "rising", "top", "controversial"}:
            return await ctx.send(f"`{sort_type}` is not a valid sort type.")

        await self.do_post(ctx, f"/r/{urlquote(subreddit, safe='')}/{sort_type}.json", limit=20)

    async def do_post(self, ctx, path, **params):
        fmt = path.lower() + ":".join([f"{k}={v}" for k, v in params.items()]).lower()

        try:
            return await self.embed_post(ctx, self._post_cache[fmt].pop())
        except (KeyError, IndexError):
            pass

        data = await ctx.get(self.BASE + path, **params, __headers=self.headers)
        results = data["data"]["children"]

        if not results:
            raise commands.BadArgument("No results.")

        self._post_cache[fmt] = ret = deque(results, maxlen=20)

        return await self.embed_post(ctx, ret.pop())

    async def embed_post(self, ctx, data):
        post = Post(data["data"])

        if post.nsfw and not ctx.channel.is_nsfw():
            raise commands.BadArgument("Post is NSFW while this channel isn't.")

        embed = discord.Embed(title=post.title, url=post.url, timestamp=post.created_at, color=discord.Color(0x008CFF))
        embed.set_author(name=post.subreddit)
        embed.set_footer(text=f"Comments: {post.comments_count} | Crossposts: {post.crossposts_count} | Posted on: ")

        if post.type is PostType.IMAGE:
            embed.set_image(url=post.link)
        elif post.type is PostType.EMBED:
            embed.url = post.url
            if post.e_title:
                embed.title = post.e_title
            if post.e_author_name and post.e_author_url:
                embed.set_author(name=post.e_author_name, url=post.e_author_url)
            if post.e_desc:
                embed.description = post.e_desc
            if post.e_thumbnail:
                embed.set_thumbnail(url=post.e_thumbnail)
        elif post.type is PostType.LINK:
            embed.add_field(name="Link post", value=html.unescape(post.link))
        elif post.type is PostType.VIDEO:
            embed.add_field(name="Video content", value=f"[Click here]({post.link})")
        elif post.type is PostType.TEXT:
            text = utils.trunc_text(post.text, 1024)
            embed.add_field(name="Text content", value=text or "No text.")

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Reddit(bot))
