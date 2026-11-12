"""Diagnostics for the Taschengeld integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN
from .coordinator import TaschengeldConfigEntry

TO_REDACT_CONFIG = {CONF_TOKEN, CONF_URL, "title"}
TO_REDACT_CHILD = {"name", "slug", "last_note"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TaschengeldConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with token, address, names and notes redacted."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": async_redact_data(
            {"title": entry.title, "data": dict(entry.data), "options": dict(entry.options)},
            TO_REDACT_CONFIG,
        ),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
        },
        "updated_at": data.updated_at.isoformat() if data.updated_at else None,
        "children": [
            async_redact_data(
                {
                    key: value.isoformat() if hasattr(value, "isoformat") else value
                    for key, value in asdict(child).items()
                },
                TO_REDACT_CHILD,
            )
            for child in data.children.values()
        ],
    }
