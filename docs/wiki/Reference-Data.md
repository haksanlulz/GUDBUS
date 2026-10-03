# Reference data

The `/skill`, `/trait`, `/spell`, `/technique`, and `/item` lookups read an
in-memory **facts-only** catalog built from the upstream
[`richardwilkes/gcs_master_library`](https://github.com/richardwilkes/gcs_master_library)
(the GURPS Character Sheet master library, MPL-2.0). It is not in this repository:
a snapshot pinned to a specific commit is fetched at build time, and the Docker
image carries it with its upstream LICENSE. Sync a local copy with:

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
