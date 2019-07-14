from datetime import timedelta

import wavelink
from dateutil import parser as dateparser
import asyncio

from .custom_queue import CustomQueue


class Track(wavelink.Track):
    def __init__(self, id_, info, ctx, *, query=None, **kwargs):
        super().__init__(id_, info, query=query)

        self.ctx = ctx
        self._metadata = {}

        self.requester = kwargs.pop("requester", ctx.author)

        self.channel_name = None
        self.channel_id = None
        self.channel_url = None
        self.channel_thumb = None

        self.description = None
        self.posted_at = None
        self.tags = None

        self.likes = None
        self.dislikes = None
        self.views = None

    @property
    def is_from_youtube(self):
        return self.ytid is not None

    @property
    def has_metadata(self):
        return bool(self._metadata)

    @property
    def fmt_duration(self):
        try:
            return str(timedelta(milliseconds=self.duration)).split(".")[0] \
                if not self.is_stream else "\U0001f534 STREAM"
        except Exception:
            return "0:00:00"

    async def set_metadata(self):
        key = self.ctx.bot.config.tokens.apis.get("yt_data")
        if not self.is_from_youtube or not key:
            return

        data = await self.ctx.get("https://www.googleapis.com/youtube/v3/videos",
                                  key=key, part="snippet,statistics", id=self.ytid, cache=True)

        try:
            self._metadata = track = data["items"][0]
        except (IndexError, KeyError):
            return

        snippet = track["snippet"]

        self.channel_name = snippet["channelTitle"]
        self.channel_id = snippet["channelId"]
        self.channel_url = f"https://www.youtube.com/channel/{self.channel_id}"

        # youtube data api pls
        channel = await self.ctx.get("https://www.googleapis.com/youtube/v3/channels", key=key, part="snippet",
                                     id=self.channel_id, cache=True)

        self.channel_thumb = channel["items"][0]["snippet"]["thumbnails"]["high"]["url"]

        self.description = snippet.get("description")
        self.posted_at = dateparser.parse(snippet["publishedAt"])
        self.tags = snippet.get("tags")

        stats = track["statistics"]

        self.likes = int(stats["likeCount"])
        self.dislikes = int(stats["dislikeCount"])
        self.views = int(stats["viewCount"])

        return self

    def __repr__(self):
        return f"<Track is_from_youtube={self.is_from_youtube} title={self.title!r}>"


class Player(wavelink.Player):
    def __init__(self, bot, guild_id, node):
        super().__init__(bot, guild_id, node)

        self.queue = CustomQueue(loop=self.bot.loop)

        self.owner = None
        self.looping = False
        self.loop_single = False
        self.eq = "FLAT"

        self.skips = set()
        self.shuffles = set()
        self.pauses = set()
        self.repeats = set()

        self.current_text = None

        self.player_task = self.bot.loop.create_task(self.task())

    @property
    def current_voice(self):
        return self.bot.get_channel(int(self.channel_id))

    async def task(self):
        while True:
            try:
                track = await self.queue.wait_get(timeout=120)
            except asyncio.TimeoutError:
                if not [x for x in self.current_voice.members if not x.bot]:
                    await self.current_text.send("Disconnected due to inactivity.")
                    return await self.destroy()
                continue

            if track:
                await self.play(track)

                await self.bot.wait_for("wavelink_track_end", check=lambda p: p.player.guild_id == self.guild_id)
                if self.loop_single:
                    self.queue.putleft(track)
                elif self.looping:
                    self.queue.put(track)

                self.skips.clear()
                self.repeats.clear()
                self.current = None

    async def destroy(self):
        self.player_task.cancel()
        self.queue.clear()

        await self.stop()
        await self.disconnect()

        await self.node._send(op="destroy", guildId=str(self.guild_id))
        self.node.players.pop(self.guild_id, None)

    def check_perms(self, ctx):
        if not ctx.author.voice or ctx.author not in ctx.me.voice.channel.members:
            return False
        if ctx.author == self.owner:
            return True

        perms = ctx.author.guild_permissions

        if perms.administrator or perms.manage_guild or ctx.guild.owner == ctx.author:
            return True

        return False

    @property
    def fmt_position(self):
        try:
            return str(timedelta(milliseconds=self.position)).split(".")[0]
        except IndexError:
            return "0:00:00"

    def __repr__(self):
        return f"<Player guild_id={self.guild_id} queue={self.queue} current={self.current!r} " \
            f"position={self.position} channel_id={self.channel_id}>"
