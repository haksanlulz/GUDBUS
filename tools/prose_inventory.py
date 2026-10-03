"""Dump every user-facing string the bot shows, for a prose review pass.

    uv run python tools/prose_inventory.py            # markdown to stdout
    uv run python tools/prose_inventory.py --stats    # counts + coverage only

Prose review is expensive per word, so the reviewer should arrive at the words
rather than spend the budget finding them. This collects them into one ordered
document.

Two sources, deliberately distinguished:

* **The live command tree** — command descriptions, parameter descriptions and
  choice names. Complete and exact, because Discord renders these verbatim in
  the command picker. This is what every user reads before they read anything
  else, and it is the highest-traffic prose in the project by a wide margin.
* **A source scan** for everything the bot *says*: reply text, and the embeds
  that carry most of it. Static analysis, so it has a floor rather than a
  guarantee — but it reports its own coverage instead of asking to be trusted.

The scan was rewritten 2026-07-29. The first version read only literal strings
passed directly to a reply call and found 48, while the codebase holds ~400
embed titles, descriptions and field values. It was seeing roughly a tenth of
what a user reads and — worse — its output gave no way to notice. A review that
believes it saw everything is worse than one that knows it did not, so § 4
counts what could not be resolved and names the files it lives in.

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

# This document is full of em dashes and arrows, and Python encodes stdout with
# the locale codec — cp1252 under PowerShell — so printing it there died on
# UnicodeEncodeError, and redirecting to a file died the same way. Set here
# rather than documented as a PYTHONIOENCODING incantation the reader has to
# remember, and which has no inline form in PowerShell anyway.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from gurps_bot.bot import EXTENSIONS  # noqa: E402


# ---------------------------------------------------------------- command tree

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


# ------------------------------------------------------------------ the scan

#: Calls whose text a user reads. `send` is included bare because followups and
#: channel sends both land on it; the cost is a few non-user `send` calls, which
#: is the right way round — a missed line is invisible, an extra one is obvious.
_REPLY_FUNCS = ("respond", "send_message", "send", "respond_and_refresh",
                "_send_error", "edit_message", "edit_original_response")

#: Embed pieces. These carry most of the bot's prose and none of it was collected
#: before. Positional forms matter too: add_field is often called positionally.
_EMBED_KWARGS = {
    "Embed": ("title", "description"),
    "add_field": ("name", "value"),
    "set_footer": ("text",),
    "set_author": ("name",),
}

#: Exceptions whose message `_send_error` shows to the user verbatim.
_USER_FACING_ERRORS = ("CombatPermissionError", "CombatTargetNotFound",
                       "ValueError", "MacroError", "LimitExceeded")

DYNAMIC = None  #: sentinel — a value this pass cannot resolve to text


def _render(node: ast.AST, scope: dict[str, str]) -> str | None:
    """Best-effort text for a string-ish expression, or DYNAMIC.

    f-strings keep their placeholders as `{expr}`: the reviewer needs to see
    where a value lands in a sentence, because that is exactly where awkward
    phrasing hides ("You have 1 items").
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else DYNAMIC
    if isinstance(node, ast.JoinedStr):
        out = []
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                out.append(part.value)
            elif isinstance(part, ast.FormattedValue):
                out.append("{" + ast.unparse(part.value) + "}")
            else:
                return DYNAMIC
        return "".join(out)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _render(node.left, scope), _render(node.right, scope)
        if left is DYNAMIC or right is DYNAMIC:
            return DYNAMIC
        return left + right
    if isinstance(node, ast.IfExp):
        # Both branches are prose a user can see; show them as alternatives.
        a, b = _render(node.body, scope), _render(node.orelse, scope)
        if a is DYNAMIC or b is DYNAMIC:
            return DYNAMIC
        return f"{a}  <or>  {b}"
    if isinstance(node, ast.Name):
        return scope.get(node.id, DYNAMIC)
    return DYNAMIC


def _collect_scope(tree: ast.Module) -> dict[str, str]:
    """Names bound to string-ish values, so `msg = "..."; respond(msg)` resolves.

    Handles `+=` accumulation, because that is how the longest replies here are
    built — `hp_cmd` assembles its entire answer that way, so the previous scan
    reported none of it.

    One flat scope per module rather than per function. That over-shares names
    across functions, which can only ever attribute a real string to the wrong
    line; for a document a human reads and edits, a slightly misfiled line is a
    far cheaper error than a silently absent one.
    """
    scope: dict[str, str] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            text = _render(n.value, scope)
            if text is not DYNAMIC:
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        scope[t.id] = text
        elif isinstance(n, ast.AugAssign) and isinstance(n.op, ast.Add):
            if isinstance(n.target, ast.Name):
                add = _render(n.value, scope)
                if add is not DYNAMIC:
                    scope[n.target.id] = scope.get(n.target.id, "") + add
    return scope


