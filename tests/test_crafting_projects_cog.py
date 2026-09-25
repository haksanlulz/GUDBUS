"""The four calculators' **Save as project** buttons, `/craft work`, `/craft roll`
and the per-domain project views — the surface half of persistent projects.

Mock-interaction tests for the wiring; whether the flows are usable is a
manual check the operator closes on the hosted bot. What IS
testable is here: each button opens the right modal and the modal saves the
calculator's own figures, `/craft work` counts the domain's unit, `/craft roll`
rolls the domain's dice (patched here), and the enchanting roll never reaches
the channel.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.cogs.crafting import (
    CraftingCog,
    MakeFlowView,
    MakeNumbers,
    SaveAlchemyModal,
    SaveCraftingModal,
    SaveEnchantmentModal,
    SaveProjectView,
    SaveRepairModal,
)
from gurps_bot.db.models import Base
from gurps_bot.mechanics import crafting_enchantment, crafting_mundane
from gurps_bot.mechanics.dice import DiceSpec, RollResult
from gurps_bot.services import crafting as service
from gurps_bot.services import crafting_alchemy as alchemy_projects
from gurps_bot.services import crafting_enchantment as enchantment_projects
from gurps_bot.services import crafting_mundane as mundane_projects
from gurps_bot.services import crafting_repair as repair_projects
from tests.test_crafting_cog import _interaction, _interaction_with_db, _result

USER, GUILD = 1, 99


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


def _roll_result(total: int, count: int = 3) -> RollResult:
    dice = tuple([total // count] * (count - 1) + [total - (total // count) * (count - 1)])
    return RollResult(spec=DiceSpec(count, 6, 0), dice=dice, total=total)


def _check_returning(rolled: int):
    """A `check` that rolls ``rolled`` against whatever target it is handed."""
    return lambda target, modifier=0: _result(rolled, target + modifier)


def _sent(interaction: MagicMock) -> dict:
    return interaction.response.send_message.await_args.kwargs


async def _seed(db, starter, **kwargs) -> int:
    async with db() as s:
        project = await starter(s, discord_user_id=USER, guild_id=GUILD, **kwargs)
        await s.commit()
        return project.id


async def _fetch(db, project_id: int):
    async with db() as s:
        return await service.get_project(s, project_id, USER)


LADDER = dict(list_price=90.0, weight=22.5, cost_per_lb=2.70, monthly_pay=790.0)


# --- the buttons ------------------------------------------------------------


class TestEveryCalculatorOffersToSave:
    async def _run(self, name: str, **kwargs) -> tuple[MagicMock, SaveProjectView]:
        interaction = _interaction()
        cog = CraftingCog(MagicMock())
        await getattr(cog, name).callback(cog, interaction, **kwargs)
        view = _sent(interaction).get("view")
        assert isinstance(view, SaveProjectView), _sent(interaction)
        return interaction, view

    async def test_make_typed_offers_the_commission_modal(self):
        _, view = await self._run("make", **LADDER)
        assert isinstance(view._modal(), SaveCraftingModal)

    async def test_brew_offers_the_batch_modal(self):
        _, view = await self._run("brew", alchemy_skill=14, cost_per_dose=50, doses=4)
        assert isinstance(view._modal(), SaveAlchemyModal)

    async def test_enchant_offers_the_enchantment_modal(self):
        _, view = await self._run("enchant", enchant_skill=18, spell_skill=16, energy=100)
        assert isinstance(view._modal(), SaveEnchantmentModal)

    async def test_repair_offers_the_repair_modal(self):
        _, view = await self._run("repair", price=500, current_hp=5, max_hp=10)
        assert isinstance(view._modal(), SaveRepairModal)

    async def test_beyond_repair_offers_nothing_to_keep(self):
        interaction = _interaction()
        cog = CraftingCog(MagicMock())
        await cog.repair.callback(cog, interaction, price=500, current_hp=-60, max_hp=10)
        assert _sent(interaction).get("view") is None

    async def test_the_button_belongs_to_whoever_ran_the_command(self):
        _, view = await self._run("repair", price=500, current_hp=5, max_hp=10)
        stranger = _interaction(user_id=2)
        assert await view.interaction_check(stranger) is False
        assert _sent(stranger)["ephemeral"] is True
        assert await view.interaction_check(_interaction(user_id=1)) is True

    async def test_the_command_remembers_its_message_for_the_timeout(self):
        interaction, view = await self._run("brew", alchemy_skill=14, cost_per_dose=50)
        assert view.message is interaction.original_response.return_value

    async def test_a_timed_out_button_disables_itself(self):
        _, view = await self._run("brew", alchemy_skill=14, cost_per_dose=50)
        view.message = MagicMock()
        view.message.edit = MagicMock(side_effect=lambda **k: _done())
        await view.on_timeout()
        assert all(item.disabled for item in view.children)

    async def test_the_guided_flow_saves_only_once_the_numbers_are_in(self):
        view = MakeFlowView(invoker_id=1, numbers=MakeNumbers())
        interaction = _interaction()
        await view.save_btn.callback(interaction)
        refusal = interaction.response.send_message.await_args
        assert "Numbers" in refusal.args[0]
        assert refusal.kwargs["ephemeral"] is True

        view = MakeFlowView(invoker_id=1, numbers=MakeNumbers(**LADDER))
        interaction = _interaction()
        interaction.response.send_modal = MagicMock(side_effect=lambda m: _done())
        await view.save_btn.callback(interaction)
        modal = interaction.response.send_modal.call_args.args[0]
        assert isinstance(modal, SaveCraftingModal)
        assert modal.figures["list_price"] == 90.0


async def _done():
    return None


class TestTheModalsSaveTheCalculatorsOwnFigures:
    async def _submit(self, db, modal, **fields) -> MagicMock:
        modal.project_name._value = fields.pop("name", "the thing")
        for field, value in fields.items():
            getattr(modal, field)._value = value
        interaction = _interaction_with_db(db)
        await modal.on_submit(interaction)
        return interaction

    async def test_the_commission_keeps_the_ladder_and_takes_the_skill(self, db):
        figures = dict(
            **LADDER, workers=2, item_class="TOOL", labor="ARTISTIC", materials="NONE"
        )
        interaction = await self._submit(
            db, SaveCraftingModal(figures), skill="13", fine_materials="2", crucible_steel="yes"
        )
        assert "Started" in _sent(interaction)["content"]
        async with db() as s:
            (project,) = await service.list_projects(s, USER, GUILD)
        assert project.domain == "crafting" and project.skill == 13
        inputs = project.state_json["inputs"]
        assert inputs["workers"] == 2 and inputs["item_class"] == "TOOL"
        assert inputs["fine_materials"] == 2 and inputs["crucible_steel"] is True

    async def test_words_where_a_skill_belongs_are_refused(self, db):
        interaction = await self._submit(
            db, SaveCraftingModal(dict(**LADDER, workers=1, item_class="GENERAL",
                                       labor="ROUTINE", materials="NONE")),
            skill="high",
        )
        assert "whole number" in _sent(interaction)["content"]
        async with db() as s:
            assert await service.list_projects(s, USER, GUILD) == []

    async def test_an_engine_refusal_reaches_the_player(self, db):
        """A ×2 material on a $90 item: the materials cost more than the piece."""
        figures = dict(**LADDER, workers=1, item_class="GENERAL", labor="ROUTINE",
                       materials="SWORD_OR_PLATE")
        interaction = await self._submit(db, SaveCraftingModal(figures), skill="14")
        assert "cost more than the item" in _sent(interaction)["content"]

    async def test_the_batch_saves_as_brewed(self, db):
        figures = dict(alchemy_skill=14, cost_per_dose=50, doses=4, technique=None,
                       lab="BASIC", mana="NORMAL", weeks=2.0, formulary=True,
                       teacher=False, helper_skill=10, tech_level=None)
        await self._submit(db, SaveAlchemyModal(figures))
        async with db() as s:
            (project,) = await service.list_projects(s, USER, GUILD)
        assert project.domain == "alchemy" and project.skill == 10
        assert project.state_json["inputs"]["doses"] == 4

    async def test_the_enchantment_takes_an_optional_materials_value(self, db):
        figures = dict(enchant_skill=18, spell_skill=16, energy=100, method="SLOW_AND_SURE",
                       assistants=1, hp_spent=0, bystanders=False, mana="NORMAL")
        await self._submit(db, SaveEnchantmentModal(figures), materials_value="1200")
        async with db() as s:
            (project,) = await service.list_projects(s, USER, GUILD)
            history = await service.charge_history(s, project.id)
        assert project.domain == "enchantment"
        assert [(c.kind, c.amount) for c in history] == [("materials", 1200)]

    async def test_the_repair_takes_the_skill(self, db):
        figures = dict(price=500, current_hp=0, max_hp=10, workspace="BASIC", time_spent=0,
                       tech_level=None, item_tech_level=None, unfamiliar=False, emp="NONE")
        await self._submit(db, SaveRepairModal(figures), skill="12")
        async with db() as s:
            (project,) = await service.list_projects(s, USER, GUILD)
        assert project.domain == "repair" and project.stage == "parts"

    async def test_an_empty_name_is_refused(self, db):
        figures = dict(price=500, current_hp=5, max_hp=10, workspace="BASIC", time_spent=0,
                       tech_level=None, item_tech_level=None, unfamiliar=False, emp="NONE")
        interaction = await self._submit(db, SaveRepairModal(figures), name="@@@", skill="12")
        assert "empty" in _sent(interaction)["content"]


# --- /craft work ------------------------------------------------------------


class TestWork:
    async def _work(self, db, project_id: int, **kwargs) -> MagicMock:
        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db)
        await cog.work.callback(cog, interaction, project_id, **kwargs)
        return interaction

    async def test_a_smith_logs_hours(self, db):
        project_id = await _seed(db, mundane_projects.start, name="a ladder", skill=14, **LADDER)
        interaction = await self._work(db, project_id, amount=5.0)
        assert _sent(interaction)["ephemeral"] is True
        assert "5/" in _sent(interaction)["content"]
        assert mundane_projects.hours_worked(await _fetch(db, project_id)) == 5.0

    async def test_an_alchemist_logs_weeks(self, db):
        project_id = await _seed(
            db, alchemy_projects.start, name="draughts", alchemy_skill=14, cost_per_dose=50
        )
        await self._work(db, project_id, amount=1.0)
        assert alchemy_projects.weeks_elapsed(await _fetch(db, project_id)) == 1.0

    async def test_an_enchanter_logs_days_and_missed_days(self, db):
        project_id = await _seed(
            db, enchantment_projects.start, name="ring", enchant_skill=18, spell_skill=16,
            energy=100,
        )
        await self._work(db, project_id, amount=10.0, missed=1)
        found = await _fetch(db, project_id)
        assert enchantment_projects.days_worked(found) == 10.0
        assert enchantment_projects.days_missed(found) == 1

    async def test_missed_days_mean_nothing_to_a_smith(self, db):
        project_id = await _seed(db, mundane_projects.start, name="a ladder", skill=14, **LADDER)
        interaction = await self._work(db, project_id, amount=1.0, missed=1)
        assert "enchanting" in _sent(interaction)["content"]
        assert mundane_projects.hours_worked(await _fetch(db, project_id)) == 0.0

    async def test_a_repair_has_no_calendar(self, db):
        project_id = await _seed(
            db, repair_projects.start, name="truck", skill=12, price=500, current_hp=5, max_hp=10
        )
        interaction = await self._work(db, project_id, amount=1.0)
        assert "no calendar" in _sent(interaction)["content"]

    async def test_an_invention_is_refused_by_name(self, db):
        async with db() as s:
            project = await service.start_project(
                s, discord_user_id=USER, guild_id=GUILD, name="mansion",
                complexity="amazing", skill=18,
            )
            await s.commit()
            project_id = project.id
        interaction = await self._work(db, project_id, amount=1.0)
        assert "invention" in _sent(interaction)["content"].lower()

    async def test_someone_elses_project_is_not_yours_to_work(self, db):
        project_id = await _seed(db, mundane_projects.start, name="a ladder", skill=14, **LADDER)
        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db, user_id=2)
        await cog.work.callback(cog, interaction, project_id, amount=5.0)
        assert "No project" in _sent(interaction)["content"]


# --- /craft roll ------------------------------------------------------------


class TestRoll:
    async def _roll(self, db, project_id: int) -> MagicMock:
        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db)
        await cog.roll_cmd.callback(cog, interaction, project_id)
        return interaction

    async def test_the_smith_rolls_for_quality_in_public(self, db):
        project_id = await _seed(db, mundane_projects.start, name="a ladder", skill=14, **LADDER)
        async with db() as s:
            project = await service.get_project(s, project_id, USER)
            await mundane_projects.log_hours(s, project, mundane_projects.required_hours(project))
            await s.commit()
        with patch("gurps_bot.cogs.crafting.check", side_effect=_check_returning(10)):
            interaction = await self._roll(db, project_id)
        sent = _sent(interaction)
        assert sent["ephemeral"] is False
        quality = crafting_mundane.craft_quality(4).quality.value
        assert quality in sent["content"]
        found = await _fetch(db, project_id)
        assert found.stage == "complete"
        assert found.state_json["result"]["quality"] == crafting_mundane.craft_quality(4).quality.name
        assert sent["embed"].footer.text == "Low-Tech Companion 3 ch. 5"

    async def test_the_roll_waits_for_the_work(self, db):
        project_id = await _seed(db, mundane_projects.start, name="a ladder", skill=14, **LADDER)
        with patch("gurps_bot.cogs.crafting.check", side_effect=_check_returning(10)):
            interaction = await self._roll(db, project_id)
        assert "not done" in _sent(interaction)["content"]
        assert (await _fetch(db, project_id)).stage == "working"

    async def test_the_enchanting_roll_stays_with_the_roller(self, db):
        """SPEC gm-rolls-stay-with-the-gm, for the domain whose book says the
        GM rolls: ephemeral, never the channel."""
        project_id = await _seed(
            db, enchantment_projects.start, name="ring", enchant_skill=18, spell_skill=16,
            energy=100, method="QUICK_AND_DIRTY",
        )
        with patch("gurps_bot.cogs.crafting.roll_3d6", return_value=_roll_result(10)):
            interaction = await self._roll(db, project_id)
        sent = _sent(interaction)
        assert sent["ephemeral"] is True
        found = await _fetch(db, project_id)
        assert found.stage == "complete"
        assert found.state_json["result"]["power"] == 16

    async def test_a_critical_enchanting_success_rolls_the_power_bonus(self, db):
        project_id = await _seed(
            db, enchantment_projects.start, name="ring", enchant_skill=18, spell_skill=16,
            energy=100, method="QUICK_AND_DIRTY",
        )
        with patch("gurps_bot.cogs.crafting.roll_3d6", return_value=_roll_result(3)), patch(
            "gurps_bot.cogs.crafting.roll", return_value=_roll_result(7, count=2)
        ):
            await self._roll(db, project_id)
        found = await _fetch(db, project_id)
        assert found.state_json["result"]["power"] == 16 + 7
        assert found.state_json["result"]["may_have_further_enhancement"] is True

    async def test_the_batch_goes_through_a_disaster_in_two_rolls(self, db):
        project_id = await _seed(
            db, alchemy_projects.start, name="draughts", alchemy_skill=14, cost_per_dose=50,
            doses=4, formulary=True,
        )
        async with db() as s:
            project = await service.get_project(s, project_id, USER)
            await alchemy_projects.log_weeks(s, project, alchemy_projects.required_weeks(project))
            await s.commit()
        with patch("gurps_bot.cogs.crafting.check", side_effect=_check_returning(18)):
            interaction = await self._roll(db, project_id)
        assert "disaster roll" in _sent(interaction)["content"]
        assert (await _fetch(db, project_id)).stage == "disaster"

        with patch("gurps_bot.cogs.crafting.check", side_effect=_check_returning(17)), patch(
            "gurps_bot.cogs.crafting.roll_3d6", return_value=_roll_result(11)
        ):
            interaction = await self._roll(db, project_id)
        assert "disaster" in _sent(interaction)["content"]
        found = await _fetch(db, project_id)
        assert found.stage == "complete"
        assert found.state_json["result"]["disaster"]["lab_destroyed"] is True

    async def test_a_major_repair_buys_parts_then_rolls_attempts(self, db):
        project_id = await _seed(
            db, repair_projects.start, name="truck", skill=12, price=500, current_hp=0, max_hp=10
        )
        with patch("gurps_bot.cogs.crafting.roll", return_value=_roll_result(3, count=1)):
            interaction = await self._roll(db, project_id)
        assert "$150" in _sent(interaction)["content"]
        found = await _fetch(db, project_id)
        assert found.stage == "repairing"

        target = repair_projects.roll_target(found)
        with patch("gurps_bot.cogs.crafting.check", side_effect=_check_returning(target - 4)):
            interaction = await self._roll(db, project_id)
        assert "+4 HP" in _sent(interaction)["content"]
        assert _sent(interaction)["ephemeral"] is False
        assert repair_projects.current_hp(await _fetch(db, project_id)) == 4

    async def test_an_invention_is_refused_by_name(self, db):
        async with db() as s:
            project = await service.start_project(
                s, discord_user_id=USER, guild_id=GUILD, name="mansion",
                complexity="amazing", skill=18,
            )
            await s.commit()
            project_id = project.id
        interaction = await self._roll(db, project_id)
        assert "invention" in _sent(interaction)["content"].lower()


# --- the views --------------------------------------------------------------


class TestProjectViews:
    async def _view(self, db, project_id: int):
        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db)
        await cog.project.callback(cog, interaction, project_id)
        return _sent(interaction)["embed"]

    async def _list(self, db) -> str:
        cog = CraftingCog(MagicMock())
        interaction = _interaction_with_db(db)
        await cog.projects.callback(cog, interaction)
        embed = _sent(interaction)["embed"]
        return "\n".join(f"{f.name}: {f.value}" for f in embed.fields)

    async def test_each_domain_renders_under_its_own_book(self, db):
        ids = {
            "crafting": await _seed(db, mundane_projects.start, name="ladder", skill=14, **LADDER),
            "alchemy": await _seed(db, alchemy_projects.start, name="draughts", alchemy_skill=14, cost_per_dose=50),
            "enchantment": await _seed(db, enchantment_projects.start, name="ring", enchant_skill=18, spell_skill=16, energy=100),
            "repair": await _seed(db, repair_projects.start, name="truck", skill=12, price=500, current_hp=5, max_hp=10),
        }
        footers = {domain: (await self._view(db, pid)).footer.text for domain, pid in ids.items()}
        assert footers == {
            "crafting": "Low-Tech Companion 3 ch. 5",
            "alchemy": "GURPS Magic ch. 28",
            "enchantment": "GURPS Magic pp. 16-18",
            "repair": "B484",
        }

    async def test_the_list_says_what_each_project_is(self, db):
        await _seed(db, mundane_projects.start, name="ladder", skill=14, **LADDER)
        await _seed(db, repair_projects.start, name="truck", skill=12, price=500, current_hp=5, max_hp=10)
        async with db() as s:
            await service.start_project(
                s, discord_user_id=USER, guild_id=GUILD, name="mansion", complexity="amazing", skill=18
            )
            await s.commit()
        listing = await self._list(db)
        assert "Making · **working**" in listing
        assert "Repairing · **repairing** · 5/10 HP" in listing
        assert "Amazing · **concept**" in listing

    async def test_the_repair_view_shows_the_modifiers_and_the_target(self, db):
        project_id = await _seed(
            db, repair_projects.start, name="truck", skill=12, price=500, current_hp=5, max_hp=10
        )
        embed = await self._view(db, project_id)
        names = [f.name for f in embed.fields]
        assert "Modifiers" in names and "Each attempt" in names
        target = repair_projects.roll_target(await _fetch(db, project_id))
        assert f"**{target}**" in next(f.value for f in embed.fields if f.name == "Each attempt")

    async def test_the_enchantment_view_never_shows_the_flawed_theory_column(self, db):
        """Belt and braces: the domain has no such thing, and the frame must not
        grow one."""
        project_id = await _seed(
            db, enchantment_projects.start, name="ring", enchant_skill=18, spell_skill=16,
            energy=100,
        )
        embed = await self._view(db, project_id)
        text = (embed.description or "") + "".join(f.name + f.value for f in embed.fields)
        assert "flawed" not in text.lower()
        assert crafting_enchantment.Method.SLOW_AND_SURE.value in (embed.description or "")
