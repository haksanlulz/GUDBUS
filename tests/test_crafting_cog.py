"""The guided invention flow — `/craft invent` and `/craft costs`.

The channel map splits this deliberately: mock-interaction tests cover the
logic, and whether the flow is *usable* is a manual rung the operator closes by
playing the anchor scene on the hosted bot. No test sees friction, which is the
operator's own top-ranked failure mode ("clunky, unintuitive, unusable").

What IS testable, and is what this file holds: that the menus assemble the same
modifier the engine would have been handed as parameters, that the secret roll
never reaches the channel, and that money stays three figures all the way to
the embed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from gurps_bot.cogs.crafting import CraftingCog, InventionFlowView
from gurps_bot.mechanics import crafting
from gurps_bot.mechanics.checks import CheckResult
from gurps_bot.mechanics.crafting import Complexity
from gurps_bot.mechanics.dice import DiceSpec, RollResult


def _interaction(user_id: int = 1) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def _choose(item, interaction, *values: str) -> None:
    """Drive a real Select the way Discord does.

    discord.py 2.7 parks the submitted options on ``Select._values`` and the
    item hands itself to the callback, so setting that and invoking the real
    callback exercises the actual wiring rather than a mock shaped like it.
    """
    item._values = list(values)
    await item.callback(interaction)


def _result(rolled: int, target: int) -> CheckResult:
    spec = DiceSpec(3, 6, 0)
    from gurps_bot.mechanics.checks import _determine_outcome

    return CheckResult(
        roll_result=RollResult(spec=spec, dice=(1, 1, 1), total=rolled),
        target=target,
        margin=target - rolled,
        outcome=_determine_outcome(rolled, target),
    )


class TestTheMenusBuildTheModifier:
    """Every parameter the engine takes must be reachable from a menu.

    "no step requires knowing a value the bot could have asked for" — so the
    test of record is that the guided path and the parameter path agree.
    """

    async def test_a_bare_complexity_choice_is_enough_to_get_a_target(self):
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "average")
        assert view.target() == 14 - 10

    async def test_the_situation_menu_maps_onto_the_engines_keywords(self):
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "simple")
        await _choose(
            view.situation_select, _interaction(), "working_model", "one_tl_above"
        )
        expected = crafting.concept_modifier(
            Complexity.SIMPLE, working_model=True, one_tl_above=True
        )
        assert view.modifier().total == expected.total

    async def test_deselecting_clears_rather_than_accumulates(self):
        """A select fires with its full current value set, not a delta."""
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "simple")
        await _choose(view.situation_select, _interaction(), "new_technology")
        await _choose(view.situation_select, _interaction())
        assert view.modifier().total == Complexity.SIMPLE.concept_penalty

    async def test_the_gm_bonuses_are_menus_not_typed_numbers(self):
        view = InventionFlowView(skill=12, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "complex")
        await _choose(view.variant_select, _interaction(), "4")
        await _choose(view.description_select, _interaction(), "2")
        assert view.modifier().total == -14 + 4 + 2

    async def test_every_situation_option_is_a_real_engine_keyword(self):
        """A typo in an option value would silently drop a modifier."""
        view = InventionFlowView(skill=10, invoker_id=1)
        for option in view.situation_select.options:
            crafting.concept_modifier(Complexity.SIMPLE, **{option.value: True})

    async def test_every_complexity_option_resolves(self):
        view = InventionFlowView(skill=10, invoker_id=1)
        for option in view.complexity_select.options:
            await _choose(view.complexity_select, _interaction(), option.value)
            assert view.complexity is not None


class TestTheFlowReportsAnImpossibleTargetHonestly:
    """SPEC impossible-targets-are-reported-honestly, at the surface."""

    async def test_a_sub_three_target_is_shown_and_explained(self):
        view = InventionFlowView(skill=12, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "amazing")
        embed = view.summary_embed()

        assert view.target() == -10
        assert "-10" in embed.fields[1].value
        assert any(f.name == "Below 3" for f in embed.fields)

    async def test_an_ordinary_target_gets_no_such_note(self):
        view = InventionFlowView(skill=18, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "simple")
        assert not any(f.name == "Below 3" for f in view.summary_embed().fields)

    async def test_the_breakdown_is_shown_not_just_the_total(self):
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "average")
        await _choose(view.situation_select, _interaction(), "working_model")
        modifiers = view.summary_embed().fields[0].value
        assert "working model" in modifiers
        assert "Average" in modifiers


class TestGmRollsStayWithTheGm:
    """SPEC gm-rolls-stay-with-the-gm.

    The bot has no GM identity — no table, no setting, no role check — so
    "routes it to the GM only" is implemented as ephemeral-to-the-roller. What
    the spec forbids absolutely is the channel, and that is what these assert.
    """

    async def test_the_roll_is_ephemeral(self, monkeypatch):
        monkeypatch.setattr(
            "gurps_bot.cogs.crafting.check", lambda target: _result(9, target)
        )
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "average")

        interaction = _interaction()
        await view.roll_btn.callback(interaction)

        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True

    async def test_the_roll_never_goes_to_the_channel(self, monkeypatch):
        monkeypatch.setattr(
            "gurps_bot.cogs.crafting.check", lambda target: _result(9, target)
        )
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "average")

        interaction = _interaction()
        await view.roll_btn.callback(interaction)

        interaction.channel.send.assert_not_called()
        interaction.followup.send.assert_not_called()

    async def test_a_flawed_theory_is_told_to_the_roller_and_nobody_else(self, monkeypatch):
        """The trap B473 builds the secrecy around: it advances AND it is dead.
        A player who saw this text would never pay for the prototype."""
        monkeypatch.setattr(
            "gurps_bot.cogs.crafting.check", lambda target: _result(18, target)
        )
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "average")

        interaction = _interaction()
        await view.roll_btn.callback(interaction)

        kwargs = interaction.response.send_message.await_args.kwargs
        assert kwargs["ephemeral"] is True
        assert any(f.name == "Flawed theory" for f in kwargs["embed"].fields)

    async def test_rolling_before_choosing_asks_rather_than_guessing(self):
        view = InventionFlowView(skill=14, invoker_id=1)
        interaction = _interaction()
        await view.roll_btn.callback(interaction)
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True
        assert view.complexity is None


class TestTheFlowBelongsToWhoeverOpenedIt:
    async def test_a_bystander_cannot_rewrite_the_gms_calls(self):
        view = InventionFlowView(skill=14, invoker_id=1)
        interaction = _interaction(user_id=999)
        assert await view.interaction_check(interaction) is False
        interaction.response.send_message.assert_awaited()

    async def test_the_owner_passes(self):
        view = InventionFlowView(skill=14, invoker_id=7)
        assert await view.interaction_check(_interaction(user_id=7)) is True

    async def test_a_timed_out_flow_disables_itself(self):
        view = InventionFlowView(skill=14, invoker_id=1)
        await view.on_timeout()
        assert all(item.disabled for item in view.children)


class TestCostsStaysThreeFigures:
    """SPEC money-is-never-summed-into-one-number, at the surface.

    The engine refusing a total is worth nothing if the embed adds one up.
    """

    async def _run(self, **kwargs):
        cog = CraftingCog(MagicMock())
        interaction = _interaction()
        await cog.costs.callback(
            cog,
            interaction,
            kwargs.pop("complexity", "complex"),
            kwargs.pop("retail_price", 5_000),
            **kwargs,
        )
        return interaction.response.send_message.await_args.kwargs["embed"]

    async def test_the_three_figures_appear_in_three_separate_fields(self):
        embed = await self._run()
        names = [f.name for f in embed.fields]
        assert "Facilities, once, up front" in names
        assert "Every prototype attempt" in names
        assert "Each copy afterwards" in names

    async def test_no_field_sums_them(self):
        embed = await self._run()
        summed = f"${250_000 + 5_000 + 1_000:,}"
        assert all(summed not in (f.value or "") for f in embed.fields)

    async def test_the_facilities_line_says_when_it_is_per_inventor(self):
        embed = await self._run(inventors=3)
        facilities = next(f for f in embed.fields if f.name.startswith("Facilities"))
        assert "$750,000" in facilities.value
        assert "3 inventors" in facilities.value

    async def test_a_lone_inventor_gets_no_confusing_multiplier_note(self):
        embed = await self._run(inventors=1)
        facilities = next(f for f in embed.fields if f.name.startswith("Facilities"))
        assert "inventors" not in facilities.value

    @pytest.mark.parametrize(
        "kwargs", [{"retail_price": -1}, {"inventors": 0}, {"inventors": 21}]
    )
    async def test_nonsense_input_is_refused_before_the_engine_sees_it(self, kwargs):
        cog = CraftingCog(MagicMock())
        interaction = _interaction()
        retail = kwargs.pop("retail_price", 100)
        await cog.costs.callback(cog, interaction, "simple", retail, **kwargs)
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True


class TestInventEntryPoint:
    async def test_it_asks_for_the_one_thing_only_the_player_knows(self):
        """Skill is the parameter; everything else is a menu. If a second
        parameter ever appears here, the anchor-scene spec is being eroded."""
        cog = CraftingCog(MagicMock())
        params = {p.name for p in cog.invent.parameters}
        assert params == {"skill"}

    async def test_it_opens_a_view(self):
        cog = CraftingCog(MagicMock())
        interaction = _interaction()
        await cog.invent.callback(cog, interaction, 14)
        view = interaction.response.send_message.await_args.kwargs["view"]
        assert isinstance(view, InventionFlowView)
        assert view.skill == 14

    @pytest.mark.parametrize("skill", [0, 41])
    async def test_an_implausible_skill_is_refused(self, skill):
        cog = CraftingCog(MagicMock())
        interaction = _interaction()
        await cog.invent.callback(cog, interaction, skill)
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True
