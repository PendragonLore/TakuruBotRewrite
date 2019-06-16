import random
from datetime import datetime, timedelta

import async_cse
import async_pokepy
import discord
from discord.ext import commands

import utils
from utils.converters import Codeblock


class NoMoreAPIKeys(Exception):
    pass


class API(commands.Cog, name="API", command_attrs=dict(cooldown=commands.Cooldown(1, 2.5, commands.BucketType.user))):
    """APIs stuff."""

    def __init__(self, bot):
        self.bot = bot

        self.anon_id = None
        self.pokeball = "https://i.imgur.com/Y6QhlhR.png"

    async def generate_gif_embed(self, ctx, to_send, search):
        for gif in to_send:
            embed = discord.Embed(
                color=discord.Colour(0xA01B1B), title=f"**Search: ** {search}", description=f"[GIF URL Link]({gif})"
            )

            embed.set_image(url=gif)

            ctx.pages.add_entry(embed)

        await ctx.paginate()

    @commands.command(name="giphy")
    @utils.requires_config("tokens", "apis", "giphy")
    async def giphy(self, ctx, *, gif):
        """Search 5 GIFs on Giphy."""
        await ctx.trigger_typing()
        to_send = []

        key = ctx.bot.config.tokens["apis"]["giphy"]
        data = (
            await ctx.get("https://api.giphy.com/v1/gifs/search", q=gif, api_key=key, limit=5)
        )["data"]

        for entry in data:
            url = entry["images"]["original"]["url"]
            to_send.append(url)

        if not to_send:
            return await ctx.send("Search returned nothing.")

        await self.generate_gif_embed(ctx, to_send, gif)

    @commands.command(name="tenor")
    @utils.requires_config("tokens", "apis", "tenor")
    async def tenor(self, ctx, *, gif):
        """Search 5 GIFs on Tenor."""
        await ctx.trigger_typing()

        to_send = []

        if not self.anon_id:
            key = ctx.bot.config.tokens["apis"]["tenor"]
            self.anon_id = (await ctx.get("https://api.tenor.com/v1/anonid", key=key))["anon_id"]

        resp = await ctx.get("https://api.tenor.com/v1/search", q=gif, anon_id=self.anon_id, limit=5, cache=True)
        data = resp["results"]

        for entry in data:
            url = entry["media"][0]["gif"]["url"]
            to_send.append(url)

        if not to_send:
            return await ctx.send("Search returned nothing.")

        await self.generate_gif_embed(ctx, to_send, gif)

    @commands.command(name="urbandictionary", aliases=["ud", "urban", "define"])
    async def urban_dictionary(self, ctx, *, word):
        """Get a word's definition on Urban Dictionary."""
        data = (await ctx.get("https://api.urbandictionary.com/v0/define", term=word))["list"]

        for d in data:
            embed = discord.Embed(title=f"{d['word']} - {d['defid']}",
                                  url=d["permalink"], color=discord.Color(0x008CFF),
                                  timestamp=datetime.strptime(d["written_on"], "%Y-%m-%dT%H:%M:%S.%fZ"))

            embed.set_author(name=d["author"] or "No author.")
            embed.add_field(
                name="Definition",
                value=utils.trunc_text(d["definition"], 1024),
                inline=False,
            )
            if d["example"]:
                embed.add_field(
                    name="Example",
                    value=utils.trunc_text(d["example"], 1024),
                    inline=False,
                )

            embed.add_field(name="Ratings", value=f"\U0001f44d {d['thumbs_up']} \U0001f44e {d['thumbs_down']}")
            embed.set_footer(text="Created at")

            ctx.pages.add_entry(embed)

        await ctx.paginate()

    @commands.command(name="yt", aliases=["youtube"])
    async def yt_search(self, ctx, *, video):
        """Get the first video result of a youtube search."""
        tracks = await self.bot.wavelink.get_tracks(f"ytsearch:{video}")
        vid = tracks[0]

        embed = discord.Embed(
            color=discord.Colour.red(), title=vid.title, url=vid.uri, description=f"Uploaded by {vid.info['author']}"
        )

        embed.set_image(url=f"https://img.youtube.com/vi/{vid.ytid}/maxresdefault.jpg")
        embed.add_field(name="Lenght", value=str(timedelta(milliseconds=vid.duration)))

        await ctx.send(embed=embed)

    @commands.command(name="sc", aliases=["soundcloud"])
    async def sc_search(self, ctx, *, video):
        """Get the first track result of a soundcloud search."""
        tracks = await self.bot.wavelink.get_tracks(f"scsearch:{video}")
        track = tracks[0]

        embed = discord.Embed(
            color=discord.Colour.orange(),
            title=track.title,
            url=track.uri,
            description=f"Track by {track.info['author']}",
        )
        embed.add_field(name="Lenght", value=str(timedelta(milliseconds=track.duration)))

        await ctx.send(embed=embed)

    @commands.group(aliases=["g"], invoke_without_command=True, case_insensitive=True)
    async def google(self, ctx):
        """Google related commands."""
        await ctx.send_help("google")

    async def get_search(self, ctx, query, is_image=False):
        await ctx.trigger_typing()
        is_safe = not ctx.channel.is_nsfw()

        try:
            result = await self.bot.google.search(query=query, image_search=is_image, safesearch=is_safe)
        except async_cse.NoMoreRequests:
            try:
                self.bot.google = async_cse.Search(api_key=next(self.bot.google_api_keys))
                result = await self.bot.google.search(query=query, image_search=is_image, safesearch=is_safe)
            except (async_cse.NoMoreRequests, StopIteration):
                raise NoMoreAPIKeys()
        except async_cse.NoResults as e:
            raise commands.BadArgument(str(e))

        try:
            return random.choice(result[:5])
        except IndexError:
            raise commands.BadArgument("No results.")

    @google.command(name="s", aliases=["search"])
    async def google_search(self, ctx, *, query: commands.clean_content):
        """Just g o o g l e it.

        Safe search is disabled for NSFW channels."""
        result = await self.get_search(ctx, query)

        embed = discord.Embed(color=discord.Colour.red(), description=result.url, title=result.title)

        embed.set_thumbnail(url=result.image_url)
        embed.add_field(name="Description", value=result.description, inline=False)

        embed.set_footer(icon_url=ctx.author.avatar_url, text=f"Safe search enabled: {not ctx.channel.is_nsfw()}")

        await ctx.send(embed=embed)

    @google.command(name="image", aliases=["i"])
    async def google_image_search(self, ctx, *, query: commands.clean_content):
        """Get an image from google image.

        Safe search is disabled for NSFW channels."""
        result = await self.get_search(ctx, query, is_image=True)

        embed = discord.Embed(color=discord.Colour.red(), title=result.title, url=result.image_url)

        embed.set_image(url=result.image_url)

        embed.set_footer(icon_url=ctx.author.avatar_url, text=f"Safe search enabled: {not ctx.channel.is_nsfw()}")

        await ctx.send(embed=embed)

    @commands.command(aliases=["mystbin"])
    async def hastebin(self, ctx, *, content: Codeblock):
        """Post code on mystbin.

        Codeblocks are escaped."""
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        await ctx.post_to_mystbin(content)

    @commands.command(name="pokemon", aliases=["poke", "pokedex"])
    async def pokemon(self, ctx, *, name):
        """Get info on a Pokemon.

        Might not be up to date with the latest entries."""
        try:
            pokemon: async_pokepy.Pokemon = await ctx.bot.pokeapi.get_pokemon(name)
        except async_pokepy.PokeAPIException:
            return await ctx.send("No results.")

        embed = discord.Embed(color=discord.Color(0x008CFF))
        embed.set_thumbnail(url=pokemon.sprites.front_default)
        embed.set_author(name=f"{pokemon} - {pokemon.id}", icon_url=self.pokeball)
        types = " and ".join([str(x.type) for x in pokemon.types])

        embed.description = (f"{types} type\n"
                             f"{pokemon.height / 10} meters tall and {pokemon.weight / 10} kilograms heavy\n"
                             f"{len(pokemon.moves)} total moves")

        embed.add_field(name="Stats", value="\n".join([f"{s.base_stat:>10} **{s.stat}**"
                                                       for s in reversed(pokemon.stats)]))
        embed.add_field(name="Abilities", value="\n".join(map(str, pokemon.abilities)) or "None :thinking:")

        await ctx.send(embed=embed)

    @commands.command(name="pkmove", aliases=["pokemove"])
    async def pokemon_move(self, ctx, *, name):
        """Get info on a Pokemon move.

        Might not be up to date with the latest entries."""
        try:
            move = await ctx.bot.pokeapi.get_move(name)
        except async_pokepy.NotFound:
            return await ctx.send("No results.")

        embed = discord.Embed(color=discord.Color(0x008CFF))

        await ctx.send(embed=embed)

    @commands.command(name="pkability", aliases=["pkab", "pokeability"])
    async def pokemon_ability(self, ctx, *, name):
        """Get info on a Pokemon ability.

        Might not be up to date with the latest entries."""
        try:
            ability: async_pokepy.Ability = await ctx.bot.pokeapi.get_ability(name)
        except async_pokepy.PokeAPIException:
            return await ctx.send("No results.")

        embed = discord.Embed(color=discord.Color(0x008CFF))

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(API(bot))
