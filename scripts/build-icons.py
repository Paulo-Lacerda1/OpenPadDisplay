#!/usr/bin/python3
"""Resize the shared master artwork into Linux and Android launcher assets."""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "android/app/src/main/res"
MASTER = ROOT / "assets/branding/openpaddisplay.png"


def main():
    with Image.open(MASTER) as source:
        image = source.convert("RGB")
        image.resize((512, 512), Image.Resampling.LANCZOS).save(
            ROOT / "assets/branding/openpaddisplay-512.png", optimize=True
        )
        for density, size in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96),
                              ("xxhdpi", 144), ("xxxhdpi", 192)):
            folder = RES / f"mipmap-{density}"
            folder.mkdir(parents=True, exist_ok=True)
            image.resize((size, size), Image.Resampling.LANCZOS).save(
                folder / "ic_launcher.png", optimize=True
            )
        folder = RES / "drawable-nodpi"
        folder.mkdir(parents=True, exist_ok=True)
        image.resize((432, 432), Image.Resampling.LANCZOS).save(
            folder / "launcher_artwork.png", optimize=True
        )


if __name__ == "__main__":
    main()
