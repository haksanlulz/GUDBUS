"""Text formatting helpers for Discord display."""

from __future__ import annotations

import discord


def _md_escape(text: object) -> str:
    """Escape markdown + masked-link chars in untrusted sheet strings — a crafted
    .gcs could otherwise render a live [text](url) link in a public embed;
    escape_markdown leaves []() alone, so strip those here."""
    s = discord.utils.escape_markdown(str(text))
    for ch in "[]()":
        s = s.replace(ch, "\\" + ch)
    return s


def format_modifier_suffix(modifier: int) -> str:
    """Format a modifier as ' (+3)' or ' (-2)'. Empty string if zero."""
    if not modifier:
        return ""
    sign = "+" if modifier > 0 else ""
    return f" ({sign}{modifier})"


def format_attr_block(attrs: dict[str, float], calc: dict) -> str:
    lines = []
    # Primary
    st = int(attrs.get("st", 10))
    dx = int(attrs.get("dx", 10))
    iq = int(attrs.get("iq", 10))
    ht = int(attrs.get("ht", 10))
    lines.append(f"**ST** {st}  **DX** {dx}  **IQ** {iq}  **HT** {ht}")

    # Secondary
    will = int(attrs.get("will", iq))
    per = int(attrs.get("per", iq))
    lines.append(f"**Will** {will}  **Per** {per}")

    # Pools
    hp_val = int(attrs.get("hp", st))
    hp_cur = attrs.get("hp_current", hp_val)
    fp_val = int(attrs.get("fp", ht))
    fp_cur = attrs.get("fp_current", fp_val)
    lines.append(f"**HP** {int(hp_cur)}/{hp_val}  **FP** {int(fp_cur)}/{fp_val}")

    # Speed/Move
    speed = attrs.get("basic_speed", 0)
    move = int(attrs.get("basic_move", 0))
    lines.append(f"**Speed** {speed}  **Move** {move}")

    # Damage
    sw = calc.get("swing", "?")
    thr = calc.get("thrust", "?")
    lines.append(f"**Swing** {sw}  **Thrust** {thr}")

    return "\n".join(lines)


def format_skill_line(name: str, spec: str | None, level: int, rsl: str, points: int) -> str:
    display = f"{_md_escape(name)} ({_md_escape(spec)})" if spec else _md_escape(name)
    return f"`{level}` {display} [{rsl}] *{points}pts*"


def format_spell_line(name: str, level: int, college: str, cost: str) -> str:
    parts = [f"`{level}` {_md_escape(name)}"]
    if college:
        parts.append(f"*{_md_escape(college)}*")
    if cost:
        parts.append(f"Cost: {_md_escape(cost)}")
    return " — ".join(parts)


def format_trait_line(name: str, points: int, level: int | None) -> str:
    """Mechanical facts only — local_notes (often verbatim SJG prose) is deliberately not rendered."""
    base = _md_escape(name)
    if level is not None:
        base = f"{base} {level}"
    cost = f"[{points:+d}]" if points != 0 else "[0]"
    return f"{base} {cost}"


def format_equipment_line(desc: str, qty: int, weight: str, equipped: bool) -> str:
    prefix = "+" if equipped else "-"
    qty_str = f"x{qty} " if qty > 1 else ""
    return f"{prefix} {qty_str}{_md_escape(desc)} ({_md_escape(weight)})"


def paginate(items: list[str], page: int, per_page: int = 15) -> tuple[str, int, int]:
    """Returns (page_text, current_page_1indexed, total_pages)."""
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    end = start + per_page
    text = "\n".join(items[start:end]) or "*None*"
    return text, page + 1, total_pages


def format_combatant_line(
    name: str,
    basic_speed: float,
    hp_current: int,
    hp_max: int,
    fp_current: int,
    fp_max: int,
    status_effects: list[str],
    maneuver: str | None,
    is_current: bool,
    is_out: bool,
) -> str:
    from gurps_bot.mechanics.combat_constants import STATUS_ICONS, hp_bar

    pointer = "\u25b6 " if is_current else "  "
    display_name = f"~~{name}~~" if is_out else f"**{name}**"

    hp_str = hp_bar(hp_current, hp_max, width=8)
    fp_str = hp_bar(fp_current, fp_max, width=8)

    parts = [f"{pointer}{display_name}", f"Spd {basic_speed}", f"{hp_str} HP", f"{fp_str} FP"]

    icons = " ".join(STATUS_ICONS.get(s, "") for s in status_effects if s in STATUS_ICONS)
    if icons:
        parts.append(icons)
    if maneuver:
        parts.append(maneuver)

    return " | ".join(parts)
