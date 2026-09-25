"""Persistent projects for the four non-invention crafting domains.

Written red-first on 2026-09-25 (DESIGN_v0.5). Each domain keeps its own
vocabulary (stages, charge kinds, what `/craft work` logs) and its own
`state_json`, on the one `crafting_projects` table invention already uses.
The rules themselves are not restated here: every expected number below is
computed from the domain's own book-checked mechanics module, so a test
compares the persisted lifecycle against the calculator, never against a
figure typed from memory.

Two spec-shaped properties carry over from the invention tests:

* SPEC a-crafting-project-survives-the-session — a started project, its
  progress and its result round-trip through a fresh session.
* SPEC a-failed-attempt-never-charges-without-recording-why — a roll is one
  row carrying its outcome, written before anything is said to the user.
"""

from __future__ import annotations

from itertools import combinations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db import crafting as db_crafting
from gurps_bot.db.crafting import CraftingCharge, CraftingProject
from gurps_bot.db.models import Base
from gurps_bot.mechanics import (
    crafting_alchemy,
    crafting_enchantment,
    crafting_mundane,
    crafting_repair,
    equipment_quality,
)
from gurps_bot.mechanics.checks import Outcome, check_against
from gurps_bot.services import crafting as service
from gurps_bot.services import crafting_alchemy as alchemy_service
from gurps_bot.services import crafting_enchantment as enchantment_service
from gurps_bot.services import crafting_mundane as mundane_service
from gurps_bot.services import crafting_repair as repair_service

USER = 4242
OTHER_USER = 9999
GUILD = 777


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory):
    async with session_factory() as s:
        yield s


# --- the LTC3 ladder example the surface tests already use ------------------
LADDER = dict(list_price=90.0, weight=22.5, cost_per_lb=2.70, monthly_pay=790.0)


async def _mundane(session, **overrides) -> CraftingProject:
    kwargs = dict(
        discord_user_id=USER, guild_id=GUILD, name="a ladder", skill=14, **LADDER
    )
    kwargs.update(overrides)
    project = await mundane_service.start(session, **kwargs)
    await session.commit()
    return project


async def _alchemy(session, **overrides) -> CraftingProject:
    kwargs = dict(
        discord_user_id=USER,
        guild_id=GUILD,
        name="healing draughts",
        alchemy_skill=14,
        cost_per_dose=50,
        doses=4,
        weeks=2.0,
    )
    kwargs.update(overrides)
    project = await alchemy_service.start(session, **kwargs)
    await session.commit()
    return project


async def _enchantment(session, **overrides) -> CraftingProject:
    kwargs = dict(
        discord_user_id=USER,
        guild_id=GUILD,
        name="ring of fire",
        enchant_skill=18,
        spell_skill=16,
        energy=100,
        method="SLOW_AND_SURE",
        assistants=1,
    )
    kwargs.update(overrides)
    project = await enchantment_service.start(session, **kwargs)
    await session.commit()
    return project


async def _repair(session, **overrides) -> CraftingProject:
    kwargs = dict(
        discord_user_id=USER,
        guild_id=GUILD,
        name="the truck",
        skill=12,
        price=500,
        current_hp=5,
        max_hp=10,
    )
    kwargs.update(overrides)
    project = await repair_service.start(session, **kwargs)
    await session.commit()
    return project


async def _history(session, project_id: int) -> list[CraftingCharge]:
    return await service.charge_history(session, project_id)


