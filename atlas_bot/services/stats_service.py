# r6 stats via r6data.eu with account lookup + clear errors
import requests
from typing import Literal, Optional, Dict, Any

BASE = "https://api.r6data.eu/api/stats"
Platform = Literal["uplay", "psn", "xbl"]
Family = Literal["pc", "console"]

class R6StatsError(Exception):
    pass

def _get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.get(url, params=params, timeout=15)
    if not r.ok:
        raise R6StatsError(f"request failed {r.status_code}: {r.text[:200]}")
    try:
        return r.json()
    except Exception as e:
        raise R6StatsError(f"invalid json: {e}")

def r6_account_info(username: str, platform: Platform) -> Dict[str, Any]:
    """lookup account to verify the username/platform pair exists"""
    data = _get(BASE, {"type": "accountInfo", "nameOnPlatform": username, "platformType": platform})
    if not data or "data" not in data or not data["data"]:
        raise R6StatsError(f"no account found for '{username}' on '{platform}'")
    return data["data"]  # pass through raw account info

def r6_player_stats(username: str, platform: Platform = "uplay", family: Family = "pc") -> Dict[str, Any]:
    """fetch ranked/lifetime stats; raises friendly errors when empty"""
    # verify the account exists first
    _ = r6_account_info(username, platform)

    stats = _get(BASE, {
        "type": "stats",
        "nameOnPlatform": username,
        "platformType": platform,
        "platform_families": family,
    })

    payload = stats.get("data") or {}
    if not payload:
        raise R6StatsError(f"no stats returned for '{username}' on '{platform}' ({family})")

    # normalize core fields (use 0 when keys are missing)
    kills  = int(payload.get("kills", 0))
    deaths = int(payload.get("deaths", 0))
    wins   = int(payload.get("wins", 0))
    losses = int(payload.get("losses", 0))

    return {
        "username": username,
        "platform": platform,
        "family": family,
        "kills": kills,
        "deaths": deaths,
        "wins": wins,
        "losses": losses,
        "matches_played": int(payload.get("matchesPlayed", 0)),
        "time_played": int(payload.get("timePlayed", 0)),
        "kd_ratio": round(kills / (deaths if deaths > 0 else 1), 3),
        "win_loss_ratio": round(wins / (losses if losses > 0 else 1), 3),
        "raw": payload,
    }

def r6_player_stats_try_all_platforms(username: str, family: Family = "pc") -> Dict[str, Any]:
    """helper: try uplay → psn → xbl automatically"""
    last_err: Optional[Exception] = None
    for platform in ("uplay", "psn", "xbl"):
        try:
            return r6_player_stats(username=username, platform=platform, family=family)
        except Exception as e:
            last_err = e
    raise R6StatsError(str(last_err) if last_err else "unknown error")
