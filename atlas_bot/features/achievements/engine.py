from sqlalchemy.orm import Session
from .rules import R6_KILL_MILESTONES
from atlas_bot.models.achievment import Achievement, Unlock
from atlas_bot.models.match import R6LifetimeAgg

def ensure_catalog(db: Session) -> None:
    # create catalog rows if missing
    for m in R6_KILL_MILESTONES:
        if not db.query(Achievement).filter_by(code=m.code).first():
            db.add(Achievement(code=m.code, name=m.name, description=m.description))
    db.commit()

def evaluate_kill_milestones(db: Session, player_id: int) -> list[str]:
    # check current lifetime kills and award missing milestones
    agg = db.query(R6LifetimeAgg).filter_by(player_id=player_id).first()
    if not agg:
        return []
    unlocked = []
    for m in R6_KILL_MILESTONES:
        has = db.query(Unlock).filter_by(player_id=player_id, achievement_code=m.code).first()
        if not has and agg.kills >= m.threshold:
            db.add(Unlock(player_id=player_id, achievement_code=m.code))
            unlocked.append(m.code)
    if unlocked:
        db.commit()
    return unlocked
