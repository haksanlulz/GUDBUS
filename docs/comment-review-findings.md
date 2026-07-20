# Comment review — findings (2026-07-20)

Prose review of every comment and docstring in `gurps_bot/` and `tools/` (93
files) against one standard: professional, concise, no wasted words, without
cutting anything that conveys real information. Logic was not reviewed.

**Verdict:** the comments are already at standard — terse, rationale-focused
(RAW/GURPS page cites, invariants, ordering constraints, security guards),
with no systemic fluff or redundancy. Two items are worth acting on.

## Act on

### 1. Incorrect comment (not fluff) — `gurps_bot/utils/sanitize.py:3`

```
# keep [ and ] (they form masked-link syntax [text](url)); ( ) alone are inert and
# appear in ~22% of catalog names like "Vow (Chastity)", so leave them intact
```

The code strips `[` and `]` — both are in `_MARKDOWN_CHARS`, which
`sanitize_name` removes — so the comment's verb is inverted. The masked-link
syntax is the reason to *strip* them. Only the verb is wrong; the rest is
correct.

Fix: `keep [ and ]` → `strip [ and ]`.

Priority: this is a security-relevant sanitizer (masked-link injection); the
comment currently misleads a reader into thinking brackets pass through.

### 2. Filler word (marginal) — `gurps_bot/db/timers.py:40`

```
"""remaining/total; the 0.0 branch just guards display math (add_timer enforces total >= 1)."""
```

`just` carries no information — the parenthetical already establishes the
branch is defensive-only. Optional trim: drop `just`.

## Considered and deliberately kept

- `gurps_bot/cogs/characters.py:95` — `extension check is just ux`. Here `just`
  means "only/merely" and carries meaning. Keep.
- Alembic `"""Upgrade schema."""` / `"""Downgrade schema."""` — framework
  boilerplate from `script.py.mako`, not author prose. Leave.
- Comments that looked redundant but carry information the code omits — tuple
  field names + 1-indexing in `ui/embeds.py` and `ui/formatters.py`, expected
  `# ValueError` markers in the golden tools, `mechanics/lifting.py`'s
  "same coefficient... not a copy-paste bug". Correctly kept.

Everything else in `services/`, `db/` (+ migrations), `cogs/`, `gcs/`,
`mechanics/`, `ui/`, `utils/`, the top-level modules, and `tools/` is clean.
