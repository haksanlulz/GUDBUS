from gurps_bot.services.character_context import CharacterContext
from gurps_bot.services.combat_session import CombatContext


class TestCharacterContextSafety:
    async def test_aexit_with_no_session_ctx(self):
        ctx = CharacterContext.__new__(CharacterContext)
        ctx._session_ctx = None
        # should not raise AttributeError
        result = await ctx.__aexit__(None, None, None)
        assert result is False


class TestCombatContextSafety:
    async def test_aexit_with_no_session_ctx(self):
        ctx = CombatContext.__new__(CombatContext)
        ctx._session_ctx = None
        ctx.interaction = None  # not used when _session_ctx is None
        # should not raise AttributeError
        result = await ctx.__aexit__(None, None, None)
        assert result is False
