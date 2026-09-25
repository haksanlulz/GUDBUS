# GUDBUS

**GUDBUS (The Generic Universal Discord Bot Unofficial System) is a Discord bot for helping you run your GURPS games.** Import GCS character sheets, roll skill checks, and run turn-based combat with persistent initiative tracking. 106 slash commands.

## Features

- **Character Management**: import `.gcs` files, view attributes/skills/spells/traits/equipment, switch between characters, export back to `.gcs`
- **Dice Rolling**: standard dice notation (`3d6`, `2d+1`, `4d6+3`), GURPS success rolls with critical thresholds, Quick Contests
- **Combat**: damage rolls with wounding multipliers, hit locations, Fright Checks, attack/defend rolls
- **Combat Tracker**: persistent initiative tracker with HP/FP tracking, status effects, maneuvers, round management, interactive buttons
- **Autocomplete**: fuzzy-matched skill, attribute, weapon, and character name suggestions

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
   Edit `.env` with your Discord bot token; the other knobs are optional and
   documented inline.

3. **Run the bot:**
   ```bash
   uv run python -m gurps_bot
   ```

4. **Command registration:** automatic. Commands register globally at startup
   whenever the command set changes. `/sync` (owner) forces a re-register;
   `@<bot> sync` is the mention-prefix rescue if registrations are ever gone.

## A session

One combat, start to finish. The message formats below are the ones the code
emits (`gurps_bot/ui/formatters.py`, `gurps_bot/ui/embeds.py` and
`gurps_bot/cogs/combat.py`), and the two most drift-prone renderings are pinned
by `tests/test_readme.py`, which builds them from those modules and fails if
what is quoted here stops matching. The character names and the individual die
faces are chosen for the example; nothing seeds `random`, so a real roll will
differ. The arithmetic follows from the same rules the code applies.

**GM, `/combat start`.** Posts the tracker, and keeps editing that one message
for the rest of the fight.

> **Combat — Round 1**
> *No combatants yet. Use `/combat join` or `/combat add-npc`.*

**Player, `/combat join`.** Speed, HP and FP come off their active character.

> **Aldric** joined combat (Speed 5.75).

**GM, `/combat add-npc` `name: Ogre` `speed: 4.5` `hp: 25` `fp: 12`.**

> Added **Ogre** (Speed 4.5, HP 25).

The tracker message now reads:

