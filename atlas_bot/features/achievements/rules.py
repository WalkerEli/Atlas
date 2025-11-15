from dataclasses import dataclass

# Kill Milestone Dataclass
@dataclass(frozen=True)
class KillMilestone:
    code: str
    name: str
    threshold: int
    description: str


# Each KillMilestone below is one achievement the player can earn.
R6_KILL_MILESTONES = [
    KillMilestone(
        code="kill_100",
        name="Rookie Shooter",
        description="Reach 100 lifetime kills.",
        threshold=100
    ),
    KillMilestone(
        code="kill_500",
        name="Sharpshooter",
        description="Reach 500 lifetime kills.",
        threshold=500
    ),
    KillMilestone(
        code="kill_1000",
        name="Veteran Operator",
        description="Reach 1000 lifetime kills.",
        threshold=1000
    ),
    KillMilestone(
        code="kill_5000",
        name="Elite Assassin",
        description="Reach 5000 lifetime kills.",
        threshold=5000
    ),
]



# Win Rate Rank Dataclass
@dataclass(frozen=True)
class WinRateMilestone:
    code: str
    name: str
    min_rate: float
    max_rate: float
    description: str


# Each WinRateMilestone below assigns the player a rank based on win rate.
R6_WINRATE_MILESTONES = [
    WinRateMilestone(
        code="wr_master",
        name="Master Rank",
        min_rate=0.85,
        max_rate=1.00,
        description="Maintain an 85–100% win rate."
    ),
    WinRateMilestone(
        code="wr_diamond",
        name="Diamond Rank",
        min_rate=0.70,
        max_rate=0.8499,
        description="Maintain a 70–84% win rate."
    ),
    WinRateMilestone(
        code="wr_gold",
        name="Gold Rank",
        min_rate=0.55,
        max_rate=0.6999,
        description="Maintain a 55–69% win rate."
    ),
    WinRateMilestone(
        code="wr_silver",
        name="Silver Rank",
        min_rate=0.40,
        max_rate=0.5499,
        description="Maintain a 40–54% win rate."
    ),
    WinRateMilestone(
        code="wr_bronze",
        name="Bronze Rank",
        min_rate=0.00,
        max_rate=0.3999,
        description="Maintain a 0–39% win rate."
    ),
]

