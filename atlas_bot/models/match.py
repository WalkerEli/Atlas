from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .db import Base

class R6Match(Base):
    __tablename__ = "r6_matches"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), index=True)
    remote_match_id = Column(String, index=True)  # id from stat tracker
    finished_at = Column(DateTime, default=func.now(), index=True)
    ranked = Column(Boolean, default=True)
    kills = Column(Integer, default=0)
    deaths = Column(Integer, default=0)
    win = Column(Boolean, default=None)

    __table_args__ = (UniqueConstraint("player_id", "remote_match_id", name="uq_r6_match_remote"),)

    player = relationship("Player", backref="r6_matches")


class R6LifetimeAgg(Base):
    __tablename__ = "r6_lifetime_agg"
    # one row per player for ranked lifetime
    player_id = Column(Integer, ForeignKey("players.id"), primary_key=True)
    # totals
    kills = Column(Integer, default=0)
    deaths = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    
Index("ix_r6agg_kills", R6LifetimeAgg.kills)
Index("ix_r6agg_deaths", R6LifetimeAgg.deaths)
Index("ix_r6agg_wins", R6LifetimeAgg.wins)
Index("ix_r6agg_losses", R6LifetimeAgg.losses)