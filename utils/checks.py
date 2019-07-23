import functools
import math
import operator

from discord.ext import commands

import utils


def bot_and_author_have_permissions(**perms):
    def predicate(ctx):
        channel = ctx.channel
        guild = ctx.guild
        me = guild.me if guild is not None else ctx.bot.user

        author_perms = channel.permissions_for(ctx.author)
        me_perms = channel.permissions_for(me)

        me_missing = [perm for perm, value in perms.items() if getattr(me_perms, perm, None) != value]
        author_missing = [perm for perm, value in perms.items() if getattr(author_perms, perm, None) != value]

        if author_missing:
            raise commands.MissingPermissions(author_missing)

        if me_missing:
            raise commands.BotMissingPermissions(me_missing)

        return True

    return commands.check(predicate)


def is_guild_owner_or_perms(**perms):
    def predicate(ctx):
        if ctx.guild.owner == ctx.author:
            return True

        p = ctx.author.permissions_in(ctx.channel)
        missing = [perm for perm, value in perms.items() if getattr(p, perm, None) != value]

        if missing:
            raise commands.MissingPermissions(missing)

        return True

    return commands.check(predicate)


def requires_config(*args):
    def predicate(ctx):
        try:
            k = functools.reduce(operator.getitem, args, ctx.bot.config)
        except KeyError:
            raise commands.BadArgument("Command cannot be used due to the lack of a config entry.")

        if not k:
            raise commands.BadArgument("Command cannot be used due to the lack of a config entry.")
        return True

    return commands.check(predicate)


def if_no_perms_then_vote(vote_name, string):
    async def inner(ctx):
        if ctx.invoked_with == "help":
            return True

        if not ctx.player.check_perms(ctx):
            if not ctx.author.voice or ctx.author not in ctx.me.voice.channel.members:
                raise commands.BadArgument("You can't vote.")
            votes = getattr(ctx.player, vote_name)

            no_bots = {x for x in ctx.author.voice.channel.members if not x.bot}
            necessary_votes = math.ceil(len(no_bots) / 2)

            if ctx.author in votes:
                raise commands.BadArgument("You already voted.")

            votes.add(ctx.author)

            if necessary_votes <= len(votes):
                votes.clear()
                return True

            raise commands.BadArgument(string.format(thing=f"{'resume' if ctx.player.paused else 'pause'}")
                                       + f"\n{utils.Plural(necessary_votes - len(votes)):vote} remaining.")

        return True

    return commands.check(inner)


def player_perms_check():
    def predicate(ctx):
        if ctx.invoked_with == "help":
            return True
        if not ctx.player.check_perms(ctx):
            raise commands.BadArgument("Only the owner of the player, moderators and admins can use this command.")

        return True

    return commands.check(predicate)
