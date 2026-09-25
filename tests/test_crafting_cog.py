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
    interaction.original_response = AsyncMock()
    return interaction


async def _choose(item, interaction, *values: str) -> None:
    """Drive a real Select the way Discord does.

    discord.py 2.7 parks the submitted options on ``Select._values`` and the
    item hands itself to the callback, so setting that and invoking the real
    callback exercises the actual wiring rather than a mock shaped like it.
    """
    item._values = list(values)
    await item.callback(interaction)


async def _adjust(view, *, tl_gap="0", variant="0", description="0") -> MagicMock:
    """Submit the GM-adjustments modal the way Discord does."""
    from gurps_bot.cogs.crafting import GmAdjustmentsModal

    modal = GmAdjustmentsModal(view)
    modal.tl_gap._value = tl_gap
    modal.variant_bonus._value = variant
    modal.description_bonus._value = description
    interaction = _interaction()
    await modal.on_submit(interaction)
    return interaction


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
            view.situation_select, _interaction(), "working_model", "device_exists"
        )
        expected = crafting.concept_modifier(
            Complexity.SIMPLE, working_model=True, device_exists=True
        )
        assert view.modifier().total == expected.total

    async def test_deselecting_clears_rather_than_accumulates(self):
        """A select fires with its full current value set, not a delta."""
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "simple")
        await _choose(view.situation_select, _interaction(), "new_technology")
        await _choose(view.situation_select, _interaction())
        assert view.modifier().total == Complexity.SIMPLE.concept_penalty

    async def test_the_gm_bonuses_come_from_the_adjustments_modal(self):
        view = InventionFlowView(skill=12, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "complex")
        await _adjust(view, variant="4", description="2")
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

    async def test_the_timeout_reaches_the_message(self):
        """Setting .disabled on the view changes nothing anyone sees; the
        message has to be edited. Without it the menus stayed live-looking and
        every click after the timeout answered "This interaction failed"."""
        view = InventionFlowView(skill=14, invoker_id=1)
        view.message = MagicMock()
        view.message.edit = AsyncMock()
        await view.on_timeout()
        view.message.edit.assert_awaited_once_with(view=view)

    async def test_a_deleted_message_does_not_break_the_timeout(self):
        import discord

        view = InventionFlowView(skill=14, invoker_id=1)
        view.message = MagicMock()
        view.message.edit = AsyncMock(
            side_effect=discord.NotFound(MagicMock(status=404), "gone")
        )
        await view.on_timeout()  # must not raise

    async def test_invent_remembers_the_message_it_sent(self):
        cog = CraftingCog(MagicMock())
        interaction = _interaction()
        sent = MagicMock()
        interaction.original_response = AsyncMock(return_value=sent)
        await cog.invent.callback(cog, interaction, 14)
        view = interaction.response.send_message.await_args.kwargs["view"]
        assert view.message is sent


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


class TestRepairAcrossATechLevelGap:
    """`/craft repair`'s tech-line layer, wired 2026-08-15.

    Written from the book alone. The scenario shape — a TL10 beam weapon
    worked on with TL9 skill — is the case the tech-level gap exists for.
    """

    async def _run(self, **kwargs):
        cog = CraftingCog(MagicMock())
        interaction = _interaction()
        await cog.repair.callback(
            cog,
            interaction,
            kwargs.pop("price", 5_000),
            kwargs.pop("current_hp", 5),
            kwargs.pop("max_hp", 10),
            **kwargs,
        )
        return interaction

    async def _embed(self, **kwargs):
        return (await self._run(**kwargs)).response.send_message.await_args.kwargs[
            "embed"
        ]

    async def test_one_tl_above_the_technician_is_minus_five(self):
        embed = await self._embed(tech_level=9, item_tech_level=10)
        modifiers = next(f for f in embed.fields if f.name == "Modifiers")
        assert "-5" in modifiers.value
        assert "B168" in modifiers.value

    async def test_one_tl_below_is_only_minus_one(self):
        """The asymmetry, at the surface. Obsolete gear is far kinder than
        advanced gear, and a symmetric implementation cannot say so."""
        embed = await self._embed(tech_level=9, item_tech_level=8)
        modifiers = next(f for f in embed.fields if f.name == "Modifiers")
        assert "-1" in modifiers.value

    async def test_four_tls_up_is_refused_as_impossible(self):
        interaction = await self._run(tech_level=9, item_tech_level=13)
        kwargs = interaction.response.send_message.await_args.kwargs
        assert kwargs["ephemeral"] is True
        assert "impossible" in kwargs["content"].lower()

    async def test_an_item_tl_without_your_tl_asks_rather_than_guessing(self):
        """A gap needs two numbers. Assuming the campaign TL here would be the
        bot inventing an adjudication."""
        interaction = await self._run(item_tech_level=10)
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True

    async def test_no_tl_given_leaves_the_roll_alone(self):
        embed = await self._embed()
        modifiers = next(f for f in embed.fields if f.name == "Modifiers")
        assert "B168" not in modifiers.value

    async def test_unfamiliarity_and_the_gap_both_land(self):
        embed = await self._embed(tech_level=9, item_tech_level=10, unfamiliar=True)
        modifiers = next(f for f in embed.fields if f.name == "Modifiers")
        assert "B168" in modifiers.value
        assert "B169" in modifiers.value

    async def test_an_emp_wrecked_circuit_board_is_ten_worse(self):
        embed = await self._embed(emp="SOLID_STATE")
        modifiers = next(f for f in embed.fields if f.name == "Modifiers")
        assert "-10" in modifiers.value


