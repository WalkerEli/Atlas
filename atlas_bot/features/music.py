import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional

import discord
import yt_dlp
from discord.ext import commands

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# yt-dlp / ffmpeg configuration
# ---------------------------------------------------------------------------

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "extractaudio": True,
    "audioformat": "mp3",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


@dataclass
class Track:
    """
    Represents a queued track.
    """

    url: str
    title: str
    requester: discord.Member
    duration: Optional[int] = None
    thumbnail: Optional[str] = None


class MusicQueue:
    """
    Per-guild queue with history and looping options.
    """

    def __init__(self) -> None:
        self.queue: Deque[Track] = deque()
        self.history: List[Track] = []
        self.current: Optional[Track] = None
        self.loop_song: bool = False
        self.loop_queue: bool = False

    def add(self, track: Track) -> None:
        self.queue.append(track)

    def extend(self, tracks: List[Track]) -> None:
        self.queue.extend(tracks)

    def next(self) -> Optional[Track]:
        if self.loop_song and self.current:
            return self.current

        if self.queue:
            if self.current:
                self.history.append(self.current)
            self.current = self.queue.popleft()

            if self.loop_queue and self.current:
                self.queue.append(self.current)

            return self.current

        return None

    def shuffle(self) -> None:
        items = list(self.queue)
        import random

        random.shuffle(items)
        self.queue = deque(items)

    def clear(self) -> None:
        self.queue.clear()
        self.history.clear()
        self.current = None

    def remove_at(self, index: int) -> Optional[Track]:
        if 0 <= index < len(self.queue):
            items = list(self.queue)
            removed = items.pop(index)
            self.queue = deque(items)
            return removed
        return None

    def as_list(self) -> List[Track]:
        return list(self.queue)


class YTDLSource(discord.PCMVolumeTransformer):
    """
    PCMVolumeTransformer wrapping an FFmpegOpusAudio source with metadata.
    """

    def __init__(
        self,
        source: discord.AudioSource,
        *,
        data: dict,
        volume: float = 0.5,
    ) -> None:
        super().__init__(source, volume)
        self.data = data
        self.title: str = data.get("title")
        self.url: str = data.get("url")
        self.duration: Optional[int] = data.get("duration")
        self.thumbnail: Optional[str] = data.get("thumbnail")
        self.requester: Optional[discord.Member] = data.get("requester")

    @classmethod
    async def from_url(
        cls,
        url: str,
        *,
        loop: asyncio.AbstractEventLoop,
        stream: bool,
        requester: discord.Member,
    ) -> "YTDLSource":
        """
        Download/stream audio for a single track and return a playable source.
        """
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=not stream)
        )

        if "entries" in data:
            # When given a playlist or search result, take the first entry.
            data = data["entries"][0]

        data["requester"] = requester
        filename = data["url"] if stream else ytdl.prepare_filename(data)

        source = await discord.FFmpegOpusAudio.from_probe(
            filename, **FFMPEG_OPTIONS
        )
        return cls(source, data=data)


