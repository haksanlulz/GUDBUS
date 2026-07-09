from __future__ import annotations

from gurps_bot.utils.cache import TTLCache

# keyed (user_id, guild_id) — rolling cog reads/writes, character cog invalidates
skill_cache = TTLCache(ttl=10.0)
