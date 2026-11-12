"""The Taschengeld integration: read-only child balances from Taschengeld."""

from __future__ import annotations

from homeassistant.const import CONF_URL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TaschengeldClient
from .const import CONF_TOKEN, DOMAIN
from .coordinator import TaschengeldConfigEntry, TaschengeldCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


def device_identifier(entry: TaschengeldConfigEntry, slug: str) -> tuple[str, str]:
    """Return the device registry identifier of a child."""
    return (DOMAIN, f"{entry.entry_id}_{slug}")


async def async_setup_entry(hass: HomeAssistant, entry: TaschengeldConfigEntry) -> bool:
    """Set up Taschengeld from a config entry."""
    client = TaschengeldClient(
        async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN]
    )
    coordinator = TaschengeldCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    @callback
    def _sync_devices() -> None:
        """Remove devices of vanished children and keep names current."""
        registry = dr.async_get(hass)
        children = coordinator.data.children
        wanted = {device_identifier(entry, slug): c for slug, c in children.items()}
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
            child = next(
                (wanted[i] for i in device.identifiers if i in wanted),
                None,
            )
            if child is None:
                registry.async_update_device(
                    device.id, remove_config_entry_id=entry.entry_id
                )
            elif device.name != f"Taschengeld {child.name}":
                registry.async_update_device(
                    device.id, name=f"Taschengeld {child.name}"
                )

    entry.async_on_unload(coordinator.async_add_listener(_sync_devices))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TaschengeldConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: TaschengeldConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow deleting a device only if its child no longer exists."""
    current = {
        device_identifier(entry, slug) for slug in entry.runtime_data.data.children
    }
    return not any(i in current for i in device_entry.identifiers)
