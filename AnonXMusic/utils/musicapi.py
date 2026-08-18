"""
AnonXMusic — Dual Music API Download System
============================================
Priority order:
  1. ArcMusic API  (https://api.arcmusic.fun)
  2. Shruti API    (https://api.shrutibots.site)
  3. yt-dlp        (local fallback — always last resort)

If API-1 fails → instantly switch to API-2 → if that fails → yt-dlp.
No audio duration limit enforced here. Files are cached on disk so
the same track is never downloaded twice.
"""

import asyncio
import logging
import os
import re
import time
from typing import Optional

import aiofiles
import aiohttp

logger = logging.getLogger(__name__)

# ── Config (read from env / config.py) ───────────────────────────────────────
ARCMUSIC_API_URL   = os.getenv("ARC_API_URL",    "https://api.arcmusic.fun")
ARCMUSIC_API_KEY   = os.getenv("ARC_API_KEY",    "")          # get from https://portal.arcmusic.fun/

SHRUTI_API_URL     = os.getenv("SHRUTI_API_URL", "https://api.shrutibots.site")
SHRUTI_API_KEY     = os.getenv("SHRUTI_API_KEY", "ShrutiBotsbGoL15gRHVmyN5BBE7DJ")

DOWNLOAD_DIR       = os.getenv("DOWNLOAD_DIR", "downloads")
API_TIMEOUT        = int(os.getenv("MUSIC_API_TIMEOUT", 900))   # 15 min stream timeout
JOB_POLL_RETRIES   = 20                                          # ArcMusic job poll attempts
JOB_POLL_SLEEP     = 4                                           # seconds between polls
CHUNK_SIZE         = 131072                                      # 128 KB chunks

# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_video_id(url: str) -> str:
    """Extract raw video ID from any YouTube URL or return as-is if already an ID."""
    if "v=" in url:
        return url.split("v=")[-1].split("&")[0]
    if "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0]
    # Already a plain video ID (11 chars)
    if re.match(r"^[A-Za-z0-9_\-]{11}$", url.strip()):
        return url.strip()
    return url


def _get_path(video_id: str, is_video: bool) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    ext = "mp4" if is_video else "mp3"
    return os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")


