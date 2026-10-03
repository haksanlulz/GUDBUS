"""Cumulative active-defense penalties (B376)."""

from __future__ import annotations

import pytest

from gurps_bot.mechanics.defense import cumulative_parry_penalty, defense_penalty


class TestCumulativeParry:
    @pytest.mark.parametrize("prior,expected", [(0, 0), (1, -4), (2, -8), (3, -12)])
    def test_penalty_steps(self, prior, expected):
        assert cumulative_parry_penalty(prior) == expected

    def test_negative_clamps_to_zero(self):
        assert cumulative_parry_penalty(-3) == 0


class TestDefensePenalty:
    def test_dodge_never_penalized(self):
        assert defense_penalty("dodge", 5, 5) == (0, None)

    def test_first_parry_is_clean(self):
        pen, note = defense_penalty("parry", 0, 0)
        assert pen == 0
        assert note is None

    def test_second_parry_is_minus4_with_note(self):
        pen, note = defense_penalty("parry", 1, 0)
        assert pen == -4
        assert note is not None and "B376" in note

    def test_third_parry_is_minus8(self):
        pen, _ = defense_penalty("parry", 2, 0)
        assert pen == -8

    def test_first_block_is_clean(self):
        assert defense_penalty("block", 0, 0) == (0, None)

    def test_second_block_notes_but_no_penalty(self):
        pen, note = defense_penalty("block", 0, 1)
        assert pen == 0
        assert note is not None and "Block" in note

    def test_case_insensitive(self):
        assert defense_penalty("PARRY", 1, 0)[0] == -4

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError):
            defense_penalty("headbutt", 0, 0)
