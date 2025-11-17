import os
import requests
import discord
from discord.ext import commands
from dotenv import load_dotenv

# load environment variables from .env file if present
load_dotenv()

# base url for the fastapi service
ATLAS_API_BASE = os.getenv("ATLAS_API_BASE", "http://127.0.0.1:8000")

# discord intents tell the gateway what events we care about
intents = discord.Intents.default()
intents.message_content = True  # needed for reading normal messages / commands

# create the bot instance with a simple command prefix
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    # this runs when the bot has connected to discord
    print(f"logged in as {bot.user} (id: {bot.user.id})")
    await bot.change_presence(activity=discord.Game(name="r6 stats"))


@bot.command(name="r6", help="show rainbow six siege stats for a player")
async def r6_stats(ctx: commands.Context, username: str):
    # show typing indicator while we call the api
    await ctx.trigger_typing()

    # call the fastapi endpoint that uses stats_service.py
    try:
        resp = requests.get(
            f"{ATLAS_API_BASE}/r6/player",
            params={"username": username},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        # this handles network or http errors talking to the api
        await ctx.send(f"could not reach the stats api: `{exc}`")
        return

    payload = resp.json()

    # api always returns {"status": "...", "data": ...} on success
    if payload.get("status") != "ok" or "data" not in payload:
        detail = payload.get("detail") or "no stats found"
        await ctx.send(f"could not fetch stats for `{username}`: {detail}")
        return

    stats = payload["data"]

    # pull normalized fields from stats_service.py
    kills = stats.get("kills", 0)
    deaths = stats.get("deaths", 0)
    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    abandons = stats.get("abandons", 0)
    matches = stats.get("matches_played", 0)
    kd = stats.get("kd_ratio", 0.0)
    wl = stats.get("win_loss_ratio", 0.0)
    time_played = stats.get("time_played", 0)
    hours_played = (time_played or 0) / 3600

    username_norm = stats.get("username", username)
    platform = stats.get("platform", "?")
    family = stats.get("family", "?")

    # build a discord embed to display the stats nicely
    embed = discord.Embed(
        title=f"r6 stats – {username_norm}",
        description=f"{platform} / {family}",
    )

    embed.add_field(name="kills", value=str(kills), inline=True)
    embed.add_field(name="deaths", value=str(deaths), inline=True)
    embed.add_field(name="k/d", value=f"{kd:.3f}", inline=True)

    embed.add_field(name="wins", value=str(wins), inline=True)
    embed.add_field(name="losses", value=str(losses), inline=True)
    embed.add_field(name="abandons", value=str(abandons), inline=True)

    embed.add_field(name="matches played", value=str(matches), inline=True)
    embed.add_field(name="time played", value=f"{hours_played:.1f} hours", inline=True)
    embed.add_field(name="win / loss", value=f"{wl:.3f}", inline=True)

    await ctx.send(embed=embed)

def _get_token() -> str:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not found.")
    return token


if __name__ == "__main__":
    # entry point for running the bot
    bot.run(_get_token())