class TestEachDomainOwnsItsVocabulary:
    """Per-domain DATA, shared container — the same line `test_crafting_domains`
    draws for `ModifierBreakdown`."""

    def test_five_domains_are_registered(self):
        assert set(db_crafting.VOCABULARIES) == {
            "invention", "crafting", "alchemy", "enchantment", "repair"
        }

    def test_the_vocabularies_differ_pairwise(self):
        for a, b in combinations(db_crafting.VOCABULARIES.values(), 2):
            assert a.stages != b.stages or a.charge_kinds != b.charge_kinds, (
                f"{a.domain} and {b.domain} share stages AND charge kinds — that "
                f"is one abstraction wearing two names"
            )

    def test_invention_keeps_the_vocabulary_it_shipped_with(self):
        inv = db_crafting.VOCABULARIES["invention"]
        assert inv.stages == db_crafting.STAGES
        assert inv.charge_kinds == db_crafting.CHARGE_KINDS

    def test_repair_has_no_calendar_the_others_do(self):
        units = {d: v.progress_unit for d, v in db_crafting.VOCABULARIES.items()}
        assert units["repair"] is None
        assert all(units[d] for d in ("invention", "crafting", "alchemy", "enchantment"))

    def test_an_unknown_domain_is_refused(self):
        with pytest.raises(ValueError):
            service.vocabulary_for("basketweaving")

    async def test_a_foreign_charge_kind_is_refused(self, session):
        """"attempt" is invention's and repair's; a smith cannot record one."""
        project = await _mundane(session)
        with pytest.raises(ValueError):
            await service.record_charge(session, project, kind="attempt", amount=1)

    async def test_a_foreign_stage_is_refused(self, session):
        project = await _mundane(session)
        with pytest.raises(ValueError):
            await service.advance_stage(session, project, "prototype")

    async def test_invention_still_starts_at_concept_with_no_state(self, session):
        project = await service.start_project(
            session,
            discord_user_id=USER,
            guild_id=GUILD,
            name="portable mansion",
            complexity="amazing",
            skill=18,
        )
        await session.commit()
        assert project.domain == "invention"
        assert project.stage == "concept"
        assert project.state_json is None