> **Combat — Round 1**
> ▶ **Aldric** | Spd 5.75 | [########] 13/13 HP | [########] 11/11 FP
>  **Ogre** | Spd 4.5 | [########] 25/25 HP | [########] 12/12 FP

Order is Basic Speed descending, then DX, then a per-combatant tiebreaker.
▶ marks whose turn it is.

**Player, `/attack` `weapon: Broadsword`.** 3d against the weapon's skill level
as imported from the sheet. The embed lays these out as fields side by side:

> **Aldric — Attack: Broadsword (swung)**
> Rolled **11** (4 + 6 + 1) — Target 14 — Margin +3
> Result: **Success**
> Damage 2d cut — Reach 1

A **Roll Damage** button comes attached to that message:

> **Damage: 2d cut**
> Rolled 1 + 5 = 6 — After DR 6 — Wound **9** (×1.5)

Cutting wounds at ×1.5 on whatever gets past DR (B379), so 6 becomes 9.

**GM, `/combat hp` `target: Ogre` `amount: -9`.**

> **Ogre** HP -9 → 16/25
> Shock -4 to DX, IQ, and DX/IQ-based skills next turn (does not affect active defenses, B419).

Shock scales with the target's own HP: at 25 HP the Ogre pays 2 HP per point of
it rather than 1 (B380/B419). The tracker redraws itself:

> **Combat — Round 1**
> ▶ **Aldric** | Spd 5.75 | [########] 13/13 HP | [########] 11/11 FP
>  **Ogre** | Spd 4.5 | [#####---] 16/25 HP | [########] 12/12 FP

**GM, `/combat end`.**

> Combat ended.

## Commands

| Command | Description |
|---------|-------------|
| `/char import` | Upload a `.gcs` character file |
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
| `/vehicle control` | Make a control roll and read it vs Stability Rating (B466) |
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
| `/craft invent` | Walk an invention through its Concept roll (B473) |
| `/craft costs` | What an invention costs to prototype and produce (B474) |
| `/craft repair` | What it takes to repair a damaged item (B484) |
| `/craft make` | Making a mundane item: cost, time, and what the roll means (LTC3 ch. 5) |
| `/craft brew` | Brewing a batch of elixirs (GURPS Magic ch. 28) |
| `/craft enchant` | Enchanting an item: Power, time, and the ceremonial thresholds (Magic pp. 16-18) |
| `/craft projects` | Your crafting projects in this server |
| `/craft project` | One project: stage, time, and what it has cost |
| `/craft abandon` | End a project; the spending stays on record |
| `/screen` | GM quick-reference: maneuvers, speed/range, encumbrance, reaction, crits, fright |
| `/gm` | GM dashboard: live timers, combat, and your recent study and notes |
| `/campaign show` | Show this server's house rules |
| `/campaign rule-of-14` | Turn B360's Rule of 14 on (RAW) or off (house rule) |
| `/skill` | Look up a GURPS skill (facts + page cite) |
| `/trait` | Look up a GURPS advantage or disadvantage (facts + page cite) |
| `/spell` | Look up a GURPS spell (facts + page cite) |
| `/technique` | Look up a GURPS technique (facts + page cite) |
| `/item` | Look up GURPS equipment (facts + page cite) |
| `/legal` | Legal notice, credits, trademark, and privacy information |
| `/about` | About this bot: credits, trademark, and privacy |
| `/support` | Ways to support the bot (donation links + how to help) |
| `/donate` | Donation links to support the bot's hosting |
| `/help` | What this bot does, by topic |
| `/status` | Bot diagnostics |
| `/sync` | Force a global command re-register (owner) |

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
    characters.py     # the /char group
    rolling.py        # /roll, /check, /contest, /damage
    combat.py         # /attack, /defend, /combat group
    error_handler.py  # Global error handler
    ...               # + 13 more cogs (calc_*, trackers, macros, reference, gmscreen, body_ref, campaign, help, legal, support)
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
    tables.py         # Fright check, critical hit/miss tables
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

## Development

Tests: see [Testing](#testing).

**Database migrations:**
```bash
# new migration after model changes
uv run python -m alembic revision --autogenerate -m "describe change"

# apply pending migrations
uv run python -m alembic upgrade head
```

Deploys run `uv run python -m gurps_bot.db.bootstrap` instead. It creates and
stamps a fresh database at head, upgrades a stamped one, and refuses with
instructions on an unstamped legacy one. Startup `create_all` builds a new
database at the current schema and stamps it automatically; `upgrade head`
only works on stamped databases (the initial migration assumes a pre-existing
schema).

**Dependencies:** Python 3.10+, discord.py 2.3+, SQLAlchemy 2.0+ (async), aiosqlite, rapidfuzz, Alembic.

## Testing

Layers and the test style each gets:

- `mechanics/`: pure functions, so every rule is a plain unit test with literal inputs and expected outputs.
- `services/` and integration tests: a real SQLite database through the async engine. No mocked sessions.
- `cogs/`: driven discord.py components (real cog callbacks, views, and modals over a faked interaction). The cog itself is never mocked.
- `db/`: bootstrap and migration paths run real Alembic against a file database.
- `ui/`: embed and formatter output asserted as payloads.

Run everything (about 80 s on a workstation):
```bash
uv run python -m pytest
```
Fast tier, which skips the `slow`, `integration`, and `load` markers:
```bash
uv run python -m pytest -m "not slow and not integration and not load"
```
Markers are declared in `pyproject.toml` under `[tool.pytest.ini_options]` with strict markers on, so a misspelled mark on a test fails collection instead of warning.

Counts, to the nearest thousand lines, pinned to the tree by `tests/test_readme.py`:
- application code: 21K lines (`find gurps_bot -name '*.py' | xargs cat | wc -l`)
- tests: 30K lines (`find tests -name '*.py' | xargs cat | wc -l`)

Rounded and pinned instead of exact and dated. The previous figures carried a
date, printed a tenth of a thousand, and were both wrong within days of being
written, sitting beside the commands that disprove them.

The collected-test total is deliberately left out. It moved on the very next
commit after it was written, and a stale number beside the command that
disproves it is worse than no number:

```bash
uv run python -m pytest --collect-only -q | tail -1
```

**Why so many tests.** The mechanics layer is pure: no I/O, no Discord, no database, so every GURPS rule the bot implements is checkable with a two-line test, and there are a lot of rules. The pins hold: mutating the natural-17 branch in `gurps_bot/mechanics/checks.py` turns exactly two tests red (`tests/test_checks.py::TestDetermineOutcome::test_crit_failure_on_17_when_target_15_or_less` and `::test_17_always_fails_even_at_high_skill`) and nothing else; removing the minimum-injury floor in `gurps_bot/mechanics/damage.py` turns exactly three red (`tests/test_damage.py::TestMinimumInjuryFloor::test_one_point_small_piercing_floors_to_1`, `::test_penetrating_after_dr_floors_to_1`, and `tests/test_injury_tolerance.py::TestInteractionWithLocationAndFloor::test_minimum_one_injury_floor_survives`).

Call-only wiring assertions (`assert_awaited()` with nothing said about the payload) were audited and pruned on 2026-09-11. Policy going forward: tests pin rules and regressions. Assert behavior and payloads, never bare invocation.

## AI assistance

This project was built with AI assistance (Claude). Correctness was established
by the test suite, including golden-file harnesses for the GCS parser and the
magic mechanics and a test that pins the SJG legal notice character-exact, and
enforced twice on the way out: CI publishes no Docker image from a commit whose
test matrix failed, and the systemd deploy script runs the full suite before
every service restart. The author reviews and is accountable for all shipped
code.

## License

MIT (see `LICENSE`). The vendored reference data is MPL-2.0; see
[Reference data](#reference-data).
