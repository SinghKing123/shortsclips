"""Download YouTube videos and extract heatmap (most-replayed) data."""

import json
import os
import subprocess
import sys
import re
import shutil
import urllib.request
from pathlib import Path
from config import DOWNLOADS_DIR, GAMEPLAY_DIR, BASE_DIR

# Resolve tool paths once at import
_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
_FFPROBE = shutil.which("ffprobe") or "ffprobe"

# Optional proxy for YouTube downloads (set PROXY env var if needed)
# e.g. PROXY=socks5://user:pass@host:port
_PROXY = os.environ.get("PROXY", "")


def _ytdlp(*args: str) -> subprocess.CompletedProcess:
    """Run yt-dlp with PO token support and optional proxy."""
    cmd = [sys.executable, "-m", "yt_dlp"]

    # Proxy support (residential proxy to bypass datacenter IP blocks)
    if _PROXY:
        cmd += ["--proxy", _PROXY]

    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True)


def download_video(url: str, output_dir: Path = DOWNLOADS_DIR, max_height: int = 720) -> Path:
    """Download a YouTube video, return path to the downloaded file."""
    video_id = extract_video_id(url)
    cached = output_dir / f"{video_id}.mp4"
    if cached.exists():
        return cached

    output_template = str(output_dir / "%(id)s.%(ext)s")

    result = _ytdlp(
        "-f", f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]",
        "--merge-output-format", "mp4",
        "--ffmpeg-location", str(Path(_FFMPEG).parent),
        "-o", output_template,
        "--no-playlist",
        url,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Download failed:\n{result.stderr}")

    if cached.exists():
        return cached

    for f in output_dir.iterdir():
        if f.stem == video_id:
            return f

    raise FileNotFoundError(f"Downloaded file not found for {video_id}")


def extract_video_id(url: str) -> str:
    """Extract the video ID from a YouTube URL."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:shorts/)([a-zA-Z0-9_-]{11})",
        r"(?:live/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from: {url}")


def get_video_duration(url: str) -> float:
    """Get video duration in seconds."""
    result = _ytdlp("--print", "duration", "--no-playlist", "--skip-download", url)
    if result.returncode == 0:
        try:
            return float(result.stdout.strip())
        except ValueError:
            pass

    # Fallback: scrape from YouTube page
    video_id = extract_video_id(url)
    return _get_duration_from_page(video_id)


def _get_duration_from_page(video_id: str) -> float:
    """Scrape video duration from YouTube page."""
    page_url = f"https://www.youtube.com/watch?v={video_id}"
    req = urllib.request.Request(page_url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        match = re.search(r'"lengthSeconds"\s*:\s*"(\d+)"', html)
        if match:
            return float(match.group(1))
    except Exception:
        pass
    raise RuntimeError("Could not determine video duration")


def get_heatmap_data(url: str) -> list[dict] | None:
    """
    Extract the most-replayed heatmap data from a YouTube video.
    Tries yt-dlp first, falls back to direct page scraping.
    """
    # Try yt-dlp
    result = _ytdlp(
        "--skip-download",
        "--print", "%(heatmap)j",
        "--no-playlist",
        url,
    )

    if result.returncode == 0:
        raw = result.stdout.strip()
        if raw and raw not in ("NA", "null", "None"):
            try:
                data = json.loads(raw)
                if isinstance(data, list) and len(data) > 0:
                    return data
            except (json.JSONDecodeError, TypeError):
                pass

    # Fallback: scrape from page
    return _scrape_heatmap(url)


def _scrape_heatmap(url: str) -> list[dict] | None:
    """Scrape heatmap data directly from YouTube page HTML."""
    video_id = extract_video_id(url)
    page_url = f"https://www.youtube.com/watch?v={video_id}"
    req = urllib.request.Request(page_url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        match = re.search(r'"heatMarkers"\s*:\s*(\[.*?\])\s*[,}]', html)
        if not match:
            match = re.search(r'heatMarkers.*?(\[\{.*?"startMillis".*?\}\])', html)
        if not match:
            return None

        markers = json.loads(match.group(1))
        heatmap = []
        for m in markers:
            ms = m.get("heatMarkerRenderer", m)
            start_ms = int(ms.get("timeRangeStartMillis", ms.get("startMillis", 0)))
            duration_ms = int(ms.get("markerDurationMillis", ms.get("durationMillis", 0)))
            intensity = float(ms.get("heatMarkerIntensityScoreNormalized",
                                     ms.get("intensityScoreNormalized", 0)))
            heatmap.append({
                "start_time": start_ms / 1000.0,
                "end_time": (start_ms + duration_ms) / 1000.0,
                "value": intensity,
            })
        return heatmap if len(heatmap) > 0 else None
    except Exception:
        return None


def download_gameplay(gameplay_key: str, gameplay_options: dict) -> Path:
    """Download a gameplay video if not already cached."""
    if gameplay_key not in gameplay_options:
        raise ValueError(f"Unknown gameplay option: {gameplay_key}")

    option = gameplay_options[gameplay_key]
    video_id = extract_video_id(option["url"])
    cached = GAMEPLAY_DIR / f"{video_id}.mp4"

    if cached.exists():
        return cached

    return download_video(option["url"], output_dir=GAMEPLAY_DIR, max_height=720)


def get_local_video_duration(path: Path) -> float:
    """Get duration of a local video file using ffprobe."""
    cmd = [
        _FFPROBE, "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed:\n{result.stderr}")
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])
