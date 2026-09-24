"""An ephemeral reply after a public defer must actually be ephemeral.

Discord turns the FIRST followup after a deferred response into an edit of the
deferred "thinking…" placeholder, and that placeholder's visibility was fixed
when it was deferred. So `followup.send(ephemeral=True)` after a public defer
posts to the whole channel. CombatContext and CharacterContext deferred
publicly, which made `/combat defend hidden:True` — a GM blind roll — public,
along with every "ephemeral" error sent from inside those contexts.

The fake here models that rule rather than trusting a MagicMock whose
`is_done()` never flips, which is how the old tests missed it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from gurps_bot.ui.respond import defer, respond


class _FakeInteraction:
    """Just enough of Discord's reply semantics to see who can read a message."""

    def __init__(self):
        self.extras: dict = {}
        self.sent: list[tuple[str, bool]] = []  # (content, visible_to_channel)
        self._done = False
        self._placeholder_public: bool | None = None
        self.deleted_original = False
        outer = self

        class _Response:
            def is_done(self):
                return outer._done

            async def defer(self, *, ephemeral=False, thinking=False):
                outer._done = True
                outer._placeholder_public = not ephemeral

            async def send_message(self, content=None, *, ephemeral=False, **kw):
                outer._done = True
                outer.sent.append((content, not ephemeral))

        class _Followup:
            async def send(self, content=None, *, ephemeral=False, **kw):
                if outer._placeholder_public is not None:
                    # first followup replaces the placeholder and inherits it
                    public = outer._placeholder_public
                    outer._placeholder_public = None
                else:
                    public = not ephemeral
                outer.sent.append((content, public))

        self.response = _Response()
        self.followup = _Followup()

    async def delete_original_response(self):
        self.deleted_original = True
        self._placeholder_public = None


class TestTheFakeModelsDiscord:
    """Verify the instrument: without the fix's help, the leak reproduces."""

    async def test_a_raw_ephemeral_followup_after_a_public_defer_is_public(self):
        i = _FakeInteraction()
        await i.response.defer()
        await i.followup.send("secret", ephemeral=True)
        assert i.sent == [("secret", True)]


class TestRespondAfterAPublicDefer:
    async def test_an_ephemeral_reply_stays_private(self):
        i = _FakeInteraction()
        await defer(i)
        await respond(i, "secret", ephemeral=True)
        assert i.sent == [("secret", False)]
        assert i.deleted_original

    async def test_a_public_reply_uses_the_placeholder(self):
        i = _FakeInteraction()
        await defer(i)
        await respond(i, "hello")
        assert i.sent == [("hello", True)]
        assert not i.deleted_original

    async def test_only_the_first_reply_touches_the_placeholder(self):
        i = _FakeInteraction()
        await defer(i)
        await respond(i, "hello")
        await respond(i, "warning", ephemeral=True)
        assert i.sent == [("hello", True), ("warning", False)]
        assert not i.deleted_original

    async def test_a_private_defer_needs_no_cleanup(self):
        i = _FakeInteraction()
        await defer(i, ephemeral=True)
        await respond(i, "secret", ephemeral=True)
        assert i.sent == [("secret", False)]
        assert not i.deleted_original

    async def test_a_mock_interaction_is_not_mistaken_for_a_placeholder(self):
        """MagicMock.extras is a MagicMock, and .get() on it is truthy."""
        i = MagicMock()
        i.response.is_done.return_value = True

        async def _send(*a, **k):
            return None

        i.followup.send = MagicMock(side_effect=_send)
        await respond(i, "x", ephemeral=True)
        i.delete_original_response.assert_not_called()
