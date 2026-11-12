"""Read-only client for the Taschengeld Home Assistant API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from email.utils import parsedate_to_datetime
import logging
from typing import Any

import aiohttp
from homeassistant.util import dt as dt_util
from yarl import URL

from .const import API_PATH, DEFAULT_CURRENCY, MAX_RETRY_AFTER, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class TaschengeldError(Exception):
    """Base error of the Taschengeld client."""


class TaschengeldConnectionError(TaschengeldError):
    """The service could not be reached or answered unexpectedly."""


class TaschengeldInvalidResponseError(TaschengeldConnectionError):
    """The service answered with something that is not the expected JSON."""


class TaschengeldAuthError(TaschengeldError):
    """The token is invalid or has been revoked (HTTP 401)."""


class TaschengeldForbiddenError(TaschengeldError):
    """The token is valid but lacks the ``ha:read`` ability (HTTP 403)."""


class TaschengeldRetryLaterError(TaschengeldError):
    """The service asks us to wait (HTTP 429 or 503)."""

    def __init__(self, status: int, retry_after: float | None) -> None:
        """Initialize the error."""
        super().__init__(f"HTTP {status}")
        self.status = status
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class Child:
    """Balance data of one child."""

    slug: str
    name: str
    balance: float | None
    currency: str
    last_amount: float | None
    last_note: str | None
    last_booked_at: datetime | None
    next_allowance_date: date | None
    next_allowance_amount: float | None


@dataclass(frozen=True, slots=True)
class BalancesData:
    """Everything the balances endpoint returns."""

    updated_at: datetime | None
    children: dict[str, Child] = field(default_factory=dict)


def normalize_base_url(value: str) -> str | None:
    """Return a clean ``https://host[:port][/path]`` URL or ``None`` if invalid.

    Only HTTPS is accepted. Credentials, query strings and fragments are
    rejected so the token can never end up on a different target by accident.
    """
    value = value.strip()
    try:
        url = URL(value)
    except ValueError:
        return None
    if url.scheme != "https" or not url.host:
        return None
    if url.user or url.password or url.query_string or url.fragment:
        return None
    return str(url.with_path(url.path.rstrip("/"))).rstrip("/")


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return round(float(value), 2)


def _to_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    return dt_util.parse_datetime(value)


def _to_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    return dt_util.parse_date(value)


def _parse_child(raw: Any) -> Child | None:
    if not isinstance(raw, dict):
        return None
    slug = raw.get("slug")
    name = raw.get("name")
    if not isinstance(slug, str) or not slug:
        return None
    if not isinstance(name, str) or not name:
        name = slug
    currency = raw.get("currency")
    if not isinstance(currency, str) or not currency:
        currency = DEFAULT_CURRENCY
    note = raw.get("last_note")
    return Child(
        slug=slug,
        name=name,
        balance=_to_float(raw.get("balance")),
        currency=currency.upper(),
        last_amount=_to_float(raw.get("last_amount")),
        last_note=note if isinstance(note, str) else None,
        last_booked_at=_to_datetime(raw.get("last_booked_at")),
        next_allowance_date=_to_date(raw.get("next_allowance_date")),
        next_allowance_amount=_to_float(raw.get("next_allowance_amount")),
    )


def parse_balances(payload: Any) -> BalancesData:
    """Turn the JSON payload into typed data."""
    if not isinstance(payload, dict) or not isinstance(payload.get("children"), list):
        raise TaschengeldInvalidResponseError("Unexpected response format")
    children: dict[str, Child] = {}
    for raw in payload["children"]:
        child = _parse_child(raw)
        if child is not None:
            children[child.slug] = child
    return BalancesData(
        updated_at=_to_datetime(payload.get("updated_at")),
        children=children,
    )


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a Retry-After header (seconds or HTTP date)."""
    if not value:
        return None
    value = value.strip()
    seconds: float | None = None
    if value.isdigit():
        seconds = float(value)
    else:
        try:
            target = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if target.tzinfo is None:
            return None
        seconds = (target - dt_util.utcnow()).total_seconds()
    return max(0.0, min(seconds, MAX_RETRY_AFTER))


class TaschengeldClient:
    """Thin read-only client. It only ever issues one GET request."""

    def __init__(
        self, session: aiohttp.ClientSession, base_url: str, token: str
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._url = f"{base_url}{API_PATH}"
        self._token = token

    async def async_get_balances(self) -> BalancesData:
        """Fetch the balances of all children."""
        try:
            async with self._session.get(
                self._url,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                # Never follow redirects: the token must only go to the
                # address the user configured.
                allow_redirects=False,
            ) as response:
                status = response.status
                if status == 401:
                    raise TaschengeldAuthError
                if status == 403:
                    raise TaschengeldForbiddenError
                if status in (429, 503):
                    raise TaschengeldRetryLaterError(
                        status,
                        _parse_retry_after(response.headers.get("Retry-After")),
                    )
                if status != 200:
                    raise TaschengeldConnectionError(f"HTTP {status}")
                try:
                    payload = await response.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError) as err:
                    raise TaschengeldInvalidResponseError(
                        "Response is not valid JSON"
                    ) from err
        except TimeoutError as err:
            raise TaschengeldConnectionError("Request timed out") from err
        except aiohttp.ClientError as err:
            # Log only the exception type; never headers or the token.
            _LOGGER.debug("Request failed: %s", type(err).__name__)
            raise TaschengeldConnectionError("Connection failed") from err
        return parse_balances(payload)
