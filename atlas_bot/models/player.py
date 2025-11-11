from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from .db import Base

class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True)
    discord_id = Column(String, unique=True, index=True)  
    display_name = Column(String, nullable=True)
    campus = Column(String, nullable=True)
    joined_at = Column(DateTime, server_default=func.now())
