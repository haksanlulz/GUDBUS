"""GM quick-reference screen — layout only; every number it renders is imported from the mechanics module that owns it."""

from __future__ import annotations

import discord

from gurps_bot.mechanics import encumbrance as enc
from gurps_bot.mechanics import hiking
from gurps_bot.mechanics import speed_range as sr
from gurps_bot.mechanics.combat_constants import STATUS_ICONS, Maneuver, StatusEffect
from gurps_bot.mechanics.hit_location import deliberate_locations, gross_targeting_reference
from gurps_bot.mechanics.posture import POSTURES
from gurps_bot.mechanics.reaction import REACTION_BANDS
from gurps_bot.mechanics.tables import (
    CRITICAL_HIT_TABLE,
    CRITICAL_MISS_TABLE,
    FRIGHT_CHECK_TABLE,
)
from gurps_bot.ui.embeds import EMBED_FIELD_LIMIT

# imported, not retyped — ui/embeds.EMBED_FIELD_LIMIT owns the 1024
_EMBED_FIELD_LIMIT = EMBED_FIELD_LIMIT

# display rows only — every penalty/SM value is still queried from speed_range
SAMPLE_DISTANCES: tuple[float, ...] = (
    2, 3, 5, 7, 10, 15, 20, 30, 50, 70, 100, 150, 200, 300, 500,
)
SAMPLE_SIZES: tuple[float, ...] = (
    0.1, 0.2, 0.5, 1, 1.5, 2, 3, 5, 10, 20, 50, 100,
)

# page order; /screen's category choice jumps to one of these
CATEGORIES: tuple[str, ...] = ("combat", "body", "ranged", "movement", "rolls", "fright")
CATEGORY_INDEX: dict[str, int] = {c: i for i, c in enumerate(CATEGORIES)}

_COMBAT = discord.Color.dark_orange()
_BLUE = discord.Color.blue()
_GREEN = discord.Color.green()
_GOLD = discord.Color.gold()
_PURPLE = discord.Color.purple()
_RED = discord.Color.dark_red()


def _yd(value: float) -> str:
    return f"{value:g}yd"


def _cap(text: str, limit: int = _EMBED_FIELD_LIMIT) -> str:
    """Truncate an embed-field body to Discord's 1024-char cap (safety net)."""
    if len(text) <= limit:
        return text
    return text[: limit - 15] + "\n…(truncated)"


# ---------------------------------------------------------------------------
# Pure data builders (no discord) — each reflects its owning mechanics module
# ---------------------------------------------------------------------------
def maneuver_names() -> list[str]:
    return [m.value for m in Maneuver]


def status_effects() -> list[tuple[str, str]]:
    return [(s.value, STATUS_ICONS[s]) for s in StatusEffect]


def encumbrance_reference() -> list[tuple[str, float, int, float]]:
    """(name, move mult, dodge penalty, max BL multiple) — queried at BL=1 so max_weight is the bare multiple."""
    return [
        (t.name, t.move_multiplier, t.dodge_penalty, t.max_weight)
        for t in enc.encumbrance_thresholds(1)
    ]


def terrain_reference() -> list[tuple[str, float]]:
    return [(t.name.replace("_", " ").title(), t.mult) for t in hiking.Terrain]


def weather_reference() -> list[tuple[str, float]]:
    return [(w.name.replace("_", " ").title(), w.mult) for w in hiking.Weather]


def speed_range_reference() -> list[tuple[float, int]]:
    return [(d, sr.speed_range_penalty(d)) for d in SAMPLE_DISTANCES]


def size_reference() -> list[tuple[float, int]]:
    return [(length, sr.size_modifier(length)) for length in SAMPLE_SIZES]


def reaction_reference() -> list[tuple[str, str]]:
    """(band name, adjusted-total range) — the two ends are open-ended."""
    rows: list[tuple[str, str]] = []
    last = len(REACTION_BANDS) - 1
    for i, band in enumerate(REACTION_BANDS):
        if i == 0:
            rng = f"≤{band.upper}"
        elif i == last:
            rng = f"≥{band.lower}"
        else:
            rng = f"{band.lower}-{band.upper}"
        rows.append((band.name, rng))
    return rows


def fright_reference() -> dict[int, str]:
    return FRIGHT_CHECK_TABLE


def crit_hit_reference() -> dict[int, str]:
    return CRITICAL_HIT_TABLE


def crit_miss_reference() -> dict[int, str]:
    return CRITICAL_MISS_TABLE


def posture_reference() -> list[dict]:
    """One dict per B551 posture, every field read from mechanics/posture.py."""
    return [
        {
            "name": p.name,
            "attack": p.attack_penalty,
            "defense": p.defense_modifier,
            "ranged": p.ranged_to_hit_you,
            "melee": p.melee_to_hit_you,
            "move": p.move_fraction,
            "effect": p.effect,
        }
        for p in POSTURES
    ]


def targeting_reference() -> list[dict]:
    """Deliberate-only hit locations the random 3d6 table omits (B552)."""
    return [
        {"name": loc.name, "penalty": loc.penalty, "effect": loc.effect}
        for loc in deliberate_locations()
    ]


def gross_target_reference() -> list[dict]:
    """Gross 3d6 body locations + aim penalty per spot, read from the random-table owner."""
    return [
        {"name": name, "penalty": penalty}
        for name, penalty, _effect in gross_targeting_reference()
    ]


