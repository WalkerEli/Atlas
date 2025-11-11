from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from .db import Base

class Achievement(Base):
    __tablename__ = "achievements"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, index=True)
    name = Column(String)
    description = Column(String)

class Unlock(Base):
    __tablename__ = "achievement_unlocks"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), index=True)
    achievement_code = Column(String, ForeignKey("achievements.code"), index=True)
    awarded_at = Column(DateTime, server_default=func.now())
    __table_args__ = (UniqueConstraint("player_id", "achievement_code", name="uq_player_award_once"),)
