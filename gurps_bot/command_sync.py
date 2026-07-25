"""Startup slash-command registration: global scope, fingerprint-gated.

Registration is treated like schema — applied idempotently at boot, not by a
human running a command from inside Discord. Single scope (global) means the
guild/global duplicate problem cannot exist; the fingerprint gate means an
unchanged command set costs zero API calls, so a crash loop cannot burn the
daily registration limit.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from discord import app_commands

log = logging.getLogger(__name__)


def tree_fingerprint(tree: app_commands.CommandTree) -> str:
    """Stable hash of the tree's full global command surface."""
    payloads = []
    for cmd in tree.get_commands():
        try:
            payloads.append(cmd.to_dict(tree))
        except TypeError:  # discord.py <= 2.3 takes no tree argument
            payloads.append(cmd.to_dict())  # type: ignore[call-arg]
    payloads.sort(key=lambda p: str(p.get("name")))
    blob = json.dumps(payloads, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


async def auto_sync(tree: app_commands.CommandTree, fingerprint_path: Path) -> str:
    """Sync globally iff the command set changed since the last successful sync.

    Returns 'synced' | 'unchanged' | 'failed'. Never raises: a failed sync must
    not kill the boot — the gateway session is still useful, and the
    mention-prefixed rescue command can repair registration afterwards.
    """
    current = tree_fingerprint(tree)
    try:
        stored: str | None = fingerprint_path.read_text(encoding="utf-8").strip()
    except OSError:
        stored = None

    if stored == current:
        log.info("Command set unchanged; skipping global sync.")
        return "unchanged"

    try:
        synced = await tree.sync()
    except Exception:
        log.exception(
            "Global command sync failed; continuing boot. Retry with @<bot> sync, "
            "or restart — the fingerprint is only written on success."
        )
        return "failed"

    fingerprint_path.parent.mkdir(parents=True, exist_ok=True)
    fingerprint_path.write_text(current, encoding="utf-8")
    log.info("Globally synced %d commands (command set changed).", len(synced))
    return "synced"
