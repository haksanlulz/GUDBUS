"""Crafting projects across sessions — the two persistence specs.

* SPEC a-crafting-project-survives-the-session
* SPEC a-failed-attempt-never-charges-without-recording-why

The second is the one with a scar behind it. On 2026-07-29 `hp_cmd` committed
an HP change and then failed on the reply, so the damage had landed while the
user was told the command failed — an invitation to apply it twice. B474 prices
a prototype attempt at the item's full retail, and facilities at up to $500,000,
so the crafting version of that bug is the same shape with a worse blast radius.
The defence is structural rather than careful: the spend and the outcome it
bought are one row, written in one transaction, and the reply happens after.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.crafting import CraftingCharge, CraftingProject
from gurps_bot.db.models import Base
from gurps_bot.services import crafting as service
from gurps_bot.services.limits import StorageLimitExceeded

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


async def _start(session, **kwargs) -> CraftingProject:
    project = await service.start_project(
        session,
        discord_user_id=kwargs.pop("discord_user_id", USER),
        guild_id=kwargs.pop("guild_id", GUILD),
        name=kwargs.pop("name", "portable mansion"),
        complexity=kwargs.pop("complexity", "amazing"),
        skill=kwargs.pop("skill", 18),
        retail_price=kwargs.pop("retail_price", 250_000),
        **kwargs,
    )
    await session.commit()
    return project


class TestAProjectSurvivesTheSession:
    """SPEC a-crafting-project-survives-the-session."""

    async def test_it_round_trips_through_a_fresh_session(self, session_factory):
        async with session_factory() as s:
            project = await _start(s)
            project_id = project.id

        async with session_factory() as s:
            found = await service.get_project(s, project_id, USER)
            assert found is not None
            assert found.name == "portable mansion"
            assert found.complexity == "amazing"
            assert found.stage == "concept"

    async def test_stage_time_and_cost_history_all_survive(self, session_factory):
        async with session_factory() as s:
            project = await _start(s)
            await service.record_charge(s, project, kind="facilities", amount=500_000)
            await service.record_attempt(
                s, project, amount=250_000, outcome="failure", elapsed_days=9
            )
            await service.advance_stage(s, project, "prototype")
            await s.commit()
            project_id = project.id

        async with session_factory() as s:
            found = await service.get_project(s, project_id, USER)
            assert found.stage == "prototype"
            assert found.elapsed_days == 9
            assert found.attempts == 1
            history = await service.charge_history(s, found.id)
            assert [c.kind for c in history] == ["facilities", "attempt"]
            assert [c.amount for c in history] == [500_000, 250_000]

    async def test_the_history_says_what_each_spend_bought(self, session_factory):
        async with session_factory() as s:
            project = await _start(s)
            await service.record_attempt(s, project, amount=100, outcome="critical_failure")
            await s.commit()
            history = await service.charge_history(s, project.id)

        assert history[0].outcome == "critical_failure"

    async def test_facilities_buy_the_right_to_roll_not_a_roll(self, session_factory):
        """A facilities charge has no outcome, and that is not missing data."""
        async with session_factory() as s:
            project = await _start(s)
            await service.record_charge(s, project, kind="facilities", amount=50_000)
            await s.commit()
            history = await service.charge_history(s, project.id)

        assert history[0].outcome is None

    async def test_a_project_can_be_abandoned(self, session_factory):
        async with session_factory() as s:
            project = await _start(s)
            await service.finish_project(s, project, "abandoned")
            await s.commit()
            project_id = project.id

        async with session_factory() as s:
            found = await service.get_project(s, project_id, USER)
            assert found.stage == "abandoned"
            assert found.is_finished

    async def test_a_project_can_be_completed(self, session_factory):
        async with session_factory() as s:
            project = await _start(s)
            await service.finish_project(s, project, "complete")
            await s.commit()
            assert project.is_finished

    async def test_abandoning_keeps_the_history(self, session_factory):
        """Abandoned is a status, not a delete — the money was still spent."""
        async with session_factory() as s:
            project = await _start(s)
            await service.record_attempt(s, project, amount=7_500_000, outcome="failure")
            await service.finish_project(s, project, "abandoned")
            await s.commit()
            project_id = project.id

        async with session_factory() as s:
            assert len(await service.charge_history(s, project_id)) == 1

    async def test_a_finished_project_refuses_further_attempts(self, session):
        project = await _start(session)
        await service.finish_project(session, project, "abandoned")
        with pytest.raises(ValueError):
            await service.record_attempt(session, project, amount=1, outcome="success")

    async def test_deleting_a_project_takes_its_charges(self, session_factory):
        async with session_factory() as s:
            project = await _start(s)
            await service.record_attempt(s, project, amount=1, outcome="success")
            await s.commit()
            await service.delete_project(s, project)
            await s.commit()

        async with session_factory() as s:
            assert (await s.scalars(select(CraftingCharge))).all() == []


class TestAFailedAttemptNeverChargesWithoutRecordingWhy:
    """SPEC a-failed-attempt-never-charges-without-recording-why."""

    async def test_the_spend_and_its_outcome_are_one_row(self, session):
        project = await _start(session)
        await service.record_attempt(session, project, amount=250_000, outcome="failure")
        await session.commit()

        charge = (await session.scalars(select(CraftingCharge))).one()
        assert charge.amount == 250_000
        assert charge.outcome == "failure"

    async def test_a_charge_cannot_be_recorded_without_an_outcome(self, session):
        """An attempt with no outcome is exactly the state the spec forbids:
        money gone, no record of what it bought."""
        project = await _start(session)
        with pytest.raises(ValueError):
            await service.record_attempt(session, project, amount=250_000, outcome=None)

    async def test_a_reply_failing_after_the_commit_leaves_true_state(
        self, session_factory
    ):
        """The 2026-07-29 shape, reproduced deliberately.

        The service commits the spend and its outcome together; the caller then
        blows up where the reply would be. The next read must show the charge
        AND its outcome — never the charge alone.
        """
        class ReplyFailed(RuntimeError):
            """Stands in for the discord.py error that broke `hp_cmd`."""

        async with session_factory() as s:
            project = await _start(s)
            project_id = project.id

        with pytest.raises(ReplyFailed):
            async with session_factory() as s:
                project = await service.get_project(s, project_id, USER)
                await service.record_attempt(
                    s, project, amount=250_000, outcome="failure"
                )
                await s.commit()
                # Exactly where the cog would call respond(). The commit above
                # has landed; this must not be able to un-land half of it.
                raise ReplyFailed("interaction token expired")

        async with session_factory() as s:
            found = await service.get_project(s, project_id, USER)
            history = await service.charge_history(s, project_id)
            assert found.attempts == 1
            assert len(history) == 1
            assert history[0].outcome == "failure"

    async def test_a_rolled_back_attempt_leaves_nothing_at_all(self, session_factory):
        """The other direction, and the reason the pair is one transaction: if
        the write does not land, the attempt count must not either."""
        async with session_factory() as s:
            project = await _start(s)
            project_id = project.id

        async with session_factory() as s:
            project = await service.get_project(s, project_id, USER)
            await service.record_attempt(s, project, amount=250_000, outcome="failure")
            await s.rollback()

        async with session_factory() as s:
            found = await service.get_project(s, project_id, USER)
            assert found.attempts == 0
            assert await service.charge_history(s, project_id) == []

    async def test_the_attempt_counter_and_the_ledger_cannot_disagree(self, session):
        project = await _start(session)
        for _ in range(3):
            await service.record_attempt(session, project, amount=10, outcome="failure")
        await session.commit()

        history = await service.charge_history(session, project.id)
        attempts = [c for c in history if c.kind == "attempt"]
        assert project.attempts == len(attempts) == 3


class TestMoneyStaysThreeFiguresInStorageToo:
    """The engine refuses to sum; so does the ledger's read model."""

    async def test_spend_is_reported_by_kind(self, session):
        project = await _start(session)
        await service.record_charge(session, project, kind="facilities", amount=500_000)
        await service.record_attempt(session, project, amount=250_000, outcome="failure")
        await service.record_attempt(session, project, amount=250_000, outcome="success")
        await service.record_charge(session, project, kind="copy", amount=50_000)
        await session.commit()

        spent = await service.spent_by_kind(session, project.id)
        assert spent == {"facilities": 500_000, "attempt": 500_000, "copy": 50_000}

    async def test_there_is_no_grand_total_helper(self):
        for banned in ("total_spent", "grand_total", "sum_charges"):
            assert not hasattr(service, banned), (
                f"services.crafting grew {banned!r} — B474's figures have "
                f"different payers and triggers, and one number is wrong for all"
            )

    async def test_an_unknown_charge_kind_is_refused(self, session):
        project = await _start(session)
        with pytest.raises(ValueError):
            await service.record_charge(session, project, kind="vibes", amount=1)


