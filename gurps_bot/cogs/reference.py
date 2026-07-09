"""/skill /trait /spell /technique /item lookups — mechanical facts + page cites, never rulebook prose."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Callable, Protocol

import discord
from discord import app_commands
from discord.ext import commands

from gurps_bot.utils.fuzzy import fuzzy_match

# gcs template token ("@Specialty@", bare or embedded) — must never reach a user
_TEMPLATE_TOKEN = re.compile(r"@[^@]*@")

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)

_REF_COLOR = discord.Color.dark_teal()

_FOOTER = "GURPS facts per SJG Online Policy - see /legal"

_NOT_SYNCED = (
    "Reference data is not synced yet — run `tools/sync_gcs_library.py` to vendor "
    "the GCS master library, then restart the bot."
)

# /item maps to the 'equipment' catalog, whose name field is 'description'
CATEGORIES: dict[str, str] = {
    "skill": "skills",
    "trait": "traits",
    "spell": "spells",
    "technique": "techniques",
    "item": "equipment",
}

_DIFFICULTY = {"e": "Easy", "a": "Average", "h": "Hard", "vh": "Very Hard"}
_ATTRIBUTE = {
    "st": "ST", "dx": "DX", "iq": "IQ", "ht": "HT", "per": "Per", "will": "Will",
}


class ReferenceService(Protocol):
    """What the cog needs from the reference service (real impl: services/reference)."""

    def names(self, category: str) -> list[str]: ...

    def get(self, category: str, name: str) -> dict | None: ...


def _decode_attr(code: str) -> str:
    """'dx' -> 'DX'. Pass through unknown tokens verbatim (e.g. templates)."""
    return _ATTRIBUTE.get(code.lower(), code.upper() if len(code) <= 3 else code)


def _decode_difficulty(raw: str | None) -> str:
    """'dx/h' -> 'DX/Hard' (skills/spells); bare 'h' -> 'Hard' (techniques)."""
    if not raw:
        return ""
    if "/" in raw:
        attr, _, diff = raw.partition("/")
        return f"{_decode_attr(attr)}/{_DIFFICULTY.get(diff.lower(), diff)}"
    return _DIFFICULTY.get(raw.lower(), raw)


def _format_reference(raw: str | None) -> str:
    """Page cite '<BookCode><Page>'; may be comma-separated -> 'B208, MA54'."""
    if not raw:
        return "—"
    return ", ".join(part.strip() for part in raw.split(",") if part.strip())


def _format_tech_level(raw: Any) -> str | None:
    """Tech level fact, or None when absent/blank."""
    if raw in (None, ""):
        return None
    return str(raw)


def _signed(value: Any) -> str:
    """Render a signed modifier ('+0' / '-5'); pass through non-ints verbatim."""
    if isinstance(value, bool):  # guard: bool is an int subclass
        return str(value)
    if isinstance(value, int):
        return f"+{value}" if value >= 0 else str(value)
    return str(value)


def _format_defaults(defaults: list[dict] | None) -> str | None:
    """Defaults array -> 'DX-5, Shortsword-2'; None if nothing renders."""
    if not defaults:
        return None
    parts: list[str] = []
    for d in defaults:
        if not isinstance(d, dict):
            continue
        dtype = d.get("type", "")
        modifier = d.get("modifier", 0)
        mod_str = ""
        if isinstance(modifier, int) and modifier:
            mod_str = str(modifier) if modifier < 0 else f"+{modifier}"
        if dtype == "skill":
            base = d.get("name", "?")
            if _TEMPLATE_TOKEN.search(str(base)):
                continue
            spec = d.get("specialization")
            if spec and not _TEMPLATE_TOKEN.search(spec):
                base = f"{base} ({spec})"
            parts.append(f"{base}{mod_str}")
        elif not _TEMPLATE_TOKEN.search(str(dtype)):
            parts.append(f"{_decode_attr(str(dtype))}{mod_str}")
    return ", ".join(parts) if parts else None


def _format_single_default(default: dict | None) -> str | None:
    """Technique default -> 'Broadsword-2'; None when the base skill is a template token."""
    if not isinstance(default, dict):
        return None
    base = default.get("name")
    if not base or _TEMPLATE_TOKEN.search(base):
        return None
    spec = default.get("specialization")
    if spec and not _TEMPLATE_TOKEN.search(spec):
        base = f"{base} ({spec})"
    modifier = default.get("modifier", 0)
    mod_str = ""
    if isinstance(modifier, int) and modifier:
        mod_str = str(modifier) if modifier < 0 else f"+{modifier}"
    return f"{base}{mod_str}"


def _weapon_damage(weapon: dict) -> str | None:
    """Resolved weapon damage fact: prefer calc.damage ('sw+1 cut'), else build."""
    calc = weapon.get("calc")
    if isinstance(calc, dict) and calc.get("damage"):
        return str(calc["damage"])
    dmg = weapon.get("damage")
    if isinstance(dmg, dict):
        st = dmg.get("st", "")
        base = dmg.get("base", "")
        dtype = dmg.get("type", "")
        body = f"{st}{base}".strip() or base
        return f"{body} {dtype}".strip() or None
    return None


# embed builders read only named fact fields — never iterate entry keys, so
# rulebook prose (local_notes, usage_notes) can't leak into an embed


def _base_embed(title: str) -> discord.Embed:
    embed = discord.Embed(title=title, color=_REF_COLOR)
    embed.set_footer(text=_FOOTER)
    return embed


def _add_tags(embed: discord.Embed, entry: dict) -> None:
    tags = entry.get("tags")
    if tags:
        # a re-vendored snapshot could carry @template@ tokens in tags — filter here too
        clean = [str(t) for t in tags if not _TEMPLATE_TOKEN.search(str(t))]
        if clean:
            embed.add_field(name="Tags", value=", ".join(clean), inline=False)


def build_skill_embed(entry: dict) -> discord.Embed:
    name = entry.get("name", "Unknown Skill")
    spec = entry.get("specialization")
    title = f"{name} ({spec})" if spec else name
    embed = _base_embed(title)

    difficulty = _decode_difficulty(entry.get("difficulty"))
    if difficulty:
        embed.add_field(name="Difficulty", value=difficulty, inline=True)
    if entry.get("points") is not None:
        embed.add_field(name="Points", value=str(entry["points"]), inline=True)
    tl = _format_tech_level(entry.get("tech_level"))
    if tl:
        embed.add_field(name="Tech Level", value=tl, inline=True)
    embed.add_field(name="Page", value=_format_reference(entry.get("reference")), inline=True)

    defaults = _format_defaults(entry.get("defaults"))
    if defaults:
        embed.add_field(name="Defaults", value=defaults, inline=False)
    _add_tags(embed, entry)
    return embed


def build_trait_embed(entry: dict) -> discord.Embed:
    embed = _base_embed(entry.get("name", "Unknown Trait"))

    base_points = entry.get("base_points")
    if base_points is not None:
        embed.add_field(name="Points", value=str(base_points), inline=True)
    if entry.get("points_per_level") is not None:
        embed.add_field(
            name="Points / Level", value=str(entry["points_per_level"]), inline=True
        )
    if entry.get("levels") is not None:
        embed.add_field(name="Levels", value=str(entry["levels"]), inline=True)

    cr = entry.get("cr")
    if cr is not None:
        cr_adj = entry.get("cr_adj")
        cr_text = f"{cr} ({cr_adj})" if cr_adj else str(cr)
        embed.add_field(name="Self-Control", value=cr_text, inline=True)

    tl = _format_tech_level(entry.get("tech_level"))
    if tl:
        embed.add_field(name="Tech Level", value=tl, inline=True)
    embed.add_field(name="Page", value=_format_reference(entry.get("reference")), inline=True)

    # modifiers deliberately omitted: a gcs trait carries its whole enhancement
    # menu (often 20+ rows), which blows discord's 1024-char field cap
    _add_tags(embed, entry)
    return embed


def build_spell_embed(entry: dict) -> discord.Embed:
    embed = _base_embed(entry.get("name", "Unknown Spell"))

    difficulty = _decode_difficulty(entry.get("difficulty"))
    if difficulty:
        embed.add_field(name="Difficulty", value=difficulty, inline=True)

    college = entry.get("college")
    if college:
        college_text = ", ".join(str(c) for c in college) if isinstance(college, list) else str(college)
        embed.add_field(name="College", value=college_text, inline=True)

    if entry.get("spell_class"):
        embed.add_field(name="Class", value=str(entry["spell_class"]), inline=True)
    if entry.get("resist"):
        embed.add_field(name="Resist", value=str(entry["resist"]), inline=True)
    if entry.get("casting_cost"):
        embed.add_field(name="Cost", value=str(entry["casting_cost"]), inline=True)
    if entry.get("maintenance_cost"):
        embed.add_field(name="Maintain", value=str(entry["maintenance_cost"]), inline=True)
    if entry.get("casting_time"):
        embed.add_field(name="Casting Time", value=str(entry["casting_time"]), inline=True)
    if entry.get("duration"):
        embed.add_field(name="Duration", value=str(entry["duration"]), inline=True)
    if entry.get("power_source"):
        embed.add_field(name="Power Source", value=str(entry["power_source"]), inline=True)
    if entry.get("points") is not None:
        embed.add_field(name="Points", value=str(entry["points"]), inline=True)

    embed.add_field(name="Page", value=_format_reference(entry.get("reference")), inline=True)
    _add_tags(embed, entry)
    return embed


def build_equipment_embed(entry: dict) -> discord.Embed:
    """Equipment facts; the name field is 'description', not 'name'."""
    embed = _base_embed(entry.get("description", "Unknown Item"))

    if entry.get("base_value") not in (None, ""):
        embed.add_field(name="Cost", value=str(entry["base_value"]), inline=True)
    if entry.get("base_weight") not in (None, ""):
        embed.add_field(name="Weight", value=str(entry["base_weight"]), inline=True)
    if entry.get("legality_class") not in (None, ""):
        embed.add_field(name="Legality", value=str(entry["legality_class"]), inline=True)
    tl = _format_tech_level(entry.get("tech_level"))
    if tl:
        embed.add_field(name="Tech Level", value=tl, inline=True)
    if entry.get("rated_strength") not in (None, ""):
        embed.add_field(name="Rated ST", value=str(entry["rated_strength"]), inline=True)
    embed.add_field(name="Page", value=_format_reference(entry.get("reference")), inline=True)

    weapons = entry.get("weapons")
    if isinstance(weapons, list):
        for weapon in weapons:
            if not isinstance(weapon, dict):
                continue
            _add_weapon_field(embed, weapon)
    _add_tags(embed, entry)
    return embed


def _add_weapon_field(embed: discord.Embed, weapon: dict) -> None:
    """Add one weapon stat block (facts only — no usage_notes prose)."""
    usage = weapon.get("usage") or "Attack"
    bits: list[str] = []
    damage = _weapon_damage(weapon)
    if damage:
        bits.append(f"Dmg {damage}")
    # Melee facts
    for key, label in (("reach", "Reach"), ("parry", "Parry"), ("block", "Block")):
        val = weapon.get(key)
        if val not in (None, ""):
            bits.append(f"{label} {val}")
    # Ranged facts
    for key, label in (
        ("accuracy", "Acc"), ("range", "Range"), ("rate_of_fire", "RoF"),
        ("shots", "Shots"), ("bulk", "Bulk"), ("recoil", "Rcl"),
    ):
        val = weapon.get(key)
        if val not in (None, ""):
            bits.append(f"{label} {val}")
    strength = weapon.get("strength")
    if strength not in (None, ""):
        bits.append(f"ST {strength}")
    if bits:
        embed.add_field(name=str(usage), value=" · ".join(bits), inline=False)


def build_technique_embed(entry: dict) -> discord.Embed:
    embed = _base_embed(entry.get("name", "Unknown Technique"))

    difficulty = _decode_difficulty(entry.get("difficulty"))
    if difficulty:
        embed.add_field(name="Difficulty", value=difficulty, inline=True)
    base = _format_single_default(entry.get("default"))
    if base:
        embed.add_field(name="Default", value=base, inline=True)
    limit = entry.get("limit")
    if isinstance(limit, int) and limit > 0:
        embed.add_field(name="Max Bonus", value=f"+{limit}", inline=True)
    if entry.get("points") is not None:
        embed.add_field(name="Points", value=str(entry["points"]), inline=True)
    embed.add_field(name="Page", value=_format_reference(entry.get("reference")), inline=True)
    _add_tags(embed, entry)
    return embed


_BUILDERS: dict[str, Callable[[dict], discord.Embed]] = {
    "skill": build_skill_embed,
    "trait": build_trait_embed,
    "spell": build_spell_embed,
    "technique": build_technique_embed,
    "item": build_equipment_embed,
}


class ReferenceCog(commands.Cog):
    "GURPS Reference Lookups (Skills, Traits, Spells, Techniques, Equipment)."

    def __init__(self, bot: GURPSBot, service: ReferenceService | None = None) -> None:
        self.bot = bot
        self._service = service

    @property
    def service(self) -> ReferenceService:
        """The in-memory reference service (constructor arg, else ``bot.reference``)."""
        if self._service is not None:
            return self._service
        return self.bot.reference  # type: ignore[attr-defined]

    async def _lookup(
        self,
        interaction: discord.Interaction,
        command: str,
        name: str,
    ) -> None:
        category = CATEGORIES[command]
        # empty catalog = snapshot never vendored; say so instead of "not found"
        if not self.service.names(category):
            await interaction.response.send_message(_NOT_SYNCED, ephemeral=True)
            return
        entry = self.service.get(category, name)
        if entry is None:
            await interaction.response.send_message(
                f"**{name}** not found in the {command} reference.",
                ephemeral=True,
            )
            return
        embed = _BUILDERS[command](entry)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="skill", description="Look Up a GURPS Skill (Facts + Page Cite)")
    @app_commands.describe(name="Skill name")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(3, 5.0)
    async def skill(self, interaction: discord.Interaction, name: str) -> None:
        await self._lookup(interaction, "skill", name)

    @app_commands.command(name="trait", description="Look Up a GURPS Advantage or Disadvantage")
    @app_commands.describe(name="Trait name")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(3, 5.0)
    async def trait(self, interaction: discord.Interaction, name: str) -> None:
        await self._lookup(interaction, "trait", name)

    @app_commands.command(name="spell", description="Look Up a GURPS Spell (Facts + Page Cite)")
    @app_commands.describe(name="Spell name")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(3, 5.0)
    async def spell(self, interaction: discord.Interaction, name: str) -> None:
        await self._lookup(interaction, "spell", name)

    @app_commands.command(name="technique", description="Look Up a GURPS Technique (Facts + Page Cite)")
    @app_commands.describe(name="Technique name")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(3, 5.0)
    async def technique(self, interaction: discord.Interaction, name: str) -> None:
        await self._lookup(interaction, "technique", name)

    @app_commands.command(name="item", description="Look Up GURPS Equipment (Facts + Page Cite)")
    @app_commands.describe(name="Equipment name")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(3, 5.0)
    async def item(self, interaction: discord.Interaction, name: str) -> None:
        await self._lookup(interaction, "item", name)

    # discord.py wants the (self, interaction, current) shape per command —
    # the thin wrappers below delegate to _suggest

    async def _suggest(
        self,
        interaction: discord.Interaction,
        command: str,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if not interaction.guild_id:
            return []
        category = CATEGORIES[command]
        try:
            # same service as the command body so suggestions never diverge from lookups
            candidates = self.service.names(category)
        except Exception:
            log.exception("reference autocomplete failed for %s", category)
            return []
        if not current:
            names = candidates[:25]
        else:
            # partial_ratio is cheap enough for per-keystroke scans over ~11k names
            names = [
                m
                for m, _ in fuzzy_match(
                    current, candidates, limit=25, score_cutoff=40, prefix_optimized=True
                )
            ]
        # discord caps choice name/value at 100 chars; over-long would 400
        return [
            app_commands.Choice(name=n[:100], value=n[:100]) for n in names
        ]

    @skill.autocomplete("name")
    async def _skill_ac(self, interaction: discord.Interaction, current: str):
        return await self._suggest(interaction, "skill", current)

    @trait.autocomplete("name")
    async def _trait_ac(self, interaction: discord.Interaction, current: str):
        return await self._suggest(interaction, "trait", current)

    @spell.autocomplete("name")
    async def _spell_ac(self, interaction: discord.Interaction, current: str):
        return await self._suggest(interaction, "spell", current)

    @technique.autocomplete("name")
    async def _technique_ac(self, interaction: discord.Interaction, current: str):
        return await self._suggest(interaction, "technique", current)

    @item.autocomplete("name")
    async def _item_ac(self, interaction: discord.Interaction, current: str):
        return await self._suggest(interaction, "item", current)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReferenceCog(bot))
