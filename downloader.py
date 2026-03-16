"""Download YouTube videos and extract heatmap (most-replayed) data."""

import json
import subprocess
import sys
import re
import shutil
from pathlib import Path
from config import DOWNLOADS_DIR, GAMEPLAY_DIR

# Resolve tool paths once at import
_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
_FFPROBE = shutil.which("ffprobe") or "ffprobe"


def _ytdlp(*args: str) -> subprocess.CompletedProcess:
    """Run yt-dlp via `py -m yt_dlp` so it works even when not on PATH."""
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        *args,
    ]
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
        raise RuntimeError(f"yt-dlp failed:\n{result.stderr}")

    if cached.exists():
        return cached

    # Check for other extensions that yt-dlp might have saved
    for f in output_dir.iterdir():
        if f.stem == video_id:
            return f

    raise FileNotFoundError(f"Downloaded file not found for {video_id}")


def extract_video_id(url: str) -> str:
    """Extract the video ID from a YouTube URL."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from: {url}")


def get_video_duration(url: str) -> float:
    """Get video duration in seconds using yt-dlp."""
    result = _ytdlp("--print", "duration", "--no-playlist", url)
    if result.returncode != 0:
        raise RuntimeError(f"Could not get duration:\n{result.stderr}")
    return float(result.stdout.strip())


def get_heatmap_data(url: str) -> list[dict] | None:
    """
    Extract the most-replayed heatmap data from a YouTube video.
    Returns a list of {start_time, end_time, value} dicts, or None if unavailable.
    """
    result = _ytdlp(
        "--skip-download",
        "--print", "%(heatmap)j",
        "--no-playlist",
        url,
    )

    if result.returncode != 0:
        return None

    raw = result.stdout.strip()
    if not raw or raw in ("NA", "null", "None"):
        return None

    try:
        data = json.loads(raw)
        if isinstance(data, list) and len(data) > 0:
            return data
    except (json.JSONDecodeError, TypeError):
        pass

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
