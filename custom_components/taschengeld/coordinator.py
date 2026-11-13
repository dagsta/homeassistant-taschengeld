"""Data update coordinator for the Taschengeld integration."""

from __future__ import annotations

from datetime import datetime, time, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    BalancesData,
    TaschengeldAuthError,
    TaschengeldClient,
    TaschengeldConnectionError,
    TaschengeldForbiddenError,
    TaschengeldRetryLaterError,
)
from .const import (
    CONF_SCAN_INTERVAL_HOURS,
    CONF_SCAN_START,
    DEFAULT_INTERVAL_HOURS,
    DEFAULT_START_TIME,
    DOMAIN,
    INTERVAL_CHOICES,
    MIN_REQUEST_GAP,
    RETRY_DELAY,
)

_LOGGER = logging.getLogger(__name__)

type TaschengeldConfigEntry = ConfigEntry[TaschengeldCoordinator]

# A slot closer than this is skipped, so a timer firing a moment early cannot
# trigger a second request right away.
SLOT_MARGIN = 60  # seconds


def next_slot_delay(
    now: datetime, start: time, interval_hours: int, margin: float = SLOT_MARGIN
) -> float:
    """Return seconds from ``now`` until the next scheduled polling time.

    Polling times are ``start`` plus multiples of ``interval_hours`` (local
    time), repeating every day.
    """
    base = now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
    per_day = 24 // interval_hours
    best: float | None = None
    for k in range(-per_day, 2 * per_day + 1):
        slot = base + timedelta(hours=interval_hours * k)
        delay = (dt_util.as_utc(slot) - dt_util.as_utc(now)).total_seconds()
        if delay > margin and (best is None or delay < best):
            best = delay
    assert best is not None
    return best


class TaschengeldCoordinator(DataUpdateCoordinator[BalancesData]):
    """Fetch all balances with a single request at fixed times of day."""

    config_entry: TaschengeldConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: TaschengeldConfigEntry,
        client: TaschengeldClient,
    ) -> None:
        """Initialize the coordinator."""
        hours = entry.options.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_INTERVAL_HOURS)
        self._hours = int(hours) if hours in INTERVAL_CHOICES else DEFAULT_INTERVAL_HOURS
        self._start = dt_util.parse_time(
            entry.options.get(CONF_SCAN_START, DEFAULT_START_TIME)
        ) or dt_util.parse_time(DEFAULT_START_TIME)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=self._delay_to_slot()),
        )
        self.client = client
        self._last_success: datetime | None = None

    def _delay_to_slot(self) -> float:
        return next_slot_delay(dt_util.now(), self._start, self._hours)

    def _schedule_next_slot(self) -> None:
        self.update_interval = timedelta(seconds=self._delay_to_slot())

    def _schedule_retry(self) -> None:
        """Retry after a failure, but no later than the next regular slot."""
        self.update_interval = timedelta(
            seconds=min(RETRY_DELAY, self._delay_to_slot())
        )

    async def _async_update_data(self) -> BalancesData:
        """Fetch data, translating client errors into coordinator errors."""
        now = dt_util.utcnow()
        if (
            self.data is not None
            and self._last_success is not None
            and (now - self._last_success).total_seconds() < MIN_REQUEST_GAP
        ):
            # Manual refresh or early timer: the service wants >= 30 min between calls.
            self._schedule_next_slot()
            return self.data
        try:
            data = await self.client.async_get_balances()
        except TaschengeldAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except TaschengeldForbiddenError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="no_permission"
            ) from err
        except TaschengeldRetryLaterError as err:
            self._schedule_retry()
            # Honour Retry-After, but never retry sooner than the normal retry delay.
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key=(
                    "rate_limited" if err.status == 429 else "service_unavailable"
                ),
                retry_after=(
                    max(err.retry_after, RETRY_DELAY)
                    if err.retry_after is not None
                    else None
                ),
            ) from err
        except TaschengeldConnectionError as err:
            self._schedule_retry()
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        self._last_success = now
        self._schedule_next_slot()
        return data