class TestMundaneCrafting:
    """LTC3 ch. 5 — the figures are charged up front, the hours are logged,
    then one roll on the highest skill present says how good it is."""

    async def test_start_charges_the_materials_and_opens_at_working(self, session):
        project = await _mundane(session)
        assert project.domain == "crafting"
        assert project.stage == "working"
        assert project.complexity is None
        expected = crafting_mundane.materials_cost(
            LADDER["weight"], LADDER["cost_per_lb"], crafting_mundane.MaterialMultiplier.NONE
        )
        (charge,) = await _history(session, project.id)
        assert charge.kind == "materials"
        assert charge.amount == round(expected)
        assert charge.outcome is None

    async def test_the_required_hours_come_from_the_book(self, session):
        project = await _mundane(session)
        materials = crafting_mundane.materials_cost(LADDER["weight"], LADDER["cost_per_lb"])
        labour = crafting_mundane.labor_cost(LADDER["list_price"], materials)
        rate = crafting_mundane.hourly_labor_rate(LADDER["monthly_pay"])
        assert mundane_service.required_hours(project) == pytest.approx(
            crafting_mundane.active_hours(labour, rate)
        )

    async def test_the_multiplier_and_class_are_kept(self, session):
        project = await _mundane(
            session, list_price=600.0, item_class="ARMS_OR_ARMOR", materials="SWORD_OR_PLATE"
        )
        (charge,) = await _history(session, project.id)
        assert charge.amount == round(
            crafting_mundane.materials_cost(
                LADDER["weight"], LADDER["cost_per_lb"],
                crafting_mundane.MaterialMultiplier.SWORD_OR_PLATE,
            )
        )
        assert project.state_json["inputs"]["item_class"] == "ARMS_OR_ARMOR"

    async def test_materials_dearer_than_the_item_are_refused(self, session):
        """The calculator warns and stops; a project cannot hold negative hours."""
        with pytest.raises(ValueError, match="cost more than the item"):
            await _mundane(session, materials="SWORD_OR_PLATE")
        assert (await session.scalars(select(CraftingProject))).all() == []

    async def test_hours_accumulate_and_survive_a_fresh_session(self, session_factory):
        async with session_factory() as s:
            project = await _mundane(s)
            await mundane_service.log_hours(s, project, 5.0)
            await mundane_service.log_hours(s, project, 2.5)
            await s.commit()
            project_id = project.id

        async with session_factory() as s:
            found = await service.get_project(s, project_id, USER)
            assert mundane_service.hours_worked(found) == pytest.approx(7.5)
            assert found.stage == "working"

    async def test_negative_or_zero_hours_are_refused(self, session):
        project = await _mundane(session)
        for bad in (0, -1):
            with pytest.raises(ValueError):
                await mundane_service.log_hours(session, project, bad)

    async def test_the_roll_waits_for_the_hours(self, session):
        project = await _mundane(session)
        assert mundane_service.ready_to_roll(project) is not None
        with pytest.raises(ValueError):
            await mundane_service.resolve_roll(session, project, rolled=10)

    async def _worked(self, session, **overrides) -> CraftingProject:
        project = await _mundane(session, **overrides)
        await mundane_service.log_hours(
            session, project, mundane_service.required_hours(project)
        )
        await session.commit()
        assert mundane_service.ready_to_roll(project) is None
        return project

    async def test_a_roll_reads_the_books_ladder(self, session):
        project = await self._worked(session, skill=14)
        result = await mundane_service.resolve_roll(session, project, rolled=10)
        await session.commit()
        expected = crafting_mundane.craft_quality(14 - 10, crafting_mundane.ItemClass.GENERAL)
        assert result == expected
        assert project.stage == "complete"
        assert project.state_json["result"]["quality"] == expected.quality.name
        materials, roll = await _history(session, project.id)
        assert roll.kind == "roll"
        assert roll.outcome == expected.quality.name
        assert project.attempts == 1

    async def test_superior_materials_add_to_the_margin_only_on_a_success(self, session):
        good = await self._worked(session, skill=14, fine_materials=5, name="good")
        result = await mundane_service.resolve_roll(session, good, rolled=10)
        assert result.margin == crafting_mundane.effective_margin(4, fine_materials=5)

        bad = await self._worked(session, skill=14, fine_materials=5, name="bad")
        result = await mundane_service.resolve_roll(session, bad, rolled=16)
        assert result.margin == -2  # a failure gets nothing

    async def test_junk_is_recorded_as_lost_materials(self, session):
        project = await self._worked(session, skill=10)
        result = await mundane_service.resolve_roll(session, project, rolled=15)
        assert result.is_junk
        _, roll = await _history(session, project.id)
        assert "materials" in (roll.note or "").lower()

    async def test_a_critical_success_is_only_its_margin(self, session):
        """LTC3: a critical success does nothing beyond margin of success."""
        project = await self._worked(session, skill=14)
        assert check_against(3, 14) is Outcome.CRITICAL_SUCCESS
        result = await mundane_service.resolve_roll(session, project, rolled=3)
        assert result == crafting_mundane.craft_quality(11)

    async def test_a_finished_project_cannot_be_rolled_again(self, session):
        project = await self._worked(session)
        await mundane_service.resolve_roll(session, project, rolled=10)
        await session.commit()
        with pytest.raises(ValueError):
            await mundane_service.resolve_roll(session, project, rolled=10)

    async def test_the_engine_refuses_bad_figures_before_anything_is_written(self, session):
        with pytest.raises(ValueError):
            await _mundane(session, weight=-1)
        assert (await session.scalars(select(CraftingProject))).all() == []

    async def test_skill_is_stored_as_the_rolling_skill(self, session):
        project = await _mundane(session, skill=13)
        assert project.skill == 13
        assert mundane_service.roll_target(project) == 13


