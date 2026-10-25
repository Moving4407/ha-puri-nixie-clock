"""Config flow for the Puri Nixie Clock."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import CannotConnect, InvalidResponse, ParameterNotSupported, PuriClockClient
from .const import (
    BRIGHTNESS_OPTIONS,
    CONF_DISPLAY_ON_DAY,
    CONF_DISPLAY_ON_NIGHT,
    CONF_MAX_ELEVATION,
    CONF_MAX_VALUE,
    CONF_MIN_ELEVATION,
    CONF_MIN_VALUE,
    DEFAULT_DISPLAY_ON_DAY,
    DEFAULT_DISPLAY_ON_NIGHT,
    DEFAULT_MAX_ELEVATION,
    DEFAULT_MAX_VALUE,
    DEFAULT_MIN_ELEVATION,
    DEFAULT_MIN_VALUE,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    PARAM_PRODUCT_ID,
    PARAM_SERIAL_NUMBER,
    PRODUCT_MODELS,
)

CONF_PRODUCT_ID = "product_id"


class UnsupportedModel(Exception):
    """The clock is not a Puri 4-tube or 6-tube."""


async def _async_identify(hass, host: str, port: int) -> tuple[str, int]:
    """Read the serial number and product id of the clock at host:port."""
    client = PuriClockClient(async_get_clientsession(hass), host, port)
    product_id = await client.get(PARAM_PRODUCT_ID)
    serial = await client.get(PARAM_SERIAL_NUMBER)
    if product_id not in PRODUCT_MODELS:
        raise UnsupportedModel
    return str(serial), product_id


def _connection_schema(host: str = "", port: int = DEFAULT_PORT) -> probatio.Schema:
    return probatio.Schema(
        {
            probatio.Required(CONF_HOST, default=host): str,
            probatio.Required(CONF_PORT, default=port): cv.port,
        }
    )


class PuriConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Puri Nixie Clock."""

    VERSION = 1

    async def _async_validate(
        self, user_input: dict[str, Any]
    ) -> tuple[tuple[str, int] | None, dict[str, str]]:
        """Identify the clock; return its identity or an error key."""
        try:
            return await _async_identify(
                self.hass, user_input[CONF_HOST].strip(), user_input[CONF_PORT]
            ), {}
        except CannotConnect:
            return None, {"base": "cannot_connect"}
        except InvalidResponse, ParameterNotSupported:
            return None, {"base": "invalid_response"}
        except UnsupportedModel:
            return None, {"base": "unsupported_model"}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the address of the clock."""
        errors: dict[str, str] = {}
        if user_input is not None:
            identity, errors = await self._async_validate(user_input)
            if identity:
                serial, product_id = identity
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Puri Nixie Clock",
                    data={
                        CONF_HOST: user_input[CONF_HOST].strip(),
                        CONF_PORT: user_input[CONF_PORT],
                        CONF_PRODUCT_ID: product_id,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(_connection_schema(), user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address of the clock, for example after a new DHCP lease."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            identity, errors = await self._async_validate(user_input)
            if identity:
                serial, product_id = identity
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_HOST: user_input[CONF_HOST].strip(),
                        CONF_PORT: user_input[CONF_PORT],
                        CONF_PRODUCT_ID: product_id,
                    },
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(entry.data[CONF_HOST], entry.data[CONF_PORT]),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PuriOptionsFlow:
        """Return the options flow."""
        return PuriOptionsFlow()


class PuriOptionsFlow(OptionsFlowWithReload):
    """Options of a clock: polling interval, display-on defaults, automatic brightness."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if (
                BRIGHTNESS_OPTIONS[user_input[CONF_MIN_VALUE]]
                > BRIGHTNESS_OPTIONS[user_input[CONF_MAX_VALUE]]
            ):
                errors[CONF_MIN_VALUE] = "value_range"
            if user_input[CONF_MIN_ELEVATION] >= user_input[CONF_MAX_ELEVATION]:
                errors[CONF_MIN_ELEVATION] = "elevation_range"
            if not errors:
                return self.async_create_entry(data=user_input)
        current = {**_OPTION_DEFAULTS, **self.config_entry.options, **(user_input or {})}
        return self.async_show_form(
            step_id="init", data_schema=_options_schema(current), errors=errors
        )


_OPTION_DEFAULTS: dict[str, Any] = {
    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    CONF_DISPLAY_ON_DAY: DEFAULT_DISPLAY_ON_DAY,
    CONF_DISPLAY_ON_NIGHT: DEFAULT_DISPLAY_ON_NIGHT,
    CONF_MIN_VALUE: DEFAULT_MIN_VALUE,
    CONF_MAX_VALUE: DEFAULT_MAX_VALUE,
    CONF_MIN_ELEVATION: DEFAULT_MIN_ELEVATION,
    CONF_MAX_ELEVATION: DEFAULT_MAX_ELEVATION,
}

# The display is never switched on at "off" (value 1): that is what the switch is for.
_ON_STEPS = [key for key in BRIGHTNESS_OPTIONS if key != "off"]


def _step_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=_ON_STEPS, mode=SelectSelectorMode.DROPDOWN, translation_key="brightness_step"
        )
    )


def _elevation_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(min=-90, max=90, step=0.5, mode=NumberSelectorMode.BOX)
    )


def _options_schema(current: dict[str, Any]) -> probatio.Schema:
    return probatio.Schema(
        {
            probatio.Required(CONF_SCAN_INTERVAL, default=current[CONF_SCAN_INTERVAL]): (
                probatio.All(int, probatio.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL))
            ),
            probatio.Required(CONF_DISPLAY_ON_DAY, default=current[CONF_DISPLAY_ON_DAY]): (
                _step_selector()
            ),
            probatio.Required(CONF_DISPLAY_ON_NIGHT, default=current[CONF_DISPLAY_ON_NIGHT]): (
                _step_selector()
            ),
            probatio.Required(CONF_MIN_VALUE, default=current[CONF_MIN_VALUE]): _step_selector(),
            probatio.Required(CONF_MAX_VALUE, default=current[CONF_MAX_VALUE]): _step_selector(),
            probatio.Required(CONF_MIN_ELEVATION, default=current[CONF_MIN_ELEVATION]): (
                _elevation_selector()
            ),
            probatio.Required(CONF_MAX_ELEVATION, default=current[CONF_MAX_ELEVATION]): (
                _elevation_selector()
            ),
        }
    )
