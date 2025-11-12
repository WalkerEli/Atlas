from dataclasses import dataclass

@dataclass(frozen=True)
class KillMilestone:
    code: str
    name: str
    threshold: int
    description: str

R6_KILL_MILESTONES = [
    KillMilestone(code="R6_KILLS_1000",  name="Rookie",   threshold=1000,  description="reach 1,000 ranked kills"),
    KillMilestone(code="R6_KILLS_5000",  name="Amateur",  threshold=5000,  description="reach 5,000 ranked kills"),
    KillMilestone(code="R6_KILLS_10000", name="Veteran",  threshold=10000, description="reach 10,000 ranked kills"),
]
