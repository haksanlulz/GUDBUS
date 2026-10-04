"""Quick reference — which command answers what, with page cites.

Each page names the commands that answer one row at a time and the book page to
read; it lists the names of the options (postures, locations, maneuvers) but
never their values in book order. Every name is read from the mechanics module
that owns it.
"""

from __future__ import annotations

import discord

from gurps_bot.mechanics.combat_constants import STATUS_ICONS, Maneuver, StatusEffect
from gurps_bot.mechanics.hit_location import deliberate_locations, gross_targeting_reference
from gurps_bot.mechanics.posture import POSTURES
from gurps_bot.mechanics.tables import (
    CRITICAL_TABLES,
    FRIGHT_TABLE_MAX,
    FRIGHT_TABLE_MIN,
    FRIGHT_TABLE_PAGES,
)
from gurps_bot.ui.embeds import EMBED_FIELD_LIMIT

# page order; /screen's category choice jumps to one of these
CATEGORIES: tuple[str, ...] = (
    "combat", "body", "ranged", "movement", "rolls", "fright",
)
CATEGORY_INDEX: dict[str, int] = {c: i for i, c in enumerate(CATEGORIES)}

_TITLE = "Quick reference"

_COMBAT = discord.Color.dark_orange()
_BLUE = discord.Color.blue()
_GREEN = discord.Color.green()
_GOLD = discord.Color.gold()
_PURPLE = discord.Color.purple()
_RED = discord.Color.dark_red()


def _cap(text: str, limit: int = EMBED_FIELD_LIMIT) -> str:
    """Truncate an embed-field body to Discord's 1024-char cap (safety net)."""
    if len(text) <= limit:
        return text
    return text[: limit - 15] + "\n…(truncated)"


# ---------------------------------------------------------------------------
# Names, read from their owners
# ---------------------------------------------------------------------------
def maneuver_names() -> list[str]:
    return [m.value for m in Maneuver]


def status_effects() -> list[tuple[str, str]]:
    return [(s.value, STATUS_ICONS[s]) for s in StatusEffect]


def posture_names() -> list[str]:
    return [p.name for p in POSTURES]


def deliberate_location_names() -> list[str]:
    return [loc.name for loc in deliberate_locations()]


def body_part_names() -> list[str]:
    return [name for name, _penalty, _effect in gross_targeting_reference()]


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def combat_page() -> discord.Embed:
    e = discord.Embed(title=f"{_TITLE}: Combat", color=_COMBAT)
    e.add_field(
        name="Maneuvers (B363) · `/combat maneuver`",
        value="\n".join(f"• {m}" for m in maneuver_names()),
        inline=True,
    )
    e.add_field(
        name="Status effects · `/combat status`",
        value="\n".join(f"{icon} {name}" for name, icon in status_effects()),
        inline=True,
    )
    return e


def body_page() -> discord.Embed:
    e = discord.Embed(title=f"{_TITLE}: Body", color=_RED)
    e.add_field(
        name="Posture (B551) · `/posture`",
        value=_cap(" · ".join(posture_names())),
        inline=False,
    )
    e.add_field(
        name="Deliberate targeting (B552) · `/target`",
        value=_cap(" · ".join(deliberate_location_names())),
        inline=False,
    )
    e.add_field(
        name="Hit locations (B552) · `/hit-location` rolls one",
        value=_cap(" · ".join(body_part_names())),
        inline=False,
    )
    return e


def ranged_page() -> discord.Embed:
    e = discord.Embed(title=f"{_TITLE}: Range and size", color=_BLUE)
    e.description = (
        "• `/range` — the speed/range penalty for a distance (B550)\n"
        "• `/size` — the Size Modifier for a length (B19)\n"
        "• `/ranged` — range, speed and size combined for one shot (B550)"
    )
    return e


def movement_page() -> discord.Embed:
    e = discord.Embed(title=f"{_TITLE}: Movement", color=_GREEN)
    e.description = (
        "• `/encumbrance` — encumbrance level, Move and Dodge (B17)\n"
        "• `/lifting` — lift, shove and drag (B353)\n"
        "• `/hike` — a day's travel by terrain and weather (B351)\n"
        "• `/jump`, `/swim`, `/throw` — B352, B354, B355"
    )
    return e


def rolls_page() -> discord.Embed:
    e = discord.Embed(title=f"{_TITLE}: Reactions and criticals", color=_GOLD)
    e.add_field(
        name="Reactions (B560)",
        value="`/reaction roll` rolls one; `/reaction band` reads a total you already have.",
        inline=False,
    )
    # The critical tables' result rows are the book's text and are not
    # reproduced (SJG Online Policy); the bot names the table and the page.
    e.add_field(
        name="Critical tables — roll 3d",
        value="\n".join(f"• {t.name} ({t.page})" for t in CRITICAL_TABLES),
        inline=False,
    )
    return e


def fright_page() -> discord.Embed:
    return discord.Embed(
        title=f"{_TITLE}: Fright Check ({FRIGHT_TABLE_PAGES})",
        description=(
            "Roll vs Will — capped at 13 if the Rule of 14 is on (see /campaign show). "
            "On a failure: roll 3d + margin of failure, and read that total "
            f"({FRIGHT_TABLE_MIN}-{FRIGHT_TABLE_MAX}+) on the Fright Check Table, "
            f"{FRIGHT_TABLE_PAGES}. `/fright-check` does the arithmetic."
        ),
        color=_PURPLE,
    )


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
        page.set_footer(text=f"{_TITLE} {i}/{total} · each command answers one row")
    return pages
