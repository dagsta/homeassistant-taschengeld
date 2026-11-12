"""Constants for the Taschengeld integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "taschengeld"

CONF_TOKEN: Final = "token"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_URL: Final = "https://taschengeld.ideenfaktor.de"

# Polling interval in minutes. The service asks for no more than one call
# every 30 minutes; 180 is plenty for balances that change a few times a week.
DEFAULT_SCAN_INTERVAL: Final = 180
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 1440

API_PATH: Final = "/api/ha/balances"
REQUEST_TIMEOUT: Final = 15  # seconds

# Upper bound for a Retry-After value we are willing to honour (24 h).
MAX_RETRY_AFTER: Final = 86400

DEFAULT_CURRENCY: Final = "EUR"

# Attribute names
ATTR_NOTE: Final = "note"
ATTR_BOOKED_AT: Final = "booked_at"
MAX_NOTE_LENGTH: Final = 255
