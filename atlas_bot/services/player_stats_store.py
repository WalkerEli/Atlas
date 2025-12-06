from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "player_stats.db"


def _get_conn() -> sqlite3.Connection:
    # open a connection to the sqlite database
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    # create the player_stats table if it does not exist
    with _get_conn() as conn:
        conn.execute(
            """
            create table if not exists player_stats (
                discord_id    integer primary key,
                username      text    not null,
                platform      text    not null,
                kd            real    not null,
                win_rate      real    not null,  -- 0.0-1.0
                matches       integer not null,
                wins          integer not null,
                losses        integer not null,
                last_updated  text    not null
            )
            """
        )
        conn.commit()


def save_player_stats(discord_id: int, data: Dict[str, Any]) -> None:
    # persist stats for a discord user
    init_db()

    kd = float(data.get("kd", 0.0))
    win_rate = float(data.get("win_rate", 0.0))
    matches = int(data.get("matches", 0))
    wins = int(data.get("wins", 0))
    losses = int(data.get("losses", 0))

    with _get_conn() as conn:
        conn.execute(
            """
            insert into player_stats (
                discord_id, username, platform, kd, win_rate,
                matches, wins, losses, last_updated
            )
            values (
                :discord_id, :username, :platform, :kd, :win_rate,
                :matches, :wins, :losses, :last_updated
            )
            on conflict(discord_id) do update set
                username     = excluded.username,
                platform     = excluded.platform,
                kd           = excluded.kd,
                win_rate     = excluded.win_rate,
                matches      = excluded.matches,
                wins         = excluded.wins,
                losses       = excluded.losses,
                last_updated = excluded.last_updated
            """,
            {
                "discord_id": int(discord_id),
                "username": data["username"],
                "platform": data["platform"],
                "kd": kd,
                "win_rate": win_rate,
                "matches": matches,
                "wins": wins,
                "losses": losses,
                "last_updated": datetime.utcnow().isoformat(timespec="seconds"),
            },
        )
        conn.commit()


def get_player_stats(discord_id: int) -> Optional[Dict[str, Any]]:
    # fetch the most recent saved stats for a discord user
    init_db()

    with _get_conn() as conn:
        row = conn.execute(
            """
            select
                discord_id, username, platform,
                kd, win_rate,
                matches, wins, losses,
                last_updated
            from player_stats
            where discord_id = ?
            """,
            (int(discord_id),),
        ).fetchone()

    if row is None:
        return None

    return dict(row)


def get_leaderboard_by_kd(limit: int = 10) -> List[Dict[str, Any]]:
    # return top players ordered by kd (desc) then win_rate (desc)
    init_db()

    with _get_conn() as conn:
        rows = conn.execute(
            """
            select
                discord_id, username, platform,
                kd, win_rate,
                matches, wins, losses,
                last_updated
            from player_stats
            order by kd desc, win_rate desc
            limit ?
            """,
            (int(limit),),
        ).fetchall()

    return [dict(r) for r in rows]


def seed_default_players() -> None:
    # always ensure the default demo players exist in the leaderboard
    init_db()

    # import here to avoid circular imports
    from atlas_bot.services.stats_service import compute_mock_stats

    # fake discord ids and usernames for demo data
    mock_players = [
        (111111111111111111, "AtlasAce", "uplay"),
        (222222222222222222, "BreachMaster", "psn"),
        (333333333333333333, "ClutchKing", "xbl"),
        (444444444444444444, "WallbangWiz", "uplay"),
        (555555555555555555, "SilentEntry", "psn"),
    ]

    for fake_id, username, platform in mock_players:
        data = compute_mock_stats(username, platform)
        save_player_stats(fake_id, data)
