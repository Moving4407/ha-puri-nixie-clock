"""Constants for the Puri Nixie Clock integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "puri_nixie_clock"

DEFAULT_PORT: Final = 88
REQUEST_TIMEOUT: Final = 5
# The clock now and then answers with its HTML page instead of JSON; try again.
MAX_ATTEMPTS: Final = 4
RETRY_DELAY: Final = 0.25

DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 15
MAX_SCAN_INTERVAL: Final = 300

# Local API parameters used by the integration (SPEC.md section 3).
PARAM_BRIGHTNESS_DAY: Final = "brightnessday"
PARAM_BRIGHTNESS_NIGHT: Final = "brightnessnight"
PARAM_DISPLAYED_VALUE: Final = "currentdisplayedvalue"
PARAM_RSSI: Final = "rssi"
PARAM_PRODUCT_ID: Final = "productid"
PARAM_SERIAL_NUMBER: Final = "serialnumber"

# `productid` -> device model.
PRODUCT_MODELS: Final = {6: "Puri Nixie Clock (4-tube)", 15: "Puri Nixie Clock (6-tube)"}

MANUFACTURER: Final = "Dalibor Farny"

# Brightness steps: translation key -> API value. 1 turns the tubes fully dark.
BRIGHTNESS_OFF: Final = 1
BRIGHTNESS_OPTIONS: Final = {
    "off": 1,
    "very_low": 6,
    "low": 71,
    "medium": 126,
    "high": 201,
    "full": 256,
}
BRIGHTNESS_STEPS: Final = tuple(BRIGHTNESS_OPTIONS.values())

# Options (SPEC.md sections 4.3, 4.4 and 4.7). Brightness options hold a key of BRIGHTNESS_OPTIONS.
CONF_DISPLAY_ON_DAY: Final = "display_on_day"
CONF_DISPLAY_ON_NIGHT: Final = "display_on_night"
CONF_MIN_VALUE: Final = "min_value"
CONF_MAX_VALUE: Final = "max_value"
CONF_MIN_ELEVATION: Final = "min_elevation"
CONF_MAX_ELEVATION: Final = "max_elevation"

DEFAULT_DISPLAY_ON_DAY: Final = "full"
DEFAULT_DISPLAY_ON_NIGHT: Final = "medium"
DEFAULT_MIN_VALUE: Final = "very_low"
DEFAULT_MAX_VALUE: Final = "full"
DEFAULT_MIN_ELEVATION: Final = -6.0
DEFAULT_MAX_ELEVATION: Final = 10.0

AUTO_BRIGHTNESS_INTERVAL: Final = 1800  # seconds; at most one adjustment round per interval
SUN_ENTITY_ID: Final = "sun.sun"
