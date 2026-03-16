"""Compose final vertical Shorts: source clip on top, gameplay on bottom."""

import random
import subprocess
from pathlib import Path
from config import OUTPUT_DIR, TEMP_DIR, OUTPUT_WIDTH, OUTPUT_HEIGHT, FPS
from downloader import get_local_video_duration, _FFMPEG


def _extract_clip(source: Path, start: float, duration: float, output: Path):
    """
    Extract a clip from a video. Uses fast seek (-ss before -i) first,
    falls back to accurate seek (-ss after -i) if that produces no output.
    """
    # Fast seek: -ss before -i (instant, works for most formats)
    cmd = [
        _FFMPEG, "-y",
        "-ss", str(start),
        "-i", str(source),
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "128k",
        "-r", str(FPS),
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    # Check if it actually produced a valid file
    if result.returncode == 0 and output.exists() and output.stat().st_size > 10000:
        return

    # Fast seek failed — use accurate seek (slower but guaranteed)
    output.unlink(missing_ok=True)
    cmd = [
        _FFMPEG, "-y",
        "-i", str(source),
        "-ss", str(start),
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "128k",
        "-r", str(FPS),
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"Clip extraction failed:\n{result.stderr[-500:]}")


def compose_short(
    source_video: Path,
    gameplay_video: Path,
    start: float,
    end: float,
    output_name: str,
    voiceover_audio: Path | None = None,
) -> Path:
    """
    Create a vertical short video:
    - Top half: source clip, cropped+scaled
    - Bottom half: gameplay clip
    - Audio: source video
    """
    clip_duration = end - start
    half_height = OUTPUT_HEIGHT // 2

    gameplay_duration = get_local_video_duration(gameplay_video)
    max_gp_start = max(0, gameplay_duration - clip_duration - 10)
    gp_start = random.uniform(0, max_gp_start) if max_gp_start > 0 else 0

    output_path = OUTPUT_DIR / f"{output_name}.mp4"

    # Step 1: Extract both clips to H.264 (handles AV1/VP9 + seeking)
    src_clip = TEMP_DIR / f"{output_name}_src.mp4"
    gp_clip = TEMP_DIR / f"{output_name}_gp.mp4"

    _extract_clip(source_video, start, clip_duration, src_clip)
    _extract_clip(gameplay_video, gp_start, clip_duration, gp_clip)

    # Step 2: Stack vertically
    video_filter = (
        f"[0:v]scale={OUTPUT_WIDTH}:{half_height}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_WIDTH}:{half_height},setsar=1[top];"
        f"[1:v]scale={OUTPUT_WIDTH}:{half_height}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_WIDTH}:{half_height},setsar=1[bottom];"
        f"[top][bottom]vstack=inputs=2[v]"
    )

    filter_complex = video_filter
    map_args = ["-map", "[v]", "-map", "0:a?"]

    if voiceover_audio:
        audio_filter = (
            f"[0:a]volume=0.3:enable='lt(t,5)'[src_duck];"
            f"[2:a]volume=1.5,apad=pad_dur=0[vo];"
            f"[src_duck][vo]amix=inputs=2:duration=first:dropout_transition=2[a]"
        )
        filter_complex = video_filter + ";" + audio_filter
        map_args = ["-map", "[v]", "-map", "[a]"]

    cmd = [
        _FFMPEG, "-y",
        "-i", str(src_clip),
        "-i", str(gp_clip),
    ]
    if voiceover_audio:
        cmd += ["-i", str(voiceover_audio)]

    cmd += [
        "-filter_complex", filter_complex,
        *map_args,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-r", str(FPS),
        "-shortest",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    # Clean up temp clips
    src_clip.unlink(missing_ok=True)
    gp_clip.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{result.stderr[-500:]}")

    return output_path
