from __future__ import annotations
from discord.ext import commands
from .cog import MusicCog

async def setup(bot: commands.Bot) -> None:
    """entry point for discord.py extension loading."""
    await bot.add_cog(MusicCog(bot))
