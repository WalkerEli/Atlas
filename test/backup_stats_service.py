# services/backup_stats_service.py
from __future__ import annotations

import os
from typing import Any, Dict, Literal, Optional

from r6statsapi import Client, Platform as R6Platform
from r6statsapi.errors import R6StatsApiException, Unauthorized, InternalError

Platform = Literal["uplay", "psn", "xbl"]
Family = Literal["pc", "console"]


class R6StatsError(Exception):
    """Domain error type exposed to the rest of the bot."""
    pass


# --------------------------------------------------------------------------- #
# R6Stats API client bootstrap
# --------------------------------------------------------------------------- #

_API_TOKEN: Optional[str] = os.getenv("R6STATS_API_TOKEN")

_client: Optional[Client] = None


def _get_client() -> Client:
    """Create (or return) a singleton R6Stats API client."""
    global _client

    if _client is not None:
        return _client

    if not _API_TOKEN:
        raise R6StatsError(
            "R6STATS_API_TOKEN is not set; cannot talk to R6Stats API."
        )

    # r6statsapi.Client(token, loop=None)
    _client = Client(token=_API_TOKEN)
    return _client


def _map_platform(platform: Platform) -> R6Platform:
    """
    Map your string literal platform to the r6statsapi Platform enum.
    r6statsapi.Platform has: uplay, psn, xbox. :contentReference[oaicite:3]{index=3}
    """
    if platform == "uplay":
        return R6Platform.uplay
    if platform == "psn":
        return R6Platform.psn
    if platform == "xbl":
        return R6Platform.xbox

    # Fallback, should not happen if callers validate
    raise R6StatsError(f"Unsupported platform: {platform}")


def _family_for_platform(platform: Platform) -> Family:
    """Best-effort mapping into 'pc' / 'console' family."""
    return "pc" if platform == "uplay" else "console"


# --------------------------------------------------------------------------- #
# Normalization helpers
# --------------------------------------------------------------------------- #

def _select_ranked_queue(queue_obj: Any) -> Dict[str, Any]:
    """
    R6Stats queue model has attributes like .ranked, .casual, .other. :contentReference[oaicite:4]{index=4}
    We prefer ranked stats; if missing, fall back to casual, then other.
    """
    ranked = getattr(queue_obj, "ranked", None) or {}
    casual = getattr(queue_obj, "casual", None) or {}
    other = getattr(queue_obj, "other", None) or {}

    if ranked:
        return dict(ranked)
    if casual:
        return dict(casual)
    if other:
        return dict(other)

    return {}


def _normalize_core_stats_from_queue(
    username: str,
    platform: Platform,
    family: Family,
    queue_obj: Any,
    include_raw: bool = True,
) -> Dict[str, Any]:
    """
    Convert the R6Stats 'Queue' model into the normalized stats dict used by the bot.
    We are defensive about field names because different wrappers/services use
    slightly different keys (snake_case vs camelCase, etc.). :contentReference[oaicite:5]{index=5}
    """
    if not queue_obj:
        raise R6StatsError(
            f"no stats returned for '{username}' on '{platform}' (family={family})"
        )

    stats_section = _select_ranked_queue(queue_obj)
    if not stats_section:
        raise R6StatsError(
            f"could not extract queue (ranked/casual) stats for '{username}' on '{platform}'"
        )

    # Accept several possible key variants from different upstreams
    def _iget(d: Dict[str, Any], *keys: str) -> int:
        for k in keys:
            if k in d and d[k] is not None:
                try:
                    return int(d[k])
                except (TypeError, ValueError):
                    continue
        return 0

    kills = _iget(stats_section, "kills")
    deaths = _iget(stats_section, "deaths")

    wins = _iget(stats_section, "wins", "won")
    losses = _iget(stats_section, "losses", "lost")
    abandons = _iget(stats_section, "abandons", "abandons_count", "abandons_total")

    # matches: prefer explicit matches/matches_played, fallback to wins+losses+abandons
    matches_played = _iget(stats_section, "matches_played", "matches")
    if matches_played == 0:
        matches_played = wins + losses + abandons

    # time played: accept multiple naming conventions
    time_played = _iget(stats_section, "time_played", "timePlayed", "time")

    # compute ratios with zero protection
    kd_ratio = round(kills / (deaths if deaths > 0 else 1), 3)
    win_loss_ratio = round(wins / (losses if losses > 0 else 1), 3)

    data: Dict[str, Any] = {
        "username": username,
        "platform": platform,
        "family": family,
        "kills": kills,
        "deaths": deaths,
        "wins": wins,
        "losses": losses,
        "matches_played": matches_played,
        "time_played": time_played,
        "kd_ratio": kd_ratio,
        "win_loss_ratio": win_loss_ratio,
    }

    if include_raw:
        # Convert whole queue object to a plain dict, if possible
        try:
            data["raw"] = {
                "casual": dict(getattr(queue_obj, "casual", {}) or {}),
                "ranked": dict(getattr(queue_obj, "ranked", {}) or {}),
                "other": dict(getattr(queue_obj, "other", {}) or {}),
            }
        except Exception:
            data["raw"] = None

    return data


# --------------------------------------------------------------------------- #
# Public API (async)
# --------------------------------------------------------------------------- #

async def r6_player_stats(
    username: str,
    platform: Platform = "uplay",
    family: Family = "pc",
) -> Dict[str, Any]:
    """
    Fetch ranked/lifetime stats for a specific username and platform using R6Stats.

    NOTE: This is async (unlike your original stats_service).
    """
    client = _get_client()

    # Map to R6Stats platform enum
    plat_enum = _map_platform(platform)

    try:
        # We use "queue" stats (ranked/casual/other) as a proxy for seasonal/ranked
        queue = await client.get_queue_stats(player=username, platform=plat_enum)
    except Unauthorized as exc:
        raise R6StatsError(
            "R6Stats API says the token is invalid or missing. "
            "Check R6STATS_API_TOKEN."
        ) from exc
    except InternalError as exc:
        raise R6StatsError("R6Stats API encountered an internal error.") from exc
    except R6StatsApiException as exc:
        # generic wrapper error
        raise R6StatsError(f"R6Stats API error: {exc}") from exc
    except Exception as exc:
        # network or unexpected failures
        raise R6StatsError(f"Unexpected error talking to R6Stats API: {exc}") from exc

    # family is inferred from platform if caller passed something weird
    normalized_family: Family = family if family in ("pc", "console") else _family_for_platform(platform)

    return _normalize_core_stats_from_queue(
        username=username,
        platform=platform,
        family=normalized_family,
        queue_obj=queue,
    )


async def r6_player_stats_try_all_platforms(
    username: str,
    family: Family = "pc",
) -> Dict[str, Any]:
    """
    Try looking up stats on each platform in turn until one succeeds, using R6Stats.

    Platform order is the same as your original helper: uplay -> psn -> xbl.
    """
    last_err: Optional[R6StatsError] = None

    for platform in ("uplay", "psn", "xbl"):
        try:
            # type narrowing is safe here
            stats = await r6_player_stats(
                username=username,
                platform=platform,  # type: ignore[arg-type]
                family=family,
            )
            return stats
        except R6StatsError as exc:
            last_err = exc
            continue

    raise R6StatsError(
        str(last_err) if last_err else "unknown error while fetching stats via R6Stats"
    )