class TestAlchemy:
    """Magic ch. 28 — ingredients up front, the calendar, then one roll with no
    critical successes and a two-step disaster on a critical failure."""

    async def test_start_charges_the_whole_batch(self, session):
        project = await _alchemy(session)
        assert project.domain == "alchemy"
        assert project.stage == "brewing"
        (charge,) = await _history(session, project.id)
        assert charge.kind == "ingredients"
        assert charge.amount == crafting_alchemy.batch_materials_cost(50, 4)

    async def test_the_weakest_hand_rolls(self, session):
        project = await _alchemy(session, alchemy_skill=18, helper_skill=10)
        assert project.skill == crafting_alchemy.final_roller_skill([18, 10])

    async def test_the_target_is_the_calculators(self, session):
        project = await _alchemy(session, formulary=True)
        assert alchemy_service.roll_target(project) == crafting_alchemy.effective_target(
            alchemy_skill=14, doses=4, formulary=True
        )

    async def test_no_mana_refuses_to_start(self, session):
        with pytest.raises(ValueError):
            await _alchemy(session, mana="NONE")

    async def test_low_mana_doubles_the_required_weeks(self, session):
        project = await _alchemy(session, mana="LOW")
        assert alchemy_service.required_weeks(project) == pytest.approx(
            2.0 * crafting_alchemy.brewing_time_multiplier(crafting_alchemy.Mana.LOW)
        )

    async def _brewed(self, session, **overrides) -> CraftingProject:
        project = await _alchemy(session, **overrides)
        await alchemy_service.log_weeks(session, project, alchemy_service.required_weeks(project))
        await session.commit()
        return project

    async def test_the_roll_waits_for_the_weeks(self, session):
        project = await _alchemy(session)
        with pytest.raises(ValueError):
            await alchemy_service.resolve_roll(session, project, rolled=5)

    async def test_a_success_completes_the_batch(self, session):
        project = await self._brewed(session, formulary=True)
        outcome = await alchemy_service.resolve_roll(session, project, rolled=5)
        assert outcome.succeeded
        assert project.stage == "complete"
        _, roll = await _history(session, project.id)
        assert roll.kind == "roll" and roll.outcome == "success"

    async def test_a_critical_success_is_just_a_success(self, session):
        """The domain's own check variant: "either the process worked or it did
        not". `resolve_brew` refuses the raw key; the service must never hand it one."""
        project = await self._brewed(session, formulary=True)
        assert check_against(3, alchemy_service.roll_target(project)) is Outcome.CRITICAL_SUCCESS
        outcome = await alchemy_service.resolve_roll(session, project, rolled=3)
        assert outcome.succeeded
        _, roll = await _history(session, project.id)
        assert roll.outcome == "success"

    async def test_a_failure_ruins_the_ingredients(self, session):
        project = await self._brewed(session, formulary=True)
        target = alchemy_service.roll_target(project)
        outcome = await alchemy_service.resolve_roll(session, project, rolled=target + 1)
        assert outcome.ingredients_ruined and not outcome.needs_disaster_roll
        assert project.stage == "complete"

    async def test_a_critical_failure_parks_the_batch_at_disaster(self, session):
        project = await self._brewed(session, formulary=True)
        outcome = await alchemy_service.resolve_roll(session, project, rolled=18)
        assert outcome.needs_disaster_roll
        assert project.stage == "disaster"
        assert project.state_json["progress"]["disaster_roll_modifier"] == (
            crafting_alchemy.disaster_roll_penalty(4)
        )

    async def test_the_disaster_roll_is_the_technique_at_minus_one_per_dose(self, session):
        project = await self._brewed(session, formulary=True)
        await alchemy_service.resolve_roll(session, project, rolled=18)
        technique = crafting_alchemy.default_technique_level(14)
        assert alchemy_service.disaster_target(project) == (
            technique + crafting_alchemy.disaster_roll_penalty(4)
        )

    async def test_averting_the_disaster_completes_with_the_ingredients_gone(self, session):
        project = await self._brewed(session, formulary=True)
        await alchemy_service.resolve_roll(session, project, rolled=18)
        disaster = await alchemy_service.resolve_disaster(session, project, rolled=3, rolled_3d=None)
        assert disaster is None
        assert project.stage == "complete"
        history = await _history(session, project.id)
        assert history[-1].outcome == "disaster averted"

    async def test_a_failed_disaster_roll_reads_the_table(self, session):
        project = await self._brewed(session, formulary=True)
        await alchemy_service.resolve_roll(session, project, rolled=18)
        target = alchemy_service.disaster_target(project)
        disaster = await alchemy_service.resolve_disaster(
            session, project, rolled=target + 1, rolled_3d=11
        )
        assert disaster == crafting_alchemy.disaster_for(11)
        assert disaster.lab_destroyed
        assert project.stage == "complete"
        history = await _history(session, project.id)
        assert history[-1].outcome == "disaster"

    async def test_the_disaster_roll_needs_a_batch_parked_at_disaster(self, session):
        project = await self._brewed(session, formulary=True)
        with pytest.raises(ValueError):
            await alchemy_service.resolve_disaster(session, project, rolled=3, rolled_3d=None)

    async def test_very_high_mana_makes_every_failure_critical(self, session):
        project = await self._brewed(session, mana="VERY_HIGH", formulary=True)
        target = alchemy_service.roll_target(project)
        outcome = await alchemy_service.resolve_roll(session, project, rolled=target + 1)
        assert outcome.needs_disaster_roll
        assert project.stage == "disaster"