class TestOwnershipAndScope:
    async def test_another_user_cannot_read_your_project(self, session):
        project = await _start(session)
        assert await service.get_project(session, project.id, OTHER_USER) is None

    async def test_listing_is_per_user(self, session):
        await _start(session)
        await _start(session, discord_user_id=OTHER_USER, name="theirs")

        mine = await service.list_projects(session, USER, GUILD)
        assert [p.name for p in mine] == ["portable mansion"]

    async def test_listing_hides_finished_projects_by_default(self, session):
        live = await _start(session, name="live one")
        done = await _start(session, name="old one")
        await service.finish_project(session, done, "complete")
        await session.commit()

        assert [p.name for p in await service.list_projects(session, USER, GUILD)] == [
            "live one"
        ]
        everything = await service.list_projects(
            session, USER, GUILD, include_finished=True
        )
        assert len(everything) == 2
        assert live in everything

    async def test_a_project_is_scoped_to_the_guild_it_started_in(self, session):
        await _start(session)
        assert await service.list_projects(session, USER, GUILD + 1) == []


class TestTheFlawedTheoryStaysStored(object):
    """B473's trap has to survive a restart or the secrecy is theatre."""

    async def test_it_persists(self, session_factory):
        async with session_factory() as s:
            project = await _start(s)
            await service.mark_flawed_theory(s, project)
            await s.commit()
            project_id = project.id

        async with session_factory() as s:
            found = await service.get_project(s, project_id, USER)
            assert found.flawed_theory is True

    async def test_it_is_off_by_default(self, session):
        project = await _start(session)
        assert project.flawed_theory is False


