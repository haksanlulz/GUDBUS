# Shipping GURPS reference data — compliance notes

Why this bot can ship a facts-only skill/trait/spell catalog, and the rules it
follows. Checked June 2026 against the sources below. Not legal advice.

## The rule

Permission comes solely from the [SJ Games Online Policy](https://www.sjgames.com/general/online_policy.html)
(there is no GURPS OGL or SRD). It allows free "game aid" programs for computers,
with the required notices:

> Character stats, and original background and scenario material using our rules
> terminology, are a permitted use, as long as you're not selling it in any way.

What it forbids is reproducing the books' text and tables. So: names, attributes,
difficulties, and page citations are fine; the skill's *description prose* is not.
The grant is revocable at any time, and it voids if you charge money.

## The four conditions this bot holds to

1. **Free.** No paywall, no donation-gating on the data.
2. **No rules text.** Name + attribute + difficulty + page cite per entry. Never
   the descriptive paragraph, never copied tables.
3. **Verbatim game-aid notice** (the §IV boilerplate) in `/legal` — pinned
   character-exact by `tests/test_legal.py`.
4. **Exhaustive, mechanically ordered.** "Every skill in the library," sorted
   alphabetically — never a curated "best of" subset. Curation is what gives a
   facts compilation a thin copyright (*Feist*; *Key Publications* vs *BellSouth*).

## Precedent

- [GCS](https://github.com/richardwilkes/gcs) has shipped exactly this data shape
  (name/attribute/difficulty/page, ~no prose) for 20 years under the same
  self-asserted permission, and SJG links it from their own
  [utilities page](https://www.sjgames.com/gurps/utilities/).
- The one forced-down fan tool (the Roll20 community sheet) was pulled for
  embedding actual rules text and tables, and was restored once they were
  stripped. The line is text, not facts.
- The policy's "no mobile apps" clause doesn't touch a Discord bot: SJG staff
  (Kromm, forums t=123635) define the split as computer-executable aids (allowed)
  vs mobile-OS apps (not). A bot runs server-side on Linux; reading its output on
  a phone doesn't change that.
- Facts themselves aren't copyrightable (17 U.S.C. §102(b), *Feist v. Rural*;
  game-side, *DaVinci v. Ziko*, *Allen v. Academic Games*). The protectable part
  is the description prose, which the bot omits.

Trademark is separate from copyright: the bot says it's "for GURPS" (nominative
use), isn't named "GURPS-anything," and never uses SJG logos or trade dress.

## Sources

- <https://www.sjgames.com/general/online_policy.html> — the governing policy
- <https://forums.sjgames.com/showthread.php?t=123635> — Kromm on computer aids vs mobile apps
- <https://github.com/richardwilkes/gcs> + <https://github.com/richardwilkes/gcs_master_library> — the 20-year precedent
- <https://www.sjgames.com/gurps/utilities/> — SJG linking GCS/GCA
- <https://app.roll20.net/forum/post/12673552/> — the Roll20 sheet takedown + restoration
- <https://supreme.justia.com/cases/federal/us/499/340/> — Feist v. Rural
- <https://law.justia.com/cases/federal/appellate-courts/F3/126/977/497929/> — ADA v. Delta Dental
- BellSouth v. Donnelley, 999 F.2d 1436 (11th Cir. en banc) — comprehensive lists have no selection originality
- <https://www.govinfo.gov/content/pkg/USCOURTS-txsd-4_13-cv-03415/pdf/USCOURTS-txsd-4_13-cv-03415-0.pdf> — DaVinci v. Ziko
- <https://cyber.harvard.edu/metaschool/fisher/domain/tmcases/newkids.htm> — nominative fair use
- <https://gsllcblog.com/2019/08/12/part1statblocks/> — RPG stat-block analysis by an IP attorney
