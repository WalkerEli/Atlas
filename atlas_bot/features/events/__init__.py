from __future__ import annotations
from discord.ext import commands
from .cog import EventCog


async def setup(bot: commands.Bot) -> None:
    """entry point for the events feature extension."""
    cog = EventCog(bot)
    await bot.add_cog(cog)

    # only register /event group if it's not already on the tree
    existing = bot.tree.get_command("event")
    if existing is None:
        bot.tree.add_command(cog.group)