class TestBrewHonoursTheReferenceScenarioAtTheSurface:
    """`/craft brew` — added 2026-08-15, when re-verifying the alchemy
    reference scenario found the domain had no consumer at all.

    Six of its seven conditions passed at module level and the module was
    imported by nothing but its own tests, so conditions 4 (mastery is
    inferred, never asked) and 7 (mana is an input) had no surface on which
    they could be honoured or broken. A domain nobody can reach is not a
    domain that passes.
    """

    async def _run(self, **kwargs):
        cog = CraftingCog(MagicMock())
        interaction = _interaction()
        await cog.brew.callback(
            cog,
            interaction,
            kwargs.pop("alchemy_skill", 12),
            kwargs.pop("cost_per_dose", 200),
            **kwargs,
        )
        return interaction

    async def _embed(self, **kwargs):
        return (await self._run(**kwargs)).response.send_message.await_args.kwargs[
            "embed"
        ]

    async def test_the_reference_scenario_reaches_eleven(self):
        embed = await self._embed(doses=2, technique=12, formulary=True)
        roll = next(f for f in embed.fields if f.name == "Roll against")
        assert "11" in roll.value

    async def test_the_command_never_asks_whether_you_mastered_it(self):
        """Condition 4. The two numbers that decide mastery are already
        parameters, so a third question would be asking the user to restate
        what the bot was handed."""
        import inspect

        params = set(inspect.signature(CraftingCog.brew.callback).parameters)
        assert not {"unmastered", "mastered", "blind"} & params

    async def test_taking_the_formulary_away_changes_nothing_when_mastered(self):
        with_book = await self._embed(doses=2, technique=12, formulary=True)
        without = await self._embed(doses=2, technique=12, formulary=False)
        assert (
            next(f for f in with_book.fields if f.name == "Roll against").value
            == next(f for f in without.fields if f.name == "Roll against").value
        )

    async def test_an_unmastered_brewer_alone_takes_the_six(self):
        embed = await self._embed(doses=2, technique=11, formulary=False)
        assert "4" in next(f for f in embed.fields if f.name == "Roll against").value
        modifiers = next(f for f in embed.fields if f.name == "Modifiers")
        assert "-6" in modifiers.value

    async def test_materials_multiply_and_time_does_not(self):
        embed = await self._embed(doses=2, technique=12, weeks=1.0)
        materials = next(f for f in embed.fields if f.name == "Materials")
        time = next(f for f in embed.fields if f.name == "Time")
        assert "$400" in materials.value
        assert "1 week" in time.value
        assert "2 weeks" not in time.value

    async def test_no_mana_is_refused_rather_than_priced(self):
        interaction = await self._run(mana="NONE")
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True

    async def test_low_mana_doubles_the_clock(self):
        embed = await self._embed(mana="LOW", weeks=1.0)
        time = next(f for f in embed.fields if f.name == "Time")
        assert "2 weeks" in time.value

    async def test_very_high_mana_says_every_failure_is_critical(self):
        embed = await self._embed(mana="VERY_HIGH")
        assert any("every** failure" in (f.value or "") for f in embed.fields)

    async def test_the_disaster_roll_is_per_dose_not_per_extra_dose(self):
        """The off-by-one this domain is built to survive: the brew roll is
        -1 per EXTRA dose, the disaster roll -1 per dose."""
        embed = await self._embed(doses=3, technique=12)
        modifiers = next(f for f in embed.fields if f.name == "Modifiers")
        failure = next(f for f in embed.fields if f.name == "On a failure")
        assert "-2" in modifiers.value
        assert "-3" in failure.value

    async def test_a_weaker_helper_takes_over_the_roll(self):
        embed = await self._embed(technique=12, helper_skill=9)
        assert any(f.name == "Who rolls" for f in embed.fields)

    @pytest.mark.parametrize(
        "kwargs", [{"doses": 0}, {"cost_per_dose": -1}, {"weeks": 0}]
    )
    async def test_nonsense_input_is_refused(self, kwargs):
        interaction = await self._run(**kwargs)
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


