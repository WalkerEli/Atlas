# provides read-only leaderboard queries from lifetime aggregates

from sqlalchemy.orm import Session
from atlas_bot.models.db import SessionLocal
from atlas_bot.models.player import Player
from atlas_bot.models.match import R6LifetimeAgg

def kills_top(limit: int = 25) -> list[dict]:
    db: Session = SessionLocal()
    try:
        rows = (
            db.query(Player.display_name, Player.discord_id, R6LifetimeAgg.kills)
            .join(R6LifetimeAgg, R6LifetimeAgg.player_id == Player.id)
            .order_by(R6LifetimeAgg.kills.desc(), Player.display_name.asc())
            .limit(limit)
            .all()
        )
        return [
            {"rank": i+1, "discord_id": d, "display_name": n or d, "kills": k}
            for i, (n, d, k) in enumerate(rows)
        ]
    finally:
        db.close()

def kdr_top(limit: int = 25) -> list[dict]:
    db: Session = SessionLocal()
    try:
        rows = (
            db.query(Player.display_name, Player.discord_id,
                     R6LifetimeAgg.kills, R6LifetimeAgg.deaths)
            .join(R6LifetimeAgg, R6LifetimeAgg.player_id == Player.id)
            .all()
        )
        scored = []
        for n, d, k, de in rows:
            de = de or 0
            kdr = (k or 0) / (de if de > 0 else 1)
            scored.append({
                "discord_id": d, "display_name": n or d,
                "kdr": round(float(kdr), 3), "kills": k or 0, "deaths": de
            })
        scored.sort(key=lambda x: (-x["kdr"], -x["kills"], x["display_name"]))
        return [{**row, "rank": i+1} for i, row in enumerate(scored[:limit])]
    finally:
        db.close()

def wlr_top(limit: int = 25) -> list[dict]:
    db: Session = SessionLocal()
    try:
        rows = (
            db.query(Player.display_name, Player.discord_id,
                     R6LifetimeAgg.wins, R6LifetimeAgg.losses)
            .join(R6LifetimeAgg, R6LifetimeAgg.player_id == Player.id)
            .all()
        )
        scored = []
        for n, d, w, l in rows:
            w = w or 0
            l = l or 0
            wlr = w / (l if l > 0 else 1)
            scored.append({
                "discord_id": d, "display_name": n or d,
                "wlr": round(float(wlr), 3), "wins": w, "losses": l
            })
        scored.sort(key=lambda x: (-x["wlr"], -x["wins"], x["display_name"]))
        return [{**row, "rank": i+1} for i, row in enumerate(scored[:limit])]
    finally:
        db.close()
