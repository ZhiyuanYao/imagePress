"""Generate a macOS .icns bundle from static/imagePress.png."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
SOURCE = STATIC / "imagePress.png"
TARGET_ICNS = STATIC / "imagePress.icns"


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing {SOURCE}")

    if TARGET_ICNS.exists():
        TARGET_ICNS.unlink()

    subprocess.run(
        [
            "magick",
            str(SOURCE),
            "-define",
            "icon:auto-resize=16,32,64,128,256,512,1024",
            str(TARGET_ICNS),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
