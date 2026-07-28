# Privacy

GUDBUS stores the minimum it needs to run its commands, in a SQLite database on
the machine the bot operator hosts it on. No third-party services, no
analytics, no data sale.

## What is stored

- **Discord IDs** — your user ID, and the guild/channel IDs a command ran in.
  These key everything below.
- **Imported characters** (`/import`) — the attributes, skills, spells, traits,
  and equipment parsed from the `.gcs` sheet you upload, plus that file's name
  and the sheet's own internal id.
- **Combat state** (`/combat`) — combatants, HP/FP, statuses, turn order.
- **Your saved content** — dice macros, notes (including GM-secret notes),
  study logs, timers, wealth records.
- **Server house rules** (`/campaign`) — which optional GURPS rules a server has
  turned on or off. No personal data; one row per server, only once something
  is changed from the default.

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
- Kicking the bot from a server deletes that server's data automatically — its
  active-character selections, combats, notes, timers and house rules. Your
  characters, macros, study logs and wealth are yours rather than the server's
  and are keyed to your user, so they survive and follow you.
- For anything else, open an issue: https://github.com/haksanlulz/GUDBUS/issues

## Visibility

GM-secret notes are shown only to their author. Blind rolls (`hidden:`) are
shown only to the roller.
