import logging
from collections import Counter
from datetime import datetime

import discord
from discord.ext import commands
from humanize import naturaldelta, naturaltime

import utils

LOG = logging.getLogger("cogs.moderator")

PRED_MAP = {
    "contains": lambda m, t: t in m.content,
    "namecontains": lambda m, t: t in m.author.name,
    "member": lambda m, t: m.author in t,
    "bots": lambda m, *_: m.author.bot,
    "startswith": lambda m, t: m.content.startswith(t),
    "endswith": lambda m, t: m.content.endswith(t)
}

PURGE_FLAGS = {
    "contains": utils.Flag(),
    "namecontains": utils.Flag(),
    "startswith": utils.Flag(),
    "endswith": utils.Flag(),
    "member": utils.Flag(greedy=True, converter=commands.MemberConverter),
    "bots": utils.Flag(const=True, type=bool, default=False, nargs="?", consume=False),
    "or": utils.Flag(const=True, type=bool, default=False, nargs="?", consume=False),
    "not": utils.Flag(const=True, type=bool, default=False, nargs="?", consume=False),
    "after": utils.Flag(converter=utils.HumanTime(arg_required=False, past_ok=True)),
    "before": utils.Flag(converter=utils.HumanTime(arg_required=False, past_ok=True)),
}


