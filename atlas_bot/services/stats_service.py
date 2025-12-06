# atlas_bot/services/stats_service.py

# simple set of allowed platforms
VALID_PLATFORMS = {"uplay", "pc", "psn", "xbl", "xbox", "ps4"}


def compute_mock_stats(username: str, platform: str = "uplay") -> dict:
    """
    compute fake r6 stats for a given username and platform.
    raises valueerror for invalid input.
    """

    username = username.strip()
    platform = platform.strip().lower()

    if not username:
        raise ValueError("username cannot be empty.")

    if platform not in VALID_PLATFORMS:
        raise ValueError(
            f"invalid platform '{platform}'. use one of: "
            f"{', '.join(sorted(VALID_PLATFORMS))}"
        )

    # simple fake stats (same logic as your fastapi version)
    fake_level = max(1, min(500, len(username) * 10))
    fake_kd = round(0.8 + (len(username) % 5) * 0.15, 2)

    return {
        "found": True,
        "platform": platform,
        "username": username,
        "level": fake_level,
        "kd": fake_kd,
        "raw_status": 200,
        "message": "mock response (no live r6 api available).",
    }
