from __future__ import annotations
from typing import Dict

# simple set of allowed platforms
VALID_PLATFORMS = {"uplay", "pc", "psn", "xbl", "xbox", "ps4"}

# map aliases to canonical r6 platforms
_PLATFORM_ALIASES = {
    "pc": "uplay",
    "xbox": "xbl",
    "ps4": "psn",
}


def _normalize_platform(platform: str) -> str:
    """normalize incoming platform names to canonical values for mock stats."""
    p = platform.strip().lower()
    if not p:
        raise ValueError("platform cannot be empty")

    if p not in VALID_PLATFORMS:
        raise ValueError(f"unsupported platform: {platform!r}")

    return _PLATFORM_ALIASES.get(p, p)


def compute_mock_stats(username: str, platform: str = "uplay") -> Dict[str, object]:
    username = username.strip()
    if not username:
        raise ValueError("username cannot be empty")

    platform = _normalize_platform(platform)

    name_len = len(username)

    # simple fake stats (same logic style as your fastapi version)
    fake_level = max(1, min(500, name_len * 10))
    fake_kd = round(0.8 + (name_len % 5) * 0.15, 2)

    # deterministic "matches played"
    matches = 50 + name_len * 5

    # base win rate between ~40% and ~70%, based on the username length
    base_wr = 0.40 + (name_len % 7) * 0.05  # 0.40, 0.45, ..., 0.70
    win_rate = max(0.30, min(base_wr, 0.80))  # clamp to [0.30, 0.80]

    wins = int(matches * win_rate)
    losses = max(0, matches - wins)

    win_rate_pct = int(round(win_rate * 100))

    return {
        "found": True,
        "platform": platform,
        "username": username,
        "level": fake_level,
        "kd": fake_kd,
        "matches": matches,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 3),      # 0.000–1.000
        "win_rate_pct": win_rate_pct,        # 0–100
        "raw_status": 200,
    }