# --- the project surface ----------------------------------------------------
#
# These need a real database: the commands are thin, and what is worth asserting
# is that they route through the service and keep the money apart end to end.

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.cogs.crafting import StartProjectModal
from gurps_bot.db import crafting as _crafting_models  # noqa: F401
from gurps_bot.db.models import Base
from gurps_bot.services import crafting as service


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


def _interaction_with_db(db, user_id: int = 1, guild_id: int = 99) -> MagicMock:
    interaction = _interaction(user_id)
    interaction.guild_id = guild_id
    interaction.client.db = db
    return interaction


async def _seed_project(db, **kwargs):
    async with db() as s:
        project = await service.start_project(
            s,
            discord_user_id=kwargs.pop("discord_user_id", 1),
            guild_id=kwargs.pop("guild_id", 99),
            name=kwargs.pop("name", "portable mansion"),
            complexity=kwargs.pop("complexity", "amazing"),
            skill=kwargs.pop("skill", 18),
            retail_price=kwargs.pop("retail_price", 250_000),
            **kwargs,
        )
        await s.commit()
        return project.id


class TestProjectsList:
    async def test_an_empty_list_says_how_to_start_one(self, db):
        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db)
        await cog.projects.callback(cog, interaction, False)
        kwargs = interaction.response.send_message.await_args.kwargs
        assert "/craft invent" in kwargs["content"]
        assert kwargs["ephemeral"] is True

    async def test_it_lists_your_live_projects(self, db):
        await _seed_project(db, name="mansion")
        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db)
        await cog.projects.callback(cog, interaction, False)
        embed = interaction.response.send_message.await_args.kwargs["embed"]
        assert any("mansion" in f.name for f in embed.fields)

    async def test_it_does_not_list_another_users(self, db):
        await _seed_project(db, discord_user_id=2, name="theirs")
        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db, user_id=1)
        await cog.projects.callback(cog, interaction, False)
        assert "content" in interaction.response.send_message.await_args.kwargs


class TestProjectDetail:
    async def test_a_missing_project_says_so_rather_than_erroring(self, db):
        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db)
        await cog.project.callback(cog, interaction, 404)
        assert "404" in interaction.response.send_message.await_args.kwargs["content"]

    async def test_the_spend_is_broken_out_by_kind(self, db):
        project_id = await _seed_project(db)
        async with db() as s:
            project = await service.get_project(s, project_id, 1)
            await service.record_charge(s, project, kind="facilities", amount=500_000)
            await service.record_attempt(s, project, amount=250_000, outcome="failure")
            await s.commit()

        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db)
        await cog.project.callback(cog, interaction, project_id)
        embed = interaction.response.send_message.await_args.kwargs["embed"]
        spent = next(f for f in embed.fields if f.name == "Spent so far")
        assert "facilities: $500,000" in spent.value
        assert "attempt: $250,000" in spent.value
        assert "$750,000" not in spent.value  # never summed

    async def test_the_history_shows_what_each_charge_bought(self, db):
        project_id = await _seed_project(db)
        async with db() as s:
            project = await service.get_project(s, project_id, 1)
            await service.record_attempt(s, project, amount=250_000, outcome="failure")
            await s.commit()

        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db)
        await cog.project.callback(cog, interaction, project_id)
        embed = interaction.response.send_message.await_args.kwargs["embed"]
        assert any("failure" in (f.value or "") for f in embed.fields)

    async def test_the_flawed_theory_never_reaches_the_embed(self, db):
        """B473 makes the Concept roll secret so the player cannot learn it.

        A project view the player runs themselves is the last place it may leak.
        """
        project_id = await _seed_project(db)
        async with db() as s:
            project = await service.get_project(s, project_id, 1)
            await service.mark_flawed_theory(s, project)
            await s.commit()

        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db)
        await cog.project.callback(cog, interaction, project_id)
        embed = interaction.response.send_message.await_args.kwargs["embed"]
        rendered = " ".join(
            [embed.title or "", embed.description or ""]
            + [f"{f.name} {f.value}" for f in embed.fields]
        ).lower()
        assert "flaw" not in rendered
        assert "theory" not in rendered

    async def test_another_user_cannot_read_it(self, db):
        project_id = await _seed_project(db, discord_user_id=2)
        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db, user_id=1)
        await cog.project.callback(cog, interaction, project_id)
        assert "content" in interaction.response.send_message.await_args.kwargs


