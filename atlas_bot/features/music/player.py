from __future__ import annotations
import asyncio
from typing import Optional, Tuple
import yt_dlp


_ytdl_opts = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "auto",
}

_ytdl = yt_dlp.YoutubeDL(_ytdl_opts)


async def get_audio_stream(
    query: str,
    *,
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> Tuple[str, str]:
    """
    resolve a url or search query into a direct audio stream url and title.

    returns (stream_url, title).
    raises whatever yt_dlp raises; caller should handle.
    """
    loop = loop or asyncio.get_running_loop()

    def _extract() -> dict:
        return _ytdl.extract_info(query, download=False)

    data = await loop.run_in_executor(None, _extract)

    # handle playlists/search results
    if "entries" in data:
        data = data["entries"][0]

    stream_url = data["url"]
    title = data.get("title", "unknown title")

    return stream_url, title
