# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10"]
# ///
"""Generate the GUDBUS app icon: a d6 showing six, with a G on the face.

    uv run --script tools/make_icon.py               # 1024x1024
    uv run --script tools/make_icon.py --size 512

Writes `icon.png` beside the repo root.

Reconstructed 2026-07-27. The original icon was produced by a throwaway script
that was not kept, so the mark could not be re-rendered at another size or
adjusted — the palette here was read back off the shipped PNG. Style lives in
`brand.py` alongside the banner's, so the two cannot drift.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import brand
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "icon.png"

SS = 2  # supersample; the mark is already large, so 2x is enough to smooth edges


def build(size: int) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (*brand.BG, 255))

    # the die fills the tile with a small breathing margin
    margin = int(s * 0.045)
    side = s - margin * 2
    face = brand.die(6, side, pad_factor=0.0, pip_scale=0.92,
                     shading="gloss")
    img.alpha_composite(face, (margin, margin))

    # the G sits on the face, between the two columns of pips
    d = ImageDraw.Draw(img)
    g_font = brand.font(brand.FONT_BOLD, int(s * 0.52))
    bb = d.textbbox((0, 0), "G", font=g_font)
    gx = (s - (bb[2] - bb[0])) // 2 - bb[0]
    gy = (s - (bb[3] - bb[1])) // 2 - bb[1]
    brand.outlined_text(d, (gx, gy), "G", g_font, brand.TEXT,
                        ring=max(4, int(s * 0.016)))

    return img.resize((size, size), Image.LANCZOS).convert("RGB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Render the GUDBUS app icon.")
    ap.add_argument("--size", type=int, default=1024,
                    help="output edge in pixels (default 1024)")
    args = ap.parse_args()

    icon = build(args.size)
    icon.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT} ({icon.width}x{icon.height})")
