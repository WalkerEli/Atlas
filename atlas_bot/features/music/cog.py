from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
import discord
from discord.ext import commands
from .player import get_audio_stream

logger = logging.getLogger(__name__)

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


@dataclass
class Track:
    """represents a single track in the queue."""
    title: str
    stream_url: str
    requester_id: int
    original_query: str


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # per-guild queue and current track
        self.queues: Dict[int, List[Track]] = {}
        self.current: Dict[int, Optional[Track]] = {}

    async def cog_load(self) -> None:
        logger.info("MusicCog ready; prefix music commands registered.")

    # ------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------

    def _get_queue(self, guild_id: int) -> List[Track]:
        """get or create the queue list for a guild."""
        return self.queues.setdefault(guild_id, [])

    async def _ensure_voice(
        self,
        ctx: commands.Context,
    ) -> Optional[discord.VoiceClient]:
        """make sure the bot is in the same voice channel as the user."""
        if ctx.guild is None:
            await ctx.send("this command only works inside a server.")
            return None

        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await ctx.send("you need to be in a voice channel first.")
            return None

        channel = ctx.author.voice.channel

        if ctx.voice_client is None:
            try:
                vc = await channel.connect()
            except discord.ClientException:
                vc = ctx.voice_client
        else:
            vc = ctx.voice_client
            if vc.channel != channel:
                await vc.move_to(channel)

        return vc

    async def _play_next(
        self,
        guild_id: int,
        text_channel_id: Optional[int],
    ) -> None:
        """
        pop the next track from the queue and play it, if any.
        this is called both after a track ends and when we want to start fresh.
        """
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return

        vc = guild.voice_client
        if vc is None or not vc.is_connected():
            self.current[guild_id] = None
            return

        queue = self._get_queue(guild_id)
        if not queue:
            # nothing left to play
            self.current[guild_id] = None

            # optional: announce queue finished
            channel = None
            if text_channel_id is not None:
                channel = self.bot.get_channel(text_channel_id)

            if channel is None:
                channel = guild.system_channel or (guild.text_channels[0] if guild.text_channels else None)

            if isinstance(channel, discord.abc.Messageable):
                await channel.send("queue finished.")
            return

        track = queue.pop(0)
        self.current[guild_id] = track

        source = discord.FFmpegPCMAudio(track.stream_url, **FFMPEG_OPTIONS)

        def _after(error: Optional[BaseException]) -> None:
            if error:
                logger.error("error in ffmpeg playback: %s", error)

            async def runner() -> None:
                await self._play_next(guild_id, text_channel_id)

            self.bot.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(runner())
            )

        vc.play(source, after=_after)

        channel = None
        if text_channel_id is not None:
            channel = self.bot.get_channel(text_channel_id)
        if channel is None:
            channel = guild.system_channel or (guild.text_channels[0] if guild.text_channels else None)

        if isinstance(channel, discord.abc.Messageable):
            asyncio.run_coroutine_threadsafe(
                channel.send(f"now playing: **{track.title}**"),
                self.bot.loop,
            )

    # commands

    @commands.command(name="join")
    async def join(self, ctx: commands.Context) -> None:
        """join the voice channel the author is currently in."""
        vc = await self._ensure_voice(ctx)
        if vc is not None:
            await ctx.send(f"joined **{vc.channel}**.")

    @commands.command(name="leave")
    async def leave(self, ctx: commands.Context) -> None:
        """disconnect from the voice channel and clear the queue."""
        if ctx.guild is None:
            await ctx.send("this command only works inside a server.")
            return

        vc = ctx.voice_client
        if vc is None or not vc.is_connected():
            await ctx.send("i'm not in a voice channel.")
            return

        self._get_queue(ctx.guild.id).clear()
        self.current[ctx.guild.id] = None

        await vc.disconnect()
        await ctx.send("left the voice channel and cleared the queue.")

    @commands.command(name="play")
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        """
        play a song immediately if the bot is idle.

        if something is already playing, tell the user to use !queue instead.
        """
        if ctx.guild is None:
            await ctx.send("this command only works inside a server.")
            return

        vc = await self._ensure_voice(ctx)
        if vc is None:
            return

        if vc.is_playing() or vc.is_paused():
            await ctx.send("i'm already playing something. use `!queue` to add songs.")
            return

        await ctx.send(f"loading: `{query}` ...")

        try:
            stream_url, title = await get_audio_stream(query)
        except Exception as exc:
            logger.exception("yt-dlp error while processing %r", query, exc_info=exc)
            await ctx.send("i couldn't get audio from that url or search. try another one.")
            return

        # reset current and queue for a clean start
        guild_id = ctx.guild.id
        self.current[guild_id] = None
        # do not clear queue here; existing queue will play after this track

        # put this track at the front of the queue and start playback
        track = Track(
            title=title,
            stream_url=stream_url,
            requester_id=ctx.author.id,
            original_query=query,
        )

        queue = self._get_queue(guild_id)
        queue.insert(0, track)

        await self._play_next(guild_id, ctx.channel.id)

    @commands.command(name="queue")
    async def queue_cmd(self, ctx: commands.Context, *, query: str) -> None:
        """
        add a song to the guild queue.

        if nothing is currently playing and the queue is empty,
        this will start playback immediately.
        """
        if ctx.guild is None:
            await ctx.send("this command only works inside a server.")
            return

        vc = await self._ensure_voice(ctx)
        if vc is None:
            return

        await ctx.send(f"adding to queue: `{query}` ...")

        try:
            stream_url, title = await get_audio_stream(query)
        except Exception as exc:
            logger.exception("yt-dlp error while processing %r", query, exc_info=exc)
            await ctx.send("i couldn't get audio from that url or search. try another one.")
            return

        guild_id = ctx.guild.id
        queue = self._get_queue(guild_id)

        track = Track(
            title=title,
            stream_url=stream_url,
            requester_id=ctx.author.id,
            original_query=query,
        )

        vc_busy = vc.is_playing() or vc.is_paused()

        # if nothing is playing and queue is empty, start immediately
        if not vc_busy and self.current.get(guild_id) is None and not queue:
            queue.append(track)
            await ctx.send(f"starting queue with: **{title}**")
            await self._play_next(guild_id, ctx.channel.id)
        else:
            queue.append(track)
            await ctx.send(
                f"queued: **{title}** (position {len(queue)})"
            )

    @commands.command(name="skip")
    async def skip(self, ctx: commands.Context) -> None:
        """skip the current track and play the next one in the queue."""
        if ctx.guild is None:
            await ctx.send("this command only works inside a server.")
            return

        vc = ctx.voice_client
        if vc is None or not vc.is_connected():
            await ctx.send("i'm not connected to a voice channel.")
            return

        if not vc.is_playing():
            await ctx.send("nothing is playing right now.")
            return

        await ctx.send("skipping current track...")
        vc.stop()  # triggers _play_next via the after callback

    @commands.command(name="replay")
    async def replay(self, ctx: commands.Context) -> None:
        """replay the current track by putting it at the front of the queue."""
        if ctx.guild is None:
            await ctx.send("this command only works inside a server.")
            return

        guild_id = ctx.guild.id
        track = self.current.get(guild_id)

        if track is None:
            await ctx.send("there is no track to replay yet.")
            return

        vc = ctx.voice_client
        if vc is None or not vc.is_connected():
            await ctx.send("i'm not connected to a voice channel.")
            return

        # put the current track at the front of the queue and stop;
        # _play_next will pick it up and start it again.
        queue = self._get_queue(guild_id)
        queue.insert(0, track)

        await ctx.send(f"replaying: **{track.title}**")
        vc.stop()
