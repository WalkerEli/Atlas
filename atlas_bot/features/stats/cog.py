# atlas_bot/features/stats/cog.py
import logging

import discord
from discord.ext import commands

from atlas_bot.services.stats_service import compute_mock_stats

log = logging.getLogger(__name__)


class StatsCog(commands.Cog):
    """commands related to mock r6 stats"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        log.info("StatsCog ready; mock stats commands registered.")

    @commands.hybrid_command(
        name="r6",
        description="look up a mock rainbow six siege player.",
    )
    async def r6(
        self,
        ctx: commands.Context,
        username: str,
        platform: str = "uplay",
    ):
        """usage: !r6 <username> [platform]"""

        username = username.strip()
        platform = platform.strip().lower()

        if not username:
            await ctx.reply("❌ username cannot be empty.", mention_author=False)
            return

        try:
            data = compute_mock_stats(username, platform)
        except ValueError as exc:
            # bad input (empty / invalid platform)
            await ctx.reply(f"❌ {exc}", mention_author=False)
            return
        except Exception as exc:  # unexpected
            log.exception("unexpected error in r6 command: %r", exc)
            await ctx.reply(
                "❌ something went wrong while looking up that player.",
                mention_author=False,
            )
            return

        msg = (
            f"✅ **r6 player (mock)**\n"
            f"username: **{data['username']}**\n"
            f"platform: `{data['platform']}`\n"
            f"level: `{data.get('level', 'n/a')}`\n"
            f"k/d: `{data.get('kd', 'n/a')}`\n"
            f"_({data.get('message', '')})_"
        )
        await ctx.reply(msg, mention_author=False)
