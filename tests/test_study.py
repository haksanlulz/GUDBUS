"""study tracker (B292-294); importing the service registers StudyLog on Base for create_all"""

from __future__ import annotations

import math

import pytest

from gurps_bot.mechanics.study import (
    METHOD_MULTIPLIERS,
    ON_THE_JOB_DAILY_CAP_HOURS,
    POINT_HOURS,
    StudyProgress,
    learning_hours_for,
    study_multiplier,
    study_progress,
)
from gurps_bot.services.characters import import_character
from gurps_bot.services.study import (
    get_skill_progress,
    list_study,
    log_study,
    reset_skill,
)

USER_ID = 111
OTHER_USER = 222


class TestStudyMultiplier:
    def test_self_teaching(self):
        assert study_multiplier("self_teaching") == 0.5

    def test_on_the_job(self):
        assert study_multiplier("on_the_job") == 0.25

    def test_education(self):
        assert study_multiplier("education") == 1.0

    def test_intensive(self):
        assert study_multiplier("intensive") == 2.0

    def test_constants_map_matches(self):
        assert METHOD_MULTIPLIERS == {
            "self_teaching": 0.5,
            "on_the_job": 0.25,
            "education": 1.0,
            "intensive": 2.0,
        }
        assert POINT_HOURS == 200.0
        assert ON_THE_JOB_DAILY_CAP_HOURS == 8.0

    def test_case_insensitive_normalization(self):
        assert study_multiplier("Self_Teaching") == 0.5
        assert study_multiplier("SELF_TEACHING") == 0.5
        assert study_multiplier("  Education  ") == 1.0

    def test_adventuring_uses_gm_multiplier(self):
        assert study_multiplier("adventuring", gm_multiplier=1.5) == 1.5
        assert study_multiplier("adventuring", gm_multiplier=0.0) == 0.0

    def test_adventuring_without_gm_raises(self):
        with pytest.raises(ValueError):
            study_multiplier("adventuring")

    def test_adventuring_negative_gm_raises(self):
        with pytest.raises(ValueError):
            study_multiplier("adventuring", gm_multiplier=-1.0)

    def test_adventuring_nan_gm_raises(self):
        with pytest.raises(ValueError):
            study_multiplier("adventuring", gm_multiplier=float("nan"))

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError, match="unknown study method"):
            study_multiplier("telepathy")


class TestLearningHoursFor:
    def test_education_one_to_one(self):
        assert learning_hours_for("education", 10.0) == 10.0

    def test_intensive_double(self):
        assert learning_hours_for("intensive", 5.0) == 10.0

    def test_self_teaching_half(self):
        assert learning_hours_for("self_teaching", 20.0) == 10.0

    def test_on_the_job_under_cap(self):
        # 4 work-hrs * 0.25 = 1.0; cap does NOT fire below 8 hrs
        assert learning_hours_for("on_the_job", 4.0) == 1.0

    def test_on_the_job_at_cap(self):
        assert learning_hours_for("on_the_job", 8.0) == 2.0

    def test_on_the_job_over_cap_clamped(self):
        # 12 real hrs capped to 8 BEFORE x0.25 -> 2.0, NOT 3.0
        assert learning_hours_for("on_the_job", 12.0) == 2.0

    def test_adventuring_with_gm(self):
        assert learning_hours_for("adventuring", 6.0, gm_multiplier=1.5) == 9.0

    def test_adventuring_no_cap(self):
        # adventuring is not subject to the on_the_job daily cap
        assert learning_hours_for("adventuring", 100.0, gm_multiplier=1.0) == 100.0

    def test_adventuring_without_gm_raises(self):
        with pytest.raises(ValueError):
            learning_hours_for("adventuring", 6.0)

    def test_adventuring_zero_gm_valid(self):
        assert learning_hours_for("adventuring", 6.0, gm_multiplier=0.0) == 0.0

    def test_zero_real_hours_valid(self):
        assert learning_hours_for("education", 0.0) == 0.0

    def test_negative_real_hours_raises(self):
        with pytest.raises(ValueError):
            learning_hours_for("education", -1.0)

    def test_nan_real_hours_raises(self):
        with pytest.raises(ValueError):
            learning_hours_for("education", float("nan"))

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError, match="unknown study method"):
            learning_hours_for("telepathy", 5.0)


