"""Binary sensors for the Taschengeld integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .coordinator import TaschengeldConfigEntry, TaschengeldCoordinator
from .entity import TaschengeldEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TaschengeldConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors; new children are added as they appear."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_children() -> None:
        new = set(coordinator.data.children) - known
        if not new:
            return
        known.update(new)
        async_add_entities(
            AllowanceDueTodaySensor(coordinator, slug) for slug in sorted(new)
        )

    _add_new_children()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_children))


class AllowanceDueTodaySensor(TaschengeldEntity, BinarySensorEntity):
    """On while the next allowance date is today (local time)."""

    _attr_translation_key = "allowance_due_today"

    def __init__(self, coordinator: TaschengeldCoordinator, slug: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, slug, "allowance_due_today")

    @property
    def is_on(self) -> bool | None:
        """Return True if the next allowance is due today."""
        child = self.child
        if child is None or child.next_allowance_date is None:
            return False
        return child.next_allowance_date == dt_util.now().date()

    async def async_added_to_hass(self) -> None:
        """Re-evaluate right after midnight, independent of the polling interval."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._handle_midnight, hour=0, minute=0, second=5
            )
        )

    @callback
    def _handle_midnight(self, _now) -> None:
        self.async_write_ha_state()