class TestEnchantment:
    """Magic pp. 16-18 — Slow and Sure burns the calendar, Quick and Dirty
    burns energy in one sitting; the ceremonial roll ends both."""

    async def test_start_stores_the_lower_skill_and_opens_at_enchanting(self, session):
        project = await _enchantment(session)
        assert project.domain == "enchantment"
        assert project.stage == "enchanting"
        assert project.skill == crafting_enchantment.enchanting_skill(18, 16)

    async def test_slow_and_sure_days_split_across_the_circle(self, session):
        project = await _enchantment(session, assistants=1)
        assert enchantment_service.required_days(project) == pytest.approx(
            crafting_enchantment.slow_and_sure_days(100, 2)
        )

    async def test_a_missed_day_costs_two(self, session):
        project = await _enchantment(session)
        await enchantment_service.log_days(session, project, 10, missed=1)
        assert enchantment_service.required_days(project) == pytest.approx(
            crafting_enchantment.slow_and_sure_days(100, 2)
            + crafting_enchantment.make_up_days(1)
        )
        assert enchantment_service.days_worked(project) == pytest.approx(10)

    async def test_quick_and_dirty_has_no_calendar(self, session):
        project = await _enchantment(session, method="QUICK_AND_DIRTY", assistants=0)
        assert enchantment_service.ready_to_roll(project) is None
        with pytest.raises(ValueError):
            await enchantment_service.log_days(session, project, 1)

    async def test_quick_and_dirty_penalties_reach_the_target(self, session):
        project = await _enchantment(
            session, method="QUICK_AND_DIRTY", assistants=1, hp_spent=2, bystanders=True
        )
        assert enchantment_service.roll_target(project) == crafting_enchantment.effective_skill(
            18, 16,
            method=crafting_enchantment.Method.QUICK_AND_DIRTY,
            assistants=1, hp_spent=2, bystanders=True,
        )

    async def test_slow_and_sure_refuses_hp_spending(self, session):
        with pytest.raises(ValueError):
            await _enchantment(session, hp_spent=1)

    async def test_the_roll_waits_for_the_days(self, session):
        project = await _enchantment(session)
        with pytest.raises(ValueError):
            await enchantment_service.resolve_roll(session, project, rolled_3d=10)

    async def _cast(self, session, **overrides) -> CraftingProject:
        project = await _enchantment(session, **overrides)
        await enchantment_service.log_days(
            session, project, enchantment_service.required_days(project)
        )
        await session.commit()
        return project

    async def test_a_success_records_the_items_power(self, session):
        project = await self._cast(session)
        result = await enchantment_service.resolve_roll(session, project, rolled_3d=10)
        assert result.outcome is crafting_enchantment.CeremonialOutcome.SUCCESS
        assert project.stage == "complete"
        assert project.state_json["result"]["power"] == crafting_enchantment.item_power(16)
        (casting,) = await _history(session, project.id)
        assert casting.kind == "casting" and casting.outcome == "success"

    async def test_a_sixteen_fails_however_high_the_skill(self, session):
        project = await self._cast(session, enchant_skill=25, spell_skill=25)
        result = await enchantment_service.resolve_roll(session, project, rolled_3d=16)
        assert result.outcome is crafting_enchantment.CeremonialOutcome.FAILURE
        assert result.materials_lost  # Slow and Sure: the materials are lost
        assert project.stage == "complete"

    async def test_a_critical_failure_destroys_the_item(self, session):
        project = await self._cast(session)
        result = await enchantment_service.resolve_roll(session, project, rolled_3d=17)
        assert result.item_destroyed and result.materials_lost
        assert project.state_json["result"]["item_destroyed"] is True

    async def test_a_critical_success_carries_the_power_bonus(self, session):
        project = await self._cast(session)
        result = await enchantment_service.resolve_roll(
            session, project, rolled_3d=3, power_bonus_rolled=7
        )
        assert result.power_bonus == crafting_enchantment.CRITICAL_SUCCESS_POWER_BONUS
        assert project.state_json["result"]["power"] == 16 + 7
        assert project.state_json["result"]["may_have_further_enhancement"] is True

    async def test_materials_value_is_charged_when_given(self, session):
        project = await _enchantment(session, materials_value=1200)
        (charge,) = await _history(session, project.id)
        assert charge.kind == "materials" and charge.amount == 1200


