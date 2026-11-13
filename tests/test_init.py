"""Tests for setup, entities, coordinator behaviour and diagnostics."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.taschengeld.const import (
    CONF_SCAN_INTERVAL_HOURS,
    CONF_SCAN_START,
    CONF_TOKEN,
    DOMAIN,
)

from .conftest import API_URL, BEN, MIA, TOKEN, URL, balances_payload


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture(autouse=True)
async def fixed_time(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Start every test at 05:00 UTC; the default daily slot is 07:00."""
    freezer.move_to("2026-11-12 05:00:00+00:00")
    await hass.config.async_set_time_zone("UTC")


async def _refresh(hass: HomeAssistant, freezer: FrozenDateTimeFactory, minutes: int) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_setup_creates_entities(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """Each child gets one device with its sensors."""
    aioclient_mock.get(API_URL, json=balances_payload(MIA, BEN))
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    state = hass.states.get("sensor.taschengeld_mia_balance")
    assert state is not None
    assert state.state == "23.5"
    assert state.attributes["unit_of_measurement"] == "EUR"
    assert state.attributes["device_class"] == "monetary"
    assert state.attributes["state_class"] == "total"

    last = hass.states.get("sensor.taschengeld_mia_last_booking")
    assert last.state == "3.0"
    assert last.attributes["note"] == "Taschengeld"
    assert last.attributes["booked_at"] == "2026-11-07T06:00:00+01:00"

    assert hass.states.get("sensor.taschengeld_mia_next_allowance_date").state == "2026-11-14"
    assert hass.states.get("sensor.taschengeld_mia_next_allowance_amount").state == "3.0"

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), config_entry.entry_id)
    assert {d.name for d in devices} == {"Taschengeld Mia", "Taschengeld Ben"}


async def test_null_values_are_unknown(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """Missing booking and rule data show up as unknown, not as errors."""
    aioclient_mock.get(API_URL, json=balances_payload(BEN))
    await _setup(hass, config_entry)
    assert hass.states.get("sensor.taschengeld_ben_last_booking").state == "unknown"
    assert hass.states.get("sensor.taschengeld_ben_next_allowance_date").state == "unknown"
    assert hass.states.get("sensor.taschengeld_ben_next_allowance_amount").state == "unknown"
    assert hass.states.get("binary_sensor.taschengeld_ben_allowance_due_today").state == "off"


async def test_due_today_binary_sensor(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The binary sensor is on exactly on the allowance date."""
    freezer.move_to("2026-11-14 12:00:00+00:00")
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    await _setup(hass, config_entry)
    assert hass.states.get("binary_sensor.taschengeld_mia_allowance_due_today").state == "on"


async def test_new_and_removed_child(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Entities appear and disappear dynamically with the children."""
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    await _setup(hass, config_entry)
    assert hass.states.get("sensor.taschengeld_ben_balance") is None

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=balances_payload(MIA, BEN))
    await _refresh(hass, freezer, minutes=125)  # 07:05, after the 07:00 slot
    assert hass.states.get("sensor.taschengeld_ben_balance") is not None

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=balances_payload(BEN))
    await _refresh(hass, freezer, minutes=24 * 60)  # next day's 07:00 slot
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), config_entry.entry_id)
    assert {d.name for d in devices} == {"Taschengeld Ben"}
    assert er.async_get(hass).async_get("sensor.taschengeld_mia_balance") is None


async def test_unique_id_uses_slug_not_name(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Renaming a child keeps the entity and updates the device name."""
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    await _setup(hass, config_entry)
    registry = er.async_get(hass)
    unique_id = registry.async_get("sensor.taschengeld_mia_balance").unique_id

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=balances_payload({**MIA, "name": "Mia-Lou"}))
    await _refresh(hass, freezer, minutes=125)
    assert registry.async_get("sensor.taschengeld_mia_balance").unique_id == unique_id
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), config_entry.entry_id)
    assert [d.name for d in devices] == ["Taschengeld Mia-Lou"]


async def test_setup_retry_on_connection_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """An unreachable service makes setup retry later."""
    aioclient_mock.get(API_URL, status=500)
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """A 401 keeps the entry and asks for a new token."""
    aioclient_mock.get(API_URL, status=401)
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_rate_limit_waits_for_retry_after(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After a 429 with Retry-After the next call is not made earlier."""
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    await _setup(hass, config_entry)

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, status=429, headers={"Retry-After": str(6 * 3600)})
    await _refresh(hass, freezer, minutes=125)  # 07:05 slot -> 429
    assert aioclient_mock.call_count == 1
    assert hass.states.get("sensor.taschengeld_mia_balance").state == "unavailable"

    # The normal 1 h retry delay has passed three times over, Retry-After (6 h) has not.
    await _refresh(hass, freezer, minutes=180)
    assert aioclient_mock.call_count == 1
    await _refresh(hass, freezer, minutes=190)
    assert aioclient_mock.call_count == 2


async def test_failure_is_retried_after_one_hour(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed slot is retried after an hour, not only at the next slot."""
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    await _setup(hass, config_entry)

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, status=503)
    await _refresh(hass, freezer, minutes=125)
    assert aioclient_mock.call_count == 1

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    await _refresh(hass, freezer, minutes=65)
    assert aioclient_mock.call_count == 1
    assert hass.states.get("sensor.taschengeld_mia_balance").state == "23.5"


async def test_polls_at_configured_times(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    """With 8 h from 06:30 the slots are 06:30, 14:30 and 22:30."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=URL,
        data={"url": URL, CONF_TOKEN: TOKEN},
        options={CONF_SCAN_INTERVAL_HOURS: 8, CONF_SCAN_START: "06:30:00"},
    )
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    await _setup(hass, entry)  # 05:00
    assert aioclient_mock.call_count == 1

    await _refresh(hass, freezer, minutes=95)  # 06:35
    assert aioclient_mock.call_count == 2
    await _refresh(hass, freezer, minutes=470)  # 14:25, slot not reached
    assert aioclient_mock.call_count == 2
    await _refresh(hass, freezer, minutes=10)  # 14:35
    assert aioclient_mock.call_count == 3


async def test_manual_refresh_respects_minimum_gap(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Two requests are at least 30 minutes apart, however often HA asks."""
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    await _setup(hass, config_entry)
    assert aioclient_mock.call_count == 1

    coordinator = config_entry.runtime_data
    freezer.tick(timedelta(minutes=10))
    await coordinator.async_refresh()
    assert aioclient_mock.call_count == 1

    freezer.tick(timedelta(minutes=25))
    await coordinator.async_refresh()
    assert aioclient_mock.call_count == 2


async def test_diagnostics_redacts_secrets(
    hass: HomeAssistant,
    hass_client,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """Token, address, names, slugs and notes never appear in diagnostics."""
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    await _setup(hass, config_entry)
    assert await async_setup_component(hass, "diagnostics", {})
    diag = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)
    text = str(diag)
    for secret in (TOKEN, "taschengeld.example.test", "Mia", "'mia'", "'Taschengeld'"):
        assert secret not in text, secret
    assert diag["children"][0]["balance"] == 23.5
