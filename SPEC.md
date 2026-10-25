# SPEC — Home Assistant integration for the Puri Nixie Clock

Status: draft 2, 25 October 2026 (updated after phase 0, see `docs/clock-probe-report.md`).
Companion file: `CLAUDE.md` (working agreements, conventions).
Sources: vendor docs [Cloud API](https://docs.daliborfarny.com/v2/en/puri-nixie-clock/cloud-api) and
[Local API](https://docs.daliborfarny.com/v2/en/puri-nixie-clock/local-api). Where the vendor docs and the
real clock differ, this spec follows the clock (section 3).

## 0. How to read this spec

- **MUST / MUST NOT / SHOULD** are used in their usual sense.
- **VERIFY** = assumption taken from the vendor documentation, to be confirmed on the real clock. All
  VERIFY items of draft 1 are resolved (phase 0). New ones get the same marker.
- **ASK** = a decision that belongs to the user (section 9). Do not guess.
- Build in the phases of section 10. Each phase ends with a gate.

## 1. Goal and scope

Goal: make the Puri Nixie Clock a first-class device in Home Assistant, controlled locally, with a
switch to turn the display on and off and a brightness that follows the sun.

In scope for version 0.1.0:

- Display on/off switch, brightness day and night.
- Automatic brightness based on solar elevation (section 4.4).
- Two sensors: the value on the tubes and the wifi signal.
- Config flow with reconfigure and options, English and Dutch strings.

Out of scope for 0.1.0 (do not build, propose later):

- Services to show text or start a countdown (`customdata`, `customdatatimeout`, `startcountdown`,
  `switchtotimemode`), buttons, and entities for the other clock settings (leading zero, DST, timezone,
  date display, transition, cleaning interval, system LED, colon mode).
- Entities for `format`, `firmware` and `freememory`: not needed. `firmware` is not readable as JSON;
  scraping the HTML page is not done.
- Cloud API and account login.
- Night schedule (`nmstr`: write-only, undocumented format). Switching off at night is done by a Home
  Assistant automation on the display switch.
- RTC calibration, HomeKit reset, `connectivitymode`, `time`, OTA.
- Network discovery (the docs describe none).
- A `light` entity (maybe later; see section 9).

## 2. Environment facts

- Clock: a Puri Nixie Clock on the LAN, Local API on port **88**. Phase 0: `productid` 6, a **4-tube**
  clock, firmware 1.40. The address is private to the user's network: take it from the user, never
  commit it.
- Target Home Assistant: **2026.10.3** (the user's current version). Use `2026.10.0` as the minimum
  in `hacs.json` unless the user chooses otherwise (section 9).
- The `sun` integration (`sun.sun`, attribute `elevation` in degrees) is available on the user's
  Home Assistant.
- The user's location is in the Netherlands (about 51° N). Solar elevation there peaks at roughly 15°
  at winter noon and roughly 62° at summer noon. This is why section 4.4 reaches full brightness at 10°.

## 3. Local API reference (as verified on the clock)

Base URL: `http://<host>:<port>/v1/<parameter>`, port default 88, no authentication.

| Method | Meaning |
| --- | --- |
| `GET` | read current value |
| `POST` | write |

Success: `{"ok": true, "status": 200, "value": <int>}`.
Errors: `{"ok": false, "status": <code>, "message": "..."}`. A 404 carries the message
"Setting not found or returned 0".

Verified behaviour (phase 0):

- **The clock answers about one request in five with its HTML configuration page** (HTTP 200, not JSON), for
  any parameter. Such a request was not handled. The client MUST treat a non-JSON answer as transient and
  try again (4 attempts, 0.25 s apart; section 4.1). In a measurement with the real client, 15 polls of four
  reads all succeeded with 13 retries in 73 requests.
- **Writes are sent as JSON** `{"value": n}` with `Content-Type: application/json`. A plain-integer body
  worked for most values, and a plain `1` once got the HTML page; whether that was the glitch above is not
  proven. JSON is known to work for every value tried.
- **The POST response is not the new value.** It is the register value, the written value minus 1
  (wrote 126, response 125; wrote 1, response 0). The next `GET` returns exactly the written value.
  The client therefore MUST read the parameter back after every write and use that value as state.
- Reads that return a real 404 every time: `firmware`, `macaddr`, `customdatatimeout`, `time`,
  `hkconnectionsnumber`, `slotmachinemode`. Message "Setting not found or returned 0"; likely a value of 0
  or a non-integer. `format` and `freememory` read fine.
- Response times are 17 to 98 ms (average 34 ms).

Brightness uses six discrete steps only: `1` off, `6` very low, `71` low, `126` medium, `201` high,
`256` full. This applies to `brightnessday` and `brightnessnight`. Value `1` makes the tubes fully dark
(confirmed by eye on the clock).

### Parameters used in 0.1.0

| Parameter | Access | Values |
| --- | --- | --- |
| `brightnessday` | RW | 1, 6, 71, 126, 201, 256 |
| `brightnessnight` | RW | 1, 6, 71, 126, 201, 256 |
| `currentdisplayedvalue` | R | number now shown on the tubes (colons excluded) |
| `rssi` | R | wifi signal strength in dBm (a negative number) |
| `productid` | R | 6 = 4-tube, 15 = 6-tube |
| `serialnumber` | R | 1 to 99999, factory-set; used as the device identity. MUST NOT be written |

## 4. Behaviour

### 4.1 API client (`api.py`)

- Async client on the Home Assistant shared `aiohttp` session. No new dependencies.
- One `asyncio.Lock`: requests go one at a time. Timeout 5 s per request.
- `get(param) -> int`. `set(param, value) -> int` posts `{"value": value}` as JSON, then reads the
  parameter back and returns the read value (section 3).
- Exceptions: `CannotConnect` (network/timeout), `InvalidResponse` (not JSON after all attempts, or `ok`
  false), `ParameterNotSupported` (404 or 405). Callers decide what to do with each.
- Retries inside the client: a non-JSON answer is retried up to 4 attempts in total, 0.25 s apart, for reads
  and writes (a request answered with HTML was not handled); a timeout on a read is retried once. Nothing
  else is retried.

### 4.2 Coordinator (`coordinator.py`)

One `DataUpdateCoordinator` subclass, one cadence: every 30 s (option, 15 to 300 s), reading
`brightnessday`, `brightnessnight`, `currentdisplayedvalue` and `rssi`, one request at a time.

- After a write the client has already read the value back; the coordinator stores it directly.
- Any failed read: `UpdateFailed` (entities become unavailable).
- Log once when the clock becomes unreachable and once when it returns (not every poll).

### 4.3 Display switch

State is derived: **on** if `brightnessday > 1` or `brightnessnight > 1`; **off** only if both equal 1.

- `turn_off`: if currently on, remember the current `(day, night)` as `last_on` (persist, section 4.9),
  then write `brightnessday = 1` and `brightnessnight = 1`.
- `turn_on`: pick the target for both values:
  1. if automatic brightness is on and a sun elevation is available: the automatic target (4.4)
     for both;
  2. else the remembered `last_on` `(day, night)`;
  3. else the option defaults, day 256 and night 126.
  Write only the values that differ from the current ones.
- Setting only one of the two brightness selects to "off" (value 1) does not turn the switch off.

### 4.4 Automatic brightness

A switch entity per clock, **default off**. While on, the integration adjusts brightness to the sun at
most once every 30 minutes.

```python
STEPS = (1, 6, 71, 126, 201, 256)


def auto_target(elev, lo_elev=-6.0, hi_elev=10.0, lo_val=6, hi_val=256):
    f = min(1.0, max(0.0, (elev - lo_elev) / (hi_elev - lo_elev)))
    raw = lo_val + f * (hi_val - lo_val)
    # nearest step; on a tie take the lower step
    return min((s for s in STEPS if lo_val <= s <= hi_val), key=lambda s: (abs(s - raw), s))
```

Reference results with the defaults (use as unit test cases): -6° or lower gives 6, -2° gives 71
(raw 68.5), 0° gives 126 (raw 99.75), 2° gives 126 (raw 131), 6° gives 201 (raw 193.5), 10° or higher
gives 256.

Rules:

- The floor is step 6 (very low): automatic brightness never switches the display off. Switching off is
  the display switch, for example from a user automation at night.
- Source: `state.attributes["elevation"]` of `sun.sun`. The `sun` integration is a hard dependency
  (`dependencies` in `manifest.json`), so Home Assistant loads it first and the integration does not
  load without it. If the state is unavailable or not a number, skip the tick and write nothing.
- Schedule with `async_track_time_interval(hass, tick, timedelta(minutes=30))`. Also run once when
  the user turns automatic brightness on and when the display switch turns on. No other triggers.
- On a tick: if the display is off (both values 1), do nothing. Otherwise compute the target and write
  `brightnessday` and `brightnessnight` only where they differ from the current value (the same value for
  both, because the integration cannot tell which one the clock is using).
- A manual brightness choice is overwritten at the next tick while automatic brightness is on.
- Options: `min_value` (step, default 6), `max_value` (step, default 256), `min_elevation` (default -6),
  `max_elevation` (default 10). Validate `min_elevation < max_elevation` and `min_value <= max_value`.
  `min_value` is one of 6, 71, 126, 201, 256 (never 1). Brightness options are stored as the step keys
  of section 4.5 (`very_low` ... `full`), not as numbers; the display-on defaults use the same keys.
- Every write goes through one controller that holds a lock, so a switch, a select and a timer tick
  cannot interleave. A write that the clock answers with a different value than written raises an error
  and the entity shows the value the clock reports.
- The elevation defaults are a proposal; see section 9.

### 4.5 Entities

One device per clock. `unique_id` of an entity = `<serial>_<key>`. Device: identifiers
`{(DOMAIN, <serial>)}` (no MAC connection, the clock does not expose one), manufacturer `Dalibor Farny`,
model `Puri Nixie Clock (4-tube)` or `(6-tube)` from `productid`, no `sw_version`. Names via
`translation_key`.

| Platform | Key | Source | Category | Notes |
| --- | --- | --- | --- | --- |
| switch | `display` | `brightnessday` + `brightnessnight` | — | section 4.3 |
| switch | `auto_brightness` | local state | config | section 4.4, default off |
| select | `brightness_day` | `brightnessday` | — | options: off, very_low, low, medium, high, full (1, 6, 71, 126, 201, 256) |
| select | `brightness_night` | `brightnessnight` | — | same options |
| sensor | `displayed_value` | `currentdisplayedvalue` | — | what is on the tubes now |
| sensor | `wifi_signal` | `rssi` | diagnostic | dBm, `signal_strength` device class |

Select options use stable string keys mapped to API integers in `const.py`; labels come from translations.

### 4.6 Services

None in 0.1.0 (section 1).

### 4.7 Config flow (`config_flow.py`)

- `user` step: `host` (required), `port` (default 88). Validate by reading `productid` and
  `serialnumber`.
- `unique_id` = the serial number as a string. If it exists: abort `already_configured`.
- Errors: `cannot_connect`, `invalid_response` (including a 404 on `serialnumber`), `unsupported_model`
  (productid not 6 or 15).
- `reconfigure` step: change host/port; abort `wrong_device` if the serial differs. This is how a changed IP
  address is handled.
- Options flow: poll interval, display-on defaults (day 256, night 126), and the automatic brightness
  options of section 4.4.
- No discovery in 0.1.0.
- The serial is a factory-set number from 0 to 99999, not a globally unique id. It is unique among the
  clocks on one network, which is enough here. Mention this in the README.

### 4.8 Errors and edge cases

- Clock unreachable at setup: raise `ConfigEntryNotReady`.
- Write failure: `HomeAssistantError` with a clear message; the entity state is not changed.
- Never write on startup; the integration only reads until a user action or an automatic-brightness tick.
- Never write any parameter other than `brightnessday` and `brightnessnight`.

### 4.9 Storage

`homeassistant.helpers.storage.Store`, key `puri_nixie_clock.<entry_id>`, version 1:
`{"last_on": {"day": int, "night": int}, "auto_enabled": bool}`. Load at setup, save on change.

## 5. Repository layout

```text
ha-puri-nixie-clock/
  CLAUDE.md  SPEC.md  README.md  LICENSE  hacs.json
  requirements_test.txt  pyproject.toml
  custom_components/puri_nixie_clock/
    __init__.py  manifest.json  const.py  api.py  coordinator.py  entity.py
    config_flow.py  switch.py  select.py  sensor.py
    diagnostics.py  icons.json  strings.json
    translations/en.json  translations/nl.json
    brand/icon.png                # required by the HACS validation
  scripts/probe_clock.py          # phase 0, read-only
  scripts/make_icon.py            # generates brand/icon.png
  docs/clock-probe-report.md      # phase 0 output
  tests/                          # pytest, fixtures with recorded clock responses
  .github/workflows/validate.yml  # hacs + hassfest
  .github/workflows/test.yml      # ruff + pytest
```

`manifest.json`:

```json
{
  "domain": "puri_nixie_clock",
  "name": "Puri Nixie Clock",
  "codeowners": ["@Moving4407"],
  "config_flow": true,
  "dependencies": ["sun"],
  "documentation": "https://github.com/Moving4407/ha-puri-nixie-clock",
  "integration_type": "device",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/Moving4407/ha-puri-nixie-clock/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

`hacs.json`: `{"name": "Puri Nixie Clock", "homeassistant": "2026.10.0", "render_readme": true}`.

Versioning: semantic, tag `v0.1.0`, GitHub release per version. `diagnostics.py` must not include the
host address or the serial number.

## 6. Security notes (for the README)

The Local API has no authentication: anyone on the network can control the clock. Use on a trusted
network only and never forward port 88 to the internet.

## 7. Testing

Automated (`pytest` with `pytest-homeassistant-custom-component`; the clock is a mocked HTTP server
fed from fixtures, including the quirks of section 3):

- API client: success, `ok: false`, 404, 405, timeout, malformed JSON, HTML body (retried, then invalid;
  recovery after HTML answers for reads and writes), JSON write body, read-back after write (POST response
  off by one).
- Config flow: success, `cannot_connect`, `invalid_response` (HTML, 404 serial), `unsupported_model`,
  duplicate serial, reconfigure (same device, different device), options validation.
- Coordinator: polling, unavailable and recovery, one log line per outage.
- Display switch: off writes 1/1 and stores `last_on`; on restores `last_on`; defaults without
  `last_on`; automatic target when automatic brightness is on; state derived correctly for (1,1),
  (1,6), (6,1).
- Automatic brightness: `auto_target` reference table of section 4.4, ties, custom options, no write
  when the target equals the current values, no write while the display is off, no write when the
  elevation is unavailable, never more than one write round per 30 minutes (use `freezegun` or HA time
  helpers).
- Static: `ruff check`, `ruff format --check`, `hassfest`, HACS validation.

Manual on the real clock: section 10.

## 8. CI

- `test.yml`: on push and pull request: `ruff`, `pytest`.
- `validate.yml`: `home-assistant/actions/hassfest` and `hacs/action` (category `integration`),
  on push, pull request and a weekly schedule.

## 9. Open decisions (ASK the user)

1. Decided: GitHub owner and `codeowners` handle `Moving4407`, repository `ha-puri-nixie-clock`,
   licence MIT (fully open and reusable). Creating the repository and pushing still needs the user's
   go-ahead in phase 4.
2. Automatic brightness elevations: -6° for the minimum, 10° for the maximum (proposed, not yet
   confirmed). Decided: the floor is 6 (very low).
3. Automatic brightness switch default: off (proposed).
4. Minimum Home Assistant version: 2026.10.0 (proposed).
5. `light` entity instead of, or next to, the display switch: not in 0.1.0 (proposed).
6. Decided: deploy through HACS as a custom repository (no copying into the configuration folder). It
   needs the GitHub repository and a release (phase 4) and a Home Assistant restart, which the user
   must approve. Phase 1 and 2 gates that need the real clock in Home Assistant therefore wait for a
   pre-release published for HACS; ask before publishing it.

## 10. Phases and gates

### Phase 0 — Verify the clock (done)

- [x] Address obtained from the user.
- [x] `scripts/probe_clock.py` written and run (read-only).
- [x] Write tests with go-ahead: no-op write, `brightnessday` round-trip, value 1 (fully dark confirmed).
      Original values restored.
- [x] `customdata` tests dropped: out of scope.
- [x] `docs/clock-probe-report.md` written.

Gate: every VERIFY item is resolved and the user has seen the report. Draft 2 of this spec reflects it.

### Phase 1 — Skeleton, client, config flow, coordinator

- [x] Repository skeleton, `pyproject.toml`, `requirements_test.txt`, ruff config, CI workflows.
- [x] `api.py`, `const.py`, `coordinator.py`, `config_flow.py` with reconfigure, `__init__.py`,
      translations (en, nl), `manifest.json`, `hacs.json`. The options flow has the poll interval only;
      the display-on defaults and automatic brightness options arrive with phase 2.
- [x] Sensors (`displayed_value`, `wifi_signal`).
- [x] Tests for client, config flow and coordinator.
- [ ] CI (`hassfest`, HACS action) has not run yet: it needs the GitHub repository (phase 4).

Gate: tests and ruff pass; the integration loads in a test Home Assistant; against the real clock the
user can add it and sees the sensors (needs the user's approval for deployment, section 9.6).

### Phase 2 — Control

- [x] `switch.py` (`display`, `auto_brightness`), `select.py`.
- [x] Display switch logic (4.3), storage (4.9), automatic brightness (4.4) with options.
- [x] Tests from section 7 for switch and automatic brightness.
- [ ] Gate checks on the real clock in Home Assistant (needs the HACS pre-release, section 9.6).

Gate: on the real clock, turning the display off and on works, the brightness selects work, and
automatic brightness sets a value that matches the current sun elevation (check against `sun.sun`).

### Phase 3 — Diagnostics, polish

- [ ] `diagnostics.py`, `icons.json`.
- [x] README (installation via HACS, entities, automation example for switching off at night, security
      notes, the serial-number identity), written early because the HACS validation requires it.
- [ ] Full test suite, `hassfest` and HACS validation locally or in CI.

Gate: `pytest`, `ruff`, `hassfest` and HACS validation all pass.

### Phase 4 — Release

- [ ] With the user's go-ahead (section 9.1): create the GitHub repository, push, tag `v0.1.0`,
      create the release.
- [ ] The user installs it via HACS as a custom repository, restarts Home Assistant and adds the clock.
- [ ] Manual checks on the real clock: brightness selects round-trip, display switch off and on, network
      interruption recovers by itself, the remembered brightness survives a Home Assistant restart.

Gate: installation through HACS works on the user's Home Assistant and the manual checks pass.

## 11. Risks

| Risk | Mitigation |
| --- | --- |
| Firmware quirks (about 1 in 5 requests answered with HTML, off-by-one POST response) | Retry HTML answers, JSON writes, read back after every write, fixtures that reproduce each quirk |
| Many requests slow the microcontroller | One request at a time, 30 s cadence, 5 s timeout; measured 17 to 98 ms |
| Serial number is not globally unique and the vendor lists it RW | Read only, never written; unique among the user's clocks; documented |
| No authentication on the API | Document it; local use only |
| IP address changes | Serial as unique id, reconfigure step, advise a fixed address |
| Day/night brightness semantics unknown | Automatic brightness writes the same value to both |
