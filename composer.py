"""Compose final vertical Shorts: source clip on top, gameplay on bottom."""

import random
import subprocess
from pathlib import Path
from config import OUTPUT_DIR, OUTPUT_WIDTH, OUTPUT_HEIGHT, FPS
from downloader import get_local_video_duration, _FFMPEG


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
    - Top half: source video clip (start->end), cropped+scaled to fit
    - Bottom half: random segment from gameplay video (same duration)
    - Audio: source video audio + optional voiceover layered on top at the start
    """
    clip_duration = end - start
    half_height = OUTPUT_HEIGHT // 2  # 960px each

    # Pick a random start point in the gameplay video
    gameplay_duration = get_local_video_duration(gameplay_video)
    max_gp_start = max(0, gameplay_duration - clip_duration - 10)
    gp_start = random.uniform(0, max_gp_start) if max_gp_start > 0 else 0

    output_path = OUTPUT_DIR / f"{output_name}.mp4"

    # --- Build FFmpeg command ---
    inputs = [
        "-ss", str(start), "-t", str(clip_duration), "-i", str(source_video),   # [0]
        "-ss", str(gp_start), "-t", str(clip_duration), "-i", str(gameplay_video),  # [1]
    ]

    # Video filter: scale + crop + stack
    video_filter = (
        f"[0:v]scale={OUTPUT_WIDTH}:{half_height}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_WIDTH}:{half_height},setsar=1[top];"
        f"[1:v]scale={OUTPUT_WIDTH}:{half_height}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_WIDTH}:{half_height},setsar=1[bottom];"
        f"[top][bottom]vstack=inputs=2[v]"
    )

    if voiceover_audio:
        # Add voiceover as input [2], mix it with source audio [0:a]
        # Voiceover plays at the start, source audio ducks slightly during voiceover
        inputs += ["-i", str(voiceover_audio)]

        # Audio filter: lower source volume during voiceover, then mix
        audio_filter = (
            # Source audio: lower volume to 30% for duration of voiceover, then back to 100%
            f"[0:a]volume=0.3:enable='lt(t,5)'[src_duck];"
            # Voiceover: slight boost
            f"[2:a]volume=1.5,apad=pad_dur=0[vo];"
            # Mix: voiceover on top of ducked source
            f"[src_duck][vo]amix=inputs=2:duration=first:dropout_transition=2[a]"
        )
        filter_complex = video_filter + ";" + audio_filter
        map_args = ["-map", "[v]", "-map", "[a]"]
    else:
        filter_complex = video_filter
        map_args = ["-map", "[v]", "-map", "0:a?"]

    cmd = [
        _FFMPEG, "-y",
        *inputs,
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

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{result.stderr}")

    return output_path
