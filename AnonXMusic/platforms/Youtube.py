import asyncio
import glob
import os
import random
import re
from typing import Union

import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch

from AnonXMusic.utils.database import is_on_off
from AnonXMusic.utils.formatters import time_to_seconds

# ---------------------------------------------------------------------------
# Cookies + official YouTube Data API support
# ---------------------------------------------------------------------------
# COOKIES_DIR: folder to look for cookie files in. Any file matching
# cookies*.txt (cookies.txt, cookies1.txt, cookies2.txt, cookies_alt.txt...)
# is picked up automatically as part of the rotation pool. Using several
# accounts spreads load across them and means one getting rate-limited or
# flagged doesn't take the whole bot down.
COOKIES_DIR = os.getenv("COOKIES_DIR", ".")

# YOUTUBE_API_KEY: optional key from console.cloud.google.com (enable the
# "YouTube Data API v3"). When set, search/detail lookups use the official
# API instead of scraping, which is far more reliable long-term. Falls back
# to the scraping-based youtube-search-python if unset or if the API call
# fails/quota is exhausted.
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", None)

_yt_api_service = None
if YOUTUBE_API_KEY:
    try:
        from googleapiclient.discovery import build as _build_yt_service

        _yt_api_service = _build_yt_service(
            "youtube", "v3", developerKey=YOUTUBE_API_KEY, cache_discovery=False
        )
    except Exception:
        _yt_api_service = None


def _cookie_pool() -> list:
    """All cookie files currently available, e.g. ['cookies.txt', 'cookies1.txt', ...]."""
    cookies_dir = os.getenv("COOKIES_DIR", ".")
    found = []
    for pat in ["cookies*.txt", "cookie*.txt", "*.txt"]:
        for f in glob.glob(os.path.join(cookies_dir, pat)):
            if os.path.isfile(f) and os.path.getsize(f) > 10 and "requirement" not in f.lower():
                abs_f = os.path.abspath(f)
                if abs_f not in found:
                    found.append(abs_f)
    if os.path.isfile("cookies.txt"):
        abs_c = os.path.abspath("cookies.txt")
        if abs_c not in found and os.path.getsize(abs_c) > 10:
            found.append(abs_c)
    return found


def _pick_cookie_file() -> Union[str, None]:
    pool = _cookie_pool()
    if not pool:
        return None
    return random.choice(pool)


def cookies_opt() -> dict:
    """Return the yt-dlp option dict fragment for cookies, picking randomly from the pool."""
    chosen = _pick_cookie_file()
    return {"cookiefile": chosen} if chosen else {}


def cookies_cli_args() -> list:
    """Return CLI args for the yt-dlp binary, picking randomly from the pool."""
    chosen = _pick_cookie_file()
    return ["--cookies", chosen] if chosen else []


def _run_ydl_with_retry(base_opts: dict, link: str):
    """Extract/download via yt-dlp, retrying with multiple client strategies and
    cookie combinations so errors like 'page needs to be reloaded' or IP blocks
    automatically fail over to working clients (ios, tv_embedded, mweb, web)."""
    pool = _cookie_pool()
    strategies = []
    for c in pool:
        strategies.append((c, None))
        strategies.append((c, ["ios", "mweb"]))
        strategies.append((c, ["tv_embedded", "mweb"]))
    strategies.append((None, ["ios", "mweb"]))
    strategies.append((None, ["tv_embedded", "mweb"]))
    strategies.append((None, None))

    last_err = None
    for cookie_file, client in strategies:
        opts = dict(base_opts)
        if cookie_file:
            opts["cookiefile"] = cookie_file
        if client:
            opts["extractor_args"] = {"youtube": {"player_client": client}}
        try:
            x = yt_dlp.YoutubeDL(opts)
            info = x.extract_info(link, download=False)
            xyz = os.path.join("downloads", f"{info['id']}.{info['ext']}")
            if not os.path.exists(xyz):
                x.download([link])
            return xyz
        except Exception as e:
            last_err = e
            continue
    raise last_err or Exception("yt-dlp failed to download media")