class TestStudyProgress:
    def test_partial(self):
        p = study_progress(450.0)
        assert p == StudyProgress(
            total_learning_hours=450.0,
            points_earned=2,
            remainder=50.0,
            hours_to_next=150.0,
        )

    def test_exact_boundary(self):
        p = study_progress(200.0)
        assert p.points_earned == 1
        assert p.remainder == 0.0
        assert p.hours_to_next == 200.0  # full next point, NOT 0
        assert p.total_learning_hours == 200.0

    def test_zero(self):
        p = study_progress(0.0)
        assert p.points_earned == 0
        assert p.remainder == 0.0
        assert p.hours_to_next == 200.0

    def test_float_drift_just_below(self):
        # 1e-9 boundary clamp prevents off-by-one
        p = study_progress(199.999999999)
        assert p.points_earned == 1
        assert p.remainder == 0.0
        assert p.hours_to_next == 200.0

    def test_float_drift_just_above(self):
        # within the documented 1e-9 clamp band above the boundary
        p = study_progress(200.0000000001)
        assert p.points_earned == 1
        assert p.remainder == 0.0
        assert p.hours_to_next == 200.0

    def test_under_one_point(self):
        p = study_progress(10.0)
        assert p.points_earned == 0
        assert p.remainder == 10.0
        assert p.hours_to_next == 190.0

    def test_negative_total_raises(self):
        with pytest.raises(ValueError):
            study_progress(-1.0)

    def test_remainder_range(self):
        # remainder always in [0, 200)
        p = study_progress(399.0)
        assert p.points_earned == 1
        assert p.remainder == 199.0
        assert p.hours_to_next == 1.0


class TestLogAndProgress:
    async def test_log_returns_flushed_row(self, db_session):
        row = await log_study(db_session, USER_ID, "Broadsword", "self_teaching", 20.0)
        assert row.id is not None
        assert row.discord_user_id == USER_ID
        assert row.skill_name == "Broadsword"
        assert row.method == "self_teaching"
        assert row.real_hours == 20.0
        assert row.learning_hours == 10.0
        assert row.character_id is None
        assert row.logged_at is not None

    async def test_single_session_round_trip(self, db_session):
        await log_study(db_session, USER_ID, "Broadsword", "self_teaching", 20.0)
        p = await get_skill_progress(db_session, USER_ID, "Broadsword")
        assert p == StudyProgress(
            total_learning_hours=10.0,
            points_earned=0,
            remainder=10.0,
            hours_to_next=190.0,
        )

    async def test_empty_bucket_zero(self, db_session):
        p = await get_skill_progress(db_session, USER_ID, "Nonexistent")
        assert p.total_learning_hours == 0.0
        assert p.points_earned == 0
        assert p.remainder == 0.0
        assert p.hours_to_next == 200.0

    async def test_multi_session_accumulation(self, db_session):
        await log_study(db_session, USER_ID, "Stealth", "self_teaching", 200.0)
        await log_study(db_session, USER_ID, "Stealth", "education", 100.0)
        p = await get_skill_progress(db_session, USER_ID, "Stealth")
        assert p.total_learning_hours == 200.0
        assert p.points_earned == 1
        assert p.remainder == 0.0

    async def test_mixed_methods_sum(self, db_session):
        # B292: methods sum fungibly
        await log_study(db_session, USER_ID, "Riding", "self_teaching", 100.0)  # 50
        await log_study(db_session, USER_ID, "Riding", "education", 100.0)  # 100
        await log_study(
            db_session, USER_ID, "Riding", "adventuring", 10.0, gm_multiplier=5.0,
        )  # 50
        p = await get_skill_progress(db_session, USER_ID, "Riding")
        assert p.total_learning_hours == 200.0
        assert p.points_earned == 1

    async def test_on_the_job_cap_stored(self, db_session):
        row = await log_study(db_session, USER_ID, "Smith", "on_the_job", 12.0)
        assert row.real_hours == 12.0
        assert row.learning_hours == 2.0
        p = await get_skill_progress(db_session, USER_ID, "Smith")
        assert p.total_learning_hours == 2.0

    async def test_adventuring_stores_result_not_multiplier(self, db_session):
        row = await log_study(
            db_session, USER_ID, "Survival", "adventuring", 6.0, gm_multiplier=1.5,
        )
        assert row.learning_hours == 9.0
        assert row.real_hours == 6.0

    async def test_bad_method_propagates(self, db_session):
        with pytest.raises(ValueError, match="unknown study method"):
            await log_study(db_session, USER_ID, "Magic", "telepathy", 5.0)

    async def test_negative_hours_propagates(self, db_session):
        with pytest.raises(ValueError):
            await log_study(db_session, USER_ID, "Magic", "education", -5.0)

    async def test_adventuring_missing_gm_propagates(self, db_session):
        with pytest.raises(ValueError):
            await log_study(db_session, USER_ID, "Magic", "adventuring", 5.0)


