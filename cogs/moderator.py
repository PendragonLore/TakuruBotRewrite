import asyncio
import logging
import typing
from datetime import datetime

import aioredis
import discord
from discord.ext import commands, flags, tasks
from humanize import naturaldelta

import utils

LOG = logging.getLogger("cogs.moderator")


class DummyObject:
    def __init__(self, **kwargs):
        self._data = kwargs

        for key, value in kwargs.items():
            try:
                setattr(self, key, int(value))
            except ValueError:
                setattr(self, key, value)

    def __getitem__(self, item):
        return self.__getattribute__(item)

    def __repr__(self):
        fmt = " ".join(f"{k}={v!r}" for k, v in self._data.items())
        return f"<{fmt}>"


class Moderator(commands.Cog, command_attrs=dict(cooldown=commands.Cooldown(5, 2.5, commands.BucketType.user))):
    """Commands for moderation purposes.
    Work in progress."""

    def __init__(self, bot):
        self.bot = bot

        self._mute_data = asyncio.Event(loop=self.bot.loop)
        self._current_mute = None
        self.channel = None

        self.fetch_timers.add_exception_type(aioredis.PoolClosedError)
        self.fetch_timers.add_exception_type(aioredis.ChannelClosedError)
        self.fetch_timers.add_exception_type(aioredis.ConnectionClosedError)
        self.fetch_timers.start()

    def cog_unload(self):
        self.fetch_timers.cancel()

    @commands.command(name="purge", aliases=["prune"], cls=flags.FlagCommand)
    @utils.bot_and_author_have_permissions(manage_messages=True)
    async def bulk_delete(
            self, ctx, *, args: flags.FlagParser(amount=int, bot_only=bool, member=discord.Member)=flags.EmptyFlags
    ):
        """Bulk-delete a certain amout of messages in the current channel.

        The amount of messages specified might not be the amount deleted.
        Limit is set to 500 per command, the bot can't delete messages older than 14 days."""
        if args["bot_only"] and args["member"]:
            raise commands.BadArgument("Either specify a member or bot only, not both.")

        amount = args["amount"] or 10
        if amount > 500:
            return await ctx.send("Maximum of 500 messages per command.")

        check = None
        if args["bot_only"] is not None:
            def check(m):
                return m.author.bot
        elif args["member"] is not None:
            def check(m):
                return m.author.id == args["member"].id

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        purge = await ctx.channel.purge(limit=amount, check=check, bulk=True)

        await ctx.send(f"Successfully deleted {len(purge)} message(s).", delete_after=5)

    @commands.command(name="kick")
    @utils.bot_and_author_have_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: typing.Optional[str] = None):
        """Kick a member, you can also provide a reason."""
        reason = reason or "No reason."
        try:
            await member.kick(reason=reason)
        except discord.HTTPException:
            return await ctx.send(f"Failed to kick {member}.")

        await ctx.send(f"Kicked {member} ({reason})")

    @commands.command(name="ban")
    @utils.bot_and_author_have_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: typing.Optional[str] = None):
        """Ban a member, you can also provide a reason."""
        reason = reason or "No reason."
        try:
            await member.ban(reason=reason)
        except discord.HTTPException:
            return await ctx.send(f"Failed to ban {member}.")

        await ctx.send(f"Banned **{member}**. ({reason})")

    @commands.command(name="unban")
    @utils.bot_and_author_have_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int, *, reason):
        """Unban a member, only IDs accepted."""
        member = discord.Object(id=user_id)
        try:
            await ctx.guild.unban(member, reason=reason or "No reason.")
        except discord.HTTPException:
            await ctx.send(f"Couldn't unban user with id `{user_id}")
            return

        await ctx.send(f"Unbanned member with id `{user_id}`")

    @tasks.loop(reconnect=True)
    async def fetch_timers(self):
        msg = await self.channel.get()
        key = getattr(msg, "decode", msg.__str__)()

        if not key.startswith("timer-"):
            return

        kwargs = dict([s.split("=") for s in key[6:].split(":")])

        name = kwargs.pop("name", None)
        if not name:
            LOG.warning("Timer with args %s doesn't have a name field, discarding.", kwargs)
        else:
            LOG.info("Dispatching timer %s with args %s", name, kwargs)
            self.bot.dispatch(f"{name}_complete", DummyObject(**kwargs))

    @fetch_timers.before_loop
    async def before_fetch_timers(self):
        db = self.bot.redis.db
        fmt = f"__keyevent@{db}__:expired"
        channels = self.bot.redis.channels

        if fmt not in channels:
            channel = await self.bot.redis.subscribe(fmt)
            self.channel = channel[0]
        else:
            channel = channels[fmt]
            self.channel = channel

    @commands.command(name="tempmute")
    @utils.bot_and_author_have_permissions(manage_roles=True)
    async def tempmute(self, ctx, time: utils.ShortTime(arg_required=False, past_ok=False),
                       member: discord.Member, *, reason="No reason"):
        guild_id = ctx.guild.id

        role_id = await self.bot.redis.get(f"mute_role_id:{guild_id}")

        if not role_id:
            raise commands.BadArgument("No mute role setup for this guild.")

        delta = (time.date - datetime.utcnow()).total_seconds() + 1
        if delta < 1:
            raise commands.BadArgument("Invalid time")

        try:
            _, key_fmt = await self.bot.create_timer("mute", __time=delta, guild_id=guild_id,
                                                     member_id=member.id, role_id=role_id)
        except aioredis.ReplyError:
            raise commands.BadArgument("Invalid time.")

        try:
            await member.add_roles(discord.Object(id=role_id), reason=reason)
        except discord.HTTPException:
            await self.bot.redis.delete(key_fmt)
            raise commands.BadArgument("Failed to give Mute role to the target, "
                                       "check permissions, hierarchy and if both are still in the guild.")

        await ctx.send(f"Muted {member}, will be unmuted in {naturaldelta(delta)}")

    @commands.Cog.listener()
    async def on_mute_complete(self, mute):
        guild = self.bot.get_guild(mute["guild_id"])

        if not guild:
            LOG.warning("Guild for mute %r not found", mute)
            return

        role = guild.get_role(mute["role_id"])
        member = guild.get_member(mute["member_id"])

        # ifs for more precise logging
        if not role and not member:
            LOG.warning("Role and member for mute %r not found", mute)
            return
        if not role:
            LOG.warning("Role for mute %r not found", mute)
            return
        if not member:
            LOG.warning("Member for mute %r not found", mute)
            return

        try:
            await member.remove_roles(role, reason="Unmute")
        except discord.HTTPException as exc:
            LOG.warning("Failed to remove mute role for mute %r [%s: %s]", mute, type(exc), exc)
        else:
            LOG.info("Sucessfully removed role for mute %r", mute)


def setup(bot):
    bot.add_cog(Moderator(bot))
