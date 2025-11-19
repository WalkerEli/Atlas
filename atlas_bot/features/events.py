import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional
from datetime import timedelta
from dateutil import parser as dtparse
from zoneinfo import ZoneInfo

from services.calender_service import CalendarService
from models.entitys import Event

def tz_or_utc(name: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(name) if name else ZoneInfo("UTC")
    except Exception:
        return ZoneInfo("UTC")

def embed_for(e: Event) -> discord.Embed:
    start = dtparse.isoparse(e.starts_at_iso)
    end = start + timedelta(minutes=e.duration_min)
    going = sum(1 for v in e.rsvps.values() if v == "going")
    maybe = sum(1 for v in e.rsvps.values() if v == "maybe")
    no = sum(1 for v in e.rsvps.values() if v == "unavailable")
    em = discord.Embed(title=f"📅 {e.title}", description=e.description, color=0x2B6CB0)
    em.add_field(name="When", value=f"<t:{int(start.timestamp())}:F> → <t:{int(end.timestamp())}:t>", inline=False)
    em.add_field(name="Location", value=e.location or "n/a", inline=True)
    em.add_field(name="RSVP", value=f"✅ {going}   ❓ {maybe}   ❌ {no}", inline=True)
    em.set_footer(text=f"Event ID: {e.id}")
    return em

class RSVPView(discord.ui.View):
    def __init__(self, svc: CalendarService, event_id: int):
        super().__init__(timeout=None)
        self.svc = svc
        self.event_id = event_id

    @discord.ui.button(label="Going", style=discord.ButtonStyle.success, custom_id="rsvp_going")
    async def btn_going(self, itx: discord.Interaction, _: discord.ui.Button):
        await self._set(itx, "going")

    @discord.ui.button(label="Maybe", style=discord.ButtonStyle.primary, custom_id="rsvp_maybe")
    async def btn_maybe(self, itx: discord.Interaction, _: discord.ui.Button):
        await self._set(itx, "maybe")

    @discord.ui.button(label="Unavailable", style=discord.ButtonStyle.danger, custom_id="rsvp_no")
    async def btn_no(self, itx: discord.Interaction, _: discord.ui.Button):
        await self._set(itx, "unavailable")

    async def _set(self, itx: discord.Interaction, status: str):
        await self.svc.set_rsvp(self.event_id, itx.user.id, status)
        ev = await self.svc.get_event(self.event_id)
        if ev and ev.message_id:
            try:
                msg = await itx.channel.fetch_message(ev.message_id)
                await msg.edit(embed=embed_for(ev), view=self)
            except Exception:
                pass
        await itx.response.send_message(f"RSVP set to **{status}**.", ephemeral=True)

class EventCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.svc = CalendarService()
        self.reminders.start()

    async def cog_unload(self):
        self.reminders.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.svc.init()
        self.bot.add_view(RSVPView(self.svc, 0))

    group = app_commands.Group(name="event", description="Manage scrims, tournaments, and game nights")

    @group.command(name="create", description="Create an event")
    @app_commands.describe(
        title="Title",
        description="Short description",
        starts_at="Start like '2025-11-12 19:30'",
        timezone_name="IANA timezone like America/New_York. Defaults to UTC.",
        duration_min="Duration in minutes",
        location="Where it happens",
    )
    async def create(
        self,
        itx: discord.Interaction,
        title: str,
        description: str,
        starts_at: str,
        duration_min: app_commands.Range[int, 1, 10080],
        timezone_name: Optional[str] = "UTC",
        location: Optional[str] = "online",
    ):
        tz = tz_or_utc(timezone_name)
        try:
            dt_local = dtparse.parse(starts_at).replace(tzinfo=tz)
        except Exception:
            await itx.response.send_message("Invalid start time. Example: `2025-11-12 19:30`.", ephemeral=True)
            return

        ev = Event(
            id=0,
            guild_id=itx.guild_id,
            channel_id=itx.channel_id,
            title=title,
            description=description,
            starts_at_iso=dt_local.isoformat(),
            duration_min=int(duration_min),
            location=location or "online",
            created_by=itx.user.id,
        )
        ev = await self.svc.create_event(ev)
        view = RSVPView(self.svc, ev.id)
        msg = await itx.channel.send(embed=embed_for(ev), view=view)
        await self.svc.set_message_id(ev.id, msg.id)
        await itx.response.send_message(f"Event **{ev.title}** created. ID `{ev.id}`.", ephemeral=True)

    @group.command(name="list", description="List upcoming events")
    async def list_(self, itx: discord.Interaction):
        evs = await self.svc.list_upcoming(itx.guild_id)
        if not evs:
            await itx.response.send_message("No upcoming events.", ephemeral=True)
            return
        lines = []
        for e in evs:
            start = dtparse.isoparse(e.starts_at_iso)
            lines.append(f"• **{e.id}** — {e.title} — <t:{int(start.timestamp())}:F>")
        await itx.response.send_message("\n".join(lines), ephemeral=True)

    @group.command(name="show", description="Show an event card")
    async def show(self, itx: discord.Interaction, event_id: int):
        ev = await self.svc.get_event(event_id)
        if not ev:
            await itx.response.send_message("Event not found.", ephemeral=True)
            return
        await itx.response.send_message(embed=embed_for(ev), view=RSVPView(self.svc, ev.id))

    @group.command(name="delete", description="Delete an event")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def delete(self, itx: discord.Interaction, event_id: int):
        ev = await self.svc.get_event(event_id)
        if not ev:
            await itx.response.send_message("Event not found.", ephemeral=True)
            return
        await self.svc.delete_event(event_id)
        await itx.response.send_message(f"Deleted event {event_id}.", ephemeral=True)

    @group.command(name="edit", description="Edit an event")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def edit(
        self,
        itx: discord.Interaction,
        event_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        starts_at: Optional[str] = None,
        timezone_name: Optional[str] = None,
        duration_min: Optional[int] = None,
        location: Optional[str] = None,
    ):
        ev = await self.svc.get_event(event_id)
        if not ev:
            await itx.response.send_message("Event not found.", ephemeral=True)
            return

        updates = {}
        if title: updates["title"] = title
        if description: updates["description"] = description
        if duration_min: updates["duration_min"] = int(duration_min)
        if location: updates["location"] = location
        if starts_at:
            tz = tz_or_utc(timezone_name)
            try:
                updates["starts_at_iso"] = dtparse.parse(starts_at).replace(tzinfo=tz).isoformat()
            except Exception:
                await itx.response.send_message("Invalid new start time.", ephemeral=True)
                return

        ev2 = await self.svc.update_event(event_id, **updates)
        if ev2 and ev2.message_id:
            try:
                ch = itx.guild.get_channel(ev2.channel_id) or await self.bot.fetch_channel(ev2.channel_id)
                msg = await ch.fetch_message(ev2.message_id)
                await msg.edit(embed=embed_for(ev2), view=RSVPView(self.svc, ev2.id))
            except Exception:
                pass
        await itx.response.send_message("Event updated.", ephemeral=True)

    @group.command(name="rsvp", description="Set your RSVP")
    @app_commands.choices(status=[
        app_commands.Choice(name="Going", value="going"),
        app_commands.Choice(name="Maybe", value="maybe"),
        app_commands.Choice(name="Unavailable", value="unavailable"),
    ])
    async def rsvp(self, itx: discord.Interaction, event_id: int, status: app_commands.Choice[str]):
        ev = await self.svc.get_event(event_id)
        if not ev:
            await itx.response.send_message("Event not found.", ephemeral=True)
            return
        await self.svc.set_rsvp(event_id, itx.user.id, status.value)
        if ev.message_id:
            try:
                msg = await itx.channel.fetch_message(ev.message_id)
                ev = await self.svc.get_event(event_id)
                await msg.edit(embed=embed_for(ev), view=RSVPView(self.svc, ev.id))
            except Exception:
                pass
        await itx.response.send_message(f"RSVP set to **{status.value}**.", ephemeral=True)

    @tasks.loop(minutes=1)
    async def reminders(self):
        for ev, mins in await self.svc.next_reminders():
            try:
                ch = self.bot.get_channel(ev.channel_id) or await self.bot.fetch_channel(ev.channel_id)
                await ch.send(f"⏰ Reminder: **{ev.title}** starts in **{mins} minutes**. Event ID `{ev.id}`")
                await self.svc.mark_reminder_sent(ev.id, mins)
            except Exception:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(EventCog(bot))