def _func_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def _sinks(tree: ast.Module, scope: dict[str, str]):
    """Yield (kind, lineno, text|DYNAMIC) for every user-facing string site."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            if _func_name(node.exc) in _USER_FACING_ERRORS and node.exc.args:
                yield "error", node.lineno, _render(node.exc.args[0], scope)
            continue
        if not isinstance(node, ast.Call):
            continue
        name = _func_name(node)

        if name in _REPLY_FUNCS:
            seen = False
            for arg in node.args:
                if isinstance(arg, (ast.Constant, ast.JoinedStr, ast.BinOp,
                                    ast.Name, ast.IfExp)):
                    yield "reply", node.lineno, _render(arg, scope)
                    seen = True
            for kw in node.keywords:
                if kw.arg == "content":
                    yield "reply", node.lineno, _render(kw.value, scope)
                    seen = True
            if not seen:
                # An embed-only answer. Its prose is collected below, so this is
                # counted separately rather than as an unresolved gap.
                yield "reply-embed-only", node.lineno, ""
            continue

        for target, kwargs in _EMBED_KWARGS.items():
            if name != target:
                continue
            for kw in node.keywords:
                if kw.arg in kwargs:
                    yield f"embed.{kw.arg}", node.lineno, _render(kw.value, scope)
            if target != "Embed":
                for i, arg in enumerate(node.args):
                    if i < len(kwargs):
                        yield f"embed.{kwargs[i]}", node.lineno, _render(arg, scope)


def _scan() -> tuple[list[tuple[str, int, str, str]], dict]:
    """Every resolvable user-facing string, plus a coverage tally."""
    found: list[tuple[str, int, str, str]] = []
    tally = {"sites": 0, "resolved": 0, "dynamic": 0, "embed_only": 0,
             "dynamic_by_file": {}}

    for path in sorted((ROOT / "gurps_bot").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        scope = _collect_scope(tree)

        for kind, lineno, text in _sinks(tree, scope):
            if kind == "reply-embed-only":
                tally["embed_only"] += 1
                continue
            tally["sites"] += 1
            if text is DYNAMIC:
                tally["dynamic"] += 1
                d = tally["dynamic_by_file"]
                d[rel] = d.get(rel, 0) + 1
                continue
            text = text.strip()
            if len(text) < 3:
                continue
            tally["resolved"] += 1
            found.append((rel, lineno, kind, text))

    return found, tally


# ------------------------------------------------------------- consistency

#: Words that stay capitalised in sentence case — GURPS terms and stat codes.
_KEEP = {
    "GURPS", "HP", "FP", "GM", "GMs", "DX", "IQ", "HT", "ST", "NPC", "NPCs",
    "PC", "PCs", "SJ", "SJG", "Discord", "GCS", "DR", "Rule", "Basic", "Set",
    "Will", "Per", "Move", "Dodge", "Parry", "Block", "Fright", "Check", "Roll",
}


def _sentence_case(text: str) -> str:
    """What a Title Case description would read as in sentence case.

    Rendered rather than described, so the ruling is a diff to approve instead
    of an exercise to perform 83 times — which only works if the diff is clean.
    Lowercasing a token's first character alone leaves the capital after a
    hyphen, producing `fall-Check trigger` and `extra-Energy skill bonus`, and a
    proposal with visible glitches in it costs the reviewer more than it saves.

    So hyphenated tokens are handled per segment, and the GURPS-term keep-list
    applies only to whole tokens: `Fright Check` survives as a proper noun,
    while `Fall-Check` becomes `fall-check`, because nothing mechanical can tell
    those apart and the compound is far more often ordinary prose.
    """
    def lower_first(w: str) -> str:
        """Lowercase the first LETTER, not the first character.

        `(Inches)` starts with a bracket, so a character-zero test skips the
        word entirely and the capital survives — which is how `(Inches)` and
        `(Yards)` came through a pass that had already handled every unbracketed
        word correctly.
        """
        for i, ch in enumerate(w):
            if ch.isalpha():
                return w[:i] + ch.lower() + w[i + 1:] if ch.isupper() else w
        return w

    out = []
    for i, w in enumerate(text.split()):
        bare = w.strip("()[],.:;/'\"")
        if i == 0 or bare in _KEEP or bare.isupper():
            out.append(w)
        elif "-" in bare:
            out.append("-".join(
                seg if seg.isupper() else lower_first(seg) for seg in w.split("-")
            ))
        else:
            out.append(lower_first(w))
    return " ".join(out)


def _title_case_suspects(rows: list[dict]) -> list[tuple[str, str, str]]:
    """Descriptions in Title Case, shown beside sentence-case ones in one picker.

    Not a defect — the single most visible consistency question in the
    inventory, surfaced so the reviewer rules once instead of per command.
    """
    out = []
    for r in rows:
        d = r["description"]
        words = [w for w in re.findall(r"[A-Za-z']+", d) if len(w) > 3]
        if len(words) >= 3 and sum(w[0].isupper() for w in words) >= len(words) - 1:
            out.append((f"/{r['command']}", d, _sentence_case(d)))
    return out


# ---------------------------------------------------------------------- main

_KIND_ORDER = ["reply", "embed.title", "embed.description", "embed.name",
               "embed.value", "embed.text", "error"]


async def main() -> None:
    rows = await _tree_prose()
    found, tally = _scan()
    suspects = _title_case_suspects(rows)
    pct = 100 * tally["resolved"] // max(tally["sites"], 1)

    if "--stats" in sys.argv:
        params = sum(len(r["params"]) for r in rows)
        choices = sum(len(p["choices"]) for r in rows for p in r["params"])
        by_kind: dict[str, int] = {}
        for _, _, kind, _ in found:
            by_kind[kind] = by_kind.get(kind, 0) + 1
        print(f"commands           {len(rows)}")
        print(f"parameters         {params}")
        print(f"choice names       {choices}")
        print(f"title-case descs   {len(suspects)} of {len(rows)}")
        print("\nscanned prose sites")
        for kind in _KIND_ORDER:
            if by_kind.get(kind):
                print(f"  {kind:<20} {by_kind[kind]}")
        print(f"  {'TOTAL resolved':<20} {tally['resolved']}")
        print(f"\ncoverage           {tally['resolved']}/{tally['sites']} "
              f"sites ({pct}%)")
        print(f"unresolved         {tally['dynamic']} assembled at runtime")
        for f, n in sorted(tally["dynamic_by_file"].items(),
                           key=lambda kv: -kv[1])[:8]:
            print(f"  {n:>3}  {f}")
        print(f"embed-only replies {tally['embed_only']} "
              "(prose collected as embed.*)")
        return

    print("# GUDBUS — user-facing prose inventory\n")
    print("Regenerate: `uv run python tools/prose_inventory.py`\n")

    print("## 1. Command descriptions — Discord's picker, verbatim\n")
    print("The highest-traffic prose in the project: every user reads these"
          " before anything else. Complete and exact, read from the live"
          " command tree rather than scanned.\n")
    for r in rows:
        print(f"- **`/{r['command']}`** — {r['description']}")
        for p in r["params"]:
            if p["description"] and p["description"] != "…":
                print(f"    - *{p['name']}*: {p['description']}")
            if p["choices"]:
                print(f"    - *{p['name']}* choices: {', '.join(p['choices'])}")
    print()

    if suspects:
        print(f"## 2. One ruling, {len(suspects)} of {len(rows)} descriptions\n")
        print("Title Case sitting beside sentence case in the same picker. The"
              " sentence-case rendering is given so the decision is a diff to"
              " approve rather than a rewrite to perform.\n")
        for cmd, current, proposed in suspects:
            print(f"- `{cmd}`")
            print(f"    - now: {current}")
            if proposed != current:
                print(f"    - or:  {proposed}")
        print()

    print(f"## 3. What the bot says — {len(found)} strings\n")
    print("Reply text, embed titles, descriptions and field values, and the"
          " error messages shown verbatim. f-string placeholders are kept as"
          " `{expr}`, because that is where awkward phrasing hides.\n")
    current_file = None
    for rel, lineno, kind, text in sorted(found, key=lambda r: (r[0], r[1])):
        if rel != current_file:
            print(f"\n### `{rel}`\n")
            current_file = rel
        print(f"- `{lineno}` *{kind}* — {text.replace(chr(10), ' / ')}")
    print()

    print(f"## 4. Coverage — {tally['resolved']} of {tally['sites']} sites ({pct}%)\n")
    print(f"{tally['dynamic']} string sites are assembled at runtime from values"
          " this pass cannot resolve, so their wording is absent above. This"
          " section exists so § 3 reads as a floor and not a guarantee — the"
          " previous version of this tool reported 48 strings with no way to"
          " tell it was missing most of them.\n")
    if tally["dynamic_by_file"]:
        print("Where the unresolved ones live:\n")
        for f, n in sorted(tally["dynamic_by_file"].items(),
                           key=lambda kv: -kv[1]):
            print(f"- `{f}` — {n}")
    print(f"\n{tally['embed_only']} replies carry an embed and no text of their"
          " own; that prose appears above as `embed.*` rather than being a gap.")


asyncio.run(main())
