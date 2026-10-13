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

## What I'd do differently

- **Pin every rule to the page it comes from.** The fright-check and critical tables shipped for over a month with invented rows: keyed on margin, no Rule of 14. A regression test also defended a +4 melee bonus against prone targets that the cited page does not contain. Mechanics tests now cite the printed page and reproduce the book's own worked examples, and each mechanics module is checked against its source.
- **The repair tool must not live inside the thing it repairs.** A server kick during the rename wiped every slash command, and `/sync`, the repair, was one of the commands wiped. Registration now runs at startup, and the rescue is a mention-prefix text command that a registration wipe cannot remove.
- **A privacy promise is a testable claim.** The privacy policy said kicking the bot deletes that server's data. A table added later was never added to the teardown, so a re-invite restored the old server's house rules. The teardown now derives its table list from the model metadata, and a test checks it.
- **Gate the deploy on the tests.** The Docker publish workflow did not depend on the test workflow, so a commit with a failing test matrix still published a pullable image. It does now, and the gate was proven by publishing a branch with a planted failing test and confirming no image appeared.
- **Order state changes and replies carefully.** After deferred replies were switched on, eight combat commands saved an HP change and then failed to reply, telling the user the command had failed and inviting them to apply the damage twice. That reply now goes through the shared helper that checks whether the interaction was already answered.
- **Local green is one interpreter.** CI runs Python 3.10 and 3.12; eleven commits went up on a green local run that CI failed.

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
