"""Export the approved butter artwork as the shared PNG and multi-size Windows ICO.

Run after installing the dev extra: python scripts/build_branding.py
Only canvas framing, resizing and format conversion are performed.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "branding" / "butter-source.png"
DESTINATION = ROOT / "src" / "misong" / "desktop" / "web" / "branding"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def main() -> None:
    with Image.open(SOURCE) as source:
        artwork = source.convert("RGBA")
    # Ignore the generated source's almost invisible alpha speckles when framing.
    visible = artwork.getchannel("A").point(lambda alpha: 255 if alpha >= 8 else 0)
    bounds = visible.getbbox()
    if bounds is None:
        raise ValueError("The branding source contains no visible artwork")
    artwork = artwork.crop(bounds)
    artwork.thumbnail((448, 448), Image.Resampling.LANCZOS)
    logo = Image.new("RGBA", (512, 512))
    logo.alpha_composite(artwork, ((512 - artwork.width) // 2, (512 - artwork.height) // 2))
    DESTINATION.mkdir(parents=True, exist_ok=True)
    logo.save(DESTINATION / "logo.png", optimize=True)
    logo.save(DESTINATION / "logo.ico", sizes=[(size, size) for size in ICON_SIZES])
    print("Exported logo.png (512px) and logo.ico (16-256px)")


if __name__ == "__main__":
    main()