class TestRepair:
    """B484 — an attempt IS the clock: thirty minutes each, and the roll
    returns a quantity."""

    async def test_a_minor_repair_starts_at_repairing(self, session):
        project = await _repair(session)
        assert project.domain == "repair"
        assert project.stage == "repairing"
        assert project.state_json["inputs"]["tier"] == "MINOR"
        assert await _history(session, project.id) == []

    async def test_the_target_is_the_calculators(self, session):
        project = await _repair(session, workspace="GOOD", time_spent=2)
        equipment = equipment_quality.modifier(
            equipment_quality.EquipmentQuality.GOOD, technological=True, tech_level=None
        )
        expected = 12 + crafting_repair.repair_modifier(
            500, crafting_repair.RepairTier.MINOR,
            equipment_modifier=equipment, time_spent_modifier=2,
        ).total
        assert repair_service.roll_target(project) == expected

    async def test_a_major_repair_waits_for_parts(self, session):
        project = await _repair(session, current_hp=0)
        assert project.stage == "parts"
        assert repair_service.needs_parts(project)
        with pytest.raises(ValueError):
            await repair_service.resolve_attempt(session, project, rolled=10)

    async def test_buying_parts_charges_the_rolled_share_and_moves_on(self, session):
        project = await _repair(session, current_hp=0)
        cost = await repair_service.buy_parts(session, project, rolled_1d=3)
        assert cost == crafting_repair.major_repair_parts_cost(500, 3)
        assert project.stage == "repairing"
        (charge,) = await _history(session, project.id)
        assert charge.kind == "parts" and charge.amount == cost

    async def test_parts_cannot_be_bought_twice(self, session):
        project = await _repair(session, current_hp=0)
        await repair_service.buy_parts(session, project, rolled_1d=3)
        with pytest.raises(ValueError):
            await repair_service.buy_parts(session, project, rolled_1d=3)

    async def test_beyond_repair_is_refused_at_the_door(self, session):
        with pytest.raises(ValueError):
            await _repair(session, current_hp=-60)

    async def test_a_success_restores_margin_hp_and_counts_the_attempt(self, session):
        project = await _repair(session, current_hp=5)  # target 13
        target = repair_service.roll_target(project)
        outcome, restored = await repair_service.resolve_attempt(
            session, project, rolled=target - 3
        )
        assert outcome is Outcome.SUCCESS
        assert restored == crafting_repair.hp_restored(3)
        assert repair_service.current_hp(project) == 8
        assert project.attempts == 1
        assert project.stage == "repairing"
        (attempt,) = await _history(session, project.id)
        assert attempt.kind == "attempt" and attempt.outcome == "success"

    async def test_restoration_is_capped_at_the_missing_hp(self, session):
        project = await _repair(session, current_hp=9)
        target = repair_service.roll_target(project)
        _, restored = await repair_service.resolve_attempt(session, project, rolled=target - 6)
        assert restored == 1
        assert repair_service.current_hp(project) == 10
        assert project.stage == "complete"

    async def test_a_failure_costs_the_half_hour_and_nothing_else(self, session):
        project = await _repair(session)
        target = repair_service.roll_target(project)
        outcome, restored = await repair_service.resolve_attempt(session, project, rolled=target + 2)
        assert outcome is Outcome.FAILURE and restored == 0
        assert repair_service.current_hp(project) == 5
        assert project.attempts == 1
        assert repair_service.minutes_spent(project) == crafting_repair.MINOR_REPAIR_MINUTES

    async def test_the_loop_survives_a_fresh_session(self, session_factory):
        async with session_factory() as s:
            project = await _repair(s)
            target = repair_service.roll_target(project)
            await repair_service.resolve_attempt(s, project, rolled=target)
            await s.commit()
            project_id = project.id

        async with session_factory() as s:
            found = await service.get_project(s, project_id, USER)
            assert repair_service.current_hp(found) == 6
            assert found.attempts == 1