def _iso8601_duration_to_min(duration: str) -> str:
    """Convert an ISO-8601 duration (PT#H#M#S) from the YouTube API to M:SS/H:MM:SS."""
    m = re.match(
        r"PT(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?", duration or ""
    )
    if not m:
        return "0:00"
    h, mi, s = (int(m.group(x) or 0) for x in ("h", "m", "s"))
    if h:
        return f"{h}:{mi:02d}:{s:02d}"
    return f"{mi}:{s:02d}"


async def _api_search(query: str, limit: int = 1):
    """Search via the official YouTube Data API v3. Returns a list of result dicts
    shaped like youtube-search-python's output so callers don't need to change."""
    if not _yt_api_service:
        return None
    try:
        loop = asyncio.get_running_loop()

        def _do_search():
            resp = (
                _yt_api_service.search()
                .list(q=query, part="id", type="video", maxResults=limit)
                .execute()
            )
            ids = [
                item["id"]["videoId"]
                for item in resp.get("items", [])
                if item["id"].get("videoId")
            ]
            if not ids:
                return []
            details = (
                _yt_api_service.videos()
                .list(id=",".join(ids), part="snippet,contentDetails")
                .execute()
            )
            out = []
            for item in details.get("items", []):
                snippet = item["snippet"]
                out.append(
                    {
                        "title": snippet["title"],
                        "id": item["id"],
                        "link": f"https://www.youtube.com/watch?v={item['id']}",
                        "duration": _iso8601_duration_to_min(
                            item["contentDetails"]["duration"]
                        ),
                        "thumbnails": [
                            {"url": snippet["thumbnails"]["high"]["url"]}
                        ],
                    }
                )
            return out

        return await loop.run_in_executor(None, _do_search)
    except Exception:
        # Quota exceeded, key invalid, network issue, etc. -> fall back silently.
        return None


async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, errorz = await proc.communicate()
    if errorz:
        if "unavailable videos are hidden" in (errorz.decode("utf-8")).lower():
            return out.decode("utf-8")
        else:
            return errorz.decode("utf-8")
    return out.decode("utf-8")


