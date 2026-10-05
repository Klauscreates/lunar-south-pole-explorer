"""Acquire the pinned NASA SVS 4K visual-context texture; macOS format conversion."""
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/lroc_color_poles_4k.tif"
SHA = "918649a7f8ed2f1329b2cd95bb0d25483befdcb60ae1a66db681a637cc21344f"


def main():
    source = ROOT / "data/cache/lroc_color_poles_4k.tif"
    destination = ROOT / "apps/web/public/terrain/lroc_color_4k.jpg"
    source.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        subprocess.run(["curl", "-fL", "--max-time", "60", URL, "-o", str(source)], check=True)
    if hashlib.sha256(source.read_bytes()).hexdigest() != SHA:
        raise ValueError("NASA texture checksum failed; refusing to convert")
    subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "90",
                    str(source), "--out", str(destination)], check=True)
    print("Visual context only; not terrain elevation or calibrated radiometry:", destination)


if __name__ == "__main__":
    main()
