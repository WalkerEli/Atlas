from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from atlas_bot.services.award_service import ingest_r6_ranked_match
from atlas_bot.services.leaderboard_service import kills_top, kdr_top, wlr_top

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
