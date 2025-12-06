from __future__ import annotations
import logging
from datetime import timedelta
from typing import Optional
import discord
from dateutil import parser as dtparse
from zoneinfo import ZoneInfo
from atlas_bot.services.calender_service import CalendarService
from atlas_bot.models.entitys import Event

log = logging.getLogger(__name__)


def tz_or_utc(name: Optional[str]) -> ZoneInfo:
    """
    resolve an IANA timezone name to a ZoneInfo instance.
    fallback to UTC if the name is invalid or missing.
    """
    try:
        return ZoneInfo(name) if name else ZoneInfo("UTC")
    except Exception:
        return ZoneInfo("UTC")


def embed_for(e: Event) -> discord.Embed:
    """
    build a rich embed for an event entity.
    """
    start = dtparse.isoparse(e.starts_at_iso)
    end = start + timedelta(minutes=e.duration_min)

    going = sum(1 for v in e.rsvps.values() if v == "going")
    maybe = sum(1 for v in e.rsvps.values() if v == "maybe")
    no = sum(1 for v in e.rsvps.values() if v == "unavailable")

    em = discord.Embed(
        title=f"📅 {e.title}",
        description=e.description,
        color=0x2B6CB0,
    )
    em.add_field(
        name="When",
        value=f"<t:{int(start.timestamp())}:F> → <t:{int(end.timestamp())}:t>",
        inline=False,
    )
    em.add_field(name="Location", value=e.location or "n/a", inline=True)
    em.add_field(
        name="RSVP",
        value=f"✅ {going}   ❓ {maybe}   ❌ {no}",
        inline=True,
    )
    em.set_footer(text=f"Event ID: {e.id}")
    return em


class RSVPView(discord.ui.View):
    """
    simple RSVP view per event. we intentionally do NOT register this as a
    persistent view; buttons are valid only for the lifetime of the process.
    """

    def __init__(self, svc: CalendarService, event_id: int) -> None:
        # timeout=None => view is kept alive as long as the bot is running
        super().__init__(timeout=None)
        self.svc = svc
        self.event_id = event_id

    @discord.ui.button(
        label="Going",
        style=discord.ButtonStyle.success,
        custom_id="rsvp_going",
    )
    async def btn_going(self, itx: discord.Interaction, _: discord.ui.Button):
        await self._set(itx, "going")

    @discord.ui.button(
        label="Maybe",
        style=discord.ButtonStyle.primary,
        custom_id="rsvp_maybe",
    )
    async def btn_maybe(self, itx: discord.Interaction, _: discord.ui.Button):
        await self._set(itx, "maybe")

    @discord.ui.button(
        label="Unavailable",
        style=discord.ButtonStyle.danger,
        custom_id="rsvp_no",
    )
    async def btn_no(self, itx: discord.Interaction, _: discord.ui.Button):
        await self._set(itx, "unavailable")

    async def _set(self, itx: discord.Interaction, status: str) -> None:
        """
        internal helper to write RSVP status and refresh the embed.
        """
        await self.svc.set_rsvp(self.event_id, itx.user.id, status)
        ev = await self.svc.get_event(self.event_id)

        if ev and ev.message_id and itx.channel:
            try:
                msg = await itx.channel.fetch_message(ev.message_id)
                await msg.edit(embed=embed_for(ev), view=self)
            except Exception as exc:
                log.warning("failed to edit event message for rsvp: %s", exc)

        await itx.response.send_message(
            f"RSVP set to **{status}**.", ephemeral=True
        )
