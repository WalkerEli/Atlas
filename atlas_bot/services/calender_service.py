import aiosqlite
from typing import List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from dateutil import parser as dtparse

from atlas_bot.models.entitys import Event  

DB_PATH = "data/events.sqlite"

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id INTEGER NOT NULL,
  channel_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  starts_at_iso TEXT NOT NULL,
  duration_min INTEGER NOT NULL,
  location TEXT NOT NULL,
  created_by INTEGER NOT NULL,
  message_id INTEGER
);
CREATE TABLE IF NOT EXISTS rsvps (
  event_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('going','maybe','unavailable')),
  PRIMARY KEY (event_id, user_id),
  FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);
"""

class CalendarService:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ready = False

    async def init(self):
        if self._ready:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()
        self._ready = True

    async def create_event(self, ev: Event) -> Event:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """INSERT INTO events
                   (guild_id, channel_id, title, description, starts_at_iso,
                    duration_min, location, created_by, message_id)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (ev.guild_id, ev.channel_id, ev.title, ev.description, ev.starts_at_iso,
                 ev.duration_min, ev.location, ev.created_by, ev.message_id),
            )
            await db.commit()
            ev.id = cur.lastrowid
        return ev

    async def set_message_id(self, event_id: int, message_id: int):
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE events SET message_id=? WHERE id=?", (message_id, event_id))
            await db.commit()

    async def update_event(self, event_id: int, **fields) -> Optional[Event]:
        await self.init()
        if not fields:
            return await self.get_event(event_id)
        sets = ", ".join([f"{k}=?" for k in fields.keys()])
        vals = list(fields.values()) + [event_id]
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE events SET {sets} WHERE id=?", vals)
            await db.commit()
        return await self.get_event(event_id)

    async def delete_event(self, event_id: int) -> bool:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM events WHERE id=?", (event_id,))
            await db.commit()
        return True

    async def get_event(self, event_id: int) -> Optional[Event]:
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT * FROM events WHERE id=?", (event_id,))
            r = await cur.fetchone()
            if not r:
                return None
            ev = Event(
                id=r[0], guild_id=r[1], channel_id=r[2], title=r[3], description=r[4],
                starts_at_iso=r[5], duration_min=r[6], location=r[7],
                created_by=r[8], message_id=r[9], rsvps={}
            )
            cur = await db.execute("SELECT user_id, status FROM rsvps WHERE event_id=?", (event_id,))
            ev.rsvps = {u: s for u, s in await cur.fetchall()}
            return ev

    async def list_upcoming(self, guild_id: int, limit: int = 10) -> List[Event]:
        await self.init()
        now_iso = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT * FROM events WHERE guild_id=? AND starts_at_iso>=? "
                "ORDER BY starts_at_iso ASC LIMIT ?",
                (guild_id, now_iso, limit),
            )
            rows = await cur.fetchall()
            out: List[Event] = []
            for r in rows:
                e = Event(
                    id=r[0], guild_id=r[1], channel_id=r[2], title=r[3], description=r[4],
                    starts_at_iso=r[5], duration_min=r[6], location=r[7],
                    created_by=r[8], message_id=r[9], rsvps={}
                )
                cur2 = await db.execute("SELECT user_id, status FROM rsvps WHERE event_id=?", (e.id,))
                e.rsvps = {u: s for u, s in await cur2.fetchall()}
                out.append(e)
            return out

    async def set_rsvp(self, event_id: int, user_id: int, status: str):
        await self.init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO rsvps(event_id, user_id, status) VALUES(?,?,?) "
                "ON CONFLICT(event_id, user_id) DO UPDATE SET status=excluded.status",
                (event_id, user_id, status),
            )
            await db.commit()

    async def next_reminders(self) -> List[Tuple[Event, int]]:
        """
        Return (Event, minutes_before) that should trigger now at 24h, 60m, 15m.
        Uses synthetic RSVP markers to avoid duplicates.
        """
        await self.init()
        out: List[Tuple[Event, int]] = []
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT * FROM events")
            for r in await cur.fetchall():
                e = Event(
                    id=r[0], guild_id=r[1], channel_id=r[2], title=r[3], description=r[4],
                    starts_at_iso=r[5], duration_min=r[6], location=r[7],
                    created_by=r[8], message_id=r[9], rsvps={}
                )
                cur2 = await db.execute("SELECT user_id, status FROM rsvps WHERE event_id=?", (e.id,))
                e.rsvps = {u: s for u, s in await cur2.fetchall()}

                start = dtparse.isoparse(e.starts_at_iso)
                now = datetime.now(start.tzinfo)
                for mins in (24*60, 60, 15):
                    marker_user = -mins
                    already = str(mins) in e.rsvps.values() or marker_user in e.rsvps
                    delta = start - now
                    due = timedelta(minutes=mins-1) < delta <= timedelta(minutes=mins)
                    if due and not already:
                        out.append((e, mins))
        return out

    async def mark_reminder_sent(self, event_id: int, minutes: int):
        await self.set_rsvp(event_id, -minutes, str(minutes))