class TestAbandon:
    async def test_it_ends_the_project_and_keeps_the_history(self, db):
        project_id = await _seed_project(db)
        async with db() as s:
            project = await service.get_project(s, project_id, 1)
            await service.record_attempt(s, project, amount=10, outcome="failure")
            await s.commit()

        cog = CraftingCog(MagicMock())
        await cog.abandon.callback(cog, _interaction_with_db(db), project_id)

        async with db() as s:
            found = await service.get_project(s, project_id, 1)
            assert found.stage == "abandoned"
            assert len(await service.charge_history(s, project_id)) == 1

    async def test_abandoning_twice_says_so(self, db):
        project_id = await _seed_project(db)
        cog = CraftingCog(MagicMock())
        await cog.abandon.callback(cog, _interaction_with_db(db), project_id)
        interaction = _interaction_with_db(db)
        await cog.abandon.callback(cog, interaction, project_id)
        assert "already" in interaction.response.send_message.await_args.kwargs["content"]

    async def test_another_user_cannot_abandon_it(self, db):
        project_id = await _seed_project(db, discord_user_id=2)
        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db, user_id=1)
        await cog.abandon.callback(cog, interaction, project_id)
        async with db() as s:
            found = await service.get_project(s, project_id, 2)
            assert found.stage == "concept"


class TestSavingFromTheGuidedFlow:
    """The anchor scene has to become a project without retyping anything."""

    async def _submit(self, db, view, name="portable mansion", price="250000"):
        modal = StartProjectModal(view)
        modal.project_name._value = name
        modal.retail_price._value = price
        interaction = _interaction_with_db(db)
        await modal.on_submit(interaction)
        return interaction

    async def test_an_absurd_price_is_refused_with_a_reason(self, db):
        """It reached SQLite as a 20-digit int and raised OverflowError on
        flush; the modal has no error hook, so the user got no reply at all."""
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "simple")
        interaction = await self._submit(db, view, price="9" * 20)
        said = interaction.response.send_message.await_args.kwargs["content"]
        assert "price" in said.lower()
        async with db() as s:
            assert await service.list_projects(s, 1, 99, include_finished=True) == []

    async def test_the_largest_allowed_price_saves(self, db):
        from gurps_bot.cogs.crafting import MAX_RETAIL_PRICE

        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "simple")
        await self._submit(db, view, price=str(MAX_RETAIL_PRICE))
        async with db() as s:
            (found,) = await service.list_projects(s, 1, 99)
            assert found.retail_price == MAX_RETAIL_PRICE

    async def test_it_stores_the_menu_choices(self, db):
        view = InventionFlowView(skill=18, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "amazing")
        await _adjust(view, tl_gap="3", variant="2")
        await _choose(view.situation_select, _interaction(), "new_technology")

        await self._submit(db, view)

        async with db() as s:
            found = (await service.list_projects(s, 1, 99))[0]
            assert found.complexity == "amazing"
            assert found.skill == 18
            assert found.modifiers_json["situations"] == ["new_technology"]
            assert found.modifiers_json["variant_bonus"] == 2
            assert found.modifiers_json["tl_gap"] == 3

    async def test_the_stored_modifiers_rebuild_the_same_number(self, db):
        """Storing the GM's calls rather than the total is only worth it if the
        total can be recovered from them."""
        view = InventionFlowView(skill=18, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "complex")
        await _choose(view.situation_select, _interaction(), "working_model")
        await _adjust(view, tl_gap="2", description="1")
        expected = view.target()

        await self._submit(db, view)

        async with db() as s:
            found = (await service.list_projects(s, 1, 99))[0]
        stored = found.modifiers_json
        rebuilt = crafting.concept_modifier(
            Complexity[found.complexity.upper()],
            variant_bonus=stored["variant_bonus"],
            description_bonus=stored["description_bonus"],
            tl_gap=stored["tl_gap"],
            **{k: True for k in stored["situations"]},
        )
        assert crafting.effective_target(found.skill, rebuilt) == expected

    async def test_a_bad_price_is_refused_without_creating_anything(self, db):
        view = InventionFlowView(skill=18, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "simple")
        interaction = await self._submit(db, view, price="lots")

        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True
        async with db() as s:
            assert await service.list_projects(s, 1, 99) == []

    async def test_a_name_that_sanitizes_to_nothing_is_refused(self, db):
        view = InventionFlowView(skill=18, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "simple")
        # "@@@", not "!!!" — sanitize_name keeps ordinary punctuation (GURPS
        # trait names like "Vow (Chastity)" depend on that), so "!!!" survives
        # and would never reach the guard this is testing.
        await self._submit(db, view, name="@@@")

        async with db() as s:
            assert await service.list_projects(s, 1, 99) == []

    async def test_saving_before_choosing_asks_first(self, db):
        view = InventionFlowView(skill=18, invoker_id=1)
        interaction = _interaction_with_db(db)
        await view.save_btn.callback(interaction)
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True
        interaction.response.send_modal.assert_not_called()