class MusicPlayer:
    """
    Long-lived per-guild music player that consumes a MusicQueue
    and feeds the guild's voice client.
    """

    def __init__(
        self,
        bot: commands.Bot,
        guild: discord.Guild,
        text_channel: discord.abc.MessageableChannel,
    ) -> None:
        self.bot = bot
        self.guild = guild
        self.text_channel = text_channel
        self.queue = MusicQueue()
        self.next_event: asyncio.Event = asyncio.Event()
        self.volume: float = 0.5
        self._task: asyncio.Task[None] = bot.loop.create_task(self._loop())

    async def _loop(self) -> None:
        """
        Main playback loop: waits for tracks in the queue and plays them.
        """
        await self.bot.wait_until_ready()

        while True:
            self.next_event.clear()
            track = self.queue.next()

            if track is None:
                # Idle for a while; disconnect if still unused.
                try:
                    await asyncio.sleep(180)
                    vc = self.guild.voice_client
                    if vc and not vc.is_playing():
                        await vc.disconnect()
                        return
                except Exception as exc:
                    log.warning(
                        "Error during idle disconnect for guild %s: %s",
                        self.guild.id,
                        exc,
                    )
                continue

            vc = self.guild.voice_client
            if not vc or not vc.is_connected():
                log.info(
                    "No voice client for guild %s; skipping track '%s'",
                    self.guild.id,
                    track.title,
                )
                continue

            try:
                source = await YTDLSource.from_url(
                    track.url,
                    loop=self.bot.loop,
                    stream=True,
                    requester=track.requester,
                )
                source.volume = self.volume

                def _after(error: Optional[Exception]) -> None:
                    # Called by discord.py in a different thread
                    if error:
                        log.warning("Playback error: %s", error)
                    self.bot.loop.call_soon_threadsafe(self.next_event.set)

                vc.play(source, after=_after)

                embed = discord.Embed(
                    title="🎵 Now Playing",
                    description=f"**{source.title}**",
                    color=discord.Color.blue(),
                )
                if source.thumbnail:
                    embed.set_thumbnail(url=source.thumbnail)
                if track.requester:
                    embed.add_field(
                        name="Requested by",
                        value=track.requester.mention,
                        inline=False,
                    )
                if source.duration:
                    minutes, seconds = divmod(source.duration, 60)
                    embed.add_field(
                        name="Duration",
                        value=f"{int(minutes)}:{int(seconds):02d}",
                        inline=True,
                    )

                await self.text_channel.send(embed=embed)
            except Exception as exc:
                log.exception("Error while playing track: %s", exc)
                try:
                    await self.text_channel.send(
                        f"❌ Error playing song: {exc}"
                    )
                except Exception:
                    pass

            # Wait for the track to finish or be skipped.
            await self.next_event.wait()

    def stop(self) -> None:
        """
        Stop the loop task when tearing down the player.
        """
        if not self._task.done():
            self._task.cancel()


