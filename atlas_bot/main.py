from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from typing_extensions import Literal 
from atlas_bot.services.award_service import ingest_r6_ranked_match
from atlas_bot.services.leaderboard_service import kills_top, kdr_top, wlr_top
from atlas_bot.services.stats_service import BASE, R6StatsError, _get, r6_player_stats, r6_player_stats_try_all_platforms

app = FastAPI(title="Atlas Discord Bot API")

class R6MatchPayload(BaseModel):
    discord_id: str
    remote_match_id: str
    kills: int
    deaths: int
    win: Optional[bool] = None

@app.post("/webhooks/r6/ranked")
def r6_ranked_match(payload: R6MatchPayload):
    return ingest_r6_ranked_match(
        discord_id=payload.discord_id,
        remote_match_id=payload.remote_match_id,
        kills=payload.kills,
        deaths=payload.deaths,
        win=payload.win,
    )

@app.get("/leaderboards/r6/kills")
def lb_kills(limit: int = 25):
    return {"metric": "kills_lifetime", "rows": kills_top(limit)}

@app.get("/leaderboards/r6/kdr")
def lb_kdr(limit: int = 25):
    return {"metric": "kdr_lifetime", "rows": kdr_top(limit)}

@app.get("/leaderboards/r6/wlr")
def lb_wlr(limit: int = 25):
    return {"metric": "wlr_lifetime", "rows": wlr_top(limit)}

@app.get("/r6/player")
def r6_player(username: str,
              platform: str | None = None,
              family: str = "pc"):
    try:
        if platform:
            try:
                return {"status": "ok", "data": r6_player_stats(username, platform, family)}
            except R6StatsError:
                # fallback if explicit platform misses
                return {"status": "ok", "data": r6_player_stats_try_all_platforms(username, family)}
        else:
            return {"status": "ok", "data": r6_player_stats_try_all_platforms(username, family)}
    except R6StatsError as e:
        # 404 is clearer than 200 with zeros
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/r6/debug/account")
def debug_account(username: str, platform: Literal["uplay","psn","xbl"]):
    # shows the raw accountInfo payload the upstream returns
    return _get(f"{BASE}", {"type": "accountInfo", "nameOnPlatform": username, "platformType": platform})

@app.get("/r6/debug/stats")
def debug_stats(username: str,
                platform: Literal["uplay","psn","xbl"] = Query("uplay"),
                family: Literal["pc","console"] = Query("pc")):
    # bypasses our normalization and shows raw stats payload
    return _get(f"{BASE}", {"type": "stats", "nameOnPlatform": username,
                            "platformType": platform, "platform_families": family})