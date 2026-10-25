# CLAUDE.md — ha-puri-nixie-clock

Home Assistant custom integration (HACS) for the Puri Nixie Clock by Dalibor Farny, talking to the
clock over its **Local HTTP API** (port 88, no authentication, no cloud).

The full specification is in [`SPEC.md`](SPEC.md). Read it completely before writing code. Build in
the phases of SPEC.md section 10, in order, and stop at each gate.

## Working agreements

- **The clock is a real device on the user's network.** It is a physical Nixie clock at a private LAN
  address that the user gives you; never hard-code that address in the integration, tests or docs.
- **Reads first, writes only when told.** Phase 0 starts read-only. Anything that changes a setting on
  the real clock needs the user's go-ahead for that step, and you restore the original value
  afterwards.
- **Never write** `reset`, `homekitreset`, `serialnumber`, `rtccalibration` or `nmstr` on the real
  clock, not even as a test.
- **Do not invent API behaviour.** Everything in SPEC.md marked `VERIFY` is an assumption from the
  vendor documentation. Confirm it on the real clock in phase 0. If reality differs, stop and report;
  do not silently adapt the design.
- **Ask before:** pushing to GitHub, creating a repository or a release, restarting Home Assistant,
  copying files into the user's Home Assistant, or choosing anything listed in SPEC.md section 9.
- **No scope creep.** Features outside SPEC.md section 1 are not built; propose them instead.
- No credentials are needed anywhere in this project. If you find yourself needing one, stop and ask.

## Stack and conventions

- Python, fully type-hinted, `from __future__ import annotations`, async only (no blocking I/O in the
  event loop). Use the Home Assistant shared `aiohttp` session; add no third-party runtime
  dependencies (`requirements: []`).
- Follow current Home Assistant integration patterns: `ConfigEntry.runtime_data`, `DataUpdateCoordinator`,
  `translation_key` for entity names and option labels, `has_entity_name = True`, `unique_id` per entity.
- Code, comments, commit messages and the README are in **English**. User-facing strings exist in
  English (`strings.json`, `translations/en.json`) **and Dutch** (`translations/nl.json`).
- Domain: `puri_nixie_clock`. Integration folder: `custom_components/puri_nixie_clock/`.
- Small commits, one logical change each, imperative present tense ("Add display switch").

## Commands

Set these up in phase 1 and keep this section current:

```bash
uv venv --python 3.14 .venv && source .venv/bin/activate   # HA 2026.10 needs Python >= 3.14.2
uv pip install -r requirements_test.txt
ruff check . && ruff format --check .
pytest -q
```

CI additionally runs `hassfest` and the HACS validation action (SPEC.md section 8).

## Definition of done (every phase)

1. `ruff check`, `ruff format --check` and `pytest` pass locally.
2. New behaviour has tests; fixed bugs have a regression test.
3. The gate of the phase in SPEC.md section 10 is met and you have told the user what was verified
   and how.
4. SPEC.md and this file still match reality. Update them in the same commit as the change.
