# Privacy

GUDBUS stores the minimum it needs to run its commands, in a SQLite database on
the machine the bot operator hosts it on. No third-party services, no
analytics, no data sale.

## What is stored

- **Discord IDs** — your user ID, and the guild/channel IDs a command ran in.
  These key everything below.
- **Imported characters** (`/import`) — the attributes, skills, spells, traits,
  and equipment parsed from the `.gcs` sheet you upload.
- **Combat state** (`/combat`) — combatants, HP/FP, statuses, turn order.
- **Your saved content** — dice macros, notes (including GM-secret notes),
  study logs, timers, wealth records.

## What is not stored

- Message content. The bot reads slash-command input only.
- Anything about users who never run a command.

## Logs

Error logs record which command failed and its option names. Free-text option
values (note bodies, titles, and any long text) are redacted to a length
placeholder before logging.

## Deletion

- `/char delete` removes a character and its data.
- `/macro delete`, note/timer delete commands remove those records.
- Kicking the bot from a server deletes that server's data automatically.
- For anything else, open an issue: https://github.com/haksanlulz/GUDBUS/issues

## Visibility

GM-secret notes are shown only to their author. Blind rolls (`hidden:`) are
shown only to the roller.
