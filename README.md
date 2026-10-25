# Puri Nixie Clock for Home Assistant

A [HACS](https://hacs.xyz) custom integration for the Puri Nixie Clock by Dalibor Farny. It talks to the
clock over its **Local HTTP API**: no cloud, no account, no authentication.

This is an unofficial integration and is not affiliated with Dalibor Farny.

## What you get

- A **display switch** to turn the tubes on and off. It remembers the brightness from before it was
  switched off.
- **Automatic brightness** that follows the sun: dim at night, bright in the day.
- **Brightness selects** for the day and the night value, with the six steps the clock knows.
- Two sensors: the number now shown on the tubes and the Wi-Fi signal.

Switching the clock off at night is left to a Home Assistant automation (example below).

## Requirements

- Home Assistant 2026.10.0 or newer.
- The [Sun](https://www.home-assistant.io/integrations/sun/) integration (part of the default Home
  Assistant setup). It is a hard dependency: this integration does not load without it.
- A Puri Nixie Clock (4-tube or 6-tube) on your network, with a fixed IP address if you can.

## Installation with HACS

1. In HACS, open the menu (three dots) and choose **Custom repositories**.
2. Add `https://github.com/Moving4407/ha-puri-nixie-clock` with the category **Integration**.
3. Install **Puri Nixie Clock** and restart Home Assistant.
4. Go to **Settings, Devices & services, Add integration**, search for **Puri Nixie Clock** and enter the
   IP address of the clock (port 88).

If the clock gets a new IP address, use **Reconfigure** on the integration. It checks that it is still the
same clock.

## Entities

| Entity | Type | Notes |
| --- | --- | --- |
| Display | switch | On unless both brightness values are "off" |
| Automatic brightness | switch | Configuration; off by default |
| Brightness (day) | select | Off, very low, low, medium, high, full |
| Brightness (night) | select | Same steps |
| Displayed value | sensor | What the tubes show now, for example 1125 for 11:25 |
| Wi-Fi signal | sensor | Diagnostic, in dBm |

The clock has two brightness values, day and night, and the integration cannot tell which one the clock
is using. Choosing "off" for only one of them does not switch the display off.

### Display switch

- **Off** remembers the current day and night brightness and sets both to "off", which makes the tubes
  fully dark.
- **On** restores the remembered brightness. If automatic brightness is on and the sun's elevation is
  known, it uses the automatic brightness instead. With nothing remembered it uses the defaults from the
  options (day full, night medium).

### Automatic brightness

While the switch is on, the integration sets the brightness from the elevation of the sun (`sun.sun`),
at most once every 30 minutes, and once when you switch it on. It writes the same value to day and night.

- At or below the minimum elevation (default -6 degrees) it uses the darkest step (default "very low").
- At or above the maximum elevation (default 10 degrees) it uses the brightest step (default "full").
- In between it rises evenly and rounds to the nearest step.

It never switches the display off, does nothing while the display is off or the elevation is unavailable,
and a brightness you choose by hand is replaced at the next adjustment. Nothing is written to the clock
when Home Assistant starts.

All of this is configurable in the integration options: polling interval (15 to 300 seconds), the
brightness used when switching on, the darkest and brightest step, and the two elevations.

### Switch the clock off at night

```yaml
automation:
  - alias: Nixie clock off at night
    triggers:
      - trigger: time
        at: "23:00:00"
    actions:
      - action: switch.turn_off
        target:
          entity_id: switch.puri_nixie_clock_display

  - alias: Nixie clock on in the morning
    triggers:
      - trigger: time
        at: "07:00:00"
    actions:
      - action: switch.turn_on
        target:
          entity_id: switch.puri_nixie_clock_display
```

## Good to know

- **The clock's API is quirky.** About one request in five is answered with the clock's web page instead
  of data. The integration retries these, so you will not notice, but the logs of the clock itself may
  look odd. The clock also reports a written value one lower than the value it stores, so the integration
  always reads a setting back after changing it.
- **Identity.** This clock does not report its MAC address, so the integration identifies it by its factory
  serial number. That number is not globally unique, which is fine for the clocks on one network.
- **Only brightness is written.** The integration never changes any other setting of the clock.

## Security

The Local API has no authentication: anyone on your network can control the clock. Use it on a trusted
network only and never forward port 88 to the internet.

## Development

```bash
uv venv --python 3.14 .venv && source .venv/bin/activate   # Home Assistant 2026.10 needs Python >= 3.14.2
uv pip install -r requirements_test.txt
ruff check . && ruff format --check .
pytest -q
```

The behaviour is specified in [`SPEC.md`](SPEC.md). What was found on the real clock is in
[`docs/clock-probe-report.md`](docs/clock-probe-report.md).

## Licence

[MIT](LICENSE).
