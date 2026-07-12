# GUDBUS

**GUDBUS (The Generic Universal Discord Bot Unofficial System) is a Discord bot for helping you run your GURPS games.** Import GCS character sheets, roll skill checks, and run turn-based combat with persistent initiative tracking. 94 slash commands.

## Features

- **Character Management** -- Import `.gcs` files, view attributes/skills/spells/traits/equipment, switch between characters, export back to `.gcs`
- **Dice Rolling** -- Standard dice notation (`3d6`, `2d+1`, `4d6+3`), GURPS success rolls with critical thresholds, quick contests
- **Combat** -- Damage rolls with wounding multipliers, hit locations, fright checks, attack/defend rolls
- **Combat Tracker** -- Persistent initiative tracker with HP/FP tracking, status effects, maneuvers, round management, interactive buttons
- **Autocomplete** -- Fuzzy-matched skill, attribute, weapon, and character name suggestions

## Setup

1. **Clone and install** (uses [uv](https://docs.astral.sh/uv/)):
   ```bash
   git clone https://github.com/haksanlulz/GUDBUS.git
   cd GUDBUS
   uv sync
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your Discord bot token and optional dev guild ID.

3. **Run the bot:**
   ```bash
   uv run python -m gurps_bot
   ```

4. **Sync commands:**
   Use `/sync` (bot owner only) to register slash commands.

## Commands

| Command | Description |
|---------|-------------|
| `/import` | Upload a `.gcs` character file |
| `/char view` | View active character summary |
| `/char skills` | List skills (with search) |
| `/char spells` | List spells (with search) |
| `/char traits` | List advantages/disadvantages |
| `/char equipment` | View equipment |
| `/char export` | Download character as `.gcs` |
| `/char list` | List all imported characters |
| `/char switch` | Switch active character |
| `/char delete` | Delete a character |
| `/roll` | Roll dice (`3d6`, `2d+1`) |
| `/check` | Roll 3d6 vs skill/attribute |
| `/contest` | Quick contest between two targets |
| `/damage` | Roll damage with type and DR |
| `/attack` | Roll attack with equipped weapon |
| `/defend` | Roll dodge/parry/block |
| `/hit-location` | Random hit location (3d6) |
| `/fright-check` | Fright check with table lookup |
| `/posture` | Posture combat modifiers lookup (B551) |
| `/target` | Deliberate hit-location penalty + effect (B552) |
| `/macro save` | Save a named dice macro |
| `/macro roll` | Roll a saved macro |
| `/macro list` | List your saved macros |
| `/macro delete` | Delete a saved macro |
| `/combat start` | Start combat in channel |
| `/combat join` | Join with active character |
| `/combat add-npc` | Add NPC (GM only) |
| `/combat leave` | Leave the current combat |
| `/combat remove` | Remove a combatant (GM only) |
| `/combat hp` | Modify combatant HP |
| `/combat fp` | Modify combatant FP |
| `/combat status` | Add/remove status effects |
| `/combat maneuver` | Set maneuver for turn |
| `/combat defend` | Active defense with cumulative-Parry tracking |
| `/combat end` | End combat (GM only) |
| `/calc fall` | Falling damage from a height (B431) |
| `/calc collision` | Two-body collision / vehicle slam damage (B430) |
| `/calc explosion` | Concussion falloff + fragmentation radius (B414) |
| `/calc knockback` | Knockback distance + fall-check trigger (B378) |
| `/jump` | High-jump and long-jump distance from Basic Move (B352) |
| `/throw` | Throwing distance and damage by ST and weight (B355) |
| `/hike` | Daily hiking distance over terrain and weather (B351) |
| `/swim` | Swimming Move, distance, and fatigue rolls (B354) |
| `/encumbrance` | Basic Lift, encumbrance level, effective Move and Dodge (B17) |
| `/lifting` | One/two-handed lift, shove, and drag capacities (B353) |
| `/vehicle cruising` | Sustainable cruising speed over terrain (B463) |
| `/vehicle endurance` | Loiter endurance: Range ÷ cruising speed (B463) |
| `/vehicle dodge` | Vehicle Dodge from control skill + Handling (B470) |
| `/vehicle control` | Roll a control roll and read it vs Stability Rating (B466) |
| `/vehicle decel` | Safe deceleration per turn by drivetrain (B468) |
| `/vehicle crash` | Crash/ram damage at velocity + ground skid (B468/B430) |
| `/reaction roll` | Roll 3d + modifier and read the reaction band (B560) |
| `/reaction band` | Look up the reaction band for an adjusted total (B560) |
| `/ranged` | Net range/speed/size modifier for a ranged attack (B550) |
| `/range` | Range penalty for a distance (B550) |
| `/size` | Size Modifier for a length (B19) |
| `/cast cost` | Energy to cast a spell, scaled for size/area then high-skill reduction (B236) |
| `/cast time` | Casting time by skill (high skill divides; ceremonial ×10) (B236) |
| `/cast ceremonial` | Pool ceremonial energy + extra-energy skill bonus (B238) |
| `/cast distance` | Skill penalty to cast a Regular spell at range (B240) |
| `/cast seek` | Long-distance modifier for an Information/Seek spell (B241) |
| `/cast missile` | Missile-spell damage: 1d/energy, ≤Magery per second, ≤3 s (B240) |
| `/study log` | Log a study session toward a skill (B292) |
| `/study progress` | Show learning-hour progress for a skill (B292) |
| `/study list` | List your recent study sessions |
| `/study reset` | Delete all study sessions for one skill |
| `/notes add` | Add a campaign/session/GM note |
| `/notes list` | List notes visible to you |
| `/notes search` | Search your visible notes (title/body/tags) |
| `/notes edit` | Edit one of your notes |
| `/notes delete` | Delete one of your notes |
| `/timer add` | Start a countdown timer (duration/condition) |
| `/timer tick` | Advance this channel's timers and report expirations |
| `/timer list` | List this channel's timers |
| `/timer remove` | Remove one timer (or clear all) in this channel |
| `/wealth show` | Show your current wallet (B265) |
| `/wealth adjust` | Add income (+) or record a spend (-) |
| `/wealth set` | Set your balance to an exact amount (GM correction) |
| `/wealth status` | Set your Status tier (drives cost of living) (B265) |
| `/wealth upkeep` | Deduct one month's cost of living (B265) |
| `/wealth starting` | Look up starting cash for a TL + Wealth level (B25) |
| `/screen` | GM quick-reference: maneuvers, speed/range, encumbrance, reaction, crits, fright |
| `/gm` | GM dashboard: live timers, combat, and your recent study/notes |
| `/skill` | Look up a GURPS skill (facts + page cite) |
| `/trait` | Look up a GURPS advantage or disadvantage (facts + page cite) |
| `/spell` | Look up a GURPS spell (facts + page cite) |
| `/technique` | Look up a GURPS technique (facts + page cite) |
| `/item` | Look up GURPS equipment (facts + page cite) |
| `/legal` | Legal notice, credits, trademark, and privacy information |
| `/about` | About this bot — credits, trademark, and privacy |
| `/support` | Ways to support the bot (donation links + how to help) |
| `/donate` | Donation links to support the bot's hosting |
| `/status` | Bot diagnostics |
| `/sync` | Sync slash commands (owner) |

## Reference data

The `/skill`, `/trait`, `/spell`, `/technique`, and `/item` lookups read an
in-memory **facts-only** catalog vendored from the upstream
[`richardwilkes/gcs_master_library`](https://github.com/richardwilkes/gcs_master_library)
(the GURPS Character Sheet master library, MPL-2.0). The snapshot is pinned to a
specific commit and synced with:

```bash
uv run python tools/sync_gcs_library.py          # clone + vendor the pinned snapshot
uv run python tools/sync_gcs_library.py --check   # dry-run audit (no network)
```

Per the Steve Jackson Games Online Policy, lookups return mechanical facts only
(name, attribute, difficulty, point cost, page reference), never description
prose or rulebook text. GURPS is a trademark of Steve Jackson Games; this bot is
unofficial. Details in `docs/GURPS-IP-COMPLIANCE.md` and `/legal`.

If the snapshot hasn't been synced, the reference commands say so and point at
`tools/sync_gcs_library.py`.

## Architecture

```
gurps_bot/
  bot.py              # Bot class, startup, extension loading
  config.py           # Environment variable configuration
  cogs/
    admin.py          # /sync, /status, guild cleanup
    characters.py     # /import, /char group
    rolling.py        # /roll, /check, /contest, /damage
    combat.py         # /attack, /defend, /combat group
    error_handler.py  # Global error handler
    ...               # + 11 more cogs (calc_*, trackers, macros, reference, gmscreen, body_ref, legal, support)
  db/
    engine.py         # Async SQLAlchemy engine + session factory
    models.py         # ORM models (Character, Skill, Spell, Trait, Combat, Combatant)
    migrations/       # Alembic migrations
    ...               # + notes, study, timers, wealth models
  services/
    characters.py     # Character data access layer
    combat.py         # Combat tracker data access layer
    ...               # + 9 more (dashboard, macros, notes, reference, timers, ...)
  mechanics/
    checks.py         # GURPS 3d6 roll-under engine
    damage.py         # Damage + wounding multipliers
    dice.py           # Dice parser and roller
    tables.py         # Fright check, critical hit/miss tables
    combat_constants.py  # Maneuvers, status effects, display helpers
    ...               # + 20 more (defense, injury, speed_range, encumbrance, ...)
  gcs/
    parser.py         # GCS v5 JSON parser
    library.py        # in-memory facts-only reference catalog
  ui/
    embeds.py         # Discord embed builders
    views.py          # Interactive UI (pagination, confirmation, combat tracker)
    formatters.py     # Text formatting helpers
    ...               # + screen, tracker
  utils/
    fuzzy.py          # rapidfuzz wrapper
    cache.py          # TTL cache for autocomplete
    sanitize.py       # Input sanitization
```

## Development

**Run tests** (~1,800 tests):
```bash
uv run python -m pytest
```

**Database migrations:**
```bash
# Generate a new migration after model changes
uv run python -m alembic revision --autogenerate -m "describe change"

# Apply migrations (stamped databases only — see note)
uv run python -m alembic upgrade head

# Deploys use the bootstrap wrapper instead: creates + stamps a fresh DB at
# head, upgrades a stamped one, refuses (with the fix) on an unstamped legacy DB
uv run python -m gurps_bot.db.bootstrap
```

A brand-new database is created at the current schema by startup `create_all`
and stamped at Alembic head automatically; `upgrade head` only works on
stamped databases (the initial migration assumes a pre-existing schema).

**Dependencies:** Python 3.10+, discord.py 2.3+, SQLAlchemy 2.0+ (async), aiosqlite, rapidfuzz, Alembic.
