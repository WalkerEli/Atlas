import discord
from discord.ext import commands
import asyncio
import yt_dlp
from collections import deque
import random
import os

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents)

# yt-dlp configuration for audio extraction
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.requester = data.get('requester')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True, requester=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # Playlist handling
            return data['entries']
        
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        data['requester'] = requester
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

class MusicQueue:
    def __init__(self):
        self.queue = deque()
        self.history = []
        self.current = None
        self.loop_song = False
        self.loop_queue = False
        self.is_shuffled = False
        
    def add(self, song):
        self.queue.append(song)
    
    def add_multiple(self, songs):
        self.queue.extend(songs)
    
    def next(self):
        if self.loop_song and self.current:
            return self.current
        
        if len(self.queue) > 0:
            if self.current:
                self.history.append(self.current)
            self.current = self.queue.popleft()
            
            if self.loop_queue and self.current:
                self.queue.append(self.current)
            
            return self.current
        return None
    
    def shuffle(self):
        queue_list = list(self.queue)
        random.shuffle(queue_list)
        self.queue = deque(queue_list)
        self.is_shuffled = True
    
    def clear(self):
        self.queue.clear()
        self.current = None
    
    def remove(self, index):
        if 0 <= index < len(self.queue):
            removed = list(self.queue)[index]
            temp_list = list(self.queue)
            temp_list.pop(index)
            self.queue = deque(temp_list)
            return removed
        return None
    
    def get_queue_list(self):
        return list(self.queue)

class MusicPlayer:
    def __init__(self, ctx):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.queue = MusicQueue()
        self.next_event = asyncio.Event()
        self.audio_player_task = self.bot.loop.create_task(self.audio_player())
        self.volume = 0.5

    async def audio_player(self):
        while True:
            self.next_event.clear()
            
            song = self.queue.next()
            if song is None:
                await asyncio.sleep(180)  # Wait 3 minutes before disconnecting
                if self.guild.voice_client:
                    await self.guild.voice_client.disconnect()
                return
            
            try:
                source = await YTDLSource.from_url(song['url'], loop=self.bot.loop, stream=True, requester=song['requester'])
                source.volume = self.volume
                
                self.guild.voice_client.play(source, after=lambda e: self.bot.loop.call_soon_threadsafe(self.next_event.set))
                
                embed = discord.Embed(
                    title="🎵 Now Playing",
                    description=f"**{source.title}**",
                    color=discord.Color.blue()
                )
                if source.thumbnail:
                    embed.set_thumbnail(url=source.thumbnail)
                embed.add_field(name="Requested by", value=song['requester'].mention)
                if source.duration:
                    minutes, seconds = divmod(source.duration, 60)
                    embed.add_field(name="Duration", value=f"{int(minutes)}:{int(seconds):02d}")
                
                await self.channel.send(embed=embed)
                
            except Exception as e:
                await self.channel.send(f"❌ Error playing song: {str(e)}")
            
            await self.next_event.wait()

# Dictionary to store music players per guild
music_players = {}

def get_music_player(ctx):
    if ctx.guild.id not in music_players:
        music_players[ctx.guild.id] = MusicPlayer(ctx)
    return music_players[ctx.guild.id]

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is ready to play music!')

@bot.command(name='join', help='Join the voice channel')
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send("❌ You need to be in a voice channel to use this command!")
        return
    
    channel = ctx.author.voice.channel
    
    if ctx.voice_client is not None:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    
    await ctx.send(f"✅ Joined {channel.name}!")

@bot.command(name='leave', help='Leave the voice channel', aliases=['disconnect', 'dc'])
async def leave(ctx):
    if ctx.voice_client:
        if ctx.guild.id in music_players:
            music_players[ctx.guild.id].queue.clear()
            del music_players[ctx.guild.id]
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Disconnected from voice channel!")
    else:
        await ctx.send("❌ I'm not in a voice channel!")

@bot.command(name='play', help='Play a song from YouTube or search query', aliases=['p'])
async def play(ctx, *, url):
    if not ctx.author.voice:
        await ctx.send("❌ You need to be in a voice channel to play music!")
        return
    
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()
    
    async with ctx.typing():
        player = get_music_player(ctx)
        
        try:
            # Check if it's a playlist
            info = await bot.loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
            
            if 'entries' in info:
                # It's a playlist
                playlist_title = info.get('title', 'Unknown Playlist')
                entries = info['entries']
                
                for entry in entries:
                    if entry:
                        song_info = {
                            'url': entry.get('webpage_url') or entry.get('url'),
                            'title': entry.get('title'),
                            'requester': ctx.author
                        }
                        player.queue.add(song_info)
                
                await ctx.send(f"📝 Added **{len(entries)}** songs from playlist **{playlist_title}** to queue!")
            else:
                # Single song
                song_info = {
                    'url': info.get('webpage_url') or url,
                    'title': info.get('title'),
                    'requester': ctx.author
                }
                player.queue.add(song_info)
                await ctx.send(f"📝 Added to queue: **{info.get('title')}**")
        
        except Exception as e:
            await ctx.send(f"❌ Error adding song: {str(e)}")

@bot.command(name='pause', help='Pause the currently playing song')
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused!")
    else:
        await ctx.send("❌ Nothing is playing right now!")

@bot.command(name='resume', help='Resume the paused song')
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed!")
    else:
        await ctx.send("❌ Nothing is paused right now!")

@bot.command(name='skip', help='Skip the current song', aliases=['next'])
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Skipped!")
    else:
        await ctx.send("❌ Nothing is playing right now!")