# bucket isolation hinges on the .is_(None) filter
class TestBucketIsolation:
    async def test_character_bucket_not_in_null_bucket(self, db_session, make_character):
        await make_character(7, USER_ID)
        # a character_id=7 row must NOT appear in the character_id IS NULL query
        await log_study(
            db_session, USER_ID, "Stealth", "education", 100.0, character_id=7,
        )
        p = await get_skill_progress(db_session, USER_ID, "Stealth")  # character_id=None
        assert p.total_learning_hours == 0.0
        assert p.points_earned == 0

    async def test_null_bucket_not_in_character_bucket(self, db_session):
        await log_study(db_session, USER_ID, "Stealth", "education", 100.0)  # char=None
        p = await get_skill_progress(
            db_session, USER_ID, "Stealth", character_id=7,
        )
        assert p.total_learning_hours == 0.0

    async def test_character_bucket_sums_own_rows(self, db_session, make_character):
        await make_character(7, USER_ID)
        await log_study(
            db_session, USER_ID, "Stealth", "education", 100.0, character_id=7,
        )
        p = await get_skill_progress(
            db_session, USER_ID, "Stealth", character_id=7,
        )
        assert p.total_learning_hours == 100.0

    async def test_distinct_characters_separate(self, db_session, make_character):
        await make_character(7, USER_ID)
        await make_character(8, USER_ID)
        await log_study(
            db_session, USER_ID, "Stealth", "education", 50.0, character_id=7,
        )
        await log_study(
            db_session, USER_ID, "Stealth", "education", 30.0, character_id=8,
        )
        p7 = await get_skill_progress(db_session, USER_ID, "Stealth", character_id=7)
        p8 = await get_skill_progress(db_session, USER_ID, "Stealth", character_id=8)
        assert p7.total_learning_hours == 50.0
        assert p8.total_learning_hours == 30.0

    async def test_distinct_users_separate(self, db_session):
        await log_study(db_session, USER_ID, "Stealth", "education", 50.0)
        await log_study(db_session, OTHER_USER, "Stealth", "education", 30.0)
        p1 = await get_skill_progress(db_session, USER_ID, "Stealth")
        p2 = await get_skill_progress(db_session, OTHER_USER, "Stealth")
        assert p1.total_learning_hours == 50.0
        assert p2.total_learning_hours == 30.0

    async def test_distinct_skills_separate(self, db_session):
        await log_study(db_session, USER_ID, "Stealth", "education", 50.0)
        await log_study(db_session, USER_ID, "Broadsword", "education", 30.0)
        ps = await get_skill_progress(db_session, USER_ID, "Stealth")
        pb = await get_skill_progress(db_session, USER_ID, "Broadsword")
        assert ps.total_learning_hours == 50.0
        assert pb.total_learning_hours == 30.0


class TestListStudy:
    async def test_lists_newest_first(self, db_session):
        await log_study(db_session, USER_ID, "Stealth", "education", 10.0)
        await log_study(db_session, USER_ID, "Stealth", "education", 20.0)
        await log_study(db_session, USER_ID, "Stealth", "education", 30.0)
        rows = await list_study(db_session, USER_ID)
        assert len(rows) == 3
        # newest first: order_by logged_at.desc(), id.desc()
        assert rows[0].real_hours == 30.0
        assert rows[-1].real_hours == 10.0

    async def test_filter_by_skill(self, db_session):
        await log_study(db_session, USER_ID, "Stealth", "education", 10.0)
        await log_study(db_session, USER_ID, "Broadsword", "education", 20.0)
        rows = await list_study(db_session, USER_ID, skill_name="Stealth")
        assert len(rows) == 1
        assert rows[0].skill_name == "Stealth"

    async def test_filter_by_character(self, db_session, make_character):
        await make_character(7, USER_ID)
        await log_study(db_session, USER_ID, "Stealth", "education", 10.0, character_id=7)
        await log_study(db_session, USER_ID, "Stealth", "education", 20.0)  # char=None
        rows = await list_study(db_session, USER_ID, character_id=7)
        assert len(rows) == 1
        assert rows[0].character_id == 7

    async def test_no_character_filter_lists_all(self, db_session, make_character):
        await make_character(7, USER_ID)
        # default character_id=None means 'do not filter on character'
        await log_study(db_session, USER_ID, "Stealth", "education", 10.0, character_id=7)
        await log_study(db_session, USER_ID, "Stealth", "education", 20.0)
        rows = await list_study(db_session, USER_ID)
        assert len(rows) == 2

    async def test_only_own_user(self, db_session):
        await log_study(db_session, USER_ID, "Stealth", "education", 10.0)
        await log_study(db_session, OTHER_USER, "Stealth", "education", 20.0)
        rows = await list_study(db_session, USER_ID)
        assert len(rows) == 1
        assert rows[0].discord_user_id == USER_ID

    async def test_limit(self, db_session):
        for i in range(5):
            await log_study(db_session, USER_ID, "Stealth", "education", float(i + 1))
        rows = await list_study(db_session, USER_ID, limit=2)
        assert len(rows) == 2

    async def test_empty(self, db_session):
        rows = await list_study(db_session, USER_ID)
        assert rows == []


