import time

from gurps_bot.utils.cache import TTLCache


class TestTTLCache:
    def test_get_returns_none_when_empty(self):
        cache = TTLCache(ttl=10.0)
        assert cache.get((1, 2)) is None

    def test_set_and_get(self):
        cache = TTLCache(ttl=10.0)
        cache.set((1, 2), ["a", "b"])
        assert cache.get((1, 2)) == ["a", "b"]

    def test_expired_entry_returns_none(self):
        cache = TTLCache(ttl=0.01)
        cache.set((1, 2), "data")
        time.sleep(0.02)
        assert cache.get((1, 2)) is None

    def test_max_size_prunes_expired(self):
        cache = TTLCache(ttl=0.01, max_size=2)
        cache.set((1, 1), "a")
        cache.set((2, 2), "b")
        time.sleep(0.02)
        # both expired; third set trips the prune
        cache.set((3, 3), "c")
        assert len(cache._store) == 1  # only the fresh entry

    def test_invalidate_removes_key(self):
        cache = TTLCache(ttl=10.0)
        cache.set((1, 2), "data")
        cache.invalidate((1, 2))
        assert cache.get((1, 2)) is None

    def test_invalidate_user_removes_all_guilds(self):
        cache = TTLCache(ttl=10.0)
        cache.set((42, 100), "guild_a")
        cache.set((42, 200), "guild_b")
        cache.set((99, 100), "other_user")
        cache.invalidate_user(42)
        assert cache.get((42, 100)) is None
        assert cache.get((42, 200)) is None
        assert cache.get((99, 100)) == "other_user"

    def test_clear_empties_store(self):
        cache = TTLCache(ttl=10.0)
        cache.set((1, 1), "a")
        cache.set((2, 2), "b")
        cache.clear()
        assert cache.get((1, 1)) is None
        assert cache.get((2, 2)) is None
