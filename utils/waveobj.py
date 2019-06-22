import asyncio
import datetime
import itertools
from typing import Union

import discord
import wavelink
from discord.ext import commands

from utils import emotes


class Track(wavelink.Track):
    __slots__ = ("requester", "channel", "message")

    def __init__(self, id_, info, *, ctx=None):
        super(Track, self).__init__(id_, info)

        self.requester = ctx.author
        self.channel = ctx.channel
        self.message = ctx.message

    @property
    def is_dead(self):
        return self.dead


class Player(wavelink.Player):
    def __init__(self, bot: Union[commands.Bot, commands.AutoShardedBot], guild_id: int, node: wavelink.Node):
        super(Player, self).__init__(bot, guild_id, node)

        self.queue = asyncio.Queue()
        self.next_event = asyncio.Event()

        self.volume = 90
        self.dj = None
        self.controller_message = None
        self.reaction_task = None
        self.looping = False
        self.update = False
        self.updating = False
        self.inactive = False

        self.controls = {"⏯": "rp", "⏹": "stop", "⏭": "skip", "🔀": "shuffle", "🔁": "loop", "ℹ": "queue"}

        self.pauses = set()
        self.resumes = set()
        self.stops = set()
        self.shuffles = set()
        self.skips = set()
        self.repeats = set()

        self.eq = "Flat"

        bot.loop.create_task(self.player_loop())
        bot.loop.create_task(self.updater())

    @property
    def entries(self):
        return list(self.queue._queue)

    async def updater(self):
        while not self.bot.is_closed():
            if self.update and not self.updating:
                self.update = False
                await self.invoke_controller()

            await asyncio.sleep(10)

    async def player_loop(self):
        await self.set_preq("Flat")
        # We can do any pre loop prep here...
        await self.set_volume(self.volume)

        while True:
            self.next_event.clear()

            self.inactive = False

            if self.looping:
                song = self.current
                if not song:
                    song = await self.queue.get()
            else:
                song = await self.queue.get()
            if not song:
                continue

            self.current = song
            self.paused = False

            await self.play(song)

            # Invoke our controller if we aren"t already...
            if not self.updating and not self.update:
                await self.invoke_controller()

            # Wait for TrackEnd event to set our event...
            await self.next_event.wait()

            # Clear votes...
            self.pauses.clear()
            self.resumes.clear()
            self.stops.clear()
            self.shuffles.clear()
            self.skips.clear()
            self.repeats.clear()

    def format_delta(self, delta: int):
        try:
            return str(datetime.timedelta(milliseconds=int(delta))).split(".")[0]
        except Exception:
            return "0:00:00"

    async def invoke_controller(self, track: wavelink.Track = None):
        """Invoke our controller message, and spawn a reaction controller if one isn"t alive."""
        if not track:
            track = self.current

        self.updating = True

        embed = discord.Embed(
            description=f"{emotes.KAZ_HAPPY} Now Playing:```\n{track.title}\n```",
            color=discord.Color(0x008CFF),
        )
        embed.set_thumbnail(url=track.thumb)

        if track.is_stream:
            embed.add_field(name="Duration", value="🔴`Streaming`")
        else:
            completed = self.format_delta(self.position)
            duration = self.format_delta(track.duration)

            embed.add_field(
                name="Completed/Duration", value=f"{completed if completed != duration else '0:00:00'}/{duration}"
            )
        embed.add_field(name="Video URL", value=f"[Click Here.]({track.uri})")
        embed.add_field(name="Requested By", value=track.requester.mention)
        embed.add_field(name="Current DJ", value=self.dj.mention)
        embed.add_field(
            name="Queue Length",
            value=f"{len(self.entries)} Tracks " f"`[{self.format_delta(sum([t.duration for t in self.entries]))}]`",
        )
        embed.add_field(name="Volume", value=f"**`{self.volume}%`**")

        if self.entries:
            data = "\n".join(
                f"**-** `{t.title[0:45]}{'...' if len(t.title) > 45 else ''}`"
                for t in itertools.islice([e for e in self.entries if not e.is_dead], 0, 3, None)
            )
            embed.add_field(name="Coming Up:", value=data, inline=False)

        if not await self.is_current_fresh(track.channel) and self.controller_message:
            try:
                await self.controller_message.delete()
            except discord.HTTPException:
                pass

            self.controller_message = await track.channel.send(embed=embed)
        elif not self.controller_message:
            self.controller_message = await track.channel.send(embed=embed)
        else:
            self.updating = False
            return await self.controller_message.edit(embed=embed, content=None)

        try:
            self.reaction_task.cancel()
        except Exception:
            pass

        self.reaction_task = self.bot.loop.create_task(self.reaction_controller())
        self.updating = False

    async def add_reactions(self):
        """Add reactions to our controller."""
        for reaction in self.controls:
            try:
                await self.controller_message.add_reaction(str(reaction))
            except discord.HTTPException:
                return

    async def reaction_controller(self):
        """Our reaction controller, attached to our controller.
        This handles the reaction buttons and it"s controls."""
        self.bot.loop.create_task(self.add_reactions())

        def check(r, u):
            if not self.controller_message:
                return False
            if str(r) not in self.controls.keys():
                return False
            if u.id == self.bot.user.id or r.message.id != self.controller_message.id:
                return False
            if u not in self.bot.get_channel(int(self.channel_id)).members:
                return False
            return True

        while self.controller_message:
            if self.channel_id is None:
                return self.reaction_task.cancel()

            react, user = await self.bot.wait_for("reaction_add", check=check)
            control = self.controls.get(str(react))

            if control == "rp":
                if self.paused:
                    control = "resume"
                else:
                    control = "pause"

            try:
                await self.controller_message.remove_reaction(react, user)
            except discord.HTTPException:
                pass
            cmd = self.bot.get_command(control)

            ctx = await self.bot.get_context(react.message)
            ctx.author = user

            try:
                if cmd.is_on_cooldown(ctx):
                    pass
                if not await self.invoke_react(cmd, ctx):
                    pass
                else:
                    self.bot.loop.create_task(ctx.invoke(cmd))
            except Exception as e:
                ctx.command = self.bot.get_command("reactcontrol")
                await cmd.dispatch_error(ctx=ctx, error=e)

        await self.destroy_controller()

    async def destroy_controller(self):
        """Destroy both the main controller and it"s reaction controller."""
        try:
            await self.controller_message.delete()
            self.controller_message = None
        except (AttributeError, discord.HTTPException):
            pass

        try:
            self.reaction_task.cancel()
        except Exception:
            pass

        self.updating = False
        self.update = False
        self.looping = False
        self.dj = None

    async def invoke_react(self, cmd, ctx):
        if not cmd._buckets.valid:
            return True

        if not await cmd.can_run(ctx):
            return False

        bucket = cmd._buckets.get_bucket(ctx)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            return False
        return True

    async def is_current_fresh(self, chan):
        """Check whether our controller is fresh in message history."""
        try:
            async for m in chan.history(limit=8):
                if m.id == self.controller_message.id:
                    return True
        except (discord.HTTPException, AttributeError):
            return False
        return False
