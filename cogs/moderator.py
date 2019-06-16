import asyncio
import typing
from datetime import datetime

import discord
from discord.ext import commands, flags
from humanize import naturaldate, naturaldelta

import utils


class Moderator(commands.Cog):
    """Commands for moderation purposes.
    Work in progress."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="purge", aliases=["prune"], cls=flags.FlagCommand)
    @utils.bot_and_author_have_permissions(manage_messages=True)
    @commands.cooldown(1, 2.5, commands.BucketType.user)
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
    @commands.cooldown(1, 2.5, commands.BucketType.user)
    async def kick(self, ctx, member: discord.Member, *, reason: typing.Optional[str] = None):
        """Kick a member, you can also provide a reason."""
        reason = reason or "No reason."
        try:
            await member.kick(reason=reason)
            ctx.bot.dispatch("member_kick", ctx.guild, member)
        except discord.HTTPException:
            return await ctx.send(f"Failed to kick {member}.")

        await ctx.send(f"Kicked {member} ({reason})")

    @commands.command(name="ban")
    @utils.bot_and_author_have_permissions(ban_members=True)
    @commands.cooldown(1, 2.5, commands.BucketType.user)
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
    @commands.cooldown(1, 2.5, commands.BucketType.user)
    async def unban(self, ctx, user_id: int, *, reason):
        """Unban a member, only IDs accepted."""
        member = discord.Object(id=user_id)
        try:
            await ctx.guild.unban(member, reason=reason or "No reason.")
        except discord.HTTPException:
            await ctx.send(f"Couldn't unban user with id `{user_id}")
            return

        await ctx.send(f"Unbanned member with id `{user_id}`")


def setup(bot):
    bot.add_cog(Moderator(bot))
