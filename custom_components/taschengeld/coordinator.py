"""Data update coordinator for the Taschengeld integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    BalancesData,
    TaschengeldAuthError,
    TaschengeldClient,
    TaschengeldConnectionError,
    TaschengeldForbiddenError,
    TaschengeldRetryLaterError,
)
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type TaschengeldConfigEntry = ConfigEntry[TaschengeldCoordinator]


class TaschengeldCoordinator(DataUpdateCoordinator[BalancesData]):
    """Fetch all balances with a single request."""

    config_entry: TaschengeldConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: TaschengeldConfigEntry,
        client: TaschengeldClient,
    ) -> None:
        """Initialize the coordinator."""
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self.client = client

    async def _async_update_data(self) -> BalancesData:
        """Fetch data, translating client errors into coordinator errors."""
        assert self.update_interval is not None
        interval = self.update_interval.total_seconds()
        try:
            return await self.client.async_get_balances()
        except TaschengeldAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except TaschengeldForbiddenError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="no_permission"
            ) from err
        except TaschengeldRetryLaterError as err:
            # Honour Retry-After, but never retry sooner than the normal
            # interval; without the header the normal interval applies anyway.
            retry_after = (
                max(err.retry_after, interval) if err.retry_after is not None else None
            )
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key=(
                    "rate_limited" if err.status == 429 else "service_unavailable"
                ),
                retry_after=retry_after,
            ) from err
        except TaschengeldConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
