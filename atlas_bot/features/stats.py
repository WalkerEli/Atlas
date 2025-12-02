# features/stats.py
import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from ..services.stats_service import (
    r6_player_stats,
    r6_player_stats_try_all_platforms,
    R6StatsError,
)
from atlas_bot.services.leaderboard_service import kills_top, kdr_top, wlr_top

log = logging.getLogger(__name__)


class StatsCog(commands.Cog):
    """
    Cog providing live R6 stats (via external API) and DB-backed leaderboards.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ----------------------------------------------------------------- R6 stats group

    r6 = app_commands.Group(
        name="r6",
        description="Rainbow Six Siege player statistics",
    )

    @r6.command(
        name="stats",
        description="Show ranked/lifetime stats for a player.",
    )
    @app_commands.describe(
        username="R6 username (name on platform)",
        platform="Optional platform: uplay, psn, xbl (auto-detect if omitted)",
        family="Platform family: pc or console",
    )
    async def r6_stats(
        self,
        itx: discord.Interaction,
        username: str,
        platform: Optional[str] = None,
        family: str = "pc",
    ) -> None:
        family = family.lower()
        if family not in {"pc", "console"}:
            family = "pc"

        try:
            if platform:
                platform = platform.lower()
                if platform not in {"uplay", "psn", "xbl"}:
                    await itx.response.send_message(
                        "Invalid platform. Use `uplay`, `psn`, or `xbl`.",
                        ephemeral=True,
                    )
                    return
                stats = r6_player_stats(
                    username=username,
                    platform=platform,  # type: ignore[arg-type]
                    family=family,     # type: ignore[arg-type]
                )
            else:
                stats = r6_player_stats_try_all_platforms(
                    username=username,
                    family=family,      # type: ignore[arg-type]
                )
        except R6StatsError as exc:
            await itx.response.send_message(
                f"Failed to fetch stats: {exc}", ephemeral=True
            )
            return
        except Exception as exc:
            log.exception("Unexpected error in r6_stats: %s", exc)
            await itx.response.send_message(
                "Unexpected error while fetching stats.", ephemeral=True
            )
            return

        # Build embed from normalized stats dict
        username = stats.get("username", username)
        platform = stats.get("platform", platform or "auto")
        family = stats.get("family", family)

        kills = stats.get("kills", 0)
        deaths = stats.get("deaths", 0)
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        matches_played = stats.get("matches_played", 0)
        time_played = stats.get("time_played", 0)
        kd_ratio = stats.get("kd_ratio", 0.0)
        win_loss_ratio = stats.get("win_loss_ratio", 0.0)

        hours = time_played // 3600
        minutes = (time_played % 3600) // 60

        embed = discord.Embed(
            title="🎮 R6 Ranked Stats",
            description=f"`{username}` on **{platform}** ({family})",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Kills", value=str(kills), inline=True)
        embed.add_field(name="Deaths", value=str(deaths), inline=True)
        embed.add_field(name="K/D Ratio", value=f"{kd_ratio:.3f}", inline=True)

        embed.add_field(name="Wins", value=str(wins), inline=True)
        embed.add_field(name="Losses", value=str(losses), inline=True)
        embed.add_field(
            name="W/L Ratio", value=f"{win_loss_ratio:.3f}", inline=True
        )

        embed.add_field(name="Matches Played", value=str(matches_played), inline=True)
        embed.add_field(
            name="Time Played",
            value=f"{hours}h {minutes}m",
            inline=True,
        )

        await itx.response.send_message(embed=embed)

    # ----------------------------------------------------------------- Leaderboard group

    leaderboard = app_commands.Group(
        name="leaderboard",
        description="R6 leaderboards based on stored lifetime stats",
    )

    async def _send_leaderboard(
        self,
        itx: discord.Interaction,
        title: str,
        rows: list[dict],
        stat_key: str,
        stat_label: str,
    ) -> None:
        if not rows:
            await itx.response.send_message(
                "No leaderboard data available yet.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=title,
            color=discord.Color.purple(),
        )

        description_lines = []
        for row in rows:
            rank = row.get("rank")
            display_name = row.get("display_name") or row.get("discord_id")
            discord_id = row.get("discord_id")
            value = row.get(stat_key)

            # mention if we have a valid discord id (stringified int)
            mention = None
            try:
                int(discord_id)
                mention = f"<@{discord_id}>"
            except Exception:
                pass

            line_name = f"#{rank} {display_name}"
            if mention:
                line_name += f" ({mention})"

            description_lines.append(f"**{line_name}** — {stat_label}: `{value}`")

        embed.description = "\n".join(description_lines[:25])

        await itx.response.send_message(embed=embed)

    @leaderboard.command(
        name="kills",
        description="Show top players by total kills.",
    )
    @app_commands.describe(limit="Number of players to show (max 50)")
    async def lb_kills(
        self,
        itx: discord.Interaction,
        limit: Optional[int] = 10,
    ) -> None:
        limit = max(1, min(limit or 10, 50))
        rows = kills_top(limit=limit)
        await self._send_leaderboard(
            itx,
            title=f"🏆 Kills Leaderboard (Top {limit})",
            rows=rows,
            stat_key="kills",
            stat_label="Kills",
        )

    @leaderboard.command(
        name="kdr",
        description="Show top players by K/D ratio.",
    )
    @app_commands.describe(limit="Number of players to show (max 50)")
    async def lb_kdr(
        self,
        itx: discord.Interaction,
        limit: Optional[int] = 10,
    ) -> None:
        limit = max(1, min(limit or 10, 50))
        rows = kdr_top(limit=limit)
        await self._send_leaderboard(
            itx,
            title=f"🏆 K/D Ratio Leaderboard (Top {limit})",
            rows=rows,
            stat_key="kdr",
            stat_label="K/D",
        )

    @leaderboard.command(
        name="wlr",
        description="Show top players by win/loss ratio.",
    )
    @app_commands.describe(limit="Number of players to show (max 50)")
    async def lb_wlr(
        self,
        itx: discord.Interaction,
        limit: Optional[int] = 10,
    ) -> None:
        limit = max(1, min(limit or 10, 50))
        rows = wlr_top(limit=limit)
        await self._send_leaderboard(
            itx,
            title=f"🏆 Win/Loss Ratio Leaderboard (Top {limit})",
            rows=rows,
            stat_key="wlr",
            stat_label="W/L Ratio",
        )


async def setup(bot: commands.Bot) -> None:
    cog = StatsCog(bot)
    await bot.add_cog(cog)

    # Only register command groups if not already present
    if bot.tree.get_command("r6") is None:
        bot.tree.add_command(cog.r6)

    if bot.tree.get_command("leaderboard") is None:
        bot.tree.add_command(cog.leaderboard)
