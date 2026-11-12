"""Base entity for the Taschengeld integration."""

from __future__ import annotations

from homeassistant.const import CONF_URL
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import device_identifier
from .api import Child
from .const import DOMAIN
from .coordinator import TaschengeldCoordinator


class TaschengeldEntity(CoordinatorEntity[TaschengeldCoordinator]):
    """An entity belonging to one child (= one device)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TaschengeldCoordinator, slug: str, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._slug = slug
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{slug}_{key}"
        child = coordinator.data.children[slug]
        self._attr_device_info = DeviceInfo(
            identifiers={device_identifier(entry, slug)},
            name=f"Taschengeld {child.name}",
            manufacturer="Taschengeld",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=entry.data[CONF_URL],
        )

    @property
    def child(self) -> Child | None:
        """Return the current data of this entity's child, if it still exists."""
        return self.coordinator.data.children.get(self._slug)

    @property
    def available(self) -> bool:
        """Entity is available while the child is part of the latest data."""
        return super().available and self.child is not None