class Moderator(commands.Cog, command_attrs=dict(cooldown=commands.Cooldown(5, 2.5, commands.BucketType.user))):
    """Commands for moderation purposes.
    Work in progress."""

    def __init__(self, bot):
        self.bot = bot

    async def do_bulk_delete(self, ctx, amount, flags):
        if amount <= 0:
            raise commands.BadArgument("Amount too little.")
        if not flags:
            flags = {}

        if flags.get("or") and flags.get("not"):
            raise commands.BadArgument("``--or`` and ``--not`` cannot be passed together")

        amount = min(amount, 1000)

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        predicates = [(n, PRED_MAP[n]) for n, f in flags.items() if f and n not in {"after", "before", "or", "not"}]

        def check(m):
            if flags.get("or"):
                return any([x(m, flags[n]) for n, x in predicates])
            elif flags.get("not"):
                return not all([x(m, flags[n]) for n, x in predicates])
            else:
                return all([x(m, flags[n]) for n, x in predicates])

        dummy = type("a", (), {"date": None})()
        kwargs = {
            "check": check,
            "after": (flags.get("after") or dummy).date,
            "before": (flags.get("before") or dummy).date
        }

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

        await ctx.send(f"Deleted {utils.Plural(len(deleted)):message} from "
                       f"{utils.Plural(len(total_authors)):different author} ({utils.Plural(len(total_bots)):bot}).\n"
                       f"Oldest message from {naturaltime(last_message_date)}, "
                       f"newest from {naturaltime(first_message_date)}.", delete_after=7)

    @commands.group(name="purge", aliases=["prune", "cleanup"], invoke_without_command=True)
    @utils.bot_and_author_have_permissions(manage_messages=True)
    async def bulk_delete(self, ctx, amount: int, *,
                          flags: utils.ShellFlags(**PURGE_FLAGS) = None):
        """Bulk delete messages from a channel.

        The amount of messages specified is not the amount deleted but the amount scanned.
        Limit is set to 1000 per command, the bot can't bulk delete messages older than 14 days.

        This commands implements the flag system to filter messages.
        Flags are passed when invoking the command, usually in a format like this ``--flagname [arguments...]``.
        Multiple flags can be passed.

        ``--after [date]`` messages will be scanned only after ``date``.
        ``--before [date]`` messages will be scanned only before ``date``.
        ``--contains [words]`` all messages not containing ``words`` will be ignored. Case sensitive.
        ``--namecontains [words]`` all messages which author's name doesn't contain ``words`` will be ignored.
                                   Case sensitive.
        ``--startswith [words]`` all messages not starting with ``words`` will be ignored. Case sensitive.
        ``--endswith [words]`` all messages not ending with ``words`` will be ignored. Case sensitive.
        ``--member [members...]`` all messages which were not written by any of ``members`` will be ignored.
                                 Members must be a list of member names/mentions/ids.
        ``--bots`` all messages which are authored from bots will be ignored. No arguments needed.
        ``--or`` only one of the conditions specified must be met to delete the message.
        ``--not`` all conditions must not match for the message to be deleted."""
        await self.do_bulk_delete(ctx, amount, flags)

    def check_hierarcy(self, ctx, other, error_message):
        if ctx.me.top_role.position < other.top_role.position or other == ctx.guild.owner:
            raise commands.BadArgument(error_message)

    @commands.command(name="kick")
    @utils.bot_and_author_have_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: commands.clean_content = "No reason."):
        """Kick a member, you can also provide a reason."""
        self.check_hierarcy(ctx, member, f"I can't kick **{member}**.")

        try:
            await member.kick(reason=reason)
        except discord.HTTPException:
            await ctx.send(f"Failed to kick {member}.")
        else:
            await ctx.send(f"Kicked **{member}** ({reason})")

    async def do_ban(self, ctx, member, reason, days=1):
        self.check_hierarcy(ctx, member, f"I can't ban **{member}**.")

        try:
            await member.ban(reason=reason, delete_message_days=days)
        except discord.HTTPException:
            await ctx.send(f"Failed to ban {member}, check permissions, hierarchy "
                           f"and if the member is still in the guild.")
        else:
            await ctx.send(f"Banned **{member}** ({reason})")

    @commands.command(name="ban")
    @utils.bot_and_author_have_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: commands.clean_content = "No reason."):
        """Ban a member, you can also provide a reason.

        Deletes a day worth of messages."""
        await self.do_ban(ctx, member, reason)

    @commands.command(name="softban")
    @utils.bot_and_author_have_permissions(ban_members=True)
    async def softban(self, ctx, member: discord.Member, *, reason: commands.clean_content = "No reason."):
        """Softban a member, you can also provide a reason.

        Softbanning means that a week worth of messages of the member will be deleted.
        The member will be unbanned immediately."""
        await self.do_ban(ctx, member, reason, days=7)

        await member.unban(reason="Softban")

    @commands.command(name="unban")
    @utils.bot_and_author_have_permissions(ban_members=True)
    async def unban(self, ctx, user: utils.BannedUser, *, reason: commands.clean_content = "No reason."):
        """Unban a member, only IDs accepted."""
        try:
            await ctx.guild.unban(user, reason=reason)
        except discord.HTTPException:
            await ctx.send(f"Couldn't unban **{user}**")
        else:
            await ctx.send(f"Unbanned **{user}**")

    async def get_mute_role(self, ctx):
        try:
            role = ctx.guild.get_role(int(await ctx.bot.redis.get(f"mute_role_id:{ctx.guild.id}")))
        except TypeError:
            raise commands.BadArgument("No mute role setup for this guild. You can set one with `setmute`.")

        if not role:
            raise commands.BadArgument("No mute role setup for this guild. You can set one with `setmute`.")

        return role

    @commands.command(name="setmute", aliases=["setmuterole"])
    @utils.bot_and_author_have_permissions(manage_roles=True)
    async def set_mute_role(self, ctx, *, role: discord.Role):
        """Set the mute role use in `tempmute` and `mute`.

        This will not automatically override the permissions of the role in any channel.
        If you want to do so, invoke ``setmuteperms``."""
        await ctx.bot.redis.set(f"mute_role_id:{ctx.guild.id}", role.id)

        await ctx.send(f"Set mute role for this guild to **{role}**")

    @commands.command(name="setmuteperms")
    @utils.bot_and_author_have_permissions(manage_roles=True)
    async def set_mute_role_perms(self, ctx):
        """Set Add Reactions and Send Messages to false for all channels for this guild's mute role."""
        role = await self.get_mute_role(ctx)

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

        lines = []

        if counter["hit"]:
            lines.append(f"Done, changed permissions of **{utils.Plural(counter['hit']):channel}** out of "
                         f"{len(channels)} for role **{role}**.")
        if counter["skip"]:
            lines.append(f"Skipped **{utils.Plural(counter['skip']):channel}** due to permissions already set up.")
        if counter["miss"]:
            lines.append(f"Failed to change the permissions of **{utils.Plural(counter['miss']):channel}**.")

        await msg.edit(content="\n".join(lines))

    @commands.command(name="mute")
    @utils.bot_and_author_have_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, *, reason: commands.clean_content = "No reason"):
        """Mute a member."""
        role = await self.get_mute_role(ctx)

        try:
            await member.add_roles(role, reason=reason)
        except discord.HTTPException:
            raise commands.BadArgument("Failed to give Mute role to the target, "
                                       "check permissions, hierarchy and if both are still in the guild.")

        await ctx.send(f"Muted {member} ({reason}).")

    @commands.command(name="tempmute")
    @utils.bot_and_author_have_permissions(manage_roles=True)
    async def tempmute(self, ctx, time: utils.ShortTime(arg_required=False, past_ok=False),
                       member: discord.Member, *, reason: commands.clean_content = "No reason"):
        """Mute temporarly a member.

        The date must be in a format like '1h30m'."""
        guild_id = ctx.guild.id

        role = await self.get_mute_role(ctx)

        delta = (time.date - ctx.message.created_at).total_seconds()
        if delta < 1:
            raise commands.BadArgument("Invalid time")

        try:
            await member.add_roles(role, reason=reason)
        except discord.HTTPException:
            raise commands.BadArgument("Failed to give Mute role to the target, "
                                       "check permissions, hierarchy and if both are still in the guild.")
        else:
            await self.bot.timers.create_timer("mute", time.date, guild_id=guild_id,
                                               member_id=member.id, role_id=role.id)

        try:
            nat = naturaldelta(delta)
        except OverflowError:
            nat = "a long time"
        await ctx.send(f"Muted {member} ({reason}), will be unmuted in {nat}.")

    @commands.command(name="unmute")
    @utils.bot_and_author_have_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member, *, reason: commands.clean_content = "No reason"):
        """Unmute a member.

        It is ***highly*** suggested to use this command instead of manually removing the role
        as that could cause unexpected behaviour in the future."""
        role = await self.get_mute_role(ctx)

        try:
            await member.remove_roles(role, reason=reason)
        except discord.HTTPException:
            return await ctx.send("Failed to remove the mute role from the member, please check my permissions.")

        async with ctx.db.acquire() as db:
            query = """
            SELECT id
            FROM times
            WHERE name = 'mute'
            AND (args->'guild_id')::bigint = $1
            AND (args->'member_id')::bigint = $2;
            """

            maybe_timer_id = await db.fetchval(query, ctx.guild.id, member.id)

        try:
            await self.bot.timers.delete_timer(maybe_timer_id)
        except TypeError:
            pass

        await ctx.send(f"Unmuted {member} ({reason}).")

    @commands.command(name="mutes")
    async def mutes(self, ctx):
        """List all the mutes active in this guild."""

        query = """
        SELECT (args->'member_id')::bigint AS member_id, expires_at
        FROM times
        WHERE name = 'mute'
        AND (args->'guild_id')::bigint = $1;
        """

        async with ctx.db.acquire() as db:
            data = await db.fetch(query, ctx.guild.id)

        if not data:
            return await ctx.send("No active mutes.")

        for chunk in utils.chunks(data, 10):
            embed = discord.Embed(title=f"Mutes for {ctx.guild}")
            embed.description = ""

            for dct in chunk:
                member = ctx.guild.get_member(dct["member_id"]) or f"*Left the guild* (id: {dct['member_id']})"
                try:
                    nat = naturaldelta(dct["expires_at"] - datetime.utcnow())
                except OverflowError:
                    nat = "a long time"

                embed.description += f"{member} | will be unmuted in **{nat}**\n"

            ctx.pages.add_entry(embed)

        await ctx.paginate()

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
