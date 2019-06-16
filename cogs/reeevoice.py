import asyncio
import datetime
import itertools
import math
import random
import re

import discord
import humanize
import wavelink
from discord.ext import commands

from utils import Player, Track

RURL = re.compile(r"https?:\/\/(?:www\.)?.+")


class Music(commands.Cog):
    """Play music in voice chat or something like that.
    Still WIP, might break."""

    def __init__(self, bot):
        self.bot = bot
        self.wave_node = None

        bot.loop.create_task(self.initiate_nodes())

    async def initiate_nodes(self):
        await self.bot.wait_until_ready()
        if not self.wave_node:
            self.wave_node = await self.bot.wavelink.initiate_node(**self.bot.config.wavelink)

        self.wave_node.set_hook(self.event_hook)

    def event_hook(self, event):
        """Our event hook. Dispatched when an event occurs on our Node."""
        if isinstance(event, wavelink.TrackEnd):
            event.player.next_event.set()
        elif isinstance(event, wavelink.TrackException):
            print(event.error)

    def required(self, player, invoked_with):
        """Calculate required votes."""
        channel = self.bot.get_channel(player.channel_id)
        if invoked_with == "stop":
            if len(channel.members) - 1 == 2:
                return 2

        return math.ceil((len(channel.members) - 1) / 2.5)

    async def has_perms(self, ctx, **perms):
        """Check whether a member has the given permissions."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if ctx.author.id == player.dj.id:
            return True

        channel = ctx.channel
        permissions = channel.permissions_for(ctx.author)

        missing = [perm for perm, value in perms.items() if getattr(permissions, perm, None) != value]

        if not missing:
            return True

        return False

    async def vote_check(self, ctx, command: str):
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        vcc = len(ctx.bot.get_channel(player.channel_id).members) - 1
        votes = getattr(player, command + "s", None)

        if vcc < 3 and not ctx.invoked_with == "stop":
            votes.clear()
            return True

        votes.add(ctx.author.id)

        if len(votes) >= self.required(player, ctx.invoked_with):
            votes.clear()
            return True

        return False

    async def do_vote(self, ctx, player, command: str):
        attr = getattr(player, command + "s", None)
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if ctx.author.id in attr:
            await ctx.send(f"**{ctx.author}**, you have already voted to {command}.")
        elif await self.vote_check(ctx, command):
            await ctx.send(f"Vote request for {command} passed.")
            to_do = getattr(self, f"do_{command}")
            await to_do(ctx)
        else:
            await ctx.send(
                f"**{ctx.author}** has voted to {command} the song."
                f" **{self.required(player, ctx.invoked_with) - len(attr)}** more votes needed."
            )

    @commands.command(name="connect", aliases=["join"])
    @commands.cooldown(1, 2.5, commands.BucketType.guild)
    async def connect_(self, ctx, *, channel: discord.VoiceChannel = None):
        """Connect the bot to voice."""
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        if not channel:
            try:
                channel = ctx.author.voice.channel
            except AttributeError:
                raise commands.BadArgument("No channel to join. Please either specify a valid channel or join one.")

        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if player.is_connected:
            if ctx.author.voice.channel == ctx.guild.me.voice.channel:
                return

        await player.connect(channel.id)

    @commands.command(name="play", aliases=["sing"])
    @commands.cooldown(1, 2.5, commands.BucketType.guild)
    async def play_(self, ctx, *, query: str):
        """Queue a song or playlist for playback."""
        await ctx.trigger_typing()

        await ctx.invoke(self.connect_)
        query = query.strip("<>")

        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send("Bot is not connected to voice. Please join a voice channel to play music.")

        if not player.dj:
            player.dj = ctx.author

        if not RURL.match(query):
            query = f"ytsearch:{query}"

        tracks = await ctx.bot.wavelink.get_tracks(query)
        if not tracks:
            return await ctx.send("No songs were found with that query. Please try again.")

        if isinstance(tracks, wavelink.TrackPlaylist):
            for t in tracks.tracks:
                await player.queue.put(Track(t.id, t.info, ctx=ctx))

            await ctx.send(
                f"Added the playlist **{tracks.data['playlistInfo']['name']}**"
                f" with **{len(tracks.tracks)} songs** to the queue."
            )
        else:
            track = tracks[0]
            await ctx.send(f"Added **{track.title}** to the queue.")
            await player.queue.put(Track(track.id, track.info, ctx=ctx))

        if player.controller_message and player.is_playing:
            if player.position == player.current.duration:
                return
            await player.invoke_controller()

    @commands.command(name="search")
    @commands.cooldown(1, 2.5, commands.BucketType.guild)
    async def search_tracks(self, ctx, *, query: str):
        """Search for a track on YouTube.
        This command is basically like `play` but it lets you choose between 5 tracks."""
        if RURL.match(query):
            return await ctx.invoke(self.play_, query)

        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player.is_connected:
            return await ctx.send("Bot is not connected to voice. Please join a voice channel to play music.")

        search = await ctx.bot.wavelink.get_tracks(f"ytsearch:{query}")
        if not search:
            return await ctx.send("No songs were found with that query. Please try again.")

        tracks = list(itertools.islice(search, 0, 5))
        fmt = [f"**{index}.** {track} [{player.format_delta(track.duration)}]" for index, track in enumerate(tracks, 1)]
        results = await ctx.send(f"Select a song with ``{ctx.prefix}1-5``.\n" + ("\n".join(fmt)))

        def response_check(m):
            return m.author == ctx.author and m.content.startswith(f"{ctx.prefix}")

        try:
            response = await ctx.bot.wait_for("message", timeout=60.0, check=response_check)
        except asyncio.TimeoutError:
            try:
                await results.delete()
            except discord.HTTPException:
                pass
        else:
            try:
                t = tracks[int(response.content.strip(ctx.prefix)) - 1]
            except (ValueError, TypeError, IndexError):
                await ctx.send("Not a valid track ID.")
                try:
                    await results.delete()
                except discord.HTTPException:
                    pass
            else:
                await results.edit(content=f"Added track **{t.title}** to the queue.")
                await player.queue.put(Track(t.id, t.info, ctx=ctx))

                if player.controller_message and player.is_playing:
                    if player.position >= player.current.duration:
                        return
                    await player.invoke_controller()

    @commands.command(name="nowplaying", aliases=["np", "current", "currentsong"])
    @commands.cooldown(1, 2.5, commands.BucketType.guild)
    async def now_playing(self, ctx):
        """Invoke the player controller."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player:
            return

        if not player.is_connected:
            return

        if player.updating or player.update:
            return

        await player.invoke_controller()

    @commands.command(name="pause")
    @commands.cooldown(1, 2.5, commands.BucketType.guild)
    async def pause_(self, ctx):
        """Pause the currently playing song.
        If you are not a DJ or have the necessary permissions it will count as a vote."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player:
            return

        if not player.is_connected:
            await ctx.send("I am not currently connected to voice!")

        if player.paused:
            return

        if await self.has_perms(ctx, manage_guild=True):
            await ctx.send(f"**{ctx.author}** has paused the song as an admin or DJ.")
            return await self.do_pause(ctx)

        await self.do_vote(ctx, player, "pause")

    async def do_pause(self, ctx):
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        player.paused = True
        await player.set_pause(True)

    @commands.command(name="resume")
    @commands.cooldown(1, 2.5, commands.BucketType.guild)
    async def resume_(self, ctx):
        """Resume a currently paused song.
        If you are not a DJ or have the necessary permissions it will count as a vote."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            await ctx.send("I am not currently connected to voice!")

        if not player.paused:
            return

        if await self.has_perms(ctx, manage_guild=True):
            await ctx.send(f"**{ctx.author}** has resumed the song as an admin or DJ.")
            return await self.do_resume(ctx)

        await self.do_vote(ctx, player, "resume")

    async def do_resume(self, ctx):
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        await player.set_pause(False)

    @commands.command(name="skip")
    @commands.cooldown(1, 2.5, commands.BucketType.guild)
    async def skip_(self, ctx):
        """Skip the current song.
        If you are not a DJ or have the necessary permissions it will count as a vote."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send("I am not currently connected to voice!")

        if await self.has_perms(ctx, manage_guild=True):
            await ctx.send(f"**{ctx.author}** has skipped the song as an admin or DJ.")
            return await self.do_skip(ctx)

        if player.current.requester.id == ctx.author.id:
            await ctx.send(f"The requester **{ctx.author}** has skipped the song.")
            return await self.do_skip(ctx)

        await self.do_vote(ctx, player, "skip")

    @commands.command(name="stop")
    @commands.cooldown(1, 2.5, commands.BucketType.guild)
    async def stop_(self, ctx):
        """Stop the player, disconnect and clear the queue."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player.is_connected:
            return await ctx.send("I am not currently connected to voice.")

        if not await self.has_perms(ctx, manage_guild=True):
            return await ctx.send("Only DJs can stop the player.")

        await self.do_stop(ctx)

    async def do_stop(self, ctx):
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        await player.destroy_controller()
        await player.disconnect()
        player.queue._queue.clear()
        await player.stop()

    @commands.command(name="volume", aliases=["vol"])
    @commands.cooldown(1, 2, commands.BucketType.guild)
    async def volume_(self, ctx, *, value: int):
        """Change the player volume."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send("I am not currently connected to voice!")

        if not 0 < value < 101:
            return await ctx.send("Please enter a value between 1 and 100.")

        if not await self.has_perms(ctx, manage_guild=True) and player.dj.id != ctx.author.id:
            if (len(ctx.bot.get_channel(player.channel_id).members) - 1) > 2:
                return

        await player.set_volume(value)
        await ctx.send(f"Set the volume to **{value}**%", delete_after=7)

        if not player.updating and not player.update:
            await player.invoke_controller()

    @commands.command(name="queue", aliases=["q", "que"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def queue_(self, ctx):
        """Show the player queue."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send("I am not currently connected to voice!")

        upcoming = list(itertools.islice(player.entries, 0, 10))

        if not upcoming:
            return await ctx.send("The queue is empty.")

        fmt = "\n".join(
            f"**{index}. `{str(song)}` [{player.format_delta(song.duration)}]**"
            for index, song in enumerate(upcoming, 1)
        )
        embed = discord.Embed(
            title=f"Upcoming - Next {len(upcoming)}", description=fmt, color=discord.Color(0x008CFF)
        )

        await ctx.send(embed=embed)

    @commands.command(name="shuffle", aliases=["mix"])
    @commands.cooldown(2, 10, commands.BucketType.user)
    async def shuffle_(self, ctx):
        """Shuffle the queue.
        There must be at least 3 songs in the queue."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not player.is_connected:
            return await ctx.send("I am not currently connected to voice.")

        if len(player.entries) < 3:
            return await ctx.send("Please add more songs to the queue before trying to shuffle.")

        if await self.has_perms(ctx, manage_guild=True):
            await ctx.send(f"**{ctx.author}** has shuffled the playlist as an admin or DJ.")
            return await self.do_shuffle(ctx)

        await self.do_vote(ctx, player, "shuffle")

    async def do_shuffle(self, ctx):
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        random.shuffle(player.queue._queue)

        player.update = True

    async def do_skip(self, ctx):
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        await player.stop()

    @commands.command(name="remove")
    async def remove_from_queue(self, ctx, index: int):
        """Remove a track from the queue.
        Only the track"s requester or DJ and Admins can use this command
        (else, in the future, it will count as a vote)."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        try:
            to_remove = player.entries[index - 1]
        except (IndexError, TypeError, ValueError):
            return await ctx.send("Not a valid track ID, check the queue.")

        if to_remove.requester.id == ctx.author.id:
            await ctx.send(f"The requester **{ctx.author}** has removed **{to_remove}** from the queue.")
            del player.queue._queue[index - 1]
            return
        if await self.has_perms(ctx, manage_guild=True):
            await ctx.send(f"**{ctx.author}** has removed **{to_remove}** as an admin or DJ from the queue.")
            del player.queue._queue[index - 1]
            return

        return await ctx.send("You don't have the necessary permissions.")

    @commands.command(name="seteq")
    @commands.cooldown(1, 2.5, commands.BucketType.user)
    async def set_eq(self, ctx, *, eq: str):
        """Set the player equalizer.
        Valid ones are `Flat`, `Boost`, `Metal`, `Piano`"""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if eq.upper() not in player.equalizers:
            return await ctx.send(f"`{eq}` - Is not a valid equalizer!\nTry Flat, Boost, Metal, Piano.")

        await player.set_preq(eq)
        player.eq = eq.capitalize()
        await ctx.send(f"The player equalizer was set to **{eq.capitalize()}**.")

    @commands.command(name="seek", aliases=["jump"])
    @commands.cooldown(1, 2.5, commands.BucketType.user)
    async def jump(self, ctx, formatted_time: str):
        """Jump to a point of a track.
        The time must be formatted like `HOURS:MINUTES:SECONDS`."""
        try:
            t = datetime.datetime.strptime(formatted_time, "%H:%M:%S")
        except ValueError:
            raise commands.BadArgument(f'"{formatted_time}" is not a properly formatted time.')
        delta = int((datetime.timedelta(hours=t.hour, minutes=t.minute, seconds=t.second).total_seconds()) * 1000)

        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        await player.seek(delta)
        await ctx.send(f"Jumped to {player.format_delta(delta)}.")

        if not player.updating and not player.update:
            await player.invoke_controller()

    @commands.command(name="loop")
    async def loop_(self, ctx):
        """Loop the currently playing track.
        Only DJs and Admins can use this command."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not await self.has_perms(ctx, manage_guild=True):
            return await ctx.send("Only DJ can activate or deactivate looping.")

        if not player.looping:
            player.looping = True
            await ctx.send("The current track is now looping.")
            player.update = True
            return

        player.looping = False
        await ctx.send("Stopped looping.")
        player.update = True

    @commands.command()
    async def wv_info(self, ctx):
        """Retrieve various Node/Server/Player information."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        node = player.node

        used = humanize.naturalsize(node.stats.memory_used)
        total = humanize.naturalsize(node.stats.memory_allocated)
        free = humanize.naturalsize(node.stats.memory_free)
        cpu = node.stats.cpu_cores

        fmt = (
            f"**WaveLink:** `{wavelink.__version__}`\n\n"
            f"Connected to `{len(ctx.bot.wavelink.nodes)}` nodes.\n"
            f"`{len(ctx.bot.wavelink.players)}` players are distributed on nodes.\n"
            f"`{node.stats.players}` players are distributed on server.\n"
            f"`{node.stats.playing_players}` players are playing on server.\n\n"
            f"Server Memory: `{used}/{total}` | `({free} free)`\n"
            f"Server CPU: `{cpu}`\n\n"
            f"Server Uptime: `{datetime.timedelta(milliseconds=node.stats.uptime)}`"
        )
        await ctx.send(fmt)


def setup(bot):
    bot.add_cog(Music(bot))
