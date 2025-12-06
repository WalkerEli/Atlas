import logging

from discord.ext import commands

from .cog import StatsCog

log = logging.getLogger(__name__)


async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))
    log.info("Stats extension loaded.")
