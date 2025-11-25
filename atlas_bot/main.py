import asyncio
import logging
import os
from typing import Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing_extensions import Literal

from atlas_bot.services.award_service import ingest_r6_ranked_match
from atlas_bot.services.leaderboard_service import kills_top, kdr_top, wlr_top
from atlas_bot.services.stats_service import (
    BASE,
    R6StatsError,
    _get,
    r6_player_stats,
    r6_player_stats_try_all_platforms,
)

# ---------------------------------------------------------------------------
# env & logging
# ---------------------------------------------------------------------------

load_dotenv()
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# discord bot setup
# ---------------------------------------------------------------------------

INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.guilds = True
INTENTS.message_content = True  # enables prefix commands later if you add them

# simple commands.Bot instance; we can add commands/cogs later
bot = commands.Bot(command_prefix="!", intents=INTENTS)


@bot.event
async def on_ready():
    print(f"[ready] logged in as {bot.user} (ID: {bot.user.id})")


def get_discord_token() -> str:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Set DISCORD_TOKEN in your .env or environment.")
    print("loaded discord token length:", len(token))
    print("first 10 chars of token:", token[:10])
    return token


# ---------------------------------------------------------------------------
# fastapi app & models
# ---------------------------------------------------------------------------

class R6MatchPayload(BaseModel):
    discord_id: str
    remote_match_id: str
    kills: int
    deaths: int
    win: Optional[bool] = None


app = FastAPI(title="Atlas Discord Bot API")


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
def r6_player(
    username: str,
    platform: str | None = None,
    family: str = "pc",
):
    try:
        if platform:
            try:
                return {
                    "status": "ok",
                    "data": r6_player_stats(username, platform, family),
                }
            except R6StatsError:
                return {
                    "status": "ok",
                    "data": r6_player_stats_try_all_platforms(username, family),
                }
        else:
            return {
                "status": "ok",
                "data": r6_player_stats_try_all_platforms(username, family),
            }
    except R6StatsError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# bot entrypoint (used when you run `python main.py`)
# ---------------------------------------------------------------------------

async def run_bot() -> None:
    token = get_discord_token()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(run_bot())