class TestStorageCap:
    async def test_projects_are_capped_per_user(self, session, monkeypatch):
        monkeypatch.setattr(service, "MAX_CRAFTING_PROJECTS_PER_USER", 2)
        await _start(session, name="a")
        await _start(session, name="b")
        with pytest.raises(StorageLimitExceeded):
            await _start(session, name="c")

    async def test_a_finished_project_still_counts_until_deleted(
        self, session, monkeypatch
    ):
        """Otherwise the cap is trivially defeated by abandoning everything."""
        monkeypatch.setattr(service, "MAX_CRAFTING_PROJECTS_PER_USER", 1)
        project = await _start(session, name="a")
        await service.finish_project(session, project, "abandoned")
        await session.commit()
        with pytest.raises(StorageLimitExceeded):
            await _start(session, name="b")


class TestGuildTeardown:
    async def test_leaving_a_guild_takes_the_projects(self, session):
        await _start(session)
        await _start(session, guild_id=GUILD + 1, name="elsewhere")
        await service.purge_guild_crafting_projects(session, GUILD)
        await session.commit()

        remaining = (await session.scalars(select(CraftingProject))).all()
        assert [p.name for p in remaining] == ["elsewhere"]

    async def test_it_takes_the_charges_with_them(self, session):
        project = await _start(session)
        await service.record_attempt(session, project, amount=1, outcome="failure")
        await session.commit()

        await service.purge_guild_crafting_projects(session, GUILD)
        await session.commit()

        assert (await session.scalars(select(CraftingCharge))).all() == []
