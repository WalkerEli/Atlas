# atlas_bot/features/achievements/__init__.py

from __future__ import annotations

from discord.ext import commands

from .cog import AchievementsCog


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AchievementsCog(bot))
