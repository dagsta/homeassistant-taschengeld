"""Sensors for the Taschengeld integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Child
from .const import ATTR_BOOKED_AT, ATTR_NOTE, MAX_NOTE_LENGTH
from .coordinator import TaschengeldConfigEntry
from .entity import TaschengeldEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class TaschengeldSensorDescription(SensorEntityDescription):
    """Describes a Taschengeld sensor."""

    value_fn: Callable[[Child], float | date | None]
    attrs_fn: Callable[[Child], dict[str, Any]] | None = None
    monetary: bool = False


def _last_booking_attrs(child: Child) -> dict[str, Any]:
    note = child.last_note
    if note is not None:
        note = note[:MAX_NOTE_LENGTH]
    return {
        ATTR_NOTE: note,
        ATTR_BOOKED_AT: (
            child.last_booked_at.isoformat() if child.last_booked_at else None
        ),
    }


SENSORS: tuple[TaschengeldSensorDescription, ...] = (
    TaschengeldSensorDescription(
        key="balance",
        translation_key="balance",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        monetary=True,
        value_fn=lambda c: c.balance,
    ),
    TaschengeldSensorDescription(
        key="last_booking",
        translation_key="last_booking",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        monetary=True,
        value_fn=lambda c: c.last_amount,
        attrs_fn=_last_booking_attrs,
    ),
    TaschengeldSensorDescription(
        key="next_allowance_date",
        translation_key="next_allowance_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda c: c.next_allowance_date,
    ),
    TaschengeldSensorDescription(
        key="next_allowance_amount",
        translation_key="next_allowance_amount",
        device_class=SensorDeviceClass.MONETARY,
        suggested_display_precision=2,
        monetary=True,
        value_fn=lambda c: c.next_allowance_amount,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TaschengeldConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors; new children are added as they appear."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_children() -> None:
        new = set(coordinator.data.children) - known
        if not new:
            return
        known.update(new)
        async_add_entities(
            TaschengeldSensor(coordinator, slug, description)
            for slug in sorted(new)
            for description in SENSORS
        )

    _add_new_children()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_children))


class TaschengeldSensor(TaschengeldEntity, SensorEntity):
    """A value of one child."""

    entity_description: TaschengeldSensorDescription

    def __init__(self, coordinator, slug: str, description) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, slug, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | date | None:
        """Return the sensor value."""
        child = self.child
        return self.entity_description.value_fn(child) if child else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Monetary sensors use the currency reported by the service."""
        if not self.entity_description.monetary:
            return None
        child = self.child
        return child.currency if child else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes, if the sensor defines any."""
        child = self.child
        attrs_fn = self.entity_description.attrs_fn
        return attrs_fn(child) if child and attrs_fn else None