def _is_cached(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 1024


def _cleanup(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _normalize_url(candidate: str, base_url: str) -> str:
    """Make a relative URL from the API absolute."""
    candidate = candidate.strip()
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate
    base = base_url.rstrip("/")
    if candidate.startswith("/"):
        return base + candidate
    return base + "/" + candidate

# ── Telegram CDN regex (same as ArcMusic Go code) ────────────────────────────
_TG_LINK_RE = re.compile(
    r"https?://t(?:elegram)?\.me/([cC]/)?([^/]+)/(\d+)"
)

# ── ArcMusic API ──────────────────────────────────────────────────────────────

async def _arcmusic_poll_job(session: aiohttp.ClientSession, job_id: str) -> Optional[str]:
    """Poll /youtube/jobStatus until done or timeout."""
    url = f"{ARCMUSIC_API_URL.rstrip('/')}/youtube/jobStatus"
    for attempt in range(JOB_POLL_RETRIES):
        try:
            async with session.get(
                url,
                params={"api_key": ARCMUSIC_API_KEY, "job_id": job_id},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    await asyncio.sleep(JOB_POLL_SLEEP)
                    continue
                data = await resp.json(content_type=None)
                if data.get("status") != "success":
                    await asyncio.sleep(JOB_POLL_SLEEP)
                    continue
                job = data.get("job", {})
                if job.get("status") != "done":
                    await asyncio.sleep(JOB_POLL_SLEEP)
                    continue
                cdn = job.get("result", {}).get("cdn", "")
                if cdn:
                    return _normalize_url(cdn, ARCMUSIC_API_URL)
        except Exception as e:
            logger.debug(f"[ArcMusic] Job poll error (attempt {attempt+1}): {e}")
            await asyncio.sleep(JOB_POLL_SLEEP)
    return None


async def _download_telegram_cdn(tg_link: str, path: str) -> Optional[str]:
    """Download audio directly from Telegram CDN link like https://t.me/ArcAPI_1/1586 using bot client."""
    try:
        m = _TG_LINK_RE.match(tg_link)
        if not m:
            return None
        from AnonXMusic import app
        channel = m.group(2)
        message_id = int(m.group(3))
        logger.info(f"[ArcMusic] Downloading Telegram CDN message {message_id} from @{channel}")
        msg = await app.get_messages(channel, message_id)
        if msg and (msg.audio or msg.document or msg.video):
            file_path = await app.download_media(msg, file_name=path)
            if file_path and _is_cached(file_path):
                logger.info(f"[ArcMusic] Downloaded via Telegram CDN: {file_path}")
                return file_path
    except Exception as e:
        logger.warning(f"[ArcMusic] Telegram CDN download failed: {e}")
    return None


async def download_via_arcmusic(video_id: str, is_video: bool = False) -> Optional[str]:
    """
    Download audio/video via ArcMusic API.
    Returns local file path on success, None on failure.
    ArcMusic returns either:
      - A direct CDN URL → stream + save locally
      - A Telegram CDN link → download via Pyrogram app
      - A job_id → poll until done
    """
    if not ARCMUSIC_API_KEY:
        logger.debug("[ArcMusic] API key not set, skipping")
        return None

    path = _get_path(video_id, is_video)
    if _is_cached(path):
        logger.info(f"[ArcMusic] Cache hit: {path}")
        return path

    req_url = f"{ARCMUSIC_API_URL.rstrip('/')}/youtube/v2/download"
    params  = {
        "api_key": ARCMUSIC_API_KEY,
        "query":   video_id,
        "isVideo": str(is_video).lower(),
    }

    try:
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            logger.info(f"[ArcMusic] Requesting {'video' if is_video else 'audio'} for {video_id}")
            async with session.get(req_url, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"[ArcMusic] API returned HTTP {resp.status}")
                    return None

                data = await resp.json(content_type=None)

            # --- Extract CDN URL ---
            cdn = ""
            if isinstance(data.get("result"), dict):
                cdn = data["result"].get("cdn", "")
            if not cdn:
                cdn = data.get("cdn", "")

            if cdn:
                cdn = _normalize_url(cdn, ARCMUSIC_API_URL)

                # Telegram CDN link — download via Pyrogram
                if _TG_LINK_RE.match(cdn):
                    logger.info(f"[ArcMusic] Got Telegram CDN link: {cdn}")
                    tg_res = await _download_telegram_cdn(cdn, path)
                    if tg_res:
                        return tg_res
                    return None

                # Direct stream URL → stream to disk
                logger.info(f"[ArcMusic] Direct CDN stream for {video_id}")
                async with aiohttp.ClientSession(timeout=timeout) as session2:
                    async with session2.get(cdn) as stream_resp:
                        if stream_resp.status != 200:
                            return None
                        async with aiofiles.open(path, "wb") as f:
                            async for chunk in stream_resp.content.iter_chunked(CHUNK_SIZE):
                                await f.write(chunk)

                if _is_cached(path):
                    logger.info(f"[ArcMusic] Downloaded: {path}")
                    return path
                _cleanup(path)
                return None

            # --- Job ID polling ---
            job_id = data.get("job_id", "")
            if not job_id:
                logger.warning("[ArcMusic] No CDN or job_id in response")
                return None

            logger.info(f"[ArcMusic] Polling job: {job_id}")
            async with aiohttp.ClientSession(timeout=timeout) as session3:
                cdn = await _arcmusic_poll_job(session3, job_id)

            if not cdn:
                logger.warning(f"[ArcMusic] Job {job_id} timed out")
                return None

            if _TG_LINK_RE.match(cdn):
                logger.info(f"[ArcMusic] Job gave Telegram CDN link: {cdn}")
                tg_res = await _download_telegram_cdn(cdn, path)
                if tg_res:
                    return tg_res
                return None

            # Stream polled CDN to disk
            async with aiohttp.ClientSession(timeout=timeout) as session4:
                async with session4.get(cdn) as stream_resp:
                    if stream_resp.status != 200:
                        return None
                    async with aiofiles.open(path, "wb") as f:
                        async for chunk in stream_resp.content.iter_chunked(CHUNK_SIZE):
                            await f.write(chunk)

            if _is_cached(path):
                logger.info(f"[ArcMusic] Downloaded via job: {path}")
                return path
            _cleanup(path)
            return None

    except Exception as e:
        logger.error(f"[ArcMusic] download_via_arcmusic error: {e}")
        _cleanup(path)
        return None


# ── Shruti API ────────────────────────────────────────────────────────────────

async def download_via_shruti(video_id: str, is_video: bool = False) -> Optional[str]:
    """
    Download audio/video via Shruti API.
    Returns local file path on success, None on failure.
    """
    path = _get_path(video_id, is_video)
    if _is_cached(path):
        logger.info(f"[Shruti] Cache hit: {path}")
        return path

    media_type = "video" if is_video else "audio"
    req_url    = f"{SHRUTI_API_URL.rstrip('/')}/download"
    params     = {
        "url":     video_id,
        "type":    media_type,
        "api_key": SHRUTI_API_KEY,
    }

    try:
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            logger.info(f"[Shruti] Requesting {media_type} for {video_id}")
            async with session.get(req_url, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"[Shruti] API returned HTTP {resp.status}")
                    return None
                async with aiofiles.open(path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                        await f.write(chunk)

        if _is_cached(path):
            logger.info(f"[Shruti] Downloaded: {path}")
            return path
        _cleanup(path)
        return None

    except Exception as e:
        logger.error(f"[Shruti] download_via_shruti error: {e}")
        _cleanup(path)
        return None


# ── Smart Download (Main Entry Point) ─────────────────────────────────────────

async def smart_download(link: str, is_video: bool = False) -> Optional[str]:
    """
    Attempt download in order:
      1. ArcMusic API
      2. Shruti API
      3. yt-dlp (fallback — runs in thread executor)

    Returns local file path or None if everything failed.
    No duration limit is enforced.
    """
    video_id = _extract_video_id(link)
    logger.info(f"[SmartDownload] video_id={video_id} is_video={is_video}")

    # ── 1. ArcMusic ──
    try:
        result = await download_via_arcmusic(video_id, is_video)
        if result:
            logger.info(f"[SmartDownload] ✅ ArcMusic success: {result}")
            return result
    except Exception as e:
        logger.warning(f"[SmartDownload] ArcMusic failed: {e}")

    # ── 2. Shruti ──
    try:
        result = await download_via_shruti(video_id, is_video)
        if result:
            logger.info(f"[SmartDownload] ✅ Shruti success: {result}")
            return result
    except Exception as e:
        logger.warning(f"[SmartDownload] Shruti failed: {e}")

    # ── 3. yt-dlp fallback ──
    logger.warning(f"[SmartDownload] Both APIs failed, falling back to yt-dlp for {video_id}")
    try:
        result = await _ytdlp_fallback(link, video_id, is_video)
        if result:
            logger.info(f"[SmartDownload] ✅ yt-dlp fallback success: {result}")
            return result
    except Exception as e:
        logger.error(f"[SmartDownload] yt-dlp fallback also failed: {e}")

    logger.error(f"[SmartDownload] ❌ All methods failed for {video_id}")
    return None


async def _ytdlp_fallback(link: str, video_id: str, is_video: bool) -> Optional[str]:
    """Last-resort yt-dlp download. Runs in thread pool to avoid blocking."""
    import yt_dlp

    path = _get_path(video_id, is_video)
    if _is_cached(path):
        return path

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    if is_video:
        opts = {
            "format": "(bestvideo[height<=?720][ext=mp4])+(bestaudio[ext=m4a])/best[height<=?720]/best",
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
            "geo_bypass": True,
            "nocheckcertificate": True,
            "quiet": True,
            "no_warnings": True,
        }
    else:
        opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
            "geo_bypass": True,
            "nocheckcertificate": True,
            "quiet": True,
            "no_warnings": True,
        }

    # Try multiple yt-dlp client strategies
    strategies = [
        (None, None),
        (None, ["ios", "mweb"]),
        (None, ["tv_embedded", "mweb"]),
    ]

    # Add cookies if available
    from AnonXMusic.platforms.Youtube import _pick_cookie_file
    cookie = _pick_cookie_file()
    if cookie:
        strategies = [
            (cookie, None),
            (cookie, ["ios", "mweb"]),
            (cookie, ["tv_embedded", "mweb"]),
        ] + strategies

    loop = asyncio.get_running_loop()

    def _run():
        last_err = None
        for cookie_file, client in strategies:
            o = dict(opts)
            if cookie_file:
                o["cookiefile"] = cookie_file
            if client:
                o["extractor_args"] = {"youtube": {"player_client": client}}
            try:
                with yt_dlp.YoutubeDL(o) as ydl:
                    info = ydl.extract_info(link, download=False)
                    out  = os.path.join(DOWNLOAD_DIR, f"{info['id']}.{info['ext']}")
                    if not os.path.exists(out):
                        ydl.download([link])
                    return out
            except Exception as e:
                last_err = e
                continue
        raise last_err or Exception("yt-dlp failed")

    return await loop.run_in_executor(None, _run)
