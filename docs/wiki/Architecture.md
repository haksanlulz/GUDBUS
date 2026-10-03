# Architecture

```
gurps_bot/
  bot.py              # Bot class, startup, extension loading
  config.py           # Environment variable configuration
  cogs/
    admin.py          # /sync, /status, guild cleanup
    characters.py     # the /char group
    rolling.py        # /roll, /check, /contest, /damage
    combat.py         # /attack, /defend, /combat group
    error_handler.py  # Global error handler
    ...               # + 12 more cogs (calc_*, trackers, macros, reference, gmscreen, body_ref, campaign, help, legal)
  db/
    engine.py         # Async SQLAlchemy engine + session factory
    models.py         # ORM models (Character, Skill, Spell, Trait, Combat, Combatant)
    migrations/       # Alembic migrations
    ...               # + notes, study, timers, wealth models
  services/
    characters.py     # Character data access layer
    combat.py         # Combat tracker data access layer
    ...               # + 12 more (dashboard, macros, notes, reference, timers, ...)
  mechanics/
    checks.py         # GURPS 3d6 roll-under engine
    damage.py         # Damage + wounding multipliers
    dice.py           # Dice parser and roller
    tables.py         # Fright check row lookup, critical-table page cites
    combat_constants.py  # Maneuvers, status effects, display helpers
    ...               # + 21 more (defense, injury, speed_range, encumbrance, ...)
  gcs/
    parser.py         # GCS v5 JSON parser
    library.py        # in-memory facts-only reference catalog
  ui/
    embeds.py         # Discord embed builders
    views.py          # Interactive UI (pagination, confirmation, combat tracker)
    formatters.py     # Text formatting helpers
    ...               # + screen, tracker, respond
  utils/
    fuzzy.py          # rapidfuzz wrapper
    cache.py          # TTL cache for autocomplete
    sanitize.py       # Input sanitization
    scope.py          # guild/channel ids for guild-only paths
```
