import asyncio
import logging
import os
import discord
import discord.ext.commands as commands
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from typing_extensions import Literal 
from atlas_bot.services.award_service import ingest_r6_ranked_match
from atlas_bot.services.leaderboard_service import kills_top, kdr_top, wlr_top
from atlas_bot.services.stats_service import BASE, R6StatsError, _get, r6_player_stats, r6_player_stats_try_all_platforms

logging.basicConfig(level=logging.INFO)  
INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.guilds = True
INTENTS.message_content = False

DEV_GUILD_ID = "placeholder" # Replace this with the Guild-ID as an integer

class AtlasBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)

    async def setup_hook(self):
        await self.load_extension("events")
        try:
            await self.tree.sync(guild=discord.Object(id=DEV_GUILD_ID))
            print(f"[setup] Slash commands synced to guild {DEV_GUILD_ID}")
        except discord.Forbidden:
            await self.tree.sync()
            print("[setup] Guild sync forbidden; synced globally (may take a minute).")
            
class R6MatchPayload(BaseModel):
    discord_id: str
    remote_match_id: str
    kills: int
    deaths: int
    win: Optional[bool] = None

bot = AtlasBot()
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
def r6_player(username: str,
              platform: str | None = None,
              family: str = "pc"):
    try:
        if platform:
            try:
                return {"status": "ok", "data": r6_player_stats(username, platform, family)}
            except R6StatsError:
                return {"status": "ok", "data": r6_player_stats_try_all_platforms(username, family)}
        else:
            return {"status": "ok", "data": r6_player_stats_try_all_platforms(username, family)}
    except R6StatsError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
@bot.event
async def on_ready():
    print(f"[ready] Logged in as {bot.user} (ID: {bot.user.id})")

async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Set DISCORD_TOKEN environment variable.")
    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