# --- choosing a method ------------------------------------------------------


class TestTheMethodIsChoosable:
    """Gadgeteering has to be reachable, or the slice did not land.

    The oracle's own words: "A slice nobody can find did not land."
    """

    async def test_new_inventions_is_the_default(self):
        view = InventionFlowView(skill=14, invoker_id=1)
        from gurps_bot.mechanics.crafting import Method

        assert view.method is Method.NEW_INVENTIONS

    async def test_every_method_option_resolves_to_a_real_method(self):
        from gurps_bot.mechanics.crafting import Method

        view = InventionFlowView(skill=14, invoker_id=1)
        for option in view.method_select.options:
            await _choose(view.method_select, _interaction(), option.value)
            assert view.method in Method

    async def test_switching_method_changes_the_target(self):
        """Complex is -14 under B473 and -4 under B475. Same everything else."""
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "complex")
        assert view.target() == 14 - 14

        await _choose(view.method_select, _interaction(), "GADGETEERING")
        assert view.target() == 14 - 4

    async def test_a_gadgeteer_ignores_the_new_technology_penalty(self):
        """B475 says ignore it. The menu still offers it, so the flow has to
        drop it rather than pass it to an engine that refuses the argument."""
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "simple")
        await _choose(view.situation_select, _interaction(), "new_technology")
        await _choose(view.method_select, _interaction(), "GADGETEERING")

        # Simple is 0 for a gadgeteer, and the -5 must not appear.
        assert view.target() == 14

    async def test_the_dropped_penalty_is_stated_not_silent(self):
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "simple")
        await _choose(view.situation_select, _interaction(), "new_technology")
        await _choose(view.method_select, _interaction(), "GADGETEERING")

        embed = view.summary_embed()
        assert any(f.name == "Ignored" for f in embed.fields)

    async def test_new_inventions_does_not_claim_to_ignore_anything(self):
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "simple")
        await _choose(view.situation_select, _interaction(), "new_technology")

        embed = view.summary_embed()
        assert not any(f.name == "Ignored" for f in embed.fields)
        assert view.target() == 14 - 6 - 5

    async def test_the_embed_names_the_method_in_play(self):
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "simple")
        await _choose(view.method_select, _interaction(), "QUICK_GADGETEERING")
        assert "Quick Gadgeteering" in view.summary_embed().description

    async def test_the_method_is_stored_with_the_project(self, db):
        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "complex")
        await _choose(view.method_select, _interaction(), "GADGETEERING")

        modal = StartProjectModal(view)
        modal.project_name._value = "ray gun"
        modal.retail_price._value = "1000"
        await modal.on_submit(_interaction_with_db(db))

        async with db() as s:
            found = (await service.list_projects(s, 1, 99))[0]
            assert found.modifiers_json["method"] == "GADGETEERING"

    async def test_the_stored_method_rebuilds_the_same_target(self, db):
        """A gadgeteering project resumed later must not silently re-render
        under the harsher New Inventions ladder."""
        from gurps_bot.mechanics.crafting import Method

        view = InventionFlowView(skill=14, invoker_id=1)
        await _choose(view.complexity_select, _interaction(), "amazing")
        await _choose(view.method_select, _interaction(), "GADGETEERING")
        await _adjust(view, tl_gap="2")
        expected = view.target()

        modal = StartProjectModal(view)
        modal.project_name._value = "mansion"
        modal.retail_price._value = "0"
        await modal.on_submit(_interaction_with_db(db))

        async with db() as s:
            found = (await service.list_projects(s, 1, 99))[0]
        stored = found.modifiers_json
        assert stored["method"] == Method.GADGETEERING.name
        rebuilt = crafting.gadgeteer_concept_modifier(
            Complexity[found.complexity.upper()],
            variant_bonus=stored["variant_bonus"],
            description_bonus=stored["description_bonus"],
            tl_gap=stored["tl_gap"],
        )
        assert crafting.effective_target(found.skill, rebuilt) == expected


