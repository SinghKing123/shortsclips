"""Analyze YouTube heatmap data to find peak moments for clipping."""

import numpy as np
from scipy.signal import find_peaks
from config import MIN_CLIP_DURATION, MAX_CLIP_DURATION, PEAK_PROMINENCE

# How many seconds of lead-in before the peak moment.
# Just enough context so the viewer isn't lost, but the hook hits almost immediately.
HOOK_LEAD_IN = 2.0


def find_clip_windows(
    heatmap: list[dict],
    video_duration: float,
    max_clips: int = 5,
    min_duration: int = MIN_CLIP_DURATION,
    max_duration: int = MAX_CLIP_DURATION,
) -> list[dict]:
    """
    Analyze heatmap data and return the best clip windows.

    Clips are positioned so the peak (hook) is right at the start — viewers see
    the most exciting moment within the first few seconds.

    Peaks are ranked by a combined score of:
      - Raw intensity (how replayed that moment is)
      - Spike sharpness (how sudden the jump is — surprises grab more attention)
    """
    if not heatmap:
        return []

    times = np.array([h["start_time"] for h in heatmap])
    values = np.array([h["value"] for h in heatmap])

    # Compute the derivative (rate of change) to find sudden spikes.
    # A big positive derivative = something surprising just happened.
    derivative = np.gradient(values)
    spike_sharpness = np.maximum(derivative, 0)  # only care about upward jumps

    # Normalize both signals to 0-1
    val_norm = values / (values.max() + 1e-9)
    spike_norm = spike_sharpness / (spike_sharpness.max() + 1e-9)

    # Combined score: 50% intensity + 50% spike sharpness.
    # This favors moments that are both popular AND surprising.
    combined = 0.5 * val_norm + 0.5 * spike_norm

    # Find peaks using the combined score
    peaks, _ = find_peaks(combined, prominence=PEAK_PROMINENCE, distance=5)

    if len(peaks) == 0:
        # Also try finding peaks on raw values alone
        peaks, _ = find_peaks(values, prominence=PEAK_PROMINENCE * 0.5, distance=5)

    if len(peaks) == 0:
        # Last resort: top N highest combined-score points
        peaks = np.argsort(combined)[::-1][:max_clips * 2]

    # Sort peaks by combined score (best hooks first)
    peak_scores = combined[peaks]
    sorted_peaks = peaks[np.argsort(peak_scores)[::-1]]

    clips = []
    used_ranges = []

    for peak_idx in sorted_peaks:
        peak_time = times[peak_idx]

        # Target duration scales with intensity
        intensity = values[peak_idx]
        target_duration = min_duration + (max_duration - min_duration) * intensity
        target_duration = np.clip(target_duration, min_duration, max_duration)

        # START the clip at the peak with a tiny lead-in.
        # The hook hits almost immediately, then the clip plays forward from there.
        start = max(0, peak_time - HOOK_LEAD_IN)
        end = min(video_duration, start + target_duration)
        start = max(0, end - target_duration)

        # Snap to whole seconds
        start = float(int(start))
        end = float(int(end))

        if end - start < min_duration:
            continue

        # Check overlap with already-selected clips
        overlaps = False
        for used_start, used_end in used_ranges:
            overlap = min(end, used_end) - max(start, used_start)
            if overlap > 5:
                overlaps = True
                break

        if overlaps:
            continue

        clips.append({
            "start": start,
            "end": end,
            "score": float(combined[peak_idx]),
            "intensity": float(intensity),
            "spike": float(spike_norm[peak_idx]),
            "peak_time": float(peak_time),
        })
        used_ranges.append((start, end))

        if len(clips) >= max_clips:
            break

    return clips


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
