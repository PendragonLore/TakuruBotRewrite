import re
import wavelink
import typing

import discord
from discord.ext import commands, tasks, flags

import utils


class TrackConverter(commands.Converter):
    URL_REGEX = re.compile(r"https?://(www\.)?[-a-zA-Z0-9@:%._+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_+.~#?&/=]*)")

    def __init__(self, *, list_ok=False, url_ok=True):
        self.list_ok = list_ok
        self.url_ok = url_ok

    async def convert(self, ctx, argument):
        if self.URL_REGEX.match(argument) and self.url_ok:
            tracks = await ctx.bot.wavelink.get_tracks(argument)
        else:
            tracks = await ctx.bot.wavelink.get_tracks(f"ytsearch:{argument}")

        if not tracks:
            raise commands.BadArgument("No tracks found.")

        if not self.list_ok:
            if isinstance(tracks, wavelink.TrackPlaylist):
                tracks.tracks = [utils.Track(id_=t.id, info=t.info, ctx=ctx, query=argument) for t in tracks.tracks]
            else:
                t = tracks[0]
                tracks = utils.Track(id_=t.id, info=t.info, ctx=ctx, query=argument)

        return tracks


class Music(commands.Cog):
    """Play music in voice chat or something like that.
    Still WIP, might break."""

    def __init__(self, bot):
        self.bot = bot

        self.wave_node: wavelink.Node = None

        self.start_nodes.start()

    def cog_unload(self):
        self.start_nodes.cancel()

    @tasks.loop(count=1)
    async def start_nodes(self):
        if not self.wave_node:
            try:
                self.wave_node = await self.bot.wavelink.initiate_node(**self.bot.config.wavelink)
            except wavelink.NodeOccupied:
                pass

        self.wave_node.set_hook(self.event_hook)

    event_regex = re.compile(r"[A-Z][^A-Z]*")

    def event_hook(self, event):
        name = "_".join([x.lower() for x in self.event_regex.findall(event.__class__.__name__)])
        self.bot.dispatch(f"wavelink_{name.replace('_event', '')}", event)

    @commands.command(name="connect", cls=flags.FlagCommand)
    async def connect(self, ctx, *, channel: typing.Optional[discord.VoiceChannel] = utils.CurrentVoiceChannel):
        if ctx.player.channel_id == channel.id:
            raise commands.BadArgument("Alread connected to the same channel.")
        perms = channel.permissions_for(ctx.me)

        if not perms.speak or not perms.connect:
            raise commands.BadArgument("I need the speak and connect permissions to play music.")

        await ctx.player.connect(channel.id)

        await ctx.send(f"Connected to **{channel}**.")

    @commands.command(name="play")
    async def play(self, ctx, *, track: TrackConverter):
        if isinstance(track, wavelink.TrackPlaylist):
            for t in track.tracks:
                await ctx.player.queue.put(t)

            return await ctx.send(f"Added **{utils.Plural(len(track.tracks)):track}** to the queue.")

        await ctx.player.queue.put(track)

        await ctx.send(f"Added **{track}** to the queue.")

    async def cog_before_invoke(self, ctx):
        if ctx.command == self.connect:
            return

        if not ctx.player.is_connected:
            if ctx.author.voice is None:
                raise commands.BadArgument("Not connected to a voice channel.")
            await ctx.invoke(self.connect, channel=ctx.author.voice.channel)


def setup(bot):
    bot.add_cog(Music(bot))