# --- /craft repair ----------------------------------------------------------


class TestRepairCommand:
    """B484 at the surface. The domain has to be findable or it did not land."""

    async def _run(self, **kwargs):
        cog = CraftingCog(MagicMock())
        interaction = _interaction()
        await cog.repair.callback(
            cog,
            interaction,
            kwargs.pop("price", 50_000),
            kwargs.pop("current_hp", 5),
            kwargs.pop("max_hp", 10),
            **kwargs,
        )
        return interaction

    async def test_a_damaged_item_gets_the_minor_tier(self):
        embed = (await self._run()).response.send_message.await_args.kwargs["embed"]
        assert "Minor repairs" in embed.title

    async def test_zero_hp_gets_the_major_tier_and_a_parts_range(self):
        embed = (
            await self._run(current_hp=0, price=1_000)
        ).response.send_message.await_args.kwargs["embed"]
        assert "Major repairs" in embed.title
        parts = next(f for f in embed.fields if f.name == "Spare parts first")
        assert "$100" in parts.value and "$600" in parts.value

    async def test_a_minor_repair_is_not_told_to_buy_parts(self):
        embed = (await self._run()).response.send_message.await_args.kwargs["embed"]
        assert not any(f.name == "Spare parts first" for f in embed.fields)

    async def test_a_destroyed_item_says_replace_and_offers_no_roll(self):
        embed = (
            await self._run(destroyed=True, price=2_500)
        ).response.send_message.await_args.kwargs["embed"]
        assert "Beyond repair" in embed.title
        assert "$2,500" in embed.fields[0].value
        assert not any(f.name == "Roll" for f in embed.fields)

    async def test_five_times_max_hp_is_also_destruction(self):
        embed = (
            await self._run(current_hp=-50, max_hp=10)
        ).response.send_message.await_args.kwargs["embed"]
        assert "Beyond repair" in embed.title

    async def test_the_roll_reports_a_quantity_not_a_pass_fail(self):
        """The domain's distinctive rule, at the surface."""
        embed = (await self._run()).response.send_message.await_args.kwargs["embed"]
        success = next(f for f in embed.fields if f.name == "On a success")
        assert "per point of margin" in success.value

    async def test_the_price_ladder_reaches_the_embed(self):
        cheap = (
            await self._run(price=500)
        ).response.send_message.await_args.kwargs["embed"]
        dear = (
            await self._run(price=5_000_000)
        ).response.send_message.await_args.kwargs["embed"]
        assert "+1" in next(f for f in cheap.fields if f.name == "Modifiers").value
        assert "-3" in next(f for f in dear.fields if f.name == "Modifiers").value

    async def test_the_workspace_ladder_reaches_the_roll(self):
        """B484 cites B345 rather than restating it, so the workspace is a
        menu of the book's rungs, not a number the player has to know."""
        improvised = (
            await self._run(price=500, workspace="IMPROVISED")
        ).response.send_message.await_args.kwargs["embed"]
        fine = (
            await self._run(price=500, workspace="FINE")
        ).response.send_message.await_args.kwargs["embed"]

        # Armoury is technological, so improvised is -5 rather than -2.
        assert "-5" in next(f for f in improvised.fields if f.name == "Workspace").value
        assert "+2" in next(f for f in fine.fields if f.name == "Workspace").value

    async def test_the_time_spent_modifier_is_still_the_gms(self):
        embed = (
            await self._run(price=500, time_spent=1)
        ).response.send_message.await_args.kwargs["embed"]
        modifiers = next(f for f in embed.fields if f.name == "Modifiers").value
        assert "B346" in modifiers

    async def test_the_best_workspace_needs_a_tech_level_rather_than_guessing(self):
        """B345 makes BEST depend on TL, so the command must ask instead of
        handing back a confidently wrong +2."""
        interaction = await self._run(price=500, workspace="BEST")
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True

        embed = (
            await self._run(price=500, workspace="BEST", tech_level=10)
        ).response.send_message.await_args.kwargs["embed"]
        assert "+5" in next(f for f in embed.fields if f.name == "Workspace").value

    async def test_the_attempt_time_does_not_depend_on_the_item(self):
        cheap = (
            await self._run(price=100)
        ).response.send_message.await_args.kwargs["embed"]
        dear = (
            await self._run(price=9_000_000)
        ).response.send_message.await_args.kwargs["embed"]
        assert (
            next(f for f in cheap.fields if f.name == "Per attempt").value
            == next(f for f in dear.fields if f.name == "Per attempt").value
        )

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"price": -1},
            {"max_hp": 0},
            {"time_spent": -99},
            {"workspace": "NONSENSE"},
        ],
    )
    async def test_nonsense_input_is_refused(self, kwargs):
        interaction = await self._run(**kwargs)
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True