class TestTheSpendAndItsOutcomeAreOneRow:
    """SPEC a-failed-attempt-never-charges-without-recording-why, across domains."""

    async def test_a_reply_failing_after_the_commit_leaves_true_state(self, session_factory):
        class ReplyFailed(RuntimeError):
            pass

        async with session_factory() as s:
            project = await _repair(s)
            project_id = project.id

        with pytest.raises(ReplyFailed):
            async with session_factory() as s:
                project = await service.get_project(s, project_id, USER)
                target = repair_service.roll_target(project)
                await repair_service.resolve_attempt(s, project, rolled=target)
                await s.commit()
                raise ReplyFailed("interaction token expired")

        async with session_factory() as s:
            found = await service.get_project(s, project_id, USER)
            assert found.attempts == 1
            (attempt,) = await _history(s, project_id)
            assert attempt.outcome == "success"

    async def test_a_rolled_back_roll_leaves_nothing(self, session_factory):
        async with session_factory() as s:
            project = await _mundane(s)
            await mundane_service.log_hours(s, project, mundane_service.required_hours(project))
            await s.commit()
            project_id = project.id

        async with session_factory() as s:
            project = await service.get_project(s, project_id, USER)
            await mundane_service.resolve_roll(s, project, rolled=10)
            await s.rollback()

        async with session_factory() as s:
            found = await service.get_project(s, project_id, USER)
            assert found.stage == "working"
            assert found.attempts == 0
            assert [c.kind for c in await _history(s, project_id)] == ["materials"]


class TestOwnershipAndListingStillHold:
    async def test_another_user_cannot_read_a_domain_project(self, session):
        project = await _alchemy(session)
        assert await service.get_project(session, project.id, OTHER_USER) is None

    async def test_mixed_domains_list_together(self, session):
        await _mundane(session)
        await _repair(session)
        found = await service.list_projects(session, USER, GUILD)
        assert sorted(p.domain for p in found) == ["crafting", "repair"]

    async def test_abandoning_a_domain_project_keeps_its_history(self, session_factory):
        async with session_factory() as s:
            project = await _alchemy(s)
            await service.finish_project(s, project, "abandoned")
            await s.commit()
            project_id = project.id
        async with session_factory() as s:
            found = await service.get_project(s, project_id, USER)
            assert found.stage == "abandoned"
            assert len(await _history(s, project_id)) == 1
