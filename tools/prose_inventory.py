"""Dump every user-facing string the bot shows, for a prose review pass.

    uv run python tools/prose_inventory.py            # markdown to stdout
    uv run python tools/prose_inventory.py --stats    # counts only

Prose review is expensive per word, so the reviewer should arrive at the words
rather than spend the budget finding them. This collects them into one ordered
document.

Two sources, deliberately distinguished:

* **The live command tree** — command descriptions, parameter descriptions and
  choice names. Complete and exact, because Discord renders these verbatim in
  the command picker. This is what every user reads before they read anything
  else, and it is the highest-traffic prose in the project by a wide margin.
* **A source scan** for the reply strings — the "No active character..." class.
  Best-effort by construction: it reads string literals passed to `respond(`
  and `send_message(`, so an f-string built in pieces or a message assembled
  across lines will be partial or missed. Marked as such rather than presented
  as complete, because a review that believes it saw everything is worse than
  one that knows it did not.

Regenerated rather than stored: a checked-in copy is a second thing to keep
true, and this project has spent a day on exactly that failure.
"""

from __future__ import annotations

import ast
import asyncio
import re
import sys
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gurps_bot.bot import EXTENSIONS  # noqa: E402


async def _tree_prose() -> list[dict]:
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    for ext in EXTENSIONS:
        await bot.load_extension(ext)

    rows: list[dict] = []

    def add(full: str, cmd) -> None:
        rows.append({
            "command": full,
            "description": cmd.description,
            "params": [
                {
                    "name": p.name,
                    "description": p.description,
                    "choices": [c.name for c in p.choices],
                }
                for p in cmd.parameters
            ],
        })

    for cmd in sorted(bot.tree.get_commands(), key=lambda c: c.name):
        if isinstance(cmd, app_commands.Group):
            for sub in sorted(cmd.commands, key=lambda c: c.name):
                add(f"{cmd.name} {sub.name}", sub)
        else:
            add(cmd.name, cmd)

    await bot.close()
    return rows


#: Only these carry text a user reads. Everything else is plumbing.
_REPLY_CALLS = ("respond", "send_message", "followup.send")


def _reply_strings() -> list[tuple[str, int, str]]:
    """String literals handed to a reply call. Best-effort — see module docstring."""
    found: list[tuple[str, int, str]] = []
    for path in sorted((ROOT / "gurps_bot").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func) if hasattr(ast, "unparse") else ""
            if not any(c in name for c in _REPLY_CALLS):
                continue
            for arg in list(node.args) + [k.value for k in node.keywords]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    text = arg.value.strip()
                    if len(text) > 3 and " " in text:
                        rel = path.relative_to(ROOT).as_posix()
                        found.append((rel, node.lineno, text))
    return found


def _title_case_suspects(rows: list[dict]) -> list[str]:
    """Descriptions in Title Case, which Discord shows next to sentence-case ones.

    Not a defect — just the single most visible consistency question in the
    inventory, surfaced so the reviewer rules on it once instead of per command.
    """
    out = []
    for r in rows:
        d = r["description"]
        words = [w for w in re.findall(r"[A-Za-z']+", d) if len(w) > 3]
        if len(words) >= 3 and sum(w[0].isupper() for w in words) >= len(words) - 1:
            out.append(f"/{r['command']} — {d}")
    return out


async def main() -> None:
    rows = await _tree_prose()
    replies = _reply_strings()

    if "--stats" in sys.argv:
        params = sum(len(r["params"]) for r in rows)
        choices = sum(len(p["choices"]) for r in rows for p in r["params"])
        print(f"commands           {len(rows)}")
        print(f"parameters         {params}")
        print(f"choice names       {choices}")
        print(f"reply strings      {len(replies)} (best-effort scan)")
        print(f"title-case descs   {len(_title_case_suspects(rows))}")
        return

    print("# GUDBUS — user-facing prose inventory\n")
    print("Regenerate: `uv run python tools/prose_inventory.py`\n")

    print("## 1. Command descriptions — Discord's picker, verbatim\n")
    print("The highest-traffic prose in the project. Every user reads these"
          " before anything else.\n")
    for r in rows:
        print(f"- **`/{r['command']}`** — {r['description']}")
        for p in r["params"]:
            if p["description"] and p["description"] != "…":
                print(f"    - *{p['name']}*: {p['description']}")
            if p["choices"]:
                print(f"    - *{p['name']}* choices: {', '.join(p['choices'])}")
    print()

    suspects = _title_case_suspects(rows)
    if suspects:
        print(f"## 2. Consistency question — {len(suspects)} Title Case descriptions\n")
        print("Ruled once, applied everywhere, rather than per command.\n")
        for s in suspects:
            print(f"- {s}")
        print()

    print(f"## 3. Reply strings — {len(replies)} found (BEST-EFFORT)\n")
    print("Literal strings passed to a reply call. An f-string assembled in"
          " pieces will be partial or missing here — do not read this section"
          " as complete.\n")
    for rel, line, text in replies:
        print(f"- `{rel}:{line}` — {text}")


asyncio.run(main())
