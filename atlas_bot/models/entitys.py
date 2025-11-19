from dataclasses import dataclass, field, asdict
from typing import Dict, Optional

@dataclass
class Event:
    id: int
    guild_id: int
    channel_id: int
    title: str
    description: str
    starts_at_iso: str          
    duration_min: int
    location: str
    created_by: int
    message_id: Optional[int] = None
    rsvps: Dict[int, str] = field(default_factory=dict)  

    def to_dict(self) -> dict:
        return asdict(self)
