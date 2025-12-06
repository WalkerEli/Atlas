# atlas_bot/features/stats/cog.py

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from atlas_bot.services.stats_service import compute_mock_stats
from atlas_bot.services.player_stats_store import save_player_stats

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
    ) -> None:
        """usage: !r6 <username> [platform]"""

        username = username.strip()
        platform = platform.strip().lower()

        if not username:
            await ctx.reply("username cannot be empty.", mention_author=False)
            return

        try:
            data = compute_mock_stats(username, platform)
        except ValueError as exc:
            # bad input (empty / invalid platform)
            await ctx.reply(f"{exc}", mention_author=False)
            return
        except Exception:
            log.exception("unexpected error in r6 command")
            await ctx.reply(
                "something went wrong while looking up that player.",
                mention_author=False,
            )
            return

        # save stats for this discord user so achievements/leaderboards can use them
        try:
            save_player_stats(ctx.author.id, data)
        except Exception:
            # log but don't bother the user if persistence fails
            log.exception(
                "failed to save player stats for user_id=%s", ctx.author.id
            )

        msg = (
            f"**Player Stats**\n"
            f"username: **{data['username']}**\n"
            f"platform: `{data['platform']}`\n"
            f"level: `{data.get('level', 'n/a')}`\n"
            f"k/d: `{data.get('kd', 'n/a')}`\n"
            f"matches: `{data.get('matches', 'n/a')}`\n"
            f"wins: `{data.get('wins', 'n/a')}` | "
            f"losses: `{data.get('losses', 'n/a')}`\n"
            f"win rate: `{data.get('win_rate_pct', 'n/a')}%`\n"
            f"_({data.get('message', '')})_"
        )

        await ctx.reply(msg, mention_author=False)
