# GUDBUS

**GUDBUS (The Generic Universal Discord Bot Unofficial System) is a Discord bot for helping you run your GURPS games.** Import GCS character sheets, roll skill checks, and run turn-based combat with persistent initiative tracking. 108 slash commands.

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

To host it for real (Docker, unRAID, systemd), see [DEPLOY.md](DEPLOY.md).

## Commands

The main areas, with the full table in the [wiki](https://github.com/haksanlulz/GUDBUS/wiki/Commands):

- **Characters**: `/char import`, `view`, `skills`, `spells`, `traits`, `equipment`, `export`, `switch`
- **Rolling and combat**: `/roll`, `/check`, `/contest`, `/damage`, `/attack`, `/defend`, `/fright-check`
- **Combat tracker**: `/combat start`, `join`, `add-npc`, `hp`, `fp`, `status`, `maneuver`, `defend`, `end`
- **Calculators**: falling, collisions, explosions, jumping, throwing, encumbrance, vehicles, range and size
- **Magic**: `/cast cost`, `time`, `ceremonial`, `distance`, `missile`
- **Campaign tools**: study logs, notes, timers, wealth, house rules
- **Crafting**: inventions, repairs, mundane crafting, alchemy, enchanting, with saved projects
- **Reference**: `/skill`, `/trait`, `/spell`, `/technique`, `/item` (facts and page cites only)

`/help` in Discord walks through them by topic.

## Documentation

The [wiki](https://github.com/haksanlulz/GUDBUS/wiki) has the detail: the [full command list](https://github.com/haksanlulz/GUDBUS/wiki/Commands),
[a worked session](https://github.com/haksanlulz/GUDBUS/wiki/A-Session), [reference data](https://github.com/haksanlulz/GUDBUS/wiki/Reference-Data),
[architecture](https://github.com/haksanlulz/GUDBUS/wiki/Architecture) and [development and testing](https://github.com/haksanlulz/GUDBUS/wiki/Development).
Its pages are kept in [`docs/wiki/`](docs/wiki/) and tested with the code.

## AI assistance

This project was built with AI assistance (Claude). Correctness was established
by the test suite, including golden-file harnesses for the GCS parser and the
magic mechanics and a test that pins the SJG legal notice character-exact, and
enforced twice on the way out: CI publishes no Docker image from a commit whose
test matrix failed, and the systemd deploy script runs the full suite before
every service restart. The author reviews and is accountable for all shipped
code.

## License

MIT (see `LICENSE`). The reference data fetched at build time is MPL-2.0; see
[Reference data](https://github.com/haksanlulz/GUDBUS/wiki/Reference-Data).

The MIT license covers this project's own code only. It grants no rights in
GURPS or any other Steve Jackson Games trademark or material. The bot runs under
the [SJ Games Online Policy](https://www.sjgames.com/general/online_policy.html),
which permits free game aids only: anyone who forks, redistributes, or hosts it
must follow that policy themselves, including not charging for it.