class TestProseAgreesWithTheEngine:
    """The 7/31 lesson (test_choice_labels): display text and the engine drift
    apart the moment nothing couples them. These pin the claims this cog makes
    that the engine can contradict."""

    def test_the_concept_warning_does_not_deny_what_the_engine_does(self):
        """A Concept critical failure ADVANCES — the flawed theory goes to
        Prototype and eats prototype money, which is the whole trap B473
        builds the secrecy around. The summary embed once said it "never
        becomes a prototype", the trap told backwards."""
        assert crafting.concept_outcome("critical_failure").advances

        view = InventionFlowView(skill=12, invoker_id=1)
        view.complexity = Complexity.AVERAGE
        embed = view.summary_embed()
        cadence = next(f for f in embed.fields if f.name == "Once per day")
        assert "never becomes a prototype" not in cadence.value

    def test_no_choice_name_carries_generated_title_caps(self):
        """Choice names are display strings, authored by hand everywhere but
        one place — an enum rendered through .title(), which capitalizes
        conjunctions: "Longbow Or Crossbow". Sentence case is the 7/31 ruling;
        GURPS proper nouns keep their caps, but "Or" is nobody's proper noun."""
        import re

        bad = re.compile(r"\b(Or|And|Of|The|In|At|Per)\b")
        offenders = [
            (command.name, choice.name)
            for command in CraftingCog.craft.commands
            for param in command.parameters
            for choice in (param.choices or [])
            if bad.search(choice.name)
        ]
        assert offenders == []


