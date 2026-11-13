"""Tests for the config, reauth and options flows."""

from __future__ import annotations

import aiohttp
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.taschengeld.const import (
    CONF_SCAN_INTERVAL_HOURS,
    CONF_SCAN_START,
    CONF_TOKEN,
    DOMAIN,
)

from .conftest import API_URL, MIA, TOKEN, URL, balances_payload


async def _start(hass: HomeAssistant, url: str = URL, token: str = TOKEN):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": url, CONF_TOKEN: token}
    )


async def test_user_flow_success(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A valid address and token create an entry."""
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    result = await _start(hass, url=f"{URL}/")
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"url": URL, CONF_TOKEN: TOKEN}


async def test_user_flow_strips_bearer_prefix(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A pasted ``Bearer`` prefix and spaces are removed."""
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    result = await _start(hass, token=f"  Bearer {TOKEN} ")
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_TOKEN] == TOKEN


@pytest.mark.parametrize(
    ("mock_kwargs", "error"),
    [
        ({"status": 401}, "invalid_auth"),
        ({"status": 403}, "no_permission"),
        ({"status": 429}, "rate_limited"),
        ({"status": 503}, "service_unavailable"),
        ({"status": 500}, "cannot_connect"),
        ({"exc": aiohttp.ClientError}, "cannot_connect"),
        ({"exc": TimeoutError}, "cannot_connect"),
    ],
)
async def test_user_flow_errors_then_recovery(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_kwargs: dict,
    error: str,
) -> None:
    """Errors are shown on the form and the user can retry successfully."""
    aioclient_mock.get(API_URL, **mock_kwargs)
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": URL, CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize("url", ["http://taschengeld.example.test", "no-url", "https://a:b@x.test"])
async def test_user_flow_invalid_url(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, url: str
) -> None:
    """Only clean https addresses are accepted; no request is made."""
    result = await _start(hass, url=url)
    assert result["errors"] == {"url": "invalid_url"}
    assert aioclient_mock.call_count == 0


async def test_user_flow_already_configured(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """The same address cannot be added twice."""
    config_entry.add_to_hass(hass)
    result = await _start(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """A new token replaces the old one without deleting the entry."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    aioclient_mock.get(API_URL, status=401)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "BAD"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "NEUES_TOKEN"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_TOKEN] == "NEUES_TOKEN"


async def _setup_for_options(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_options_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """Interval and start time can be changed."""
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    await _setup_for_options(hass, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL_HOURS: "8", CONF_SCAN_START: "06:30:00"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_SCAN_INTERVAL_HOURS: 8, CONF_SCAN_START: "06:30:00"}


@pytest.mark.parametrize("value", ["1", "5", "7", "48"])
async def test_options_flow_only_allows_listed_intervals(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry, value: str
) -> None:
    """Only 6, 8, 12 and 24 hours are accepted."""
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    await _setup_for_options(hass, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL_HOURS: value, CONF_SCAN_START: "07:00:00"}
        )
