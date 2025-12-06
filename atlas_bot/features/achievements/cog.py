from __future__ import annotations
from typing import List
import discord
from discord.ext import commands

from atlas_bot.services.player_stats_store import (
    get_player_stats,
    get_leaderboard_by_kd,
)


def compute_awards(kd: float, win_rate_pct: int) -> List[str]:
    """compute a list of award names based solely on kd and win rate."""

    awards: List[str] = []

    # baseline tier
    if kd < 1.0 or win_rate_pct < 45:
        awards.append("boot camp recruit")

    # progressive tiers, all kd + win rate based
    if kd >= 1.0 and win_rate_pct >= 45:
        awards.append("bronze operator")

    if kd >= 1.2 and win_rate_pct >= 50:
        awards.append("silver operator")

    if kd >= 1.4 and win_rate_pct >= 55:
        awards.append("gold operator")

    if kd >= 1.6 and win_rate_pct >= 60:
        awards.append("platinum operator")

    if kd >= 1.8 and win_rate_pct >= 65:
        awards.append("diamond operator")

    if kd >= 2.0 and win_rate_pct >= 70:
        awards.append("champion operator")

    # ensure at least one award exists
    if not awards:
        awards.append("boot camp recruit")

    return awards


class AchievementsCog(commands.Cog):
    """award players based purely on kd and win/loss rates."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="achievements",
        description="show your mock r6 achievements based on kd and win rate.",
    )
    async def achievements(self, ctx: commands.Context) -> None:
        """show the caller's awards using their saved mock stats."""

        row = get_player_stats(ctx.author.id)

        if row is None:
            await ctx.reply(
                "i don't have any stats saved for you yet. "
                "run the r6 command first so i can record your mock stats.",
                mention_author=False,
            )
            return

        kd = float(row["kd"])
        win_rate = float(row["win_rate"])  # 0.0–1.0
        win_rate_pct = int(round(win_rate * 100))

        awards = compute_awards(kd, win_rate_pct)

        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s achievements",
            description="mock awards based on kd and win/loss rates.",
            color=discord.Color.gold(),
        )

        embed.add_field(name="kd", value=f"{kd:.2f}", inline=True)
        embed.add_field(name="win rate", value=f"{win_rate_pct}%", inline=True)

        embed.add_field(
            name="awards",
            value="\n".join(f"• {name}" for name in awards),
            inline=False,
        )

        embed.set_footer(text="stats are mock and based on your username/platform.")

        await ctx.reply(embed=embed, mention_author=False)

    @commands.hybrid_command(
        name="leaderboard",
        description="show the kd-based leaderboard.",
    )
    async def leaderboard(
        self,
        ctx: commands.Context,
        limit: int = 10,
    ) -> None:
        """show top players by kd (tiebreak: win rate)."""

        # clamp limit to a sane range
        limit = max(1, min(limit, 25))

        rows = get_leaderboard_by_kd(limit)

        if not rows:
            await ctx.reply(
                "no player stats have been saved yet. "
                "run the r6 command first to start populating the leaderboard.",
                mention_author=False,
            )
            return

        lines: List[str] = []

        for idx, row in enumerate(rows, start=1):
            kd = float(row["kd"])
            win_rate = float(row["win_rate"])
            win_rate_pct = int(round(win_rate * 100))
            username = row["username"]
            platform = row["platform"]

            lines.append(
                f"**{idx}.** `{username}` [{platform}] — "
                f"kd `{kd:.2f}`, win rate `{win_rate_pct}%`"
            )

        embed = discord.Embed(
            title="achievements leaderboard (by kd)",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )

        await ctx.reply(embed=embed, mention_author=False)