class TestEnchantMethodsDisagreeOnAssistants:
    """Settled against the printed page 2026-08-15: every skill penalty in
    enchanting — assistants, the caster's HP, bystanders — is printed inside
    Quick and Dirty (p. 17). Slow and Sure's assistants divide the mage-days
    and touch no roll, and it has no FP or HP cost at all. The cog used to
    apply the Quick and Dirty penalties to both methods."""

    async def _run(self, **kwargs):
        from unittest.mock import MagicMock as _MM

        interaction = _interaction()
        cog = CraftingCog(_MM())
        defaults = dict(enchant_skill=17, spell_skill=16, energy=100)
        await cog.enchant.callback(cog, interaction, **{**defaults, **kwargs})
        return interaction

    def _field(self, interaction, name):
        embed = interaction.response.send_message.await_args.kwargs["embed"]
        return next((f for f in embed.fields if f.name == name), None)

    async def test_slow_and_sure_assistants_do_not_touch_the_roll(self):
        interaction = await self._run(method="SLOW_AND_SURE", assistants=2)
        roll = self._field(interaction, "Roll against, and the item's Power")
        assert "**16**" in roll.value
        assert self._field(interaction, "Modifiers") is None

    async def test_quick_and_dirty_assistants_still_cost_one_each(self):
        interaction = await self._run(method="QUICK_AND_DIRTY", assistants=2)
        roll = self._field(interaction, "Roll against, and the item's Power")
        assert "**14**" in roll.value
        assert "2 assistants" in self._field(interaction, "Modifiers").value

    async def test_slow_and_sure_refuses_hp(self):
        interaction = await self._run(method="SLOW_AND_SURE", hp_spent=2)
        call = interaction.response.send_message.await_args
        assert call.kwargs["ephemeral"] is True
        text = call.kwargs.get("content") or (call.args[0] if call.args else "")
        assert "no FP or HP" in text

    async def test_the_headcount_cap_is_quick_and_dirty_only(self):
        crowded = await self._run(method="QUICK_AND_DIRTY", assistants=5)
        assert self._field(crowded, "⚠️ Too many hands") is not None
        slow = await self._run(method="SLOW_AND_SURE", assistants=5)
        assert self._field(slow, "⚠️ Too many hands") is None


class TestTheFlowLeavesDiscordsHooksAlone:
    """``View._refresh(components)`` is discord.py's, not ours.

    The gateway calls it on every MESSAGE_UPDATE for a message whose view it
    tracks. The flow once defined its own ``async def _refresh(interaction)``,
    so each edit of the flow's message handed the component list to our
    redraw, got back a coroutine nobody awaited, and skipped discord.py's own
    component sync.
    """

    def test_discords_refresh_hook_is_not_overridden(self):
        view = InventionFlowView(skill=14, invoker_id=1)
        assert view._refresh([]) is None


class TestDelete:
    """The project cap counts finished projects on purpose and tells the user
    to "Delete some first" — but nothing could delete one, so reaching it was
    a permanent lockout. /craft delete removes a FINISHED project."""

    async def test_a_finished_project_goes_with_its_history(self, db):
        project_id = await _seed_project(db)
        async with db() as s:
            project = await service.get_project(s, project_id, 1)
            await service.record_attempt(s, project, amount=10, outcome="failure")
            await service.finish_project(s, project, "abandoned")
            await s.commit()

        cog = CraftingCog(MagicMock())
        await cog.delete.callback(cog, _interaction_with_db(db), project_id)

        async with db() as s:
            assert await service.get_project(s, project_id, 1) is None
            assert await service.charge_history(s, project_id) == []

    async def test_an_active_project_must_be_abandoned_first(self, db):
        project_id = await _seed_project(db)
        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db)
        await cog.delete.callback(cog, interaction, project_id)
        assert "abandon" in interaction.response.send_message.await_args.kwargs["content"].lower()
        async with db() as s:
            assert await service.get_project(s, project_id, 1) is not None

    async def test_another_users_project_is_untouched(self, db):
        project_id = await _seed_project(db, discord_user_id=2)
        async with db() as s:
            await service.finish_project(s, await service.get_project(s, project_id, 2), "abandoned")
            await s.commit()
        cog = CraftingCog(MagicMock())
        await cog.delete.callback(cog, _interaction_with_db(db, user_id=1), project_id)
        async with db() as s:
            assert await service.get_project(s, project_id, 2) is not None

    async def test_deleting_frees_a_slot_under_the_cap(self, db, monkeypatch):
        from gurps_bot.services import crafting as svc_mod
        from gurps_bot.services.limits import StorageLimitExceeded

        monkeypatch.setattr(svc_mod, "MAX_CRAFTING_PROJECTS_PER_USER", 1)
        project_id = await _seed_project(db)
        async with db() as s:
            await service.finish_project(s, await service.get_project(s, project_id, 1), "complete")
            await s.commit()
        with pytest.raises(StorageLimitExceeded):
            await _seed_project(db, name="second")

        cog = CraftingCog(MagicMock())
        await cog.delete.callback(cog, _interaction_with_db(db), project_id)
        await _seed_project(db, name="second")  # no longer refused
