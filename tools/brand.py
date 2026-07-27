"""Shared GUDBUS brand primitives — palette and the d6 the marks are built from.

Imported by `make_icon.py` and `make_banner.py`, which are otherwise standalone
PEP 723 scripts (a script's own directory lands on sys.path, so a plain
`import brand` resolves). One owner for the palette so the icon and the banner
cannot drift apart — the original assets were produced by a throwaway script
that was not kept, and the colours had to be read back off the PNGs to write
this.

Treatment, in one place:
  * dark slate face, heavy near-black keyline, sticker-weight
  * gold pips, each outlined, each with a catch of light up-left
  * cel shading as a RIM (lit edge up-left, shaded edge down-right), never a
    diagonal fill across the face — see `die()`
"""

from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw

# --- palette --------------------------------------------------------------
BG = (26, 26, 30)
BG_GLOW = (46, 47, 58)
FACE = (79, 83, 101)
FACE_LIT = (108, 113, 134)
FACE_SHADE = (52, 55, 68)
OUTLINE = (17, 17, 20)
PIP = (240, 180, 41)
PIP_LIT = (250, 214, 120)
TEXT = (238, 238, 240)
TAGLINE = (240, 180, 41)

FONT_BOLD = "C:/Windows/Fonts/ariblk.ttf"
FONT_TAG = "C:/Windows/Fonts/arialbd.ttf"

#: pip positions on a 3x3 grid, by face value
PIPS: dict[int, list[tuple[int, int]]] = {
    1: [(1, 1)],
    2: [(0, 0), (2, 2)],
    3: [(0, 0), (1, 1), (2, 2)],
    4: [(0, 0), (2, 0), (0, 2), (2, 2)],
    5: [(0, 0), (2, 0), (1, 1), (0, 2), (2, 2)],
    6: [(0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2)],
}


def font(path: str, size: int):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(path, size)
    except OSError:  # no such font on this box — legible beats nothing
        return ImageFont.load_default()


def cel_rim(img: Image.Image, box: tuple[int, int, int, int], radius: int,
            edge: int, band: int) -> None:
    """Lit edge up-left, shaded edge down-right, drawn onto ``img`` in place.

    Cel shading as a rim rather than a fill. A diagonal half-split reads as a
    crease down the middle of the face and a corner wedge reads as a grey patch
    stuck on — both were tried. A rim gives the same hard-edged light and never
    crosses the pips, and it holds up when the mark is scaled down.
    """
    x0, y0, x1, y1 = box
    w, h = img.size
    inner = [x0 + edge, y0 + edge, x1 - edge, y1 - edge]
    for colour, wedge in (
        (FACE_LIT, [(0, 0), (w, 0), (0, h)]),
        (FACE_SHADE, [(w, 0), (w, h), (0, h)]),
    ):
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(
            inner, radius=max(1, radius - edge), outline=colour, width=band
        )
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).polygon(wedge, fill=255)
        layer.putalpha(ImageChops.multiply(layer.split()[3], mask))
        img.alpha_composite(layer)


def pip(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
        edge: int) -> None:
    """One gold pip with its keyline and catch of light."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r],
              fill=PIP, outline=OUTLINE, width=max(2, edge))
    lr = r * 0.46
    d.ellipse([cx - r * 0.42 - lr, cy - r * 0.42 - lr,
               cx - r * 0.42 + lr, cy - r * 0.42 + lr], fill=PIP_LIT)


def cel_gloss(img: Image.Image, box: tuple[int, int, int, int], radius: int,
              edge: int) -> None:
    """One hard diagonal sweep across the upper-left, drawn in place.

    The counterpart to :func:`cel_rim`, and the choice is a matter of scale, not
    taste. A big tile carries a diagonal fine — it is what the app icon has
    always had. Shrink the same treatment to a 70px die and the split reads as a
    crease down the middle of the face, which is why the banner uses the rim.
    """
    x0, y0, x1, y1 = box
    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon(
        [(x0, y0), (x1, y0), (x0, y1)], fill=(*FACE_LIT, 255)
    )
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [x0 + edge, y0 + edge, x1 - edge, y1 - edge],
        radius=max(1, radius - edge), fill=255,
    )
    layer.putalpha(ImageChops.multiply(layer.split()[3], mask))
    img.alpha_composite(layer)


def die(face: int, side: int, angle: float = 0.0, *, pad_factor: float = 1.0,
        pip_scale: float = 1.0, shading: str = "rim") -> Image.Image:
    """A cel-shaded d6 on transparent ground, rotated by ``angle`` degrees.

    ``pad_factor`` sizes the transparent margin as a multiple of ``side``; a
    steep tilt needs room or the rotation clips the die's own corners.
    ``shading`` is ``"rim"`` (small dice), ``"gloss"`` (large tiles) or
    ``"none"`` — see :func:`cel_gloss` for why that depends on size.
    """
    pad = int(side * pad_factor)
    box_px = side + pad * 2
    img = Image.new("RGBA", (box_px, box_px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    x0, y0, x1, y1 = pad, pad, pad + side, pad + side
    radius = side // 5
    edge = max(3, side // 19)  # sticker weight

    d.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=FACE,
                        outline=OUTLINE, width=edge)
    if shading == "rim":
        cel_rim(img, (x0, y0, x1, y1), radius, edge, band=max(3, side // 13))
    elif shading == "gloss":
        cel_gloss(img, (x0, y0, x1, y1), radius, edge)
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius, outline=OUTLINE,
                        width=edge)

    cell = side / 3
    pr = (side / 11) * pip_scale
    for gx, gy in PIPS[face]:
        pip(d, x0 + cell * gx + cell / 2, y0 + cell * gy + cell / 2, pr,
            edge=max(2, edge // 2))

    if angle:
        img = img.rotate(angle, resample=Image.BICUBIC, expand=False)
    return img


def outlined_text(d: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
                  font_obj, fill, ring: int) -> None:
    """Text with a solid keyline, matching the marks' outlined lettering.

    Drawn as a filled disc of offsets rather than a stroke so the outline stays
    even on the diagonals of heavy letterforms.
    """
    x, y = xy
    for dx in range(-ring, ring + 1):
        for dy in range(-ring, ring + 1):
            if dx * dx + dy * dy <= ring * ring:
                d.text((x + dx, y + dy), text, font=font_obj, fill=OUTLINE)
    d.text((x, y), text, font=font_obj, fill=fill)
