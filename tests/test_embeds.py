import discord
from gurps_bot.mechanics.checks import CheckResult, Outcome
from gurps_bot.mechanics.damage import DamageResult, HitLocationResult
from gurps_bot.mechanics.dice import DiceSpec, RollResult
from gurps_bot.ui.embeds import (
    BLUE,
    DARK_RED,
    GOLD,
    GREEN,
    RED,
    char_list_embed,
    char_summary_embed,
    check_embed,
    contest_embed,
    damage_embed,
    fright_check_embed,
    hit_location_embed,
    paginated_list_embed,
    roll_embed,
)


def _make_check(rolled: int, target: int, outcome: Outcome) -> CheckResult:
    spec = DiceSpec(3, 6, 0)
    dice = (rolled // 3, rolled // 3, rolled - 2 * (rolled // 3))
    roll_result = RollResult(spec=spec, dice=dice, total=rolled)
    return CheckResult(
        roll_result=roll_result,
        target=target,
        margin=target - rolled,
        outcome=outcome,
    )


class TestCharSummaryEmbed:
    def test_has_correct_title(self):
        attrs = {"st": 13, "dx": 12, "iq": 10, "ht": 11}
        embed = char_summary_embed("Gandalf", 250, attrs, {}, "gandalf.gcs")
        assert embed.title == "Gandalf"
        assert embed.color == BLUE

    def test_has_points_field(self):
        embed = char_summary_embed("Test", 100, {}, {}, "t.gcs")
        values = [f.value for f in embed.fields]
        assert "100" in values


class TestCharListEmbed:
    def test_empty_list(self):
        embed = char_list_embed([])
        assert "No characters" in embed.description

    def test_with_characters(self):
        chars = [("Knight", 150, True), ("Wizard", 200, False)]
        embed = char_list_embed(chars)
        assert "Knight" in embed.description
        assert "**[active]**" in embed.description
        assert "Wizard" in embed.description


class TestRollEmbed:
    def test_shows_total(self):
        spec = DiceSpec(3, 6, 0)
        result = RollResult(spec=spec, dice=(3, 4, 5), total=12)
        embed = roll_embed(result)
        assert "**12**" in embed.fields[1].value


class TestCheckEmbed:
    def test_success_is_green(self):
        result = _make_check(10, 14, Outcome.SUCCESS)
        embed = check_embed(result, "Test Check")
        assert embed.color == GREEN

    def test_critical_success_is_gold(self):
        result = _make_check(3, 14, Outcome.CRITICAL_SUCCESS)
        embed = check_embed(result, "Test Check")
        assert embed.color == GOLD

    def test_failure_is_red(self):
        result = _make_check(15, 10, Outcome.FAILURE)
        embed = check_embed(result, "Test Check")
        assert embed.color == RED

    def test_critical_failure_is_dark_red(self):
        result = _make_check(18, 10, Outcome.CRITICAL_FAILURE)
        embed = check_embed(result, "Test Check")
        assert embed.color == DARK_RED

    def test_has_margin_field(self):
        result = _make_check(10, 14, Outcome.SUCCESS)
        embed = check_embed(result, "Test")
        margin_field = next(f for f in embed.fields if f.name == "Margin")
        assert "+4" in margin_field.value


class TestDamageEmbed:
    def test_shows_wound(self):
        spec = DiceSpec(2, 6, 0)
        roll_result = RollResult(spec=spec, dice=(4, 5), total=9)
        result = DamageResult(
            roll_result=roll_result, damage_type="cut",
            raw_damage=9, wounding_multiplier=1.5, wound=13, location=None,
        )
        embed = damage_embed(result)
        assert "**13**" in embed.fields[2].value

    def test_shows_location(self):
        spec = DiceSpec(1, 6, 0)
        roll_result = RollResult(spec=spec, dice=(4,), total=4)
        result = DamageResult(
            roll_result=roll_result, damage_type="cr",
            raw_damage=4, wounding_multiplier=4.0, wound=16, location="skull",
        )
        embed = damage_embed(result)
        loc_field = next(f for f in embed.fields if f.name == "Location")
        assert loc_field.value == "skull"


class TestHitLocationEmbed:
    def test_shows_location(self):
        result = HitLocationResult(rolled=10, location="Torso", hit_penalty=0)
        embed = hit_location_embed(result)
        assert embed.fields[1].value == "Torso"


class TestContestEmbed:
    def test_shows_winner(self):
        a = _make_check(10, 14, Outcome.SUCCESS)
        b = _make_check(12, 12, Outcome.SUCCESS)
        embed = contest_embed(a, b, "A", "Alice", "Bob")
        winner_field = next(f for f in embed.fields if f.name == "Winner")
        assert "Alice" in winner_field.value

    def test_shows_tie(self):
        a = _make_check(10, 12, Outcome.SUCCESS)
        b = _make_check(10, 12, Outcome.SUCCESS)
        embed = contest_embed(a, b, "Tie", "Alice", "Bob")
        winner_field = next(f for f in embed.fields if f.name == "Winner")
        assert "Tie" in winner_field.value


class TestFrightCheckEmbed:
    def test_success_no_effect(self):
        result = _make_check(8, 12, Outcome.SUCCESS)
        embed = fright_check_embed(result, "")
        field_names = [f.name for f in embed.fields]
        assert "Effect" not in field_names

    def test_failure_shows_effect(self):
        result = _make_check(15, 10, Outcome.FAILURE)
        embed = fright_check_embed(result, "Stunned for 1d seconds.")
        effect_field = next(f for f in embed.fields if f.name == "Effect")
        assert "Stunned" in effect_field.value


class TestPaginatedListEmbed:
    def test_single_page_no_footer(self):
        embed = paginated_list_embed("Skills", "line1\nline2", 1, 1, "Hero")
        assert not embed.footer or not embed.footer.text

    def test_multi_page_has_footer(self):
        embed = paginated_list_embed("Skills", "line1\nline2", 2, 5, "Hero")
        assert embed.footer and "2/5" in embed.footer.text


class TestEmbedThinBranches:
    """Branches the happy-path tests miss: optional fields + truncation."""

    def test_summary_shows_dodge_when_present(self):
        e = char_summary_embed("Hero", 100, {"st": 10}, {"dodge": [8]}, "x.gcs")
        assert any(f.name == "Dodge" for f in e.fields)

    def test_roll_embed_shows_positive_modifier_sign(self):
        result = RollResult(spec=DiceSpec(count=3, sides=6, modifier=2), dice=(3, 4, 5), total=14)
        e = roll_embed(result)
        dice_field = next(f for f in e.fields if f.name == "Dice")
        assert "+2" in dice_field.value

    def test_char_list_truncates_many(self):
        chars = [(f"Character Number {i} With A Fairly Long Name", i, False) for i in range(200)]
        e = char_list_embed(chars)
        assert "truncated" in e.description

    def test_summary_truncates_oversized_attr_block(self):
        # pathological calc value overflows the 1024 field cap -> truncated
        e = char_summary_embed("Hero", 100, {"st": 10}, {"swing": "d" * 2000}, "x.gcs")
        attr_field = next(f for f in e.fields if f.name == "Attributes")
        assert len(attr_field.value) <= 1024
        assert "truncated" in attr_field.value