@bot.command(name='queue', help='Show the current music queue', aliases=['q'])
async def queue_display(ctx):
    player = get_music_player(ctx)
    queue_list = player.queue.get_queue_list()
    
    if not queue_list:
        await ctx.send("📝 Queue is empty!")
        return
    
    embed = discord.Embed(title="🎵 Music Queue", color=discord.Color.blue())
    
    if player.queue.current:
        embed.add_field(
            name="Now Playing",
            value=f"**{player.queue.current.get('title', 'Unknown')}**",
            inline=False
        )
    
    queue_text = ""
    for i, song in enumerate(queue_list[:10], 1):
        queue_text += f"`{i}.` **{song.get('title', 'Unknown')}**\n"
    
    if len(queue_list) > 10:
        queue_text += f"\n... and {len(queue_list) - 10} more songs"
    
    embed.add_field(name="Up Next", value=queue_text or "Nothing queued", inline=False)
    embed.set_footer(text=f"Total songs in queue: {len(queue_list)}")
    
    await ctx.send(embed=embed)

@bot.command(name='shuffle', help='Shuffle the current queue')
async def shuffle(ctx):
    player = get_music_player(ctx)
    
    if len(player.queue.queue) == 0:
        await ctx.send("❌ Queue is empty!")
        return
    
    player.queue.shuffle()
    await ctx.send("🔀 Queue shuffled!")

@bot.command(name='clear', help='Clear the music queue')
async def clear(ctx):
    player = get_music_player(ctx)
    player.queue.clear()
    await ctx.send("🗑️ Queue cleared!")

@bot.command(name='remove', help='Remove a song from queue by position')
async def remove(ctx, position: int):
    player = get_music_player(ctx)
    removed = player.queue.remove(position - 1)
    
    if removed:
        await ctx.send(f"🗑️ Removed: **{removed.get('title', 'Unknown')}**")
    else:
        await ctx.send("❌ Invalid queue position!")

@bot.command(name='nowplaying', help='Show currently playing song', aliases=['np'])
async def now_playing(ctx):
    player = get_music_player(ctx)
    
    if not player.queue.current:
        await ctx.send("❌ Nothing is playing right now!")
        return
    
    current = player.queue.current
    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**{current.get('title', 'Unknown')}**",
        color=discord.Color.blue()
    )
    embed.add_field(name="Requested by", value=current.get('requester').mention)
    
    await ctx.send(embed=embed)

@bot.command(name='volume', help='Change player volume (0-100)', aliases=['vol'])
async def volume(ctx, volume: int):
    if not ctx.voice_client:
        await ctx.send("❌ Not connected to a voice channel!")
        return
    
    if not 0 <= volume <= 100:
        await ctx.send("❌ Volume must be between 0 and 100!")
        return
    
    player = get_music_player(ctx)
    player.volume = volume / 100
    
    if ctx.voice_client.source:
        ctx.voice_client.source.volume = player.volume
    
    await ctx.send(f"🔊 Volume set to {volume}%")

@bot.command(name='loop', help='Toggle loop mode (song/queue/off)')
async def loop(ctx, mode: str = None):
    player = get_music_player(ctx)
    
    if mode is None:
        status = "off"
        if player.queue.loop_song:
            status = "song"
        elif player.queue.loop_queue:
            status = "queue"
        await ctx.send(f"🔁 Current loop mode: **{status}**")
        return
    
    mode = mode.lower()
    
    if mode == 'song':
        player.queue.loop_song = True
        player.queue.loop_queue = False
        await ctx.send("🔁 Looping current song!")
    elif mode == 'queue':
        player.queue.loop_song = False
        player.queue.loop_queue = True
        await ctx.send("🔁 Looping queue!")
    elif mode == 'off':
        player.queue.loop_song = False
        player.queue.loop_queue = False
        await ctx.send("🔁 Loop disabled!")
    else:
        await ctx.send("❌ Invalid mode! Use: song, queue, or off")

@bot.command(name='music_help', help='Show all music commands', aliases=['mhelp'])
async def music_help(ctx):
    embed = discord.Embed(
        title="🎵 Music Bot Commands",
        description="All available music commands",
        color=discord.Color.blue()
    )
    
    commands_list = {
        "Basic Controls": {
            "!play <song/url>": "Play a song or playlist from YouTube",
            "!pause": "Pause current song",
            "!resume": "Resume paused song",
            "!skip": "Skip to next song",
            "!stop": "Stop playback and clear queue"
        },
        "Queue Management": {
            "!queue": "Show current queue",
            "!shuffle": "Shuffle the queue",
            "!clear": "Clear the queue",
            "!remove <position>": "Remove song from queue",
            "!nowplaying": "Show current song"
        },
        "Settings": {
            "!volume <0-100>": "Change volume",
            "!loop <song/queue/off>": "Toggle loop mode"
        },
        "Voice Channel": {
            "!join": "Join your voice channel",
            "!leave": "Leave voice channel"
        }
    }
    
    for category, cmds in commands_list.items():
        cmd_text = "\n".join([f"`{cmd}` - {desc}" for cmd, desc in cmds.items()])
        embed.add_field(name=category, value=cmd_text, inline=False)
    
    await ctx.send(embed=embed)

# Run the bot
if __name__ == '__main__':
    DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    if not DISCORD_TOKEN:
        print("Error: DISCORD_BOT_TOKEN environment variable not set")
    else:
        bot.run(DISCORD_TOKEN)