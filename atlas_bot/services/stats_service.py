# services/stats_service.py
from __future__ import annotations

import os
from typing import Any, Dict, Literal, Optional

import requests

BASE: str = os.getenv("R6DATA_BASE_URL", "https://api.r6data.eu/api/stats")

Platform = Literal["uplay", "psn", "xbl"]
Family = Literal["pc", "console"]


class R6StatsError(Exception):
    pass


class _HttpClient:
    # small http client wrapper so we can reuse a single session
    def __init__(self, timeout: float = 15.0) -> None:
        # default timeout for outgoing requests
        self._timeout = timeout
        # session is reused for better performance
        self._session = requests.Session()

    def get(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        # send a get request to the stats provider
        try:
            resp = self._session.get(url, params=params, timeout=self._timeout)
        except requests.RequestException as exc:
            # network-level problems (timeouts, dns, connection, etc.)
            raise R6StatsError(f"network error talking to stats provider: {exc}") from exc

        # handle non-2xx responses
        if not resp.ok:
            # keep a short slice of the body for easier debugging
            snippet = resp.text[:200] if resp.text else ""
            raise R6StatsError(f"upstream returned {resp.status_code}: {snippet}")

        # parse json response into a python dict
        try:
            payload: Dict[str, Any] = resp.json()
        except ValueError as exc:
            raise R6StatsError(f"invalid json from stats provider: {exc}") from exc

        return payload


# single shared http client instance for this module
_client = _HttpClient()


def _get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    # wrapper around the shared client so other modules can call http get
    return _client.get(url, params)


def r6_account_info(username: str, platform: Platform) -> Dict[str, Any]:
    # fetch account information and normalize the payload into a single dict
    raw = _get(
        BASE,
        {
            "type": "accountInfo",
            "nameOnPlatform": username,
            "platformType": platform,
        },
    )

    # some providers return a "data" field, others return the payload directly
    payload: Any
    if "data" in raw and raw["data"]:
        payload = raw["data"]
    else:
        payload = raw

    # some providers wrap the payload in a list, so grab the first entry if needed
    if isinstance(payload, list):
        payload = payload[0] if payload else None

    # make sure we ended up with a usable dict
    if not payload or not isinstance(payload, dict):
        raise R6StatsError(f"no account found for '{username}' on '{platform}'")

    return payload


def _extract_season_stats(payload: Dict[str, Any], family: Family) -> Dict[str, Any]:
    # pull the season statistics section for the requested platform family
    platform_families = payload.get("platform_families_full_profiles") or []

    # loop over platform families until we find the matching one (pc or console)
    for pf in platform_families:
        if pf.get("platform_family") != family:
            continue

        # each platform family can have multiple boards (ranked, casual, etc.)
        boards = pf.get("board_ids_full_profiles") or []
        if not boards:
            continue

        # prefer the ranked board when available
        ranked_board = None
        for board in boards:
            if board.get("board_id") == "ranked":
                ranked_board = board
                break

        target_board = ranked_board or boards[0]

        # within a board, stats live inside full profile entries
        full_profiles = target_board.get("full_profiles") or []
        if not full_profiles:
            continue

        # take the first profile and read its season statistics
        stats = full_profiles[0].get("season_statistics") or {}
        if stats:
            return stats

    # return an empty dict if nothing usable was found
    return {}


def _normalize_core_stats(
    username: str,
    platform: Platform,
    family: Family,
    payload: Dict[str, Any],
    include_raw: bool = True,
) -> Dict[str, Any]:
    # convert the raw provider payload into the stat shape used by the bot
    if not payload:
        raise R6StatsError(
            f"no stats returned for '{username}' on '{platform}' (family={family})"
        )

    # some payloads embed stats under nested platform / board / profile structures
    if "platform_families_full_profiles" in payload:
        stats_section = _extract_season_stats(payload, family)
    else:
        stats_section = payload

    if not stats_section:
        raise R6StatsError(
            f"could not extract season statistics for '{username}' on '{platform}'"
        )

    # core kill / death counts
    kills = int(stats_section.get("kills", 0) or 0)
    deaths = int(stats_section.get("deaths", 0) or 0)

    # win / loss / abandon counts are grouped under match outcomes
    match_outcomes = stats_section.get("match_outcomes") or {}
    wins = int(match_outcomes.get("wins", 0) or 0)
    losses = int(match_outcomes.get("losses", 0) or 0)
    abandons = int(match_outcomes.get("abandons", 0) or 0)

    # total matches played is derived from wins, losses, and abandons
    matches_played = wins + losses + abandons

    # time played may or may not be present; default to 0 when missing
    time_played = int(stats_section.get("timePlayed", 0) or 0)

    # compute kd and win/loss ratios with simple zero-protection
    kd_ratio = round(kills / (deaths if deaths > 0 else 1), 3)
    win_loss_ratio = round(wins / (losses if losses > 0 else 1), 3)

    # build normalized stats dict
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

    # optionally include the raw payload for debugging
    if include_raw:
        data["raw"] = payload

    return data


def r6_player_stats(
    username: str,
    platform: Platform = "uplay",
    family: Family = "pc",
) -> Dict[str, Any]:
    # fetch ranked / lifetime stats for a specific username and platform
    # first confirm the account exists so error messages stay clear
    _ = r6_account_info(username, platform)

    # request stats data for the given account and platform family
    raw_stats = _get(
        BASE,
        {
            "type": "stats",
            "nameOnPlatform": username,
            "platformType": platform,
            "platform_families": family,
        },
    )

    # handle both direct and "data" wrapped responses
    if "data" in raw_stats and raw_stats["data"]:
        payload = raw_stats["data"]
    else:
        payload = raw_stats

    # some providers return a list; grab the first element if so
    if isinstance(payload, list):
        payload = payload[0] if payload else {}

    # normalize into the structure the rest of the bot expects
    return _normalize_core_stats(username, platform, family, payload)


def r6_player_stats_try_all_platforms(
    username: str,
    family: Family = "pc",
) -> Dict[str, Any]:
    # try looking up stats on each platform in turn until one succeeds
    last_err: Optional[R6StatsError] = None

    for platform in ("uplay", "psn", "xbl"):
        try:
            # literal narrowing is safe here even though mypy complains
            return r6_player_stats(
                username=username,
                platform=platform,  # type: ignore[arg-type]
                family=family,
            )
        except R6StatsError as exc:
            # remember the last error so we can report it if all platforms fail
            last_err = exc

    # if we get here, all platform attempts failed
    raise R6StatsError(
        str(last_err) if last_err else "unknown error while fetching stats"
    )
