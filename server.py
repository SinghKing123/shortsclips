"""ShortsClips — Flask web app backend."""

import os
import json
import threading
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file

from config import GAMEPLAY_OPTIONS, OUTPUT_DIR, DEFAULT_CLIP_COUNT
from downloader import (
    download_video, get_heatmap_data, get_video_duration,
    download_gameplay, extract_video_id, _ytdlp,
)
from heatmap import find_clip_windows, format_timestamp
from composer import compose_short

app = Flask(__name__, static_folder="static")

# Track jobs: {job_id: {status, progress, logs, clips, error}}
jobs = {}


def _log(job_id: str, message: str, level: str = "info"):
    if job_id in jobs:
        jobs[job_id]["logs"].append({"message": message, "level": level})


def _run_job(job_id: str, url: str, gameplay_key: str, max_clips: int):
    try:
        jobs[job_id]["status"] = "running"

        # Step 1: Heatmap
        _log(job_id, "Fetching video info & heatmap...", "bold")
        result = _ytdlp("--skip-download", "--print", "title", "--no-playlist", url)
        title = result.stdout.strip() if result.returncode == 0 else "Unknown"
        _log(job_id, f"Video: {title}")

        heatmap = get_heatmap_data(url)
        duration = get_video_duration(url)

        if not heatmap:
            _log(job_id, "No heatmap data — video needs more views", "error")
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "No heatmap data available. Try a more popular video."
            return

        _log(job_id, f"Found {len(heatmap)} heatmap points", "success")
        clips = find_clip_windows(heatmap, duration, max_clips=max_clips)

        if not clips:
            _log(job_id, "No suitable clips found", "error")
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "Could not find any clip-worthy moments."
            return

        _log(job_id, f"Found {len(clips)} clips:", "success")
        for i, c in enumerate(clips):
            dur = c["end"] - c["start"]
            _log(job_id,
                 f"  {i+1}. {format_timestamp(c['start'])} -> {format_timestamp(c['end'])} "
                 f"({dur:.0f}s) pop={c.get('intensity', 0):.0%} surprise={c.get('spike', 0):.0%}")

        jobs[job_id]["total"] = len(clips)

        # Step 2: Download source
        _log(job_id, "Downloading source video...", "bold")
        source_path = download_video(url)
        _log(job_id, f"Source ready: {source_path.name}", "success")

        # Step 3: Download gameplay
        gp_name = GAMEPLAY_OPTIONS[gameplay_key]["name"]
        _log(job_id, f"Downloading {gp_name}...", "bold")
        gameplay_path = download_gameplay(gameplay_key, GAMEPLAY_OPTIONS)
        _log(job_id, "Gameplay ready", "success")

        # Step 4: Render shorts
        _log(job_id, f"Rendering {len(clips)} shorts...", "bold")
        video_id = extract_video_id(url)
        output_files = []

        for i, clip in enumerate(clips):
            jobs[job_id]["progress"] = i
            _log(job_id, f"  Rendering {i+1}/{len(clips)}...")

            output_name = f"{video_id}_short_{i+1}"
            output_path = compose_short(
                source_video=source_path,
                gameplay_video=gameplay_path,
                start=clip["start"],
                end=clip["end"],
                output_name=output_name,
            )
            output_files.append(output_path.name)
            _log(job_id, f"  Done: {output_path.name}", "success")

        jobs[job_id]["progress"] = len(clips)
        jobs[job_id]["clips"] = output_files
        jobs[job_id]["status"] = "done"
        _log(job_id, f"All done! {len(clips)} shorts ready", "success")

    except Exception as e:
        _log(job_id, f"Error: {e}", "error")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


# --- Routes ---

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")


@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js")


@app.route("/icon-192.png")
def icon_192():
    return send_from_directory("static", "icon-192.png")


@app.route("/icon-512.png")
def icon_512():
    return send_from_directory("static", "icon-512.png")


@app.route("/api/gameplay")
def get_gameplay_options():
    options = [
        {"key": k, "name": v["name"]}
        for k, v in GAMEPLAY_OPTIONS.items()
    ]
    return jsonify(options)


@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.json
    url = data.get("url", "").strip()
    gameplay = data.get("gameplay", "minecraft_parkour")
    max_clips = data.get("clips", DEFAULT_CLIP_COUNT)

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    if gameplay not in GAMEPLAY_OPTIONS:
        return jsonify({"error": "Invalid gameplay option"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "starting",
        "progress": 0,
        "total": 0,
        "logs": [],
        "clips": [],
        "error": None,
    }

    thread = threading.Thread(target=_run_job, args=(job_id, url, gameplay, max_clips), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Return logs since last check
    since = request.args.get("since", 0, type=int)
    return jsonify({
        "status": job["status"],
        "progress": job["progress"],
        "total": job["total"],
        "logs": job["logs"][since:],
        "log_count": len(job["logs"]),
        "clips": job["clips"],
        "error": job["error"],
    })


@app.route("/api/download/<filename>")
def download_clip(filename):
    # Sanitize filename
    safe_name = Path(filename).name
    file_path = OUTPUT_DIR / safe_name
    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path, as_attachment=True)


@app.route("/api/stream/<filename>")
def stream_clip(filename):
    safe_name = Path(filename).name
    file_path = OUTPUT_DIR / safe_name
    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path, mimetype="video/mp4")


def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5555))
    ip = get_local_ip()
    print("")
    print("  ==========================================")
    print("           ShortsClips Running")
    print("  ==========================================")
    print(f"  Local:  http://localhost:{port}")
    print(f"  Phone:  http://{ip}:{port}")
    print("  ==========================================")
    print("")
    app.run(host="0.0.0.0", port=port, debug=False)
