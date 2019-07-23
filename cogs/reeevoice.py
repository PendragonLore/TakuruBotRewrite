import asyncio
import logging
import re
import typing
from datetime import datetime, timedelta

import discord
import wavelink
from discord.ext import commands, flags, tasks
from jishaku.paginators import PaginatorEmbedInterface

import utils
from utils import if_no_perms_then_vote, player_perms_check

LOG = logging.getLogger("cogs.reeevoice")


class Music(commands.Cog):
    """Play music in voice chat or something like that.
    Still WIP, might break."""

    def __init__(self, bot):
        self.bot = bot

        self.wave_node = None

        self.start_nodes.start()

    def cog_unload(self):
        self.start_nodes.cancel()

    @tasks.loop(count=1)
    async def start_nodes(self):
        if not self.wave_node:
            try:
                self.wave_node = await self.bot.wavelink.initiate_node(**self.bot.config.wavelink)
            except wavelink.NodeOccupied:
                self.wave_node = self.bot.wavelink.nodes["salieri"]

        self.wave_node.set_hook(self.event_hook)

    event_regex = re.compile(r"[A-Z][^A-Z]*")

    def event_hook(self, event):
        name = "_".join([x.lower() for x in self.event_regex.findall(event.__class__.__name__)])
        self.bot.dispatch(f"wavelink_{name.replace('_event', '')}", event)

    @commands.group(name="v", invoke_without_command=True, case_insensitive=True)
    async def voice_(self, ctx):
        """Main voice related group."""

    @voice_.command(name="connect", cls=flags.FlagCommand)
    async def connect(self, ctx, *, channel: typing.Optional[discord.VoiceChannel] = utils.CurrentVoiceChannel):
        """Connect to the author's voice channel or a mentioned one."""
        if ctx.player.channel_id == channel.id:
            raise commands.BadArgument("Alread connected to the same channel.")

        perms = channel.permissions_for(ctx.me)
        if not perms.speak or not perms.connect:
            raise commands.BadArgument("I need the speak and connect permissions to play music.")

        await ctx.player.connect(channel.id)

        await ctx.send(f"Connected to **{channel}**.", delete_after=10)

        ctx.player.current_text = ctx.channel

    @voice_.command(name="play", cls=flags.FlagCommand)
    async def play(self, ctx, *, track: utils.TrackConverter = utils.FirstAttachment(with_filename=True)):
        """Play music.

        This supports youtube, vimeo, bandcamp, twitch, soundcloud, normal http streams and discord attachments urls.
        By default searches youtube. If no arguments are provided it will check for attachments."""
        if isinstance(track, tuple):  # attachment
            # if the file name doesn't have an extension and no "." the title will be at index 2
            title, _, maybe_title = track[1].rpartition(".")
            track = await utils.TrackConverter().convert(ctx, track[0])

            track.title = title or maybe_title or "Unknown Title"

        if isinstance(track, wavelink.TrackPlaylist):
            for t in track.tracks:
                ctx.player.queue.put(t)

            title = track.data["playlistInfo"]["name"]
            return await ctx.player.current_text.send(
                f"Added **{utils.Plural(len(track.tracks)):track}** from **{title}** to the queue."
            )

        ctx.player.queue.put(track)

        await ctx.player.current_text.send(f"Added **{track}** to the queue.")

    @voice_.command(name="dc", aliases=["disconnect", "destroy", "stop"])
    @player_perms_check()
    async def disconnect(self, ctx):
        """Stop, clear the queue and disconnect the player from the current channel.

        Only the player owner, an admin or a moderator can use this command."""
        fmt = f"Disconnected from **{ctx.player.current_voice}**."

        await ctx.player.destroy()

        await ctx.send(fmt)

    @voice_.command(name="np")
    async def nowplaying(self, ctx):
        """Show some basic information about the currently playing track.

        If the track is from youtube, a lot more metadata will be fetched."""
        track = ctx.player.current
        await track.set_metadata()

        embed = discord.Embed(title=str(track), url=track.uri, color=discord.Color(0xd7140e))

        if track.is_from_youtube and track.has_metadata:
            embed.set_footer(text="Posted at")
            embed.timestamp = track.posted_at
            if track.description.strip():
                embed.add_field(name="Description", value=utils.trunc_text(track.description, 200))
            embed.set_author(name=track.channel_name, url=track.channel_url, icon_url=track.channel_thumb)
            embed.add_field(name="Stats", value=(f"{track.views:,} \U0001f440 | "
                                                 f"{track.likes:,} \U0001f44d/\U0001f44e {track.dislikes:,}"))

        embed.set_thumbnail(url=f"https://img.youtube.com/vi/{track.ytid}/maxresdefault.jpg")

        embed.add_field(name="Completed / Duration", value=f"{ctx.player.fmt_position} / {track.fmt_duration}")

        await ctx.player.current_text.send(embed=embed)

    @voice_.command(name="queue")
    async def queue(self, ctx):
        """Get a list of songs currently in the queue."""
        total = list(filter(lambda t: not t.is_dead, ctx.player.queue.fetch_all()))

        print(total)

        if not total:
            return await ctx.player.current_text.send("The queue is empty.")

        duration = sum(x.duration for x in total if not x.is_stream)

        try:
            fmt = str(timedelta(milliseconds=duration)).split(".")[0]
        except IndexError:
            fmt = "0:00:00"

        pages = commands.Paginator(max_size=1000, prefix="", suffix="")
        interface = PaginatorEmbedInterface(bot=ctx.bot, owner=ctx.author, paginator=pages,
                                            embed=discord.Embed(
                                                title=f"**{utils.Plural(len(total)):track}** with a remaining duration "
                                                f"of **{fmt}** (not counting streams)"
                                            ), timeout=60)
        for n, track in enumerate(total, 1):
            trunc = 62 - len(str(track.requester))
            pages.add_line(f"`{n}` - [**{utils.trunc_text(track.title, trunc)}**]({track.uri}) by "
                           f"**{track.requester}**")

        await interface.send_to(ctx)

    @voice_.command(name="qrem")
    async def qskip(self, ctx, index: lambda x: int(x) - 1):
        """Remove a track from the queue.

        The index are based on the ones seen in ``queue``."""
        if not ctx.player.queue:
            return await ctx.send("The queue is empty.")
        if index < 0:
            return await ctx.send("Index cannot be negative or zero.")

        try:
            track = ctx.player.queue.pop(index)
        except IndexError:
            await ctx.send(f"No track present at index {index + 1}.")
        else:
            await ctx.send(f"Removed **{track}** from the queue.")

    @voice_.command(name="skip")
    @if_no_perms_then_vote("skips", "Voted to skip the current track.")
    async def skip(self, ctx):
        """Skip the current song.

        If you're not an admin, player owner or moderator this will be counted as a vote."""
        fmt = f"Skipped **{ctx.player.current}**."
        await ctx.player.stop()

        await ctx.player.current_text.send(fmt)

    @voice_.command(name="shuffle")
    @if_no_perms_then_vote("shuffles", "Voted to shuffle the queue.")
    async def shuffle(self, ctx):
        """Shuffle the queue.

        If you're not an admin, player owner or moderator this will be counted as a vote."""
        ctx.player.queue.shuffle()

        await ctx.player.current_text.send("Shuffled the queue.")

    @voice_.command(name="setvol", aliases=["setvolume", "volume"])
    async def volume(self, ctx, volume: typing.Optional[lambda x: min(int(x), 1000)] = None):
        """Set the volume for the player.

        Max is set to 1000."""
        if volume is None:
            return await ctx.player.current_text.send(f"The player's current volume is set to `{ctx.player.volume:,}`.")
        await ctx.player.set_volume(volume)

        await ctx.player.current_text.send(f"Set volume of the player to {volume}.")

    @voice_.command(name="search")
    async def search(self, ctx, *, tracks: utils.TrackConverter(list_ok=True, url_ok=False)):
        """Search and select a track to put it in the queue."""
        pages = commands.Paginator(prefix=None, suffix=None, max_size=500)

        interface = PaginatorEmbedInterface(
            bot=ctx.bot, owner=ctx.author, paginator=pages, embed=discord.Embed(
                title="Type **{0}1-{1}** to select a song."
            ), timeout=60
        )

        for index, track in enumerate(tracks, 1):
            pages.add_line(f"`{index}.` `[{track.fmt_duration}]` [**{utils.trunc_text(str(track), 55)}**]({track.uri})")

        interface._embed.title = interface._embed.title.format(ctx.prefix, index)

        await interface.send_to(ctx)

        prompt = interface.message

        def check(m):
            actual = m.content.replace(ctx.prefix, "")
            if not actual.isdigit():
                return False

            return (0 <= (int(actual) - 1) <= index and m.content.startswith(ctx.prefix)
                    and ctx.author == m.author and ctx.channel == m.channel)

        try:
            response = await ctx.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            await prompt.edit(content="Took too long.", embed=None)
        else:
            await prompt.delete()
            await ctx.invoke(self.play, track=tracks[int(response.content.replace(ctx.prefix, "")) - 1])

    @voice_.command(name="repeat")
    @if_no_perms_then_vote("repeats", "Voted to repeat the current track.")
    async def repeat_current(self, ctx):
        """Repeat the current track. This means that it will be put at the top of the queue.

        If you're not an admin, player owner or moderator this will be counted as a vote"""
        ctx.player.queue.put(ctx.player.current)

        await ctx.player.current_text.send(f"**{ctx.player.current}** has been put back into the queue.")

    @voice_.command(name="loop")
    @player_perms_check()
    async def loop(self, ctx):
        """Loop the current queue.

        This means that every time a song ends or is skipped it will be put back at the end of the queue.
        Only the player owner, an admin or a moderator can use this command."""
        ctx.player.looping = not ctx.player.looping

        await ctx.player.current_text.send(
            f"The player {'is now looping' if ctx.player.looping else 'has stopped looping.'}"
        )

    @voice_.command(name="loopcurrent")
    @player_perms_check()
    async def loop_current(self, ctx):
        """Loop the current track.

        This means that every time the current song ends or is skipped it will be put back at the start of the queue.
        Only the player owner, an admin or a moderator can use this command."""
        ctx.player.loop_single = not ctx.player.loop_single

        await ctx.player.current_text.send(
            f"The current track {'is now looping' if ctx.player.loop_single else 'has stopped looping.'}"
        )

    @voice_.command(name="seek", aliases=["jump"])
    async def seek(self, ctx, *, time: utils.ShortTime(past_ok=False, arg_required=False)):
        """Seek to a point in time of a song.

        The date must be in a format like ``2m45s``."""
        delta = (time.date - datetime.utcnow()) + timedelta(seconds=1)

        await ctx.player.seek(delta.total_seconds() * 1000)

        fmt = str(delta).split(".")[0]

        await ctx.player.current_text.send(f"{ctx.command.qualified_name.capitalize()}ed to {fmt}.")

    @voice_.command(name="pause")
    @if_no_perms_then_vote("pauses", "Voted to {thing} the player.")
    async def pause(self, ctx):
        """Pause (or resume if it was already paused) the player.

        If you're not an admin, player owner or moderator this will be counted as a vote."""
        await ctx.player.set_pause(not ctx.player.paused)

        await ctx.player.current_text.send(f"{'Paused' if ctx.player.paused else 'Resumed'} the player.")

    @voice_.command(name="move")
    async def move(self, ctx, index: int, target: int):
        """Move a track to a certain index of the queue."""
        if not ctx.player.queue:
            return await ctx.player.current_text.send("The queue is empty.")

        if len(ctx.player.queue) < index:
            return await ctx.player.current_text.send("Index higher then queue's length.")

        track = ctx.player.queue.pop(index - 1)
        ctx.player.queue.put(track, index=target - 1)

        await ctx.player.current_text.send(f"Moved track from index ``{index}`` to ``{target}``")

    @voice_.command(name="eq")
    async def set_equalizer(self, ctx, *, equalizer: lambda x: x.upper() = None):
        """Set the player's equalizer.

        Must be one of `flat` (default), `boost`, `metal` or `piano`."""
        if not equalizer:
            return await ctx.player.current_text.send(f"Current equalizer set to {ctx.player.eq}")
        if equalizer not in ctx.player.equalizers:
            return await ctx.player.current_text.send(f"`{equalizer}` is not a valid equalizer. "
                                                      "Try one of `flat` (default), `boost`, `metal` or `piano`")
        ctx.player.eq = equalizer
        await ctx.player.set_preq(equalizer)

        await ctx.player.current_text.send(f"Player equalizer set to `{equalizer}`.")

    @play.before_invoke
    @search.before_invoke
    async def ensure_voice(self, ctx):
        if not ctx.player.is_connected:
            if ctx.author.voice is None:
                raise commands.BadArgument("Not connected to a voice channel.")
            await ctx.invoke(self.connect, channel=ctx.author.voice.channel)

    async def cog_before_invoke(self, ctx):
        if ctx.command == self.voice_:
            return

        if not ctx.player.owner:
            ctx.player.owner = ctx.author
        # a bit of a cluster fuck to ensure that there will always be a player owner.
        if ctx.player.is_connected and ctx.author.voice:
            c = ctx.author.voice.channel.members
            if ctx.me in c and ctx.player.owner not in c:
                ctx.player.owner = ctx.author

        if ctx.command in {self.connect, self.play, self.search}:
            return

        if not ctx.player.is_connected or not ctx.author.voice:
            raise commands.BadArgument("Not connected to a voice channel.")
        if ctx.me not in ctx.author.voice.channel.members:
            raise commands.BadArgument("Not in my same voice channel.")

        if ctx.command in {self.disconnect, self.queue, self.qskip, self.move}:
            return

        if not ctx.player.is_playing:
            raise commands.BadArgument("I'm not playing anything.")

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload):
        await payload.player.player.current_text.send(f"{payload.error} - Removing from the queue.")
        payload.player.queue.popleft()

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload):
        await payload.track.ctx.send("The track somehow got stuck. "
                                     "If the track was a stream it means the stream is having latency issues.")
        await payload.player.stop()


def setup(bot):
    bot.add_cog(Music(bot))
