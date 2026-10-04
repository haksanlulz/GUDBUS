# Privacy

GUDBUS keeps what its commands need in a SQLite database on the machine of
whoever hosts that copy of the bot. That host is the operator: they control the
data, and `/legal` shows how to reach them. The instance the author runs is
operated by haksanlulz. There are no third-party services, no analytics and no
data sale.

## What is stored

- **Discord IDs**: your user ID, the server and channel IDs a command ran in,
  and the message ID of each combat tracker so the bot can keep editing it.
- **Imported characters** (`/char import`): the attributes, skills, spells,
  traits and equipment parsed from your `.gcs` sheet, plus the uploaded file
  itself, kept whole so `/char export` can give it back. That file includes
  whatever the sheet holds, such as its player-name field, portrait and notes.
- **Combat state** (`/combat`): combatants, HP and FP, statuses, maneuvers,
  turn order, and the user who started the combat.
- **Your saved content**: dice macros, notes (including GM-secret notes),
  study logs, wealth, and crafting projects with their cost ledgers.
- **Channel timers** (`/timer`): label, counts and unit, kept per channel
  rather than per user.
- **Server house rules** (`/campaign`): which optional rules a server has
  changed. No personal data; one row per server.

## What is not stored

- Message content. The bot reads slash-command input only.
- Anything about users who never run a command.

## Logs

- Routine log lines record activity by ID (user, server, channel and record
  IDs), not names or text you typed.
- When a command fails, the error log records the command, those IDs and its
  options. Free-text options (notes, titles, search text) and any value over
  50 characters are replaced by a length placeholder; short values such as a
  dice expression or a skill name are kept so the failure can be reproduced.
- The log file rotates at 5 MB and keeps three old files (about 20 MB in
  all), so older entries are overwritten as new ones arrive. There is no fixed
  retention period. A host running the Docker image also keeps console output
  for as long as its Docker log settings allow.

## Deletion

- **`/privacy delete-my-data`** deletes everything keyed to your Discord ID, in
  every server: characters and their stored sheets, macros, notes, study logs,
  wealth and crafting projects. Your entries in a running combat stay on its
  tracker without your ID attached, and a combat you started keeps your ID as
  its starter, until that combat ends. Combats untouched for 24 hours are
  deleted automatically.
- **`/char delete`** removes one character, its parsed data and its stored
  sheet. Notes, study logs and crafting projects linked to it are kept and
  unlinked; its wallet balance moves to your default wallet.
- `/macro delete`, `/notes delete`, `/timer remove` and `/craft delete` remove
  those records.
- **When the bot leaves a server** it deletes that server's active-character
  selections, combats, notes, timers, house rules and crafting projects. Your
  characters, macros, study logs and wealth belong to you rather than the
  server, so they are kept; `/privacy delete-my-data` removes them.
- For anything else, use the contact link in `/legal`.

## Visibility

GM-secret notes are shown only to their author. Blind rolls (`hidden:`) are
shown only to the roller.
