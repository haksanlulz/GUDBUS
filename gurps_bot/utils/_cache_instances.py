from __future__ import annotations

from gurps_bot.utils.cache import TTLCache

# keyed (user_id, guild_id) — rolling cog reads/writes; services/characters.py
# invalidates, at the service layer rather than the cog so every caller of
# set_active_character / delete_character / import_character gets it for free
skill_cache = TTLCache(ttl=10.0)
