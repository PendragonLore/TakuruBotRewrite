import inspect
import io
# UJSON DOESN'T PRETTIFY WELL REEEE
import json
import os
import platform
import time
import typing
from collections import Counter
from datetime import datetime

import discord
import humanize
import psutil
from discord.ext import commands, flags
from jishaku.paginators import PaginatorInterface, WrappedPaginator

import utils


class General(commands.Cog, command_attrs=dict(cooldown=commands.Cooldown(1, 2.5, commands.BucketType.user))):
    """General use commands."""

    def __init__(self, bot):
        self.bot = bot

        self.status_mapping = {
            discord.Status.online: utils.ONLINE,
            discord.Status.idle: utils.IDLE,
            discord.Status.dnd: utils.DND,
            discord.Status.do_not_disturb: utils.DND,
            discord.Status.offline: utils.OFFLINE,
            discord.Status.invisible: utils.OFFLINE
        }

    @commands.command(aliases=["socketstats"])
    async def gatewaystats(self, ctx):
        pag = PaginatorInterface(bot=ctx.bot,
                                 paginator=commands.Paginator(prefix="```json", suffix="```", max_size=1800),
                                 owner=ctx.author)

        jsonified = json.dumps(dict(ctx.bot.gateway_messages), sort_keys=True, indent=4)

        for field in jsonified.splitlines():
            await pag.add_line(field)

        await pag.send_to(ctx)

    @commands.Cog.listener()
    async def on_socket_response(self, payload):
        event_type = payload.get("t")
        if event_type is None:
            return

        self.bot.gateway_messages[event_type] += 1

    @commands.command(name="userinfo", cls=flags.FlagCommand)
    async def userinfo(self, ctx, *, member: typing.Optional[discord.Member] = utils.Author):
        """Get yours or a mentioned user's information."""
        bot = "\U0001f916"
        guild = member.guild

        embed = discord.Embed(color=member.color)
        embed.set_author(name=f"{bot if member.bot else ''} {member} - {member.id}", url=member.avatar_url)
        embed.set_thumbnail(url=member.avatar_url)

        if member.nick:
            embed.add_field(name="Nickname", value=member.nick)

        ex = f"\n\U000026fd nitro boosted on {utils.fmt_delta(member.premium_since)}" if member.premium_since else ''
        embed.add_field(name="Dates", value=(f"\U0001f389 joined {guild} on {utils.fmt_delta(member.joined_at)}\n"
                                             f"\U0001f4c5 joined discord on {utils.fmt_delta(member.created_at)}" + ex))

        if member.activity:
            activity_type = member.activity.type.name.capitalize()
            embed.add_field(name=activity_type, value=member.activity.name)
        if member.roles[1:]:
            roles = " ".join(role.mention for role in reversed(member.roles[1:20]))
            embed.add_field(name="Roles", value=f"{roles}{'...' if len(member.roles) > 20 else ''}")

        embed.add_field(
            name="Status",
            value=f"{self.status_mapping[member.desktop_status]} Desktop\n"
            f"{self.status_mapping[member.web_status]} Web\n"
            f"{self.status_mapping[member.mobile_status]} Mobile", inline=False
        )

        await ctx.send(embed=embed)

    async def do_perms(self, ctx, iterable, color):
        def fmt(arg: str):
            return arg.replace("_", " ").title().replace("Tts", "TTS")

        missing = [fmt(perm) for perm, value in iterable if not value]
        has = [fmt(perm) for perm, value in iterable if value]

        embed = discord.Embed(color=color)
        embed.add_field(name="Allowed", value="\n".join(has) or "None :thinking:")
        embed.add_field(name="Missing", value="\n".join(missing) or "None :thinking:")

        await ctx.send(embed=embed)

    @commands.group(name="perms", aliases=["permissions"], invoke_without_command=True, case_insensitive=True)
    async def perms(self, ctx):
        """Group about permissions."""
        await ctx.invoke(self.perms_guild, member=ctx.author)

    @perms.command(name="guild", aliases=["server"], cls=flags.FlagCommand)
    async def perms_guild(self, ctx, *, member: discord.Member = utils.Author):
        """Gives the missing and available guild permissions for the author or a member.

        This does **not** count in channel overwrites."""
        await self.do_perms(ctx, member.guild_permissions, member.color)

    @perms.command(name="channel", aliases=["overwrites", "overwrite"], cls=flags.FlagCommand)
    async def perms_channel(self, ctx, member: typing.Optional[discord.Member] = utils.Author,
                            channel: typing.Optional[
                                typing.Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel]
                            ] = utils.CurrentTextChannel):
        """Gives the missing and available permissions of the author or a member in a channel.

        The channel could be a text, voice or category one."""
        await self.do_perms(ctx, member.permissions_in(channel), member.color)

    @commands.command(name="invite")
    async def invite(self, ctx):
        """Send an invite for the bot."""
        await ctx.send(discord.utils.oauth_url(ctx.bot.user.id, permissions=discord.Permissions(37055814)))

    @commands.command(name="avatar", aliases=["av", "pfp"], cls=flags.FlagCommand)
    async def avatar_url(self, ctx, member: typing.Optional[discord.Member] = utils.Author):
        """Get yours or some mentioned users' profile picture."""
        a = member.avatar_url_as

        png = a(format="png", size=1024)
        jpeg = a(format="jpeg", size=1024)
        webp = a(format="webp", size=1024)

        gif = a(format="gif", size=1024) if member.is_avatar_animated() else None

        embed = discord.Embed(
            color=discord.Color(0x008CFF),
            title=str(member),
            description=f"[png]({png}) | [jpeg]({jpeg}) | [webp]({webp}) {f'| [gif]({gif})' if gif else ''} ",
        )

        embed.set_image(url=member.avatar_url)

        await ctx.send(embed=embed)

    @commands.command(name="ping")
    async def ping(self, ctx):
        """It's like pings but pongs without pings."""
        start = time.perf_counter()
        message = await ctx.send("Ping...")
        end = time.perf_counter()

        await message.edit(
            content=f"Pong! Latency is: {(end - start) * 1000:.2f}ms, "
            f"websocket latency is {ctx.bot.latency * 1000:.2f}ms"
        )

    @commands.command(name="about")
    async def about(self, ctx):
        """Get some basic info about the bot."""
        invite = discord.utils.oauth_url(ctx.bot.user.id, permissions=discord.Permissions(37055814))

        member_status = Counter(str(m.status) for m in ctx.bot.get_all_members())
        channels = Counter(str(m.__class__.__name__) for m in ctx.bot.get_all_channels())

        embed = discord.Embed(title="About", color=discord.Color(0x008CFF))
        embed.description = "A silly multi purpose bot. Testing version of Takuru#7838"

        embed.add_field(name="Members", value=(f"{utils.ONLINE} {member_status['online']}"
                                               f"{utils.IDLE} {member_status['idle']}\n"
                                               f"{utils.DND} {member_status['dnd']}"
                                               f"{utils.OFFLINE} {member_status['offline']}"))
        embed.add_field(name="Channels", value=(f"{utils.TEXT} {channels['TextChannel']}\n"
                                                f"{utils.VOICE} {channels['VoiceChannel']}"))
        embed.add_field(name="Guilds", value=str(len(ctx.bot.guilds)))
        embed.add_field(name="Uptime", value=utils.fmt_uptime(ctx.bot.uptime))
        embed.add_field(name="Useful links", value=(f"[Invite]({invite}) | [Support](https://discord.gg/tH92pwF) | "
                                                    f"[Source](https://github.com/PendragonLore/TakuruBotRewrite)"),
                        inline=False)
        embed.set_footer(text=f"Smh wrong siders. | Made by {ctx.bot.owner}", icon_url=ctx.bot.user.avatar_url)

        await ctx.send(embed=embed)

    @commands.command()
    async def techinfo(self, ctx):
        lines = ctx.bot.python_lines
        nat = humanize.naturalsize

        py_fmt = (f"{platform.python_implementation()} {platform.python_version()} "
                  f"using discord.py {discord.__version__}"
                  f"\n{lines[0]} lines across {lines[1]} files")

        total, used, free, _ = psutil.disk_usage("/")

        vem = psutil.virtual_memory()

        sys_fmt = (f"{platform.platform()}\nSystem has been up for "
                   f"{utils.fmt_uptime(datetime.fromtimestamp(psutil.boot_time()) - datetime.utcnow())}\n"
                   f"{nat(vem.total)} total memory, "
                   f"{nat(vem.used)} used and {nat(vem.free)} free\n"
                   f"{nat(total)} total disk space, {nat(used)} used and {nat(free)} free")

        embed = discord.Embed(color=discord.Color(0x008CFF), title="Technical information")
        embed.add_field(name="Python stats", value=py_fmt, inline=False)
        embed.add_field(name="System info", value=sys_fmt)

        proc = psutil.Process()

        with proc.oneshot():
            mem = proc.memory_full_info()

            embed.add_field(name="Process info", value=(f"`{proc.name()}` ({proc.pid} PID) "
                                                        f"with {proc.num_threads()} threads\n"
                                                        f"Using {nat(mem.rss)} physical memory and "
                                                        f"{nat(mem.vms)} virtual memory ({nat(mem.uss)} unique)"))

        pool = ctx.db
        embed.add_field(name="Database pool info", value=(f"Total `Pool.acquire` waiters: {len(pool._queue._getters)}\n"
                                                          f"Current pool generation: {pool._generation}\n"
                                                          f"Connections in use: "
                                                          f"{len(pool._holders) - pool._queue.qsize()}"))

        await ctx.send(embed=embed)

    @commands.command()
    async def source(self, ctx, *, command: str = None):
        """Get the url of this bot's source.

        You can also include a command to get the specific page for it."""
        source_url = "https://github.com/PendragonLore/TakuruBotRewrite"
        if command is None:
            return await ctx.send(source_url)

        if command == "help":
            src = type(ctx.bot.help_command)
            module = src.__module__
            filename = inspect.getsourcefile(src)
        else:
            obj = ctx.bot.get_command(command.replace(".", " "))
            if obj is None:
                return await ctx.send('Could not find command.')

            src = obj.callback.__code__
            module = obj.callback.__module__
            filename = src.co_filename

        lines, firstlineno = inspect.getsourcelines(src)
        if not module.startswith("discord"):
            location = os.path.relpath(filename).replace("\\", "/")
        else:
            location = module.replace(".", "/") + ".py"
            source_url = "https://github.com/Rapptz/discord.py"

        final_url = f"<{source_url}/blob/master/{location}#L{firstlineno}-L{firstlineno + len(lines) - 1}>"
        await ctx.send(final_url)

    @commands.command(name="serverinfo", aliases=["guildinfo"])
    async def guild_info(self, ctx):
        """Get some of this guild's information."""
        guild: discord.Guild = ctx.guild
        embed = discord.Embed(color=discord.Color(0x008CFF), title=f"{guild} - {guild.id}")

        total_nsfw = sum([1 for channel in guild.text_channels if channel.is_nsfw()])

        embed.set_thumbnail(url=guild.icon_url)
        embed.set_author(icon_url=guild.owner.avatar_url, name=str(guild.owner))

        if guild.banner_url:
            embed.set_image(url=guild.banner_url)

        available_features = []
        for feature in guild.features:
            available_features.append(f"\U00002705 {feature.replace('_', ' ').title()}")

        embed.add_field(
            name="Channel Stats",
            value=f"{utils.TEXT} {len(guild.text_channels)} ({total_nsfw} NSFW)"
            f"\n{utils.VOICE} {len(guild.voice_channels)}\n"
            f"\U0001f4d8 {len(guild.categories)}",
        )

        member_status = Counter(str(m.status) for m in guild.members)

        embed.add_field(name="Member stats", value=(f"{guild.member_count} total members\n"
                                                    f"{utils.ONLINE} {member_status['online']} "
                                                    f"{utils.OFFLINE} {member_status['offline']}\n"
                                                    f"{utils.IDLE} {member_status['idle']} "
                                                    f"{utils.DND} {member_status['dnd']}\n"
                                                    f"{guild.premium_subscription_count} nitro boosters\n"))
        embed.add_field(name="Other stats", value=(f"{len(guild.roles)} total roles\n"
                                                   f"{len(guild.emojis)} total emotes ({guild.emoji_limit} max)\n"
                                                   f"{guild.premium_tier} nitro boost tier\n"
                                                   f"{humanize.naturalsize(guild.filesize_limit)} upload limit\n"
                                                   f"{humanize.naturalsize(guild.bitrate_limit)} voice rate limit"))

        if available_features:
            embed.add_field(name="Features", value="\n".join(available_features))
        embed.add_field(
            name="Created at",
            value=utils.fmt_delta(guild.created_at),
        )

        await ctx.send(embed=embed)

    @commands.command(name="firstmsg", aliases=["firstmessage"], cls=flags.FlagCommand)
    async def first_message(self, ctx, channel: typing.Optional[discord.TextChannel] = utils.CurrentTextChannel):
        """Get the current or a mentioned channel's first message."""
        first_message = (await channel.history(limit=1, oldest_first=True).flatten())[0]

        embed = discord.Embed(title=f"#{channel}'s first message", color=discord.Color(0x008CFF))
        embed.set_author(name=str(first_message.author), icon_url=first_message.author.avatar_url)
        embed.description = first_message.content
        embed.add_field(name="\u200b", value=f"[Jump!]({first_message.jump_url})")
        embed.set_footer(text=f"Message is from {utils.fmt_delta(first_message.created_at)}")

        await ctx.send(embed=embed)

    @commands.command(name="emoji", aliases=["bigmoji", "hugemoji", "e"])
    async def big_emoji(self, ctx, emoji: typing.Union[discord.Emoji, discord.PartialEmoji, str]):
        """Get a big version of an emoji."""
        if isinstance(emoji, (discord.Emoji, discord.PartialEmoji)):
            fp = io.BytesIO()
            await emoji.url.save(fp)

            await ctx.send(file=discord.File(fp, filename=f"{emoji.name}{'.png' if not emoji.animated else '.gif'}"))
        else:
            fmt_name = "-".join(f"{ord(c):x}" for c in emoji)
            r = await ctx.get(f"http://twemoji.maxcdn.com/2/72x72/{fmt_name}.png")

            await ctx.send(file=discord.File(io.BytesIO(r), filename=f"{fmt_name}.png"))

    @commands.command(name="say", aliases=["echo"])
    async def say(self, ctx, *, arg: commands.clean_content):
        """Make the bot repeat what you say."""
        await ctx.send(arg)

    @commands.command(name="urlshort", aliases=["bitly"])
    @utils.requires_config("tokens", "apis", "bitly")
    async def bitly(self, ctx, *, url: lambda x: x.strip("<>")):
        """Make an url shorter idk."""
        data = json.dumps({"long_url": url})

        r = await ctx.post(
            "https://api-ssl.bitly.com/v4/shorten",
            __data=data,
            __headers=(("Content-Type", "application/json"),
                       ("Authorization", ctx.bot.config.tokens.apis.bitly)),
        )

        if len(r["link"]) > len(url):
            return await ctx.send(f"<{r['link']}>")

        await ctx.send(f"<{r['link']}> (shortened by **{len(url) - len(r['link'])}** characters)")

    def build_amiibo_embed(self, data):
        id_ = data["head"] + "-" + data["tail"]
        embed = discord.Embed(
            title=data["character"], url=f"https://amiibo.life/nfc/{id_}", color=discord.Color(0x008CFF)
        )
        embed.set_thumbnail(url=data["image"])
        embed.description = (
            f"**Game Series:** {data['gameSeries']}\n"
            f"**Amiibo Series:** {data['amiiboSeries']}\n"
            f"**Type**: {data['type']}"
        )
        try:
            r = datetime.strptime(data["release"]["eu"], "%Y-%m-%d")
            delta = humanize.naturaldelta(datetime.utcnow() - r)
            embed.set_footer(text=f"Released {delta} ago")
        except (ValueError, TypeError, AttributeError):
            pass

        return embed

    @commands.command(name="amiibo")
    async def amiibo(self, ctx, *, name: commands.clean_content):
        """Get info about an amiibo."""
        amiibo = await ctx.get("https://www.amiiboapi.com/api/amiibo", cache=True, name=name)

        for data in amiibo["amiibo"]:
            embed = self.build_amiibo_embed(data)

            ctx.pages.add_entry(embed)

        await ctx.paginate()

    @commands.command()
    async def tree(self, ctx):
        """Gives a tree like view of the guild's channels."""
        paginator = WrappedPaginator()
        paginator.add_line(".")

        memo = "\U0001f4dd"
        speaker = "\U0001f508"

        categories = ctx.guild.by_category()

        for index, (category, channels) in enumerate(categories, 1):
            if len(categories) == index:
                div = "└──"
                ex = " "
            else:
                div = "├──"
                ex = "│"

            paginator.add_line(f"{div}\U0001f4d8 {category}")

            for i, chan in enumerate(channels, 1):
                if len(category.channels) == i:
                    div = "└──"
                else:
                    div = "├──"

                paginator.add_line(f"{ex}  {div}{memo if isinstance(chan, discord.TextChannel) else speaker} #{chan}")

        for p in paginator.pages:
            await ctx.send(p)

    @commands.group(case_insensitive=True, invoke_without_command=True)
    async def prefix(self, ctx):
        """Group related to prefixes.

        If no command is provided it will specify the current prefix."""
        pre = ctx.bot.prefix_dict.get(ctx.guild.id, "kur ")

        await ctx.send(f"Current prefix is {pre!r}")

    @prefix.command(name="set")
    @utils.is_guild_owner_or_perms(manage_guild=True)
    async def prefix_set(self, ctx, prefix):
        """Set this guild's prefix.

        A prefix can't be longer then 32 characters.
        You must also either be the guild's owner or have the manage guild permission."""
        if len(prefix) > 32:
            raise commands.BadArgument("Prefix length can be 32 at maximum.")

        async with ctx.db.acquire() as db:
            sql = """
            INSERT INTO prefixes (guild_id, prefix) 
            VALUES ($1, $2) 
            ON CONFLICT (guild_id) DO 
            UPDATE SET prefix = $2;
            """
            await db.execute(sql, ctx.guild.id, prefix)

        ctx.bot.prefix_dict[ctx.guild.id] = prefix

        await ctx.send(f"Set prefix to {prefix!r}")

    @prefix.command(name="remove", aliases=["del", "delete"])
    @utils.is_guild_owner_or_perms(manage_guild=True)
    async def prefix_remove(self, ctx):
        """Remove the custom prefix for this guild.

        You must also either be the guild's owner or have the manage guild permission."""
        async with ctx.db.acquire() as db:
            sql = """
            DELETE FROM prefixes
            WHERE guild_id = $1
            RETURNING prefix;
            """
            ret = await db.fetchval(sql, ctx.guild.id)

        if not ret:
            return await ctx.send("No custom prefix set.")

        del ctx.bot.prefix_dict[ctx.guild.id]

        await ctx.send(f"Custom prefix {ret!r} removed.")

    @commands.Cog.listener()
    async def on_test_complete(self, thing):
        await self.bot.get_guild(thing.gid).get_channel(thing.cid).send(repr(thing))


def setup(bot):
    bot.add_cog(General(bot))
