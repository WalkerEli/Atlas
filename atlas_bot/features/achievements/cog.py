import logging
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.orm import Session

from ...models.db import SessionLocal, Base, engine
from ...models.player import Player
from ...models.achievment import Achievement, Unlock
from .engine import ensure_catalog, evaluate_all_achievements

log = logging.getLogger(__name__)

# make sure tables exist (safe to call multiple times)
Base.metadata.create_all(bind=engine)


def _get_or_create_player(
    db: Session,
    discord_user: discord.abc.User,
) -> Player:
    """
    Map a Discord user to a Player row, creating one if needed.
    """
    discord_id = str(discord_user.id)

    player = db.query(Player).filter_by(discord_id=discord_id).first()
    if player:
        # optionally keep display name in sync
        if discord_user.display_name and player.display_name != discord_user.display_name:
            player.display_name = discord_user.display_name
        return player

    player = Player(
        discord_id=discord_id,
        display_name=discord_user.display_name,
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


def _fetch_unlocks_for_player(db: Session, player: Player) -> List[tuple[Achievement, Unlock]]:
    """
    Return (Achievement, Unlock) pairs for a given player.
    """
    rows = (
        db.query(Achievement, Unlock)
        .join(Unlock, Unlock.achievement_code == Achievement.code)
        .filter(Unlock.player_id == player.id)
        .order_by(Unlock.awarded_at.desc())
        .all()
    )
    return rows


class AchievementsCog(commands.Cog):
    """
    Cog providing commands to view and maintain R6 achievements.
    Backed by the SQLAlchemy models + rules engine.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # --------------------------------------------------------------------- events

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """
        Ensure the achievements catalog is present when the bot starts.
        """
        db: Session = SessionLocal()
        try:
            ensure_catalog(db)
            db.commit()
            log.info("Achievements catalog ensured.")
        except Exception as exc:
            log.exception("Error ensuring achievements catalog: %s", exc)
            db.rollback()
        finally:
            db.close()

    # --------------------------------------------------------------------- helpers

    async def _send_achievements_embed(
        self,
        itx: discord.Interaction,
        discord_user: discord.abc.User,
        ephemeral: bool = True,
    ) -> None:
        db: Session = SessionLocal()
        try:
            # make sure the player exists (creates row if missing)
            player = _get_or_create_player(db, discord_user)

            # ensure catalog exists (idempotent)
            ensure_catalog(db)

            # gather unlocks
            unlock_rows = _fetch_unlocks_for_player(db, player)
            total_ach = db.query(Achievement).count()
            unlocked_count = len(unlock_rows)

            if unlocked_count == 0:
                await itx.response.send_message(
                    f"{discord_user.mention} has no unlocked achievements yet.",
                    ephemeral=ephemeral,
                )
                return

            title_name = discord_user.display_name or discord_user.name

            embed = discord.Embed(
                title=f"🏆 Achievements for {title_name}",
                description=f"{unlocked_count}/{total_ach} achievements unlocked",
                color=discord.Color.gold(),
            )

            # show up to 20 latest achievements; note we ordered desc by awarded_at
            for ach, unlock in unlock_rows[:20]:
                awarded_ts = int(unlock.awarded_at.timestamp()) if unlock.awarded_at else None
                when = f"<t:{awarded_ts}:R>" if awarded_ts else "unknown"
                embed.add_field(
                    name=f"{ach.name} (`{ach.code}`)",
                    value=f"{ach.description}\nUnlocked: {when}",
                    inline=False,
                )

            if unlocked_count > 20:
                embed.set_footer(
                    text=f"Showing 20 of {unlocked_count} unlocked achievements."
                )

            await itx.response.send_message(embed=embed, ephemeral=ephemeral)
        finally:
            db.close()

    # --------------------------------------------------------------------- slash group

    group = app_commands.Group(
        name="achievements",
        description="View and manage Rainbow Six achievements",
    )

    @group.command(name="mine", description="Show your unlocked achievements")
    async def mine(self, itx: discord.Interaction) -> None:
        await self._send_achievements_embed(itx, itx.user)

    @group.command(name="user", description="Show achievements for another user")
    async def user(
        self,
        itx: discord.Interaction,
        member: discord.Member,
    ) -> None:
        await self._send_achievements_embed(itx, member, ephemeral=False)

    @group.command(
        name="recalc",
        description="Recalculate achievements for a player based on lifetime stats",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def recalc(
        self,
        itx: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        """
        Admin-only: run the rules engine for the specified member (or yourself).
        This assumes R6LifetimeAgg rows are already populated (via ingest).
        """
        target_user = member or itx.user
        db: Session = SessionLocal()
        try:
            player = _get_or_create_player(db, target_user)
            ensure_catalog(db)
            new_codes = evaluate_all_achievements(db, player.id)

            if not new_codes:
                await itx.response.send_message(
                    f"No new achievements unlocked for {target_user.mention}.",
                    ephemeral=True,
                )
                return

            # fetch achievement details to show names
            achs = (
                db.query(Achievement)
                .filter(Achievement.code.in_(new_codes))
                .all()
            )
            names = ", ".join(a.name for a in achs)
            await itx.response.send_message(
                f"🏆 New achievements unlocked for {target_user.mention}: {names}",
                ephemeral=False,
            )
        except Exception as exc:
            log.exception("Error recalculating achievements: %s", exc)
            await itx.response.send_message(
                "Error recalculating achievements. Check logs.", ephemeral=True
            )
        finally:
            db.close()


async def setup(bot: commands.Bot) -> None:
    cog = AchievementsCog(bot)
    await bot.add_cog(cog)

    # Only register the /achievements group if not already present
    existing = bot.tree.get_command("achievements")
    if existing is None:
        bot.tree.add_command(cog.group)
