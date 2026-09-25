"""SIGTERM must reach GURPSBot.close().

asyncio.run (inside discord.py's Client.run) installs a SIGINT handler only.
Under Docker the bot runs as PID 1, and the kernel drops SIGTERM for a PID 1
with no handler, so `docker stop` waited out the 20s grace period and then
SIGKILLed it; under systemd, SIGTERM killed it before close() could dispose
the database engine. The entrypoint's comment said the opposite.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys

import pytest

from gurps_bot.bot import install_sigterm_handler

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX signals; the handler is a no-op on Windows"
)


class _FakeBot:
    def __init__(self):
        self.closed = asyncio.Event()

    async def close(self):
        self.closed.set()


async def test_sigterm_closes_the_bot():
    bot = _FakeBot()
    loop = asyncio.get_running_loop()
    install_sigterm_handler(bot, loop)
    try:
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.wait_for(bot.closed.wait(), timeout=2)
    finally:
        loop.remove_signal_handler(signal.SIGTERM)


async def test_setup_hook_installs_it():
    """Wiring, not just the helper: the bot must call it on startup."""
    import inspect

    from gurps_bot.bot import GURPSBot

    assert "install_sigterm_handler" in inspect.getsource(GURPSBot.setup_hook)
