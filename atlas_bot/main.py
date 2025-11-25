# atlas_bot/main.py

import asyncio
import logging
import os
from typing import List

import discord
from discord.ext import commands
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# config / env
# -----------------------------------------------------------------------------

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is not set in your .env file")

# logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("atlas_bot")

# -----------------------------------------------------------------------------
# intents & bot setup
# -----------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True      # for normal commands
intents.members = True              # for member info / leaderboards
intents.voice_states = True         # for music


class MasterBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix="!",
            intents=intents,
            application_id=None,  # you can set this if desired
        )

    async def setup_hook(self) -> None:
        """
        Called by discord.py before the bot connects.
        Use this to load feature extensions / cogs.
        """
        # Full dotted paths to your feature modules
        initial_extensions: List[str] = [
            "atlas_bot.features.events",
            "atlas_bot.features.music",
            "atlas_bot.features.achievements.cog",
            "atlas_bot.features.stats",
            # add more as you create them (e.g., admin, fun, moderation, etc.)
        ]

        for ext in initial_extensions:
            try:
                await self.load_extension(ext)
                logger.info("Loaded extension %s", ext)
            except Exception as exc:
                logger.exception("Failed to load extension %s: %s", ext, exc)

        # Sync slash commands once on startup (for app_commands / hybrid commands)
        try:
            synced = await self.tree.sync()
            logger.info("Synced %d application commands", len(synced))
        except Exception as exc:
            logger.exception("Failed to sync app commands: %s", exc)


bot = MasterBot()

# -----------------------------------------------------------------------------
# global / core commands (live on the master bot)
# -----------------------------------------------------------------------------


@bot.event
async def on_ready():
    logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    logger.info("------")


@bot.hybrid_command(name="ping", description="Check if the bot is alive")
async def ping(ctx: commands.Context):
    """Simple ping command (works as !ping or /ping)."""
    await ctx.reply("Pong!", mention_author=False)


# add any other core commands that don't logically belong to a feature here


# -----------------------------------------------------------------------------
# entrypoint
# -----------------------------------------------------------------------------

async def main() -> None:
    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
