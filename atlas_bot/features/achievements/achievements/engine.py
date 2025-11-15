from sqlalchemy.orm import Session
from .rules import R6_KILL_MILESTONES, R6_WINRATE_MILESTONES
from atlas_bot.models.achievment import Achievement, Unlock
from atlas_bot.models.match import R6LifetimeAgg

# Register achievements in the database 
def ensure_catalog(db: Session) -> None:
    all_milestones = R6_KILL_MILESTONES + R6_WINRATE_MILESTONES

    for m in all_milestones:
        exists = db.query(Achievement).filter_by(code=m.code).first()
        if not exists:
            db.add(Achievement(
                code=m.code,
                name=m.name,
                description=m.description
            ))

    db.commit()

# Evaluate Kill Milestones
def evaluate_kill_milestones(db: Session, player_id: int) -> list[str]:
    agg = db.query(R6LifetimeAgg).filter_by(player_id=player_id).first()
    if not agg:
        return []

    unlocked = []

    for m in R6_KILL_MILESTONES:
        already = db.query(Unlock).filter_by(
            player_id=player_id,
            achievement_code=m.code
        ).first()

        if not already and agg.kills >= m.threshold:
            db.add(Unlock(player_id=player_id, achievement_code=m.code))
            unlocked.append(m.code)

    if unlocked:
        db.commit()

    return unlocked

# Evaluate Win Rate Milestones 

def evaluate_winrate_milestones(db: Session, player_id: int) -> list[str]:
    agg = db.query(R6LifetimeAgg).filter_by(player_id=player_id).first()
    if not agg:
        return []

    total_games = agg.wins + agg.losses
    if total_games == 0:
        return []  # No matches played

    winrate = agg.wins / total_games
    unlocked = []

    for m in R6_WINRATE_MILESTONES:
        already = db.query(Unlock).filter_by(
            player_id=player_id,
            achievement_code=m.code
        ).first()

        if not already and (m.min_rate <= winrate <= m.max_rate):
            db.add(Unlock(player_id=player_id, achievement_code=m.code))
            unlocked.append(m.code)

    if unlocked:
        db.commit()

    return unlocked


# Combined evaluation (call this after stats update)
def evaluate_all_achievements(db: Session, player_id: int) -> list[str]:
    new_kills = evaluate_kill_milestones(db, player_id)
    new_winrates = evaluate_winrate_milestones(db, player_id)
    return new_kills + new_winrates
