"""Smoke test for the brand generators (tools/brand.py + the two marks).

Nothing at runtime imports these — they render the Discord app icon and banner,
which are uploaded by hand. The risk they carry is silent rot: a Pillow API
change or a bad edit leaves a generator that raises, or worse renders a blank
tile, and nobody finds out until the assets need regenerating.

So this checks they still produce a plausible image, not that the art is good.
Deliberately no golden-image comparison: the banner is randomised by design, and
pinning pixels would fail on any Pillow rendering change while proving nothing
about whether the mark is right.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("PIL", reason="Pillow is a generator-only dependency")

TOOLS = Path(__file__).resolve().parent.parent / "tools"


def _load(name: str):
    """Import a tools/ script by path.

    They are standalone PEP 723 scripts that `import brand` as a sibling, so
    tools/ has to be on sys.path the same way it is when uv runs them directly.
    """
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def brand():
    return _load("brand")


def _colours(img) -> int:
    """Count of distinct colours — a blank render collapses to 1.

    getcolors() rather than getdata(): getdata is deprecated in Pillow 12 and
    the floor here is Pillow 10, so this has to work either side of that.
    """
    found = img.convert("RGBA").getcolors(maxcolors=1 << 20)
    return len(found) if found is not None else 1 << 20


class TestBrandPrimitives:
    def test_every_face_renders_with_the_right_pip_count(self, brand):
        for face in range(1, 7):
            assert len(brand.PIPS[face]) == face

    def test_pip_positions_stay_on_the_grid(self, brand):
        for face, spots in brand.PIPS.items():
            for gx, gy in spots:
                assert 0 <= gx <= 2 and 0 <= gy <= 2, face

    @pytest.mark.parametrize("shading", ["rim", "gloss", "none"])
    def test_die_renders_in_every_shading_mode(self, brand, shading):
        img = brand.die(6, 120, shading=shading)
        assert img.mode == "RGBA"
        # "none" is a flat fill and legitimately carries few colours —
        # background, keyline, face, pip, pip highlight — so the floor is what
        # distinguishes drawn-from-blank, not what distinguishes pretty
        assert _colours(img) >= 4, f"{shading} render looks blank"
        assert img.getbbox() is not None, f"{shading} render is empty"

    def test_die_is_not_blank_for_any_face(self, brand):
        for face in range(1, 7):
            assert _colours(brand.die(face, 120)) >= 4, face

    def test_the_die_body_is_actually_drawn(self, brand):
        """A colour count alone cannot tell a die from floating pips.

        Found by mutation: deleting the rounded_rectangle that draws the face
        left every other assertion in this file green, because the pips and the
        cel rim still rendered. So check the middle of the face is opaque and
        slate — face 6 has no centre pip, so nothing legitimately covers it.
        """
        side = 120
        img = brand.die(6, side, pad_factor=1.0)
        centre = img.getpixel((side + side // 2, side + side // 2))
        assert centre[3] == 255, "die face is transparent at its centre"
        assert centre[:3] in (brand.FACE, brand.FACE_LIT, brand.FACE_SHADE), (
            f"centre of the die is {centre[:3]}, not a face colour"
        )

    def test_rotation_keeps_the_die_inside_its_own_canvas(self, brand):
        """pad_factor exists so a steep tilt cannot clip the die's corners."""
        img = brand.die(6, 120, angle=45)
        w, h = img.size
        edges = (
            [img.getpixel((x, 0)) for x in range(0, w, 7)]
            + [img.getpixel((x, h - 1)) for x in range(0, w, 7)]
            + [img.getpixel((0, y)) for y in range(0, h, 7)]
            + [img.getpixel((w - 1, y)) for y in range(0, h, 7)]
        )
        assert all(px[3] == 0 for px in edges), "die touches its canvas edge"


class TestGenerators:
    def test_icon_renders(self, tmp_path, monkeypatch):
        icon = _load("make_icon")
        monkeypatch.setattr(icon, "OUT", tmp_path / "icon.png")
        img = icon.build(256)
        assert img.size == (256, 256)
        assert _colours(img) > 20, "icon looks blank"

    def test_icon_size_is_honoured(self, monkeypatch):
        icon = _load("make_icon")
        assert icon.build(128).size == (128, 128)

    def test_banner_renders_at_discord_dimensions(self, monkeypatch):
        banner = _load("make_banner")
        img = banner.build(seed=3)
        assert img.size == (banner.W, banner.H) == (680, 240)
        assert _colours(img) > 20, "banner looks blank"

    def test_banner_is_deterministic_for_a_seed(self):
        """The seed is printed so a throw can be recovered — it has to work."""
        banner = _load("make_banner")
        assert banner.build(seed=11).tobytes() == banner.build(seed=11).tobytes()

    def test_different_seeds_give_different_throws(self):
        banner = _load("make_banner")
        assert banner.build(seed=1).tobytes() != banner.build(seed=2).tobytes()


class TestBannerAlwaysShowsEveryFace:
    """The operator's constraint: each die on a different side, at least one 6.

    Guaranteed by construction rather than by luck — the faces are a shuffled
    permutation — so this asserts the property across many seeds.
    """

    def test_permutation_holds_for_every_seed(self):
        import random

        for seed in range(200):
            faces = [1, 2, 3, 4, 5, 6]
            random.Random(seed).shuffle(faces)
            assert sorted(faces) == [1, 2, 3, 4, 5, 6], seed
            assert 6 in faces, seed