class TestResetSkill:
    async def test_reset_clears_bucket(self, db_session):
        await log_study(db_session, USER_ID, "First Aid", "education", 10.0)
        await log_study(db_session, USER_ID, "First Aid", "education", 20.0)
        await log_study(db_session, USER_ID, "First Aid", "education", 30.0)
        deleted = await reset_skill(db_session, USER_ID, "First Aid")
        assert deleted == 3
        p = await get_skill_progress(db_session, USER_ID, "First Aid")
        assert p.total_learning_hours == 0.0

    async def test_reset_empty_returns_zero(self, db_session):
        assert await reset_skill(db_session, USER_ID, "Nonexistent") == 0

    async def test_reset_only_target_bucket(self, db_session):
        await log_study(db_session, USER_ID, "First Aid", "education", 10.0)
        await log_study(db_session, USER_ID, "Stealth", "education", 20.0)
        deleted = await reset_skill(db_session, USER_ID, "First Aid")
        assert deleted == 1
        # Stealth untouched
        p = await get_skill_progress(db_session, USER_ID, "Stealth")
        assert p.total_learning_hours == 20.0

    async def test_reset_respects_character_bucket(self, db_session, make_character):
        await make_character(7, USER_ID)
        await log_study(db_session, USER_ID, "Stealth", "education", 10.0, character_id=7)
        await log_study(db_session, USER_ID, "Stealth", "education", 20.0)  # char=None
        # reset only the NULL bucket
        deleted = await reset_skill(db_session, USER_ID, "Stealth")
        assert deleted == 1
        # character_id=7 row survives
        p = await get_skill_progress(db_session, USER_ID, "Stealth", character_id=7)
        assert p.total_learning_hours == 10.0

    async def test_reset_character_bucket(self, db_session, make_character):
        await make_character(7, USER_ID)
        await log_study(db_session, USER_ID, "Stealth", "education", 10.0, character_id=7)
        await log_study(db_session, USER_ID, "Stealth", "education", 20.0)  # char=None
        deleted = await reset_skill(db_session, USER_ID, "Stealth", character_id=7)
        assert deleted == 1
        # NULL bucket survives
        p = await get_skill_progress(db_session, USER_ID, "Stealth")
        assert p.total_learning_hours == 20.0


class TestCharacterDeleteSetNull:
    async def test_delete_character_sets_study_null(self, db_session, sample_gcs_data):
        from sqlalchemy import text

        from gurps_bot.gcs.parser import parse_gcs

        # sqlite ignores ON DELETE SET NULL unless FK enforcement is on for this connection
        await db_session.execute(text("PRAGMA foreign_keys=ON"))

        parsed = parse_gcs(sample_gcs_data)
        char, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await db_session.flush()

        await log_study(
            db_session, USER_ID, "Broadsword", "education", 50.0, character_id=char.id,
        )
        await db_session.commit()

        from gurps_bot.services.characters import delete_character

        await delete_character(db_session, char.id)
        await db_session.commit()

        # row falls into the no-character bucket
        p = await get_skill_progress(db_session, USER_ID, "Broadsword")
        assert p.total_learning_hours == 50.0


class TestStudySkillNameCaseFold:
    """regression: skill_name buckets must not split on case/whitespace"""

    async def test_progress_matches_across_case_and_whitespace(self, db_session):
        await log_study(db_session, USER_ID, "Stealth", "self_teaching", 10.0)
        await db_session.commit()

        prog = await get_skill_progress(db_session, USER_ID, "  stealth ")
        assert prog.total_learning_hours > 0

    async def test_reset_matches_across_case(self, db_session):
        await log_study(db_session, USER_ID, "Broadsword", "self_teaching", 5.0)
        await db_session.commit()

        deleted = await reset_skill(db_session, USER_ID, "broadsword")
        assert deleted == 1
