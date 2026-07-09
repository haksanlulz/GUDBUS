from gurps_bot.utils.fuzzy import best_match, fuzzy_match


class TestFuzzyMatch:
    def test_exact_match(self):
        results = fuzzy_match("Broadsword", ["Broadsword", "Shortsword", "Knife"])
        assert results[0][0] == "Broadsword"
        assert results[0][1] >= 90

    def test_partial_match(self):
        results = fuzzy_match("broad", ["Broadsword", "Shortsword", "Knife"])
        assert any(m == "Broadsword" for m, _ in results)

    def test_no_match(self):
        results = fuzzy_match("zzzzzzz", ["Broadsword", "Shortsword"], score_cutoff=80)
        assert results == []

    def test_empty_query(self):
        results = fuzzy_match("", ["Broadsword", "Shortsword"])
        assert results == []

    def test_empty_candidates(self):
        results = fuzzy_match("Broadsword", [])
        assert results == []

    def test_limit(self):
        candidates = [f"Skill {i}" for i in range(50)]
        results = fuzzy_match("Skill", candidates, limit=5, score_cutoff=40)
        assert len(results) <= 5

    def test_score_cutoff_filters(self):
        results = fuzzy_match("xyz", ["Broadsword"], score_cutoff=90)
        assert results == []


class TestBestMatch:
    def test_returns_single_best(self):
        result = best_match("broad", ["Broadsword", "Shortsword", "Knife"])
        assert result == "Broadsword"

    def test_returns_none_below_cutoff(self):
        result = best_match("zzzzz", ["Broadsword"], score_cutoff=90)
        assert result is None


class TestPrefixOptimized:
    """prefix_optimized (partial_ratio) must stay case-insensitive without WRatio's processing."""

    def test_substring_ranks_first(self):
        results = fuzzy_match(
            "broad", ["Broadsword", "Shortsword", "Shield"],
            limit=5, score_cutoff=40, prefix_optimized=True,
        )
        assert results[0][0] == "Broadsword"
        assert results[0][1] >= 90  # full substring => high partial_ratio

    def test_case_insensitive(self):
        results = fuzzy_match(
            "BROADSWORD", ["Broadsword", "Shortsword"],
            prefix_optimized=True, score_cutoff=80,
        )
        assert any(m == "Broadsword" for m, _ in results)

    def test_empty_query_and_candidates(self):
        assert fuzzy_match("", ["Broadsword"], prefix_optimized=True) == []
        assert fuzzy_match("broad", [], prefix_optimized=True) == []

    def test_miss_below_cutoff(self):
        assert fuzzy_match(
            "zzzzzzz", ["Broadsword", "Shortsword"],
            score_cutoff=80, prefix_optimized=True,
        ) == []

    def test_default_path_still_wratio(self):
        # regression: default path stays WRatio
        results = fuzzy_match("Broadsword", ["Broadsword", "Shortsword", "Knife"])
        assert results[0][0] == "Broadsword"
        assert results[0][1] >= 90