async def _universal_search(query: str, limit: int = 1) -> list:
    """
    Robust YouTube search with 4-tier fallback:
      1. Official YouTube Data API v3 (if key provided)
      2. youtubesearchpython (VideosSearch)
      3. youtube-search (YoutubeSearch)
      4. yt-dlp flat search (ytsearch)
    Returns list of dicts: [{'title': str, 'id': str, 'link': str, 'duration': str, 'thumbnails': [{'url': str}]}]
    """
    loop = asyncio.get_running_loop()

    # Tier 1: YouTube Data API v3
    try:
        api_res = await _api_search(query, limit=limit)
        if api_res:
            return api_res
    except Exception:
        pass

    # Tier 2: youtubesearchpython (VideosSearch)
    try:
        vs = VideosSearch(query, limit=limit)
        res = await vs.next()
        items = res.get("result", []) if isinstance(res, dict) else []
        if items:
            out = []
            for item in items:
                dur = str(item.get("duration", "0:00"))
                thumbs = item.get("thumbnails", [{}])
                thumb_url = thumbs[0].get("url", "").split("?")[0] if thumbs else ""
                vid = item.get("id", "")
                if not thumb_url and vid:
                    thumb_url = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
                out.append({
                    "title": item.get("title", "Unknown"),
                    "id": vid,
                    "link": item.get("link", f"https://www.youtube.com/watch?v={vid}"),
                    "duration": dur,
                    "thumbnails": [{"url": thumb_url}],
                })
            if out:
                return out
    except Exception:
        pass

    # Tier 3: youtube_search (YoutubeSearch)
    try:
        from youtube_search import YoutubeSearch

        def _do_ys():
            ys = YoutubeSearch(query, max_results=limit).to_dict()
            if not ys:
                return []
            out = []
            for item in ys:
                vid = item.get("id", "")
                dur = str(item.get("duration", "0:00"))
                thumbs = item.get("thumbnails", [])
                thumb_url = thumbs[0].split("?")[0] if (thumbs and isinstance(thumbs, list)) else f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
                out.append({
                    "title": item.get("title", "Unknown"),
                    "id": vid,
                    "link": f"https://www.youtube.com/watch?v={vid}",
                    "duration": dur,
                    "thumbnails": [{"url": thumb_url}],
                })
            return out

        ys_res = await loop.run_in_executor(None, _do_ys)
        if ys_res:
            return ys_res
    except Exception:
        pass

    # Tier 4: yt-dlp flat search
    try:
        def _do_ytdlp():
            opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "skip_download": True,
                **cookies_opt(),
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
                entries = info.get("entries") or []
                out = []
                for entry in entries:
                    if not entry:
                        continue
                    vid = entry.get("id", "")
                    dur_sec = entry.get("duration") or 0
                    if dur_sec:
                        m, s = divmod(int(dur_sec), 60)
                        h, m = divmod(m, 60)
                        dur_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
                    else:
                        dur_str = "0:00"
                    thumb = entry.get("thumbnail") or f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
                    out.append({
                        "title": entry.get("title", "Unknown"),
                        "id": vid,
                        "link": f"https://www.youtube.com/watch?v={vid}",
                        "duration": dur_str,
                        "thumbnails": [{"url": thumb}],
                    })
                return out

        ytdlp_res = await loop.run_in_executor(None, _do_ytdlp)
        if ytdlp_res:
            return ytdlp_res
    except Exception:
        pass

    return []


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if re.search(self.regex, link):
            return True
        else:
            return False

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        text = ""
        offset = None
        length = None
        for message in messages:
            if offset:
                break
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        offset, length = entity.offset, entity.length
                        break
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        if offset in (None,):
            return None
        return text[offset : offset + length]

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = await _universal_search(link, limit=1)
        if not results:
            raise Exception(f"No results found for query: {link}")
        res = results[0]
        title = res["title"]
        duration_min = res["duration"]
        duration_sec = 0 if duration_min == "None" or not duration_min else int(time_to_seconds(duration_min))
        thumbnail = res["thumbnails"][0]["url"].split("?")[0] if res["thumbnails"] else f"https://img.youtube.com/vi/{res['id']}/hqdefault.jpg"
        vidid = res["id"]
        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = await _universal_search(link, limit=1)
        if not results:
            raise Exception(f"No results found for query: {link}")
        return results[0]["title"]

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = await _universal_search(link, limit=1)
        if not results:
            raise Exception(f"No results found for query: {link}")
        return results[0]["duration"]

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = await _universal_search(link, limit=1)
        if not results:
            raise Exception(f"No results found for query: {link}")
        res = results[0]
        return res["thumbnails"][0]["url"].split("?")[0] if res["thumbnails"] else f"https://img.youtube.com/vi/{res['id']}/hqdefault.jpg"

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "-g",
            "-f",
            "best[height<=?720][width<=?1280]",
            *cookies_cli_args(),
            f"{link}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if stdout:
            return 1, stdout.decode().split("\n")[0]
        else:
            return 0, stderr.decode()

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        chosen_cookie = _pick_cookie_file()
        cookie_flag = f'--cookies "{chosen_cookie}"' if chosen_cookie else ""
        playlist = await shell_cmd(
            f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} "
            f"{cookie_flag} --skip-download {link}"
        )
        try:
            result = playlist.split("\n")
            for key in result:
                if key == "":
                    result.remove(key)
        except:
            result = []
        return result

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = await _universal_search(link, limit=1)
        if not results:
            raise Exception(f"No results found for query: {link}")
        res = results[0]
        thumb = res["thumbnails"][0]["url"].split("?")[0] if res["thumbnails"] else f"https://img.youtube.com/vi/{res['id']}/hqdefault.jpg"
        track_details = {
            "title": res["title"],
            "link": res["link"],
            "vidid": res["id"],
            "duration_min": res["duration"],
            "thumb": thumb,
        }
        return track_details, res["id"]

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        ytdl_opts = {"quiet": True, **cookies_opt()}
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        with ydl:
            formats_available = []
            r = ydl.extract_info(link, download=False)
            for format in r["formats"]:
                try:
                    str(format["format"])
                except:
                    continue
                if not "dash" in str(format["format"]).lower():
                    try:
                        format["format"]
                        format["filesize"]
                        format["format_id"]
                        format["ext"]
                        format["format_note"]
                    except:
                        continue
                    formats_available.append(
                        {
                            "format": format["format"],
                            "filesize": format["filesize"],
                            "format_id": format["format_id"],
                            "ext": format["ext"],
                            "format_note": format["format_note"],
                            "yturl": link,
                        }
                    )
        return formats_available, link

    async def slider(
        self,
        link: str,
        query_type: int,
        videoid: Union[bool, str] = None,
    ):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = await _universal_search(link, limit=10)
        if not results:
            raise Exception(f"No results found for query: {link}")
        idx = query_type if len(results) > query_type else 0
        res = results[idx]
        thumb = res["thumbnails"][0]["url"].split("?")[0] if res["thumbnails"] else f"https://img.youtube.com/vi/{res['id']}/hqdefault.jpg"
        return res["title"], res["duration"], thumb, res["id"]

    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> str:
        if videoid:
            link = self.base + link
        loop = asyncio.get_running_loop()

        # ── songvideo / songaudio (specific format_id download — use yt-dlp directly) ──
        if songvideo:
            def song_video_dl():
                fpath = f"downloads/{title}"
                opts = {
                    "format": f"{format_id}+140/best",
                    "outtmpl": fpath,
                    "geo_bypass": True,
                    "nocheckcertificate": True,
                    "quiet": True,
                    "no_warnings": True,
                    "prefer_ffmpeg": True,
                    "merge_output_format": "mp4",
                    **cookies_opt(),
                }
                yt_dlp.YoutubeDL(opts).download([link])

            await loop.run_in_executor(None, song_video_dl)
            return f"downloads/{title}.mp4"

        elif songaudio:
            def song_audio_dl():
                fpath = f"downloads/{title}.%(ext)s"
                opts = {
                    "format": f"{format_id}/bestaudio/best/ba/b",
                    "outtmpl": fpath,
                    "geo_bypass": True,
                    "nocheckcertificate": True,
                    "quiet": True,
                    "no_warnings": True,
                    "prefer_ffmpeg": True,
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        }
                    ],
                    **cookies_opt(),
                }
                yt_dlp.YoutubeDL(opts).download([link])

            await loop.run_in_executor(None, song_audio_dl)
            return f"downloads/{title}.mp3"

        # ── video streaming URL (direct URL mode, no download) ──
        elif video:
            if not await is_on_off(1):
                proc = await asyncio.create_subprocess_exec(
                    "yt-dlp",
                    "-g",
                    "-f",
                    "best[height<=?720][width<=?1280]/best",
                    *cookies_cli_args(),
                    f"{link}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if stdout:
                    return stdout.decode().split("\n")[0], None
                # URL fetch failed — fall through to smart download

            # Smart download: ArcMusic → Shruti → yt-dlp
            from AnonXMusic.utils.musicapi import smart_download
            downloaded_file = await smart_download(link, is_video=True)
            if downloaded_file:
                return downloaded_file, True
            return None, None

        # ── audio (default) — Smart download: ArcMusic → Shruti → yt-dlp ──
        else:
            from AnonXMusic.utils.musicapi import smart_download
            downloaded_file = await smart_download(link, is_video=False)
            if downloaded_file:
                return downloaded_file, True
            return None, None
