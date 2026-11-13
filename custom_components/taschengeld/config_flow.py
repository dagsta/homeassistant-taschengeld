"""Config flow for the Taschengeld integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import random
from typing import Any

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_URL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)
import voluptuous as vol

from .api import (
    TaschengeldAuthError,
    TaschengeldClient,
    TaschengeldConnectionError,
    TaschengeldForbiddenError,
    TaschengeldRetryLaterError,
    normalize_base_url,
)
from .const import (
    CONF_SCAN_INTERVAL_HOURS,
    CONF_SCAN_START,
    CONF_START_OFFSET,
    CONF_TOKEN,
    DEFAULT_INTERVAL_HOURS,
    DEFAULT_START_TIME,
    DEFAULT_URL,
    DOMAIN,
    INTERVAL_CHOICES,
    MAX_START_OFFSET,
)
from .coordinator import TaschengeldConfigEntry

_LOGGER = logging.getLogger(__name__)

TOKEN_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="off")
)


def _clean_token(value: str) -> str | None:
    """Strip whitespace and an accidental ``Bearer`` prefix; reject bad input."""
    token = value.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token or any(ch.isspace() or not ch.isprintable() for ch in token):
        return None
    return token


class TaschengeldConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup, reauth and reconfiguration of a Taschengeld entry."""

    VERSION = 1

    async def _async_validate(self, url: str, token: str) -> str | None:
        """Try one request; return an error key or ``None`` on success."""
        client = TaschengeldClient(async_get_clientsession(self.hass), url, token)
        try:
            await client.async_get_balances()
        except TaschengeldAuthError:
            return "invalid_auth"
        except TaschengeldForbiddenError:
            return "no_permission"
        except TaschengeldRetryLaterError as err:
            return "rate_limited" if err.status == 429 else "service_unavailable"
        except TaschengeldConnectionError:
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error while validating the connection")
            return "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for address and token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = normalize_base_url(user_input[CONF_URL])
            token = _clean_token(user_input[CONF_TOKEN])
            if url is None:
                errors[CONF_URL] = "invalid_url"
            elif token is None:
                errors[CONF_TOKEN] = "invalid_auth"
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                if error := await self._async_validate(url, token):
                    errors["base"] = error
                else:
                    return self.async_create_entry(
                        title="Taschengeld",
                        data={
                            CONF_URL: url,
                            CONF_TOKEN: token,
                            CONF_START_OFFSET: random.randint(0, MAX_START_OFFSET),
                        },
                    )

        defaults = user_input or {CONF_URL: DEFAULT_URL}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=defaults.get(CONF_URL, DEFAULT_URL)): str,
                    vol.Required(CONF_TOKEN): TOKEN_SELECTOR,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after a 401/403."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new token."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            token = _clean_token(user_input[CONF_TOKEN])
            if token is None:
                errors[CONF_TOKEN] = "invalid_auth"
            elif error := await self._async_validate(entry.data[CONF_URL], token):
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: token}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): TOKEN_SELECTOR}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: TaschengeldConfigEntry) -> OptionsFlowWithReload:
        """Return the options flow."""
        return TaschengeldOptionsFlow()


class TaschengeldOptionsFlow(OptionsFlowWithReload):
    """Let the user choose the polling interval and the daily start time."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the schedule form."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL_HOURS: int(user_input[CONF_SCAN_INTERVAL_HOURS]),
                    CONF_SCAN_START: user_input[CONF_SCAN_START],
                }
            )
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL_HOURS,
                        default=str(
                            options.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_INTERVAL_HOURS)
                        ),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[str(h) for h in INTERVAL_CHOICES],
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key=CONF_SCAN_INTERVAL_HOURS,
                        )
                    ),
                    vol.Required(
                        CONF_SCAN_START,
                        default=options.get(CONF_SCAN_START, DEFAULT_START_TIME),
                    ): TimeSelector(),
                }
            ),
        )