# ---------------------------------------------------------------------------
# Page builders (discord.Embed) — layout only
# ---------------------------------------------------------------------------
def combat_page() -> discord.Embed:
    e = discord.Embed(title="GM Screen — Combat", color=_COMBAT)
    e.add_field(
        name="Maneuvers (B363)",
        value="\n".join(f"• {m}" for m in maneuver_names()),
        inline=True,
    )
    e.add_field(
        name="Status Effects",
        value="\n".join(f"{icon} {name}" for name, icon in status_effects()),
        inline=True,
    )
    return e


def ranged_page() -> discord.Embed:
    e = discord.Embed(title="GM Screen — Speed/Range & Size (B550)", color=_BLUE)
    e.add_field(
        name="Speed/Range penalty",
        value="\n".join(f"`{_yd(d):>6}` {p}" for d, p in speed_range_reference()),
        inline=True,
    )
    e.add_field(
        name="Size Modifier",
        value="\n".join(f"`{_yd(length):>6}` {sm:+d}" for length, sm in size_reference()),
        inline=True,
    )
    return e


def movement_page() -> discord.Embed:
    e = discord.Embed(title="GM Screen — Movement", color=_GREEN)
    e.add_field(
        name="Encumbrance (B17)",
        value="\n".join(
            f"**{name}** ×{move:g} Move · Dodge -{dodge} · ≤{bl:g}×BL"
            for name, move, dodge, bl in encumbrance_reference()
        ),
        inline=False,
    )
    e.add_field(
        name="Travel terrain (B351)",
        value=" · ".join(f"{n} ×{m:g}" for n, m in terrain_reference()),
        inline=False,
    )
    e.add_field(
        name="Travel weather (B351)",
        value=" · ".join(f"{n} ×{m:g}" for n, m in weather_reference()),
        inline=False,
    )
    return e


def rolls_page() -> discord.Embed:
    e = discord.Embed(title="GM Screen — Reaction & Criticals", color=_GOLD)
    e.add_field(
        name="Reaction (B560)",
        value="\n".join(f"`{rng:>5}` {name}" for name, rng in reaction_reference()),
        inline=False,
    )
    e.add_field(
        name="Critical Hit — 3d6 (B556)",
        value=_cap("\n".join(f"`{r:>2}` {eff}" for r, eff in sorted(crit_hit_reference().items()))),
        inline=True,
    )
    e.add_field(
        name="Critical Miss — 3d6 (B556)",
        value=_cap("\n".join(f"`{r:>2}` {eff}" for r, eff in sorted(crit_miss_reference().items()))),
        inline=True,
    )
    return e


def fright_page() -> discord.Embed:
    e = discord.Embed(
        title="GM Screen — Fright Check (B360)",
        description="Roll vs HT (or Will); read the margin of failure here.",
        color=_PURPLE,
    )
    items = sorted(fright_reference().items())
    e.add_field(
        name="Margin 0-9",
        value=_cap("\n".join(f"`{m:>2}` {eff}" for m, eff in items if m < 10)),
        inline=False,
    )
    e.add_field(
        name="Margin 10-19",
        value=_cap("\n".join(f"`{m:>2}` {eff}" for m, eff in items if m >= 10)),
        inline=False,
    )
    return e


def _move_label(fraction: float) -> str:
    """Render a Move fraction compactly: 1.0 -> 'full', 0 -> 'none', else 'x2/3'."""
    if fraction >= 1.0:
        return "full"
    if fraction <= 0.0:
        return "none"
    # recognise the canonical thirds; round anything else
    if abs(fraction - 2 / 3) < 1e-6:
        return "×2/3"
    if abs(fraction - 1 / 3) < 1e-6:
        return "×1/3"
    return f"×{fraction:.2g}"


def body_page() -> discord.Embed:
    """Posture (B551) + deliberate targeting (B552) — the data the random 3d6 table omits."""
    e = discord.Embed(
        title="GM Screen - Body (Posture & Targeting)",
        description="Att/Def = to your melee attack/defense · Rngd/Mle = to hit you.",
        color=_RED,
    )
    posture_lines = []
    for p in posture_reference():
        posture_lines.append(
            f"**{p['name']}** Att {p['attack']:+d} · Def {p['defense']:+d} · "
            f"Rngd {p['ranged']:+d} · Mle {p['melee']:+d} · Move {_move_label(p['move'])}"
        )
    e.add_field(name="Posture (B551)", value=_cap("\n".join(posture_lines)), inline=False)

    # effect notes are original summaries, not SJG text
    e.add_field(
        name="Posture notes",
        value=_cap("\n".join(f"**{p['name']}** — {p['effect']}" for p in posture_reference())),
        inline=False,
    )

    target_lines = [
        f"`{r['penalty']:>3}` **{r['name']}** — {r['effect']}"
        for r in targeting_reference()
    ]
    e.add_field(
        name="Deliberate targeting (B552)",
        value=_cap("\n".join(target_lines)),
        inline=False,
    )

    gross_lines = [
        f"`{g['penalty']:>3}` {g['name']}" for g in gross_target_reference()
    ]
    e.add_field(
        name="Aim at a body part (B552) · `/hit-location` rolls one",
        value=_cap(" · ".join(gross_lines)),
        inline=False,
    )
    return e


_PAGE_BUILDERS = (
    combat_page,
    body_page,
    ranged_page,
    movement_page,
    rolls_page,
    fright_page,
)


def build_screen_pages() -> list[discord.Embed]:
    pages = [build() for build in _PAGE_BUILDERS]
    total = len(pages)
    for i, page in enumerate(pages, start=1):
        page.set_footer(text=f"GM Screen {i}/{total} · GURPS quick-reference")
    return pages
