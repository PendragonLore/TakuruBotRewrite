import asyncio
from dateutil import parser as dateparser
import random

import wavelink
from discord.ext import tasks


class CustomQueue(asyncio.Queue):
    def fetch_all(self):
        return list(self._queue)

    def shuffle(self):
        random.shuffle(self._queue)

    def clear(self):
        while self.qsize():
            self.get_nowait()
        while self._unfinished_tasks:
            self.task_done()


class Track(wavelink.Track):
    def __init__(self, id_, info, ctx, *, query=None):
        super().__init__(id_, info, query=query)

        self.ctx = ctx
        self._metadata = {}

        self.channel_name = None
        self.channel_id = None
        self.channel_url = None

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

        self.channel_name = snippet.get("channelTitle")
        self.channel_id = snippet.get("channelId")
        self.channel_url = f"https://www.youtube.com/channel/{self.channel_id}"

        self.description = snippet.get("description")
        self.posted_at = dateparser.parse(snippet.get("publishedAt"))
        self.tags = snippet.get("tags")

        stats = track["statistics"]

        self.likes = stats["likeCount"]
        self.dislikes = stats["dislikeCount"]
        self.views = stats["viewCount"]

        return self

    def __repr__(self):
        return f"<Track is_from_youtube={self.is_from_youtube} title={self.title!r}>"


class Player(wavelink.Player):
    def __init__(self, bot, guild_id, node):
        super().__init__(bot, guild_id, node)

        self.queue = CustomQueue(loop=self.bot.loop)

        self.player_task.start()

    @tasks.loop()
    async def player_task(self):
        track = await self.queue.get()

        if track:
            await track.set_metadata()
            await self.play(track)

            await track.ctx.send(f"Now playing **{track}** with {len(track.tags or [])} tags ({track.likes} \U0001f44d"
                                 f" - {track.dislikes}\U0001f44e).")

            await self.bot.wait_for("wavelink_track_end", check=lambda p: p.player.guild_id == self.guild_id)
