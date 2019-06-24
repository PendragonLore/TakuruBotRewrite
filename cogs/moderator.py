import asyncio
import logging
from collections import Counter
from datetime import datetime

import aioredis
import discord
from discord.ext import commands, tasks
from humanize import naturaldelta, naturaltime

import utils

LOG = logging.getLogger("cogs.moderator")


class Moderator(commands.Cog, command_attrs=dict(cooldown=commands.Cooldown(5, 2.5, commands.BucketType.user))):
    """Commands for moderation purposes.
    Work in progress."""

    def __init__(self, bot):
        self.bot = bot

        self._mute_data = asyncio.Event(loop=self.bot.loop)
        self._current_mute = None
        self.channel = None

        db = self.bot.redis.db
        self._channel_fmt = f"__keyevent@{db}__:expired"

        self.fetch_timers.add_exception_type(aioredis.PoolClosedError)
        self.fetch_timers.add_exception_type(aioredis.ChannelClosedError)
        self.fetch_timers.add_exception_type(aioredis.ConnectionClosedError)
        self.fetch_timers.start()

    def cog_unload(self):
        self.fetch_timers.cancel()

    async def do_bulk_delete(self, ctx, amount, **kwargs):
        if amount <= 0:
            raise commands.BadArgument("Amount too little.")

        amount = min(amount, 1000)

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        try:
            deleted = await ctx.channel.purge(limit=amount, bulk=True, **kwargs)
        except discord.HTTPException:
            raise commands.BadArgument("Sorry, but I wasn't able to bulk delete messages "
                                       "in this channel, please check my permissions.")

        if not deleted:
            return await ctx.send("No messages deleted.")

        last_message_date = datetime.utcnow() - deleted[-1].created_at
        first_message_date = datetime.utcnow() - deleted[0].created_at
        total_authors = {m.author for m in deleted}
        total_bots = {m.author for m in deleted if m.author.bot}

        await ctx.send(f"Deleted {len(deleted)} messages from "
                       f"{len(total_authors)} different authors ({len(total_bots)} bots).\n"
                       f"Oldest message from {naturaltime(last_message_date)}, "
                       f"newest from {naturaltime(first_message_date)}.", delete_after=7)

    @commands.group(name="purge", aliases=["prune", "cleanup"], invoke_without_command=True)
    @utils.bot_and_author_have_permissions(manage_messages=True)
    async def bulk_delete(self, ctx, amount: int):
        """Group of commands for bulk deleting messages.

        The amount of messages specified is not the amount deleted but the amount scanned.
        Limit is set to 1000 per command, the bot can't delete messages older than 14 days.

        If no subcommand is called this bulk deleting will not be filtered."""
        await self.do_bulk_delete(ctx, amount, check=lambda _: True)

    @bulk_delete.command(name="member", aliases=["m"])
    @utils.bot_and_author_have_permissions(manage_messages=True)
    async def bulk_delete_member(self, ctx, amount: int, members: commands.Greedy[discord.Member]):
        """Bulk delete x amount of messages from a list of members."""
        if not members:
            raise commands.BadArgument("Must provide at least one member.")
        await self.do_bulk_delete(ctx, amount, check=lambda m: m.author in members)

    @bulk_delete.command(name="bots", aliases=["bot", "b"])
    @utils.bot_and_author_have_permissions(manage_messages=True)
    async def bulk_delete_bots(self, ctx, amount: int):
        """Bulk delete x amount of messages from bots."""
        await self.do_bulk_delete(ctx, amount, check=lambda m: m.author.bot)

    @commands.command(name="kick")
    @utils.bot_and_author_have_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: commands.clean_content="No reason."):
        """Kick a member, you can also provide a reason."""
        try:
            await member.kick(reason=reason)
        except discord.HTTPException:
            return await ctx.send(f"Failed to kick {member}.")

        await ctx.send(f"Kicked {member} ({reason})")

    @commands.command(name="ban")
    @utils.bot_and_author_have_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: commands.clean_content="No reason."):
        """Ban a member, you can also provide a reason."""
        try:
            await member.ban(reason=reason)
        except discord.HTTPException:
            return await ctx.send(f"Failed to ban {member}, check permissions, hierarchy "
                                  f"and if the member is still in the guild.")

        await ctx.send(f"Banned **{member}** ({reason})")

    @commands.command(name="unban")
    @utils.bot_and_author_have_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int, *, reason: commands.clean_content="No reason."):
        """Unban a member, only IDs accepted."""
        try:
            await ctx.guild.unban(discord.Object(id=user_id), reason=reason)
        except discord.HTTPException:
            return await ctx.send(f"Couldn't unban user with id `{user_id}`")

        await ctx.send(f"Unbanned user with id `{user_id}`")

    @tasks.loop(reconnect=True)
    async def fetch_timers(self):
        key = await self.channel.get(encoding="utf-8")

        if not key or not key.startswith("timer-"):
            self.fetch_timers.restart()

        tr = self.bot.redis.multi_exec()

        tr.hgetall(f"lookup-{key}")
        tr.delete(f"lookup-{key}")

        kwargs, _ = await tr.execute()

        try:
            name = kwargs.pop("name")
        except KeyError:
            LOG.warning("Timer with args %s doesn't have a name field, discarding.", kwargs)
        else:
            LOG.info("Dispatching timer %s with args %s", name, kwargs)
            self.bot.dispatch(f"{name}_complete", kwargs)

    @fetch_timers.before_loop
    async def before_fetch_timers(self):
        self.channel = (await self.bot.redis.subscribe(self._channel_fmt))[0]

    @fetch_timers.after_loop
    async def after_fetch_timers(self):
        await self.bot.redis.unsubscribe(self._channel_fmt)

    @commands.command(name="setmute", aliases=["setmuterole"])
    @utils.bot_and_author_have_permissions(manage_roles=True)
    async def set_mute_role(self, ctx, *, role: discord.Role):
        """Set the mute role use in `tempmute` and `mute`.

        This will not automatically override the permissions of the role in any channel.
        If you want to do so, invoke ``setmuteperms``."""
        resp = await ctx.bot.redis.set(f"mute_role_id:{ctx.guild.id}", role.id)

        if not resp:
            return await ctx.send("Something went wrong while setting the mute role, report this to the developer.")

        await ctx.send(f"Set mute role for this guild to `{role}`")

    @commands.command(name="setmuteperms")
    @utils.bot_and_author_have_permissions(manage_roles=True)
    async def set_mute_role_perms(self, ctx):
        """Set the overwrites of each channel of this guild for the mute role.

        :x: Send Messages
        :x: Add Reactions."""

        role = ctx.guild.get_role(int(await self.bot.redis.get(f"mute_role_id:{ctx.guild.id}")))

        if not role:
            raise commands.BadArgument("No mute role setup for this guild.")

        msg = await ctx.send("Setting permissions, might take a while...")

        channels = ctx.guild.text_channels
        counter = Counter()

        for channel in channels:
            perms = channel.overwrites_for(role)

            if not perms.send_messages and not perms.add_reactions:
                counter["skip"] += 1
                continue
            try:
                await channel.set_permissions(role, send_messages=False, add_reactions=False)
            except discord.HTTPException:
                counter["miss"] += 1
            else:
                counter["hit"] += 1

        lines = [f"Done, changed permissions of {counter['hit']} channels out of {len(channels)} for role {role}."]

        if counter["skip"]:
            lines.append(f"Skipped {counter['skip']} channels due to permissions already set up.")
        if counter["miss"]:
            lines.append(f"Failed to change the permissions of {counter['miss']} channels.")

        await msg.edit(content="\n".join(lines))

    @commands.command(name="tempmute")
    @utils.bot_and_author_have_permissions(manage_roles=True)
    async def tempmute(self, ctx, time: utils.ShortTime(arg_required=False, past_ok=False),
                       member: discord.Member, *, reason: commands.clean_content="No reason"):
        guild_id = ctx.guild.id

        role_id = await self.bot.redis.get(f"mute_role_id:{guild_id}")

        if not role_id:
            raise commands.BadArgument("No mute role setup for this guild.")

        delta = (time.date - ctx.message.created_at).total_seconds()
        if delta < 1:
            raise commands.BadArgument("Invalid time")

        try:
            await member.add_roles(discord.Object(id=role_id), reason=reason)
        except discord.HTTPException:
            raise commands.BadArgument("Failed to give Mute role to the target, "
                                       "check permissions, hierarchy and if both are still in the guild.")
        else:
            await self.bot.create_timer("mute", delta, guild_id=guild_id, member_id=member.id, role_id=role_id)

        try:
            nat = naturaldelta(delta)
        except OverflowError:
            nat = "a long time"
        await ctx.send(f"Muted {member} ({reason}), will be unmuted in {nat}.")

    @commands.command(name="mutes")
    async def mutes(self, ctx):
        redis = ctx.bot.redis
        lines = []

        async for key in redis.iscan(match="timer-mute:*"):
            data = await redis.hmget(key, "guild_id", "member_id")
            if not int(data[0]) == ctx.guild.id:
                continue

            ttl = await redis.ttl(key)

            lines.append(f"{ctx.guild.get_member(int(data[1]))} - Going to be unmuted in {naturaldelta(ttl)}")

        await ctx.send("\n".join(lines) or "none")

    @commands.Cog.listener()
    async def on_mute_complete(self, mute):
        guild = self.bot.get_guild(int(mute["guild_id"]))

        if not guild:
            LOG.warning("Guild for mute %r not found", mute)
            return

        role = guild.get_role(int(mute["role_id"]))
        member = guild.get_member(int(mute["member_id"]))

        if not role or not member:
            # yes.
            warn = ("Role" if not role else "") + \
                   ("and member" if role and not member else ("Member" if not member else ""))
            LOG.warning("%s for mute %r not found", warn.strip(), mute)
            return

        try:
            await member.remove_roles(role, reason="Unmute")
        except discord.HTTPException as exc:
            LOG.warning("Failed to remove mute role for mute %r [%s: %s]", mute, type(exc), exc)
        else:
            LOG.info("Sucessfully removed role for mute %r", mute)


def setup(bot):
    bot.add_cog(Moderator(bot))
