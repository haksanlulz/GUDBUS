import pytest
from gurps_bot.mechanics.dice import DiceSpec, parse_dice, roll, roll_3d6


class TestParseDice:
    def test_standard_3d6(self):
        spec = parse_dice("3d6")
        assert spec == DiceSpec(count=3, sides=6, modifier=0)

    def test_shorthand_3d(self):
        spec = parse_dice("3d")
        assert spec == DiceSpec(count=3, sides=6, modifier=0)

    def test_1d(self):
        spec = parse_dice("1d")
        assert spec == DiceSpec(count=1, sides=6, modifier=0)

    def test_with_positive_modifier(self):
        spec = parse_dice("2d+1")
        assert spec == DiceSpec(count=2, sides=6, modifier=1)

    def test_with_negative_modifier(self):
        spec = parse_dice("1d-2")
        assert spec == DiceSpec(count=1, sides=6, modifier=-2)

    def test_modifier_out_of_range_raises(self):
        # oversized modifier -> embed field over discord's 1024 cap -> HTTP 400
        with pytest.raises(ValueError):
            parse_dice("1d6+99999")
        with pytest.raises(ValueError):
            parse_dice("1d6-99999")

    def test_non_d6(self):
        spec = parse_dice("4d10+3")
        assert spec == DiceSpec(count=4, sides=10, modifier=3)

    def test_case_insensitive(self):
        spec = parse_dice("3D6")
        assert spec == DiceSpec(count=3, sides=6, modifier=0)

    def test_whitespace(self):
        spec = parse_dice("  2d+1  ")
        assert spec == DiceSpec(count=2, sides=6, modifier=1)

    def test_invalid_notation(self):
        with pytest.raises(ValueError):
            parse_dice("not_dice")

    def test_empty_string(self):
        with pytest.raises(ValueError):
            parse_dice("")

    def test_d_alone(self):
        spec = parse_dice("d")
        assert spec == DiceSpec(count=1, sides=6, modifier=0)

    def test_rejects_too_many_dice(self):
        with pytest.raises(ValueError, match="cannot exceed"):
            parse_dice("101d6")

    def test_rejects_too_many_sides(self):
        with pytest.raises(ValueError, match="cannot exceed"):
            parse_dice("1d1001")

    def test_max_dice_allowed(self):
        spec = parse_dice("100d6")
        assert spec.count == 100

    def test_max_sides_allowed(self):
        spec = parse_dice("1d1000")
        assert spec.sides == 1000


class TestDiceSpec:
    def test_str_3d6(self):
        assert str(DiceSpec(3, 6, 0)) == "3d"

    def test_str_with_plus(self):
        assert str(DiceSpec(2, 6, 1)) == "2d+1"

    def test_str_with_minus(self):
        assert str(DiceSpec(1, 6, -2)) == "1d-2"

    def test_str_non_d6(self):
        assert str(DiceSpec(4, 10, 3)) == "4d10+3"

    def test_min_max(self):
        spec = DiceSpec(3, 6, 0)
        assert spec.min == 3
        assert spec.max == 18

    def test_min_max_with_modifier(self):
        spec = DiceSpec(2, 6, 3)
        assert spec.min == 5
        assert spec.max == 15

    def test_average(self):
        spec = DiceSpec(3, 6, 0)
        assert spec.average == 10.5


class TestRoll:
    def test_roll_result_in_range(self):
        spec = DiceSpec(3, 6, 0)
        for _ in range(100):
            result = roll(spec)
            assert 3 <= result.total <= 18
            assert len(result.dice) == 3
            assert all(1 <= d <= 6 for d in result.dice)

    def test_roll_from_string(self):
        result = roll("2d+1")
        assert 3 <= result.total <= 13
        assert len(result.dice) == 2

    def test_roll_modifier_applied(self):
        spec = DiceSpec(1, 6, 10)
        for _ in range(50):
            result = roll(spec)
            assert 11 <= result.total <= 16

    def test_roll_3d6(self):
        for _ in range(100):
            result = roll_3d6()
            assert 3 <= result.total <= 18
            assert len(result.dice) == 3


class TestParseDiceBareNumber:
    """Bare integer is GURPS shorthand: '8' -> 8d6."""

    def test_bare_number_is_d6(self):
        assert parse_dice("8") == DiceSpec(count=8, sides=6, modifier=0)

    def test_bare_zero_rejected(self):
        with pytest.raises(ValueError, match="at least 1"):
            parse_dice("0")

    def test_bare_over_100_rejected(self):
        with pytest.raises(ValueError, match="cannot exceed"):
            parse_dice("101")


class TestParseDiceLowerBounds:
    def test_zero_count_rejected(self):
        with pytest.raises(ValueError, match="at least 1"):
            parse_dice("0d6")

    def test_zero_sides_rejected(self):
        with pytest.raises(ValueError, match="at least 1"):
            parse_dice("3d0")


class TestRollResultStr:
    def test_str_format(self):
        from gurps_bot.mechanics.dice import RollResult

        rr = RollResult(spec=DiceSpec(2, 6, 1), dice=(3, 4), total=8)
        assert str(rr) == "2d+1 = [3, 4] = 8"
