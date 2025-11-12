from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from atlas_bot.models.db import SessionLocal, Base, engine
from atlas_bot.models.player import Player
from atlas_bot.models.match import R6Match, R6LifetimeAgg
from atlas_bot.features.achievements.engine import ensure_catalog, evaluate_kill_milestones

# create tables once
Base.metadata.create_all(bind=engine)

def _get_or_create_player(db: Session, discord_id: str, display_name: Optional[str] = None) -> Player:
    # fetch player by discord id or create
    p = db.query(Player).filter_by(discord_id=discord_id).first()
    if not p:
        p = Player(discord_id=discord_id, display_name=display_name)
        db.add(p)
        db.commit()
        db.refresh(p)
    return p

def ingest_r6_ranked_match(*, discord_id: str, remote_match_id: str, kills: int, deaths: int, win: Optional[bool]) -> dict:
    # store match, update lifetime aggregates, compute awards
    db = SessionLocal()
    try:
        ensure_catalog(db)

        player = _get_or_create_player(db, discord_id)

        # idempotent upsert by remote id
        existing = db.query(R6Match).filter_by(player_id=player.id, remote_match_id=remote_match_id).first()
        if existing:
            return {"status": "ignored", "reason": "duplicate"}

        m = R6Match(
            player_id=player.id,
            remote_match_id=remote_match_id,
            ranked=True,
            kills=max(0, kills),
            deaths=max(0, deaths),
            win=win,
        )
        db.add(m)

        # upsert lifetime aggregate row
        agg = db.query(R6LifetimeAgg).filter_by(player_id=player.id).first()
        if not agg:
            agg = R6LifetimeAgg(player_id=player.id, kills=0, deaths=0, wins=0, losses=0)
            db.add(agg)

        agg.kills += m.kills
        agg.deaths += m.deaths
        if win is True:
            agg.wins += 1
        elif win is False:
            agg.losses += 1

        db.commit()

        unlocked = evaluate_kill_milestones(db, player.id)
        return {"status": "ok", "unlocked": unlocked}
    finally:
        db.close()

def leaderboard_kills(limit: int = 25) -> list[dict]:
    # order by total kills desc
    db = SessionLocal()
    try:
        rows = (
            db.query(Player.display_name, Player.discord_id, R6LifetimeAgg.kills)
            .join(R6LifetimeAgg, R6LifetimeAgg.player_id == Player.id)
            .order_by(R6LifetimeAgg.kills.desc(), Player.display_name.asc())
            .limit(limit)
            .all()
        )
        return [
            {"discord_id": d, "display_name": n or d, "kills": k} for (n, d, k) in rows
        ]
    finally:
        db.close()

def leaderboard_kdr(limit: int = 25) -> list[dict]:
    # compute k/d as kills / max(1, deaths)
    db = SessionLocal()
    try:
        rows = (
            db.query(Player.display_name, Player.discord_id, R6LifetimeAgg.kills, R6LifetimeAgg.deaths)
            .join(R6LifetimeAgg, R6LifetimeAgg.player_id == Player.id)
            .all()
        )
        scored = []
        for n, d, k, de in rows:
            kdr = float(k) / float(de if de and de > 0 else 1.0)
            scored.append({"discord_id": d, "display_name": n or d, "kdr": round(kdr, 3), "kills": k, "deaths": de or 0})
        scored.sort(key=lambda x: (-x["kdr"], -x["kills"], x["display_name"]))
        return scored[:limit]
    finally:
        db.close()

def leaderboard_wlr(limit: int = 25) -> list[dict]:
    # compute w/l as wins / max(1, losses)
    db = SessionLocal()
    try:
        rows = (
            db.query(Player.display_name, Player.discord_id, R6LifetimeAgg.wins, R6LifetimeAgg.losses)
            .join(R6LifetimeAgg, R6LifetimeAgg.player_id == Player.id)
            .all()
        )
        scored = []
        for n, d, w, l in rows:
            wlr = float(w or 0) / float(l if l and l > 0 else 1.0)
            scored.append({"discord_id": d, "display_name": n or d, "wlr": round(wlr, 3), "wins": w or 0, "losses": l or 0})
        scored.sort(key=lambda x: (-x["wlr"], -x["wins"], x["display_name"]))
        return scored[:limit]
    finally:
        db.close()
