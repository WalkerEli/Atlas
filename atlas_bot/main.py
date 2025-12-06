import asyncio
import logging
import os
from typing import List
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from atlas_bot.services.player_stats_store import seed_default_players

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is not set in your .env file")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("atlas_bot.main")


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True


class MasterBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix="!",
            intents=intents,
            # discord.py will fetch the application id after login if this is None
            application_id=None,
        )

    async def setup_hook(self) -> None:
        """load feature extensions / cogs before connecting"""

        initial_extensions: List[str] = [
            "atlas_bot.features.events",
            "atlas_bot.features.music",
            "atlas_bot.features.stats",
            "atlas_bot.features.achievements",
        ]

        for ext in initial_extensions:
            try:
                await self.load_extension(ext)
                logger.info("Loaded extension %s", ext)
            except Exception as exc:
                logger.exception("Failed to load extension %s: %s", ext, exc)

        # seed default leaderboard entries on first run
        try:
            seed_default_players()
            logger.info("Seeded default leaderboard players (if needed)")
        except Exception as exc:
            logger.exception("Failed to seed default players: %s", exc)

        # we sync the tree in on_ready


bot = MasterBot()



# core events / commands

@bot.event
async def on_ready():
    logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)

    # sync application (slash + hybrid) commands once
    if not getattr(bot, "synced", False):
        try:
            synced = await bot.tree.sync()
            bot.synced = True
            logger.info("Synced %d application commands", len(synced))
            for cmd in synced:
                # use .name instead of .qualified_name for logging
                logger.info(" - /%s", getattr(cmd, "name", repr(cmd)))
        except Exception as exc:
            logger.exception("Failed to sync app commands: %s", exc)

    logger.info("------")


@bot.hybrid_command(name="ping", description="check if the bot is alive")
async def ping(ctx: commands.Context) -> None:
    """simple ping command"""
    await ctx.reply("Pong!", mention_author=False)


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    """generic error handler for prefix / hybrid commands"""

    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.CommandInvokeError):
        original = error.original
        logger.exception("Unhandled command error: %r", original)
    else:
        logger.exception("Unhandled command error: %r", error)

    try:
        await ctx.reply(
            "something went wrong running that command. the error has been logged.",
            mention_author=False,
        )
    except Exception:
        pass


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    """generic error handler for slash commands"""

    logger.exception("Unhandled slash command error: %r", error)

    msg = (
        "something went wrong while running that slash command. "
        "the error has been logged."
    )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass


# entrypoint

async def main() -> None:
    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
