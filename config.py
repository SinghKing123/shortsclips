"""Default configuration and gameplay video sources."""

from pathlib import Path

# Directories
BASE_DIR = Path(__file__).parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
GAMEPLAY_DIR = BASE_DIR / "gameplay"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"

for d in [DOWNLOADS_DIR, GAMEPLAY_DIR, OUTPUT_DIR, TEMP_DIR]:
    d.mkdir(exist_ok=True)

# Short clip settings
MIN_CLIP_DURATION = 15   # seconds
MAX_CLIP_DURATION = 59   # seconds (YouTube Shorts limit)
DEFAULT_CLIP_COUNT = 5
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
FPS = 30

# Peak detection — how sensitive the heatmap peak finder is.
# Lower = more clips found, higher = only the biggest spikes.
PEAK_PROMINENCE = 0.15

# Default gameplay options (long, generic gameplay loops on YouTube)
GAMEPLAY_OPTIONS = {
    "minecraft_parkour": {
        "name": "Minecraft Parkour",
        "url": "https://www.youtube.com/watch?v=n_Dv4JMiwK8",
    },
    "subway_surfers": {
        "name": "Subway Surfers",
        "url": "https://www.youtube.com/watch?v=zZ7AimPACzc",
    },
    "gta_driving": {
        "name": "GTA Night Drive",
        "url": "https://www.youtube.com/watch?v=sofeqXN4JCg",
    },
    "slicing_asmr": {
        "name": "Slicing ASMR",
        "url": "https://www.youtube.com/watch?v=lqW69i5-Sxw",
    },
    "soap_asmr": {
        "name": "Soap Cutting ASMR",
        "url": "https://www.youtube.com/watch?v=J9dvPQuHz-I",
    },
}

DEFAULT_GAMEPLAY = "minecraft_parkour"