class MusicCog(commands.Cog):
    """
    Cog exposing music commands for the shared MasterBot instance.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.players: Dict[int, MusicPlayer] = {}

    # ------------------------------------------------------------------ helpers

    def get_player(self, ctx: commands.Context) -> MusicPlayer:
        assert ctx.guild is not None

        player = self.players.get(ctx.guild.id)
        if player is None:
            player = MusicPlayer(
                self.bot, ctx.guild, ctx.channel  # type: ignore[arg-type]
            )
            self.players[ctx.guild.id] = player
        else:
            # Keep text channel updated to the last command location
            player.text_channel = ctx.channel  # type: ignore[assignment]

        return player

    async def ensure_voice(self, ctx: commands.Context) -> bool:
        """
        Ensure the bot is in the caller's voice channel.
        Returns True on success, False if preconditions failed.
        """
        if not isinstance(ctx.author, discord.Member):
            await ctx.send("❌ Voice commands can only be used in guilds.")
            return False

        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(
                "❌ You need to be in a voice channel to use this command!"
            )
            return False

        voice = ctx.voice_client
        channel = ctx.author.voice.channel

        if voice:
            if voice.channel != channel:
                await voice.move_to(channel)
        else:
            await channel.connect()

        return True

    # ------------------------------------------------------------------ events

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        log.info("MusicCog is ready.")

    # ------------------------------------------------------------------ commands

    @commands.hybrid_command(
        name="join",
        help="Join your current voice channel.",
        aliases=["connect"],
    )
    async def join(self, ctx: commands.Context) -> None:
        if await self.ensure_voice(ctx):
            assert ctx.author.voice is not None
            await ctx.send(f"✅ Joined {ctx.author.voice.channel.name}!")

    @commands.hybrid_command(
        name="leave",
        help="Leave the voice channel.",
        aliases=["disconnect", "dc"],
    )
    async def leave(self, ctx: commands.Context) -> None:
        vc = ctx.voice_client
        if not vc:
            await ctx.send("❌ I'm not in a voice channel!")
            return

        if ctx.guild and ctx.guild.id in self.players:
            self.players[ctx.guild.id].queue.clear()
            self.players[ctx.guild.id].stop()
            del self.players[ctx.guild.id]

        await vc.disconnect()
        await ctx.send("👋 Disconnected from voice channel!")

    @commands.hybrid_command(
        name="play",
        help="Play a song or playlist from YouTube (URL or search).",
        aliases=["p"],
    )
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        if not await self.ensure_voice(ctx):
            return

        player = self.get_player(ctx)

        async with ctx.typing():
            loop = self.bot.loop
            try:
                info = await loop.run_in_executor(
                    None, lambda: ytdl.extract_info(query, download=False)
                )
            except Exception as exc:
                await ctx.send(f"❌ Failed to fetch info: {exc}")
                return

            tracks: List[Track] = []

            # Playlist
            if "entries" in info:
                playlist_title = info.get("title", "Playlist")
                for entry in info["entries"]:
                    if not entry:
                        continue
                    url = entry.get("webpage_url") or entry.get("url")
                    title = entry.get("title", "Unknown title")
                    duration = entry.get("duration")
                    thumbnail = entry.get("thumbnail")
                    tracks.append(
                        Track(
                            url=url,
                            title=title,
                            requester=ctx.author,  # type: ignore[arg-type]
                            duration=duration,
                            thumbnail=thumbnail,
                        )
                    )

                player.queue.extend(tracks)
                await ctx.send(
                    f"📝 Added **{len(tracks)}** songs "
                    f"from playlist **{playlist_title}** to queue!"
                )
            else:
                # Single track
                url = info.get("webpage_url") or query
                title = info.get("title", "Unknown title")
                duration = info.get("duration")
                thumbnail = info.get("thumbnail")
                track = Track(
                    url=url,
                    title=title,
                    requester=ctx.author,  # type: ignore[arg-type]
                    duration=duration,
                    thumbnail=thumbnail,
                )
                player.queue.add(track)
                await ctx.send(f"▶️ Queued: **{title}**")

            # Kick the player loop if idle
            vc = ctx.voice_client
            if vc and not vc.is_playing() and not player.next_event.is_set():
                player.next_event.set()

    @commands.hybrid_command(
        name="pause",
        help="Pause the current song.",
    )
    async def pause(self, ctx: commands.Context) -> None:
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await ctx.send("⏸️ Paused!")
        else:
            await ctx.send("❌ Nothing is playing right now!")

    @commands.hybrid_command(
        name="resume",
        help="Resume a paused song.",
    )
    async def resume(self, ctx: commands.Context) -> None:
        vc = ctx.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await ctx.send("▶️ Resumed!")
        else:
            await ctx.send("❌ Nothing is paused right now!")

    @commands.hybrid_command(
        name="skip",
        help="Skip the current song.",
        aliases=["next"],
    )
    async def skip(self, ctx: commands.Context) -> None:
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await ctx.send("⏭️ Skipped!")
        else:
            await ctx.send("❌ Nothing is playing right now!")

    @commands.hybrid_command(
        name="stop",
        help="Stop playback and clear the queue.",
    )
    async def stop(self, ctx: commands.Context) -> None:
        vc = ctx.voice_client
        if ctx.guild and ctx.guild.id in self.players:
            self.players[ctx.guild.id].queue.clear()

        if vc:
            vc.stop()
        await ctx.send("⏹️ Stopped and cleared queue.")

    @commands.hybrid_command(
        name="queue",
        help="Show the current queue.",
        aliases=["q"],
    )
    async def queue_display(self, ctx: commands.Context) -> None:
        if not ctx.guild or ctx.guild.id not in self.players:
            await ctx.send("📝 Queue is empty!")
            return

        player = self.players[ctx.guild.id]
        items = player.queue.as_list()

        if not items:
            await ctx.send("📝 Queue is empty!")
            return

        embed = discord.Embed(
            title="🎵 Music Queue", color=discord.Color.blue()
        )

        if player.queue.current:
            embed.add_field(
                name="Now Playing",
                value=f"**{player.queue.current.title}**",
                inline=False,
            )

        queue_text = ""
        for i, track in enumerate(items[:10], start=1):
            queue_text += f"`{i}.` **{track.title}**\n"

        if len(items) > 10:
            queue_text += f"\n... and {len(items) - 10} more songs"

        embed.add_field(
            name="Up Next", value=queue_text or "Nothing queued", inline=False
        )
        embed.set_footer(text=f"Total songs in queue: {len(items)}")

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="shuffle",
        help="Shuffle the current queue.",
    )
    async def shuffle(self, ctx: commands.Context) -> None:
        if not ctx.guild or ctx.guild.id not in self.players:
            await ctx.send("❌ Queue is empty!")
            return

        player = self.players[ctx.guild.id]
        if not player.queue.as_list():
            await ctx.send("❌ Queue is empty!")
            return

        player.queue.shuffle()
        await ctx.send("🔀 Queue shuffled!")

    @commands.hybrid_command(
        name="clear",
        help="Clear the queue.",
    )
    async def clear(self, ctx: commands.Context) -> None:
        if not ctx.guild or ctx.guild.id not in self.players:
            await ctx.send("📝 Nothing to clear.")
            return

        player = self.players[ctx.guild.id]
        player.queue.clear()
        await ctx.send("🗑️ Queue cleared!")

    @commands.hybrid_command(
        name="remove",
        help="Remove a song from the queue by position.",
    )
    async def remove(self, ctx: commands.Context, position: int) -> None:
        if not ctx.guild or ctx.guild.id not in self.players:
            await ctx.send("❌ Queue is empty!")
            return

        player = self.players[ctx.guild.id]
        removed = player.queue.remove_at(position - 1)
        if removed:
            await ctx.send(f"🗑️ Removed: **{removed.title}**")
        else:
            await ctx.send("❌ Invalid queue position!")

    @commands.hybrid_command(
        name="nowplaying",
        help="Show the currently playing song.",
        aliases=["np"],
    )
    async def now_playing(self, ctx: commands.Context) -> None:
        if not ctx.guild or ctx.guild.id not in self.players:
            await ctx.send("❌ Nothing is playing right now!")
            return

        player = self.players[ctx.guild.id]
        if not player.queue.current:
            await ctx.send("❌ Nothing is playing right now!")
            return

        current = player.queue.current
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{current.title}**",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Requested by", value=current.requester.mention, inline=False
        )

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="volume",
        help="Change player volume (0–100).",
        aliases=["vol"],
    )
    async def volume(self, ctx: commands.Context, volume: int) -> None:
        vc = ctx.voice_client
        if not vc:
            await ctx.send("❌ Not connected to a voice channel!")
            return

        if not 0 <= volume <= 100:
            await ctx.send("❌ Volume must be between 0 and 100!")
            return

        if not ctx.guild or ctx.guild.id not in self.players:
            await ctx.send("❌ No active player for this guild.")
            return

        player = self.players[ctx.guild.id]
        player.volume = volume / 100.0

        if vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = player.volume

        await ctx.send(f"🔊 Volume set to {volume}%")

    @commands.hybrid_command(
        name="loop",
        help="Toggle loop mode: song / queue / off.",
    )
    async def loop(
        self,
        ctx: commands.Context,
        mode: Optional[str] = None,
    ) -> None:
        if not ctx.guild or ctx.guild.id not in self.players:
            await ctx.send("❌ No active player for this guild.")
            return

        player = self.players[ctx.guild.id]

        if mode is None:
            status = "off"
            if player.queue.loop_song:
                status = "song"
            elif player.queue.loop_queue:
                status = "queue"
            await ctx.send(f"🔁 Current loop mode: **{status}**")
            return

        mode = mode.lower()
        if mode == "song":
            player.queue.loop_song = True
            player.queue.loop_queue = False
            await ctx.send("🔁 Looping current song!")
        elif mode == "queue":
            player.queue.loop_song = False
            player.queue.loop_queue = True
            await ctx.send("🔁 Looping queue!")
        elif mode == "off":
            player.queue.loop_song = False
            player.queue.loop_queue = False
            await ctx.send("🔁 Loop disabled!")
        else:
            await ctx.send("❌ Invalid mode! Use: song, queue, or off")

    @commands.hybrid_command(
        name="music_help",
        help="Show all music commands.",
        aliases=["mhelp"],
    )
    async def music_help(self, ctx: commands.Context) -> None:
        embed = discord.Embed(
            title="🎵 Music Bot Commands",
            description="All available music commands",
            color=discord.Color.blue(),
        )

        commands_list = {
            "Basic Controls": {
                "!play <song/url>": "Play a song or playlist from YouTube",
                "!pause": "Pause current song",
                "!resume": "Resume paused song",
                "!skip": "Skip to next song",
                "!stop": "Stop playback and clear queue",
            },
            "Queue Management": {
                "!queue": "Show current queue",
                "!shuffle": "Shuffle the queue",
                "!clear": "Clear the queue",
                "!remove <position>": "Remove song from queue",
                "!nowplaying": "Show current song",
            },
            "Settings": {
                "!volume <0-100>": "Change volume",
                "!loop <song/queue/off>": "Toggle loop mode",
            },
            "Voice Channel": {
                "!join": "Join your voice channel",
                "!leave": "Leave voice channel",
            },
        }

        for category, cmds in commands_list.items():
            cmd_text = "\n".join(
                f"`{cmd}` - {desc}" for cmd, desc in cmds.items()
            )
            embed.add_field(name=category, value=cmd_text, inline=False)

        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
