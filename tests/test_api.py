"""Tests for the API client."""

from __future__ import annotations

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.taschengeld.api import (
    TaschengeldAuthError,
    TaschengeldClient,
    TaschengeldConnectionError,
    TaschengeldForbiddenError,
    TaschengeldInvalidResponseError,
    TaschengeldRetryLaterError,
    normalize_base_url,
    parse_balances,
)

from .conftest import API_URL, BEN, MIA, TOKEN, URL, balances_payload


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://taschengeld.ideenfaktor.de", "https://taschengeld.ideenfaktor.de"),
        ("  https://example.test/  ", "https://example.test"),
        ("https://example.test:8443/sub/", "https://example.test:8443/sub"),
        ("http://example.test", None),
        ("example.test", None),
        ("https://user:pw@example.test", None),
        ("https://example.test?x=1", None),
        ("https://example.test#frag", None),
        ("", None),
    ],
)
def test_normalize_base_url(value: str, expected: str | None) -> None:
    """Only clean https URLs are accepted."""
    assert normalize_base_url(value) == expected


def test_parse_handles_nulls_and_garbage() -> None:
    """Null values and malformed children do not break parsing."""
    data = parse_balances(
        balances_payload(MIA, BEN, {"name": "no slug"}, "junk", {"slug": "x", "balance": "n/a"})
    )
    assert set(data.children) == {"mia", "ben", "x"}
    assert data.children["mia"].balance == 23.5
    assert data.children["ben"].last_amount is None
    assert data.children["ben"].next_allowance_date is None
    assert data.children["x"].balance is None
    assert data.children["x"].name == "x"
    assert data.children["x"].currency == "EUR"


def test_parse_rejects_wrong_shape() -> None:
    """A payload without a children list is an invalid response."""
    with pytest.raises(TaschengeldInvalidResponseError):
        parse_balances({"foo": 1})


async def _client(hass: HomeAssistant) -> TaschengeldClient:
    return TaschengeldClient(async_get_clientsession(hass), URL, TOKEN)


async def test_success_sends_bearer_header(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The request carries the bearer token and asks for JSON."""
    aioclient_mock.get(API_URL, json=balances_payload(MIA))
    data = await (await _client(hass)).async_get_balances()
    assert data.children["mia"].balance == 23.5
    headers = aioclient_mock.mock_calls[0][3]
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["Accept"] == "application/json"


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, TaschengeldAuthError), (403, TaschengeldForbiddenError)],
)
async def test_auth_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    error: type[Exception],
) -> None:
    """401 and 403 map to distinct errors."""
    aioclient_mock.get(API_URL, status=status)
    with pytest.raises(error):
        await (await _client(hass)).async_get_balances()


@pytest.mark.parametrize(
    ("status", "header", "expected"),
    [(429, "120", 120.0), (503, None, None), (429, "abc", None), (503, "999999999", 86400.0)],
)
async def test_retry_later(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    header: str | None,
    expected: float | None,
) -> None:
    """429/503 carry the (capped) Retry-After value."""
    aioclient_mock.get(API_URL, status=status, headers={"Retry-After": header} if header else {})
    with pytest.raises(TaschengeldRetryLaterError) as exc:
        await (await _client(hass)).async_get_balances()
    assert exc.value.status == status
    assert exc.value.retry_after == expected


@pytest.mark.parametrize("exc", [aiohttp.ClientError, TimeoutError])
async def test_connection_errors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, exc: type[Exception]
) -> None:
    """Network problems become connection errors."""
    aioclient_mock.get(API_URL, exc=exc)
    with pytest.raises(TaschengeldConnectionError):
        await (await _client(hass)).async_get_balances()


async def test_redirect_is_not_followed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A redirect is an error; the token must not travel to another host."""
    aioclient_mock.get(API_URL, status=302, headers={"Location": "https://evil.test/"})
    with pytest.raises(TaschengeldConnectionError):
        await (await _client(hass)).async_get_balances()
    assert aioclient_mock.call_count == 1


async def test_invalid_json(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A non-JSON body is an invalid response."""
    aioclient_mock.get(API_URL, text="<html>maintenance</html>")
    with pytest.raises(TaschengeldInvalidResponseError):
        await (await _client(hass)).async_get_balances()
