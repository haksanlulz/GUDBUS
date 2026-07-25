# tests/fixtures/gcs_mini — synthetic mini catalog

A hand-authored, **committed** stand-in for the vendored GCS master library, so
the copyright-wall invariants run on every checkout instead of skipping when
`gurps_bot/data/gcs_library/` is absent (that directory is gitignored and
reproduced by `tools/sync_gcs_library.py`, so on a fresh clone or in CI the
deep wall scans were unenforced and green).

**Every name, number, page cite and sentence in these files is invented.** No
Steve Jackson Games content is reproduced here — the page cites use a fake
`SYN` book code, and the prose strings exist only to be *dropped* by the loader.
Do not paste real catalog rows into this directory.

Layout mirrors the real snapshot the loader walks
(`gurps_bot/gcs/library.py::load_library`): `<root>/<Book>/<Book> <Category>.<ext>`,
where the **file extension is the category discriminator** (`.skl` skills +
techniques, `.adq` traits, `.spl` spells, `.eqp` equipment) and each file is a
JSON object with a `rows` list.

Deliberate shapes covered (each one is a rung the wall would otherwise miss):

| Shape | Where |
|---|---|
| `@token@` in a name | `Bind Servitor (@Servitor@)` (skl), `Summon @Element@ Wisp` (spl) |
| `@token@` specialization | `Duskspeech` (skl) |
| `@token@` in a `default` base skill | `Rote Feint` (skl) |
| `@token@` cost/weight expression | `Cut Gemstone` (eqp) |
| `@token@` on BOTH raw and resolved value | `Tuned Resonator` (eqp) |
| over-long name (>100 chars) | `A Rambling Upstream Row…` (skl) |
| prose fields the wall must drop | `local_notes` / `reference_highlight` / `weapons[].usage_notes` / `modifiers[].local_notes` throughout |
| prose-shaped spell facts (`;`, long, multi-word) | `Mend the Weeping Seam` (spl) |
| self-control rows | `Hoardsickness` (cr 12), `Nightdread` (cr 6) (adq) |
| multi-college spell | `Lantern of Quiet Hours` (spl) |
| string (not list) college | `Mend the Weeping Seam` (spl) |
| grouping container (never emitted) | `Bladework Techniques` (skl) |
| meta-trait container that IS emitted, then recursed | `Frame of Brass` (adq) |
| placeholder trait (filtered) | `Assorted Oddments` (adq) |
| leveled trait cost | `Stonehide` (adq) |

Consumed by `tests/test_wall_fixture.py`. If you add a row, add the assertion
that proves the loader actually reads it — a fixture the loader silently
ignores is a fail-open rung, which is the exact failure this fixture exists to
kill.
