import asyncio
import random

import asyncpg
import discord
import more_itertools
import re
from discord.ext import commands, flags

import utils


class MemeName(commands.clean_content):
    async def convert(self, ctx, argument):
        converted = await super().convert(ctx, argument)

        stripped = converted.strip()

        if not stripped:
            raise commands.BadArgument("Meme name missing.")

        if len(stripped) > 128:
            raise commands.BadArgument("Meme name can be up to 128 characters.")

        fw, _, _ = stripped.partition(" ")
        if fw in ctx.bot.get_command("meme").all_commands:
            raise commands.BadArgument("This meme name starts with a reserved word.")

        return converted


class MemeContent(commands.clean_content):
    async def convert(self, ctx, argument):
        argument = await super().convert(ctx, argument)

        try:
            att = ctx.message.attachments[0].url
            argument += f"\n\n{att}"
        except IndexError:
            pass

        if len(argument) > 1850 or argument.count("\n") >= 40:
            raise commands.BadArgument("Meme content too long.")

        return argument


class Memes(commands.Cog, command_attrs=dict(cooldown=commands.Cooldown(1, 2.5, commands.BucketType.user))):
    """EPIC M E M E Z"""

    URL_REGEX = r"(<https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)>)"

    @commands.command(name="install")
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def install_(self, ctx, *, package: commands.clean_content):
        """Install a package from homebrew.

        ~~not really tho.~~"""
        msg = await ctx.send("Updating homebrew...")

        await asyncio.sleep(3)

        await msg.edit(
            content=f'**Error**: No available formula with the name "{package}"\n'
            "==> Searching for a previously deleted formula (in the last month)..."
        )

        await asyncio.sleep(2)

        await msg.edit(
            content=f"{msg.content}\n\n**Error**: No previously deleted formula found.\n"
            "==> Searching for similarly named formulae."
        )

        await asyncio.sleep(1)

        await msg.edit(
            content=f"{msg.content}\n==> Searching taps...\n"
            "==> Searching taps on GitHub...\n"
            "**Error**: No formulae found in taps."
        )

        await asyncio.sleep(2)

        await ctx.send("tldr no")

    @commands.command(name="realquote")
    async def real_quote(self, ctx):
        """Get an inspring quote..."""

        def predicate(m):
            return (
                m.content and not
                m.author == ctx.bot.user
            )

        messages = await ctx.channel.history(limit=100).filter(predicate).flatten()
        if not messages:
            return await ctx.send("No quotes for today... 😔")

        quote = random.choice(messages)
        return await ctx.send(f"A certain {quote.author.name} once said: *\"{quote.content}\"* 😔")

    @commands.command(name="funnyjoke")
    async def joke(self, ctx):
        """Get an ~~un~~funny joke."""
        await ctx.send(
            (await ctx.get("https://icanhazdadjoke.com/", __headers=(("Accept", "application/json"),)))["joke"]
        )

    async def generate_embeds(self, ctx, meme_list):
        for meme in more_itertools.chunked(meme_list, 20):
            meme_embed = discord.Embed(color=discord.Color(0x008CFF))
            meme_embed.set_footer(text=f"Total Memes: {len(meme_list)}")

            fin_memes = []

            for m in meme:
                fin_memes.append(m)

            meme_embed.description = f"\n".join(fin_memes)
            ctx.pages.add_entry(meme_embed)

        await ctx.paginate()

    async def round_search(self, ctx, name):
        async with ctx.db.acquire() as db:
            sql = """
            SELECT   name
            FROM     memes
            WHERE    guild_id = $1 AND
                     name % $2
            ORDER BY similarity(NAME, $2) DESC, name ASC 
            LIMIT 15;
            """

            search = await db.fetch(sql, ctx.guild.id, name)

        results = [result["name"] for result in search]

        return results

    async def get_meme(self, ctx, name, *, raw=False):
        async with ctx.db.acquire() as db:
            sql = """SELECT content
                        FROM memes
                        WHERE guild_id = $1
                        AND name = $2;"""

            meme = await db.fetchval(sql, ctx.guild.id, name)

        if not meme:
            results = await self.round_search(ctx, name)

            if not results:
                return await ctx.send("Meme not found.")

            results = "\n".join(results[:5])

            return await ctx.send(f"Meme not found. Did you mean...\n{results}")

        async with ctx.db.acquire() as db:
            update = """UPDATE memes
                          SET count = count + 1
                          WHERE name = $1 AND guild_id = $2;"""

            await db.execute(update, name, ctx.guild.id)

        if raw:
            cleaned = discord.utils.escape_markdown(meme)

            escape_channels = re.sub(r"(<#\d+>)", r"\\\1", cleaned)
            escape_urls = re.sub(self.URL_REGEX, "\\\\\\1 \u200b", escape_channels)

            meme = escape_urls

        await ctx.send(meme)

    @commands.group(name="meme", invoke_without_command=True, case_insensitive=True)
    async def meme(self, ctx, *, meme: MemeName = None):
        """Commands related to the meme system.

        If a meme name is provided it will search the database for it."""
        if not meme and ctx.invoked_subcommand is None:
            return await ctx.send_help("meme")

        await ctx.invoke(self.meme_send, name=meme)

    @meme.command(name="get", aliases=["send"])
    async def meme_send(self, ctx, *, name: MemeName):
        """Send a meme."""
        await self.get_meme(ctx, name, raw=False)

    @meme.command(name="raw")
    @commands.cooldown(1, 2.5, commands.BucketType.user)
    async def meme_raw(self, ctx, *, name: MemeName):
        """Get the raw content of a meme.

        Raw content escapes any markdown formatting,
        e.g. \"**a meme**\" becomes \"\\*\\*a meme\\*\\*\""""
        await self.get_meme(ctx, name, raw=True)

    @meme.command(name="claim")
    async def meme_claim(self, ctx, *, meme: MemeName):
        """Claim the ownership of a meme.

        The original owner must have left the guild."""
        async with ctx.db.acquire() as db:
            sql = """SELECT owner_id
                        FROM memes
                        WHERE name = $1
                        AND guild_id = $2"""

            check = await db.fetchval(sql, meme, ctx.guild.id)

        if check is None:
            return await ctx.send("Meme not found.")

        if check == ctx.author.id:
            return await ctx.send(f"You already own {meme}.")

        if not ctx.guild.chunked:
            await ctx.bot.request_offline_members(ctx.guild)

        member = ctx.guild.get_member(check)

        if member is not None:
            return await ctx.send("The owner is still in the guild.")

        async with ctx.db.acquire() as db:
            sql = """UPDATE memes
                        SET owner_id = $1
                        WHERE name = $2
                        AND guild_id = $3;"""

            await db.execute(sql, ctx.author.id, meme, ctx.guild.id)

        await ctx.send(f"You are now the owner of {meme}.")

    @meme.command(name="add", cls=flags.FlagCommand)
    async def meme_add(self, ctx, name: MemeName, *, content: MemeContent = utils.FirstAttachment):
        """Add a meme.

        You can also add an attachment to the meme as an url,
        only the first one of your message will be included.

        If with the URL the meme's content becomes too big it will be discarded."""
        async with ctx.db.acquire() as db:
            sql = """INSERT INTO memes
                        (guild_id, name, content, owner_id)
                        VALUES
                        ($1, $2, $3, $4);"""

            try:
                await db.execute(sql, ctx.guild.id, name, content, ctx.author.id)
            except asyncpg.UniqueViolationError:
                return await ctx.send(f"Meme {name} already exists.")

        await ctx.send(f"Successfully added meme {name}.")

    @meme.command(name="list", aliases=["lis"])
    async def meme_list(self, ctx):
        """Get a list of all the guild's memes."""
        async with ctx.db.acquire() as db:
            sql = """SELECT name
                        FROM memes
                        WHERE guild_id=$1
                        ORDER BY name ASC;"""

            memes = await db.fetch(sql, ctx.guild.id)

        if not memes:
            return await ctx.send("There are no logged memes.")

        memes_list = [f"{index}. {meme['name']}" for index, meme in enumerate(memes, 1)]

        await self.generate_embeds(ctx, memes_list)

    @meme.command(name="remove", aliases=["delete", "del"])
    async def meme_remove(self, ctx, *, name: MemeName):
        """Delete a meme, you have to own it."""
        async with ctx.db.acquire() as db:
            sql = """
            DELETE FROM memes
            WHERE  guild_id = $1 AND
                   name = $2 AND
                   owner_id = $3;
            """

            deleted = await db.execute(sql, ctx.guild.id, name, ctx.author.id)

        if deleted[-1] == "0":
            return await ctx.send("Couldn't delete meme. You either are not the owner of it or it was not found.")

        await ctx.send(f"Successfully deleted meme {name}.")

    @meme.command(name="search")
    async def meme_search(self, ctx, *, name: MemeName):
        """Search for a meme from the database.

        The query must be at least 3 characters."""
        if len(name) < 3:
            raise commands.BadArgument("Query must be at least 3 characters.")

        results = await self.round_search(ctx, name)

        if not results:
            return await ctx.send("Search returned nothing.")

        memes = [f"{index}. {meme}" for index, meme in enumerate(results, 1)]

        await self.generate_embeds(ctx, memes)

    @meme.command(name="edit")
    async def meme_edit(self, ctx, name: MemeName, *, new_content: MemeContent):
        """Edit a meme's content, you have to own it.

        Editing the content will replace it completely."""
        async with ctx.db.acquire() as db:
            sql = """
            UPDATE memes
            SET    content = $1
            WHERE  guild_id = $2 AND
                   name = $3 AND
                   owner_id = $4;
            """

            edited = await db.execute(sql, new_content, ctx.guild.id, name, ctx.author.id)

        if edited[-1] == "0":
            return await ctx.send("Could not edit meme, it either doesn't exist or you don't own it.")

        await ctx.send(f"Updated content of {name} to {new_content}")

    @meme.command(name="info")
    async def meme_info(self, ctx, *, name: MemeName):
        """Get a meme's info.

        This includes owner info, number of uses, name and creation date."""
        async with ctx.db.acquire() as db:
            sql = """
            SELECT *
            FROM   memes
            WHERE  guild_id = $1 AND
                   name = $2;
            """

            data = await db.fetchrow(sql, ctx.guild.id, name)

        if not data:
            return await ctx.send("Meme not found.")

        owner = ctx.bot.get_user(data["owner_id"])

        embed = discord.Embed(
            color=discord.Color(0x008CFF), title="Meme info", timestamp=data["created_at"]
        )

        embed.set_author(icon_url=owner.avatar_url, name=str(owner))

        embed.add_field(name="Name", value=data["name"])
        embed.add_field(name="Owner", value=owner.mention)
        embed.add_field(name="Number of uses", value=str(data["count"]))

        embed.set_footer(icon_url=ctx.author.avatar_url, text="Created at")

        await ctx.send(embed=embed)

    @meme.command(name="memes", cls=flags.FlagCommand)
    async def meme_memes(self, ctx, member: discord.Member = utils.Author):
        """Get all the memes a member owns."""
        async with ctx.db.acquire() as db:
            sql = """
            SELECT NAME
            FROM   memes
            WHERE  owner_id = $1 AND 
                   guild_id = $2
            ORDER  BY name ASC;
            """

            results = await db.fetch(sql, member.id, ctx.guild.id)

        if not results:
            return await ctx.send(f"{member} has no memes.")

        memes_list = [f"{index}. {meme['name']}" for index, meme in enumerate(results, 1)]

        await self.generate_embeds(ctx, memes_list)

    @meme.command(name="transfer")
    async def transfer_ownership(self, ctx, name: MemeName, recipient: discord.Member):
        """Transfer the ownership of a meme, you have to own it."""
        if recipient.id == ctx.author.id:
            return await ctx.send(f"You already own {name}.")

        async with ctx.db.acquire() as db:
            sql = """
            SELECT owner_id
            FROM   memes
            WHERE  guild_id = $1 AND
                   name = $2     AND
                   owner_id = $3;
            """

            check = await db.fetchrow(sql, ctx.guild.id, name, ctx.author.id)

        if check is None:
            return await ctx.send(f"You are not the owner of {name} or it doesn't exist.")

        async with ctx.db.acquire() as db:
            sql = """
            UPDATE memes
            SET    owner_id = $1
            WHERE  name = $2 AND
                   guild_id = $3;
            """

            await db.execute(sql, recipient.id, name, ctx.guild.id)

        await ctx.send(f"{recipient} is now the owner of {name}.")

    @meme.command(name="random")
    async def meme_random(self, ctx):
        """Get a random meme.

        The number of uses will not be increased."""
        async with ctx.db.acquire() as db:
            sql = """
            SELECT name,
                   content
            FROM   memes
            WHERE  guild_id = $1
            ORDER  BY Random()
            LIMIT  1;
            """

            data = await db.fetchrow(sql, ctx.guild.id)

        await ctx.send(f"Random meme: **{data['name']}**\n\n{data['content']}")


def setup(bot):
    bot.add_cog(Memes())
