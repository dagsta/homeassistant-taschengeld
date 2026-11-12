"""Shared fixtures for the Taschengeld tests."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.taschengeld.const import CONF_TOKEN, DOMAIN

URL = "https://taschengeld.example.test"
API_URL = f"{URL}/api/ha/balances"
TOKEN = "DEIN_TOKEN"  # dummy value, never a real token


def balances_payload(*children: dict[str, Any]) -> dict[str, Any]:
    """Build an API response."""
    return {"updated_at": "2026-11-12T18:30:00+01:00", "children": list(children)}


MIA: dict[str, Any] = {
    "slug": "mia",
    "name": "Mia",
    "balance": 23.5,
    "currency": "EUR",
    "last_amount": 3.0,
    "last_note": "Taschengeld",
    "last_booked_at": "2026-11-07T06:00:00+01:00",
    "next_allowance_date": "2026-11-14",
    "next_allowance_amount": 3.0,
}

BEN: dict[str, Any] = {
    "slug": "ben",
    "name": "Ben",
    "balance": 0.0,
    "currency": "EUR",
    "last_amount": None,
    "last_note": None,
    "last_booked_at": None,
    "next_allowance_date": None,
    "next_allowance_amount": None,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load the custom integration under test."""


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry for the test address."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Taschengeld",
        unique_id=URL,
        data={"url": URL, CONF_TOKEN: TOKEN},
    )
