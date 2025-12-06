from __future__ import annotations
from discord.ext import commands
from .cog import AchievementsCog


async def setup(bot: commands.Bot) -> None:
    cog = AchievementsCog(bot)
    await bot.add_cog(cog)

    # only register the /achievements group if not already present
    existing = bot.tree.get_command("achievements")
    if existing is None:
        bot.tree.add_command(cog.group)
