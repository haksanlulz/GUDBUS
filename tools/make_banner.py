# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10"]
# ///
"""Generate the GUDBUS app banner: a scattered throw of d6 showing every face.

    uv run --script tools/make_banner.py            # new random throw
    uv run --script tools/make_banner.py --seed 7   # reproduce one you liked

Writes `banner.png` at 680x240, Discord's app-banner size. The seed is printed
on every run, so a throw worth keeping can always be recovered.

Replaces a banner that was one wide stretched die with three pips down each
side. This draws six separate dice, and the face order is shuffled rather than
counted 1..6 — always a permutation of all six, so every side appears exactly
once and one of them is necessarily the 6.

Palette is taken from the app icon so the pair reads as one set: dark slate
faces, gold pips with a catch of light, heavy black keyline. The icon's
diagonal sweep is reworked as a cel rim rather than copied — see _die(). No
generator was kept for the original assets, which is half why this exists.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import brand
from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "banner.png"

W, H = 680, 240
SS = 4  # supersample; PIL has no shape antialiasing, so draw big and shrink

# Palette, fonts, pip layout and the die itself live in brand.py — one owner,
# shared with make_icon.py, so the two marks cannot drift apart.
BG, BG_GLOW = brand.BG, brand.BG_GLOW
OUTLINE, TEXT, TAGLINE = brand.OUTLINE, brand.TEXT, brand.TAGLINE


def _background(w: int, h: int) -> Image.Image:
    """Flat fill plus a soft pool of light behind the wordmark.

    A single flat colour is most of what made earlier versions read as empty:
    there was nothing for the eye to rest on between the type and the dice.
    """
    base = Image.new("RGB", (w, h), BG)
    glow = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(glow)
    cx, cy = w // 2, int(h * 0.40)
    rx, ry = int(w * 0.44), int(h * 0.58)
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=200)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=w // 10))
    return Image.composite(Image.new("RGB", (w, h), BG_GLOW), base, glow)


def _contact_shadow(die: Image.Image, blur: int, opacity: int) -> Image.Image:
    """Soft shadow cast from the die's own silhouette.

    Without this the dice read as printed onto the background rather than
    resting on it — the other half of why it felt flat.
    """
    alpha = die.split()[3].point(lambda a: opacity if a > 40 else 0)
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=blur))
    sh = Image.new("RGBA", die.size, (0, 0, 0, 255))
    sh.putalpha(alpha)
    return sh


def build(seed: int) -> Image.Image:
    rng = random.Random(seed)
    w, h = W * SS, H * SS
    img = _background(w, h).convert("RGBA")
    d = ImageDraw.Draw(img)

    # ---- wordmark
    title = brand.font(brand.FONT_BOLD, int(h * 0.31))
    tag = brand.font(brand.FONT_TAG, int(h * 0.092))
    ty = int(h * 0.045)

    tb = d.textbbox((0, 0), "GUDBUS", font=title)
    tx = (w - (tb[2] - tb[0])) // 2 - tb[0]
    brand.outlined_text(d, (tx, ty), "GUDBUS", title, TEXT,
                        ring=max(3, int(h * 0.013)))

    sub = "GURPS 4e TABLE AID"
    sb = d.textbbox((0, 0), sub, font=tag)
    sx = (w - (sb[2] - sb[0])) // 2 - sb[0]
    sy = ty + int(h * 0.31) + int(h * 0.026)
    d.text((sx, sy), sub, font=tag, fill=TAGLINE)

    # ---- the throw: a shuffled permutation of all six faces
    faces = [1, 2, 3, 4, 5, 6]
    rng.shuffle(faces)

    margin, gap_ratio = 0.05, 0.19
    usable = w * (1 - margin * 2)
    side = int(usable / (len(faces) + (len(faces) - 1) * gap_ratio))
    side = min(side, int(h * 0.325))
    gap = int((usable - side * len(faces)) / (len(faces) - 1))

    total = side * len(faces) + gap * (len(faces) - 1)
    x = (w - total) // 2
    row_mid = int(h * 0.725)

    placed = []
    for face in faces:
        # jitter rather than a fixed alternating tilt, which still reads as a
        # row of stamps instead of dice that were actually thrown
        angle = rng.uniform(-17, 17)
        jx = int(rng.uniform(-0.035, 0.035) * side)
        jy = int(rng.uniform(-0.07, 0.07) * side)
        die = brand.die(face, side, angle, shading="rim")
        placed.append((die, (x - side + jx, row_mid - die.height // 2 + jy)))
        x += side + gap

    # shadows first, all of them, so no die casts onto another die's face
    for die, (px, py) in placed:
        sh = _contact_shadow(die, blur=max(5, side // 8), opacity=150)
        img.alpha_composite(sh, (px, py + int(side * 0.11)))
    for die, pos in placed:
        img.alpha_composite(die, pos)

    return img.resize((W, H), Image.LANCZOS).convert("RGB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=None,
                    help="reproduce a specific throw (the seed is printed each run)")
    args = ap.parse_args()
    seed = args.seed if args.seed is not None else random.randrange(1_000_000)

    banner = build(seed)
    banner.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT} ({banner.width}x{banner.height})  seed={seed}")
