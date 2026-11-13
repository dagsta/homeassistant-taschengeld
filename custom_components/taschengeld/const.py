"""Constants for the Taschengeld integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "taschengeld"

CONF_TOKEN: Final = "token"
CONF_SCAN_INTERVAL_HOURS: Final = "scan_interval_hours"
CONF_SCAN_START: Final = "scan_start_time"

DEFAULT_URL: Final = "https://taschengeld.ideenfaktor.de"

# Polling happens at fixed times of day: the start time plus multiples of the
# interval. All choices divide 24, so the slots repeat identically every day.
INTERVAL_CHOICES: Final = (6, 8, 12, 24)
DEFAULT_INTERVAL_HOURS: Final = 24
DEFAULT_START_TIME: Final = "07:00:00"

# Each installation gets a fixed random delay (0..180 min) added to the start
# time, so that all installations do not hit the server at the same minute.
CONF_START_OFFSET: Final = "start_offset_minutes"
MAX_START_OFFSET: Final = 180

# The service asks for at most one call every 30 minutes.
MIN_REQUEST_GAP: Final = 1800  # seconds between two successful requests
RETRY_DELAY: Final = 3600  # seconds before retrying after a failure

API_PATH: Final = "/api/ha/balances"
REQUEST_TIMEOUT: Final = 15  # seconds

# Upper bound for a Retry-After value we are willing to honour (24 h).
MAX_RETRY_AFTER: Final = 86400

DEFAULT_CURRENCY: Final = "EUR"

# Attribute names
ATTR_NOTE: Final = "note"
ATTR_BOOKED_AT: Final = "booked_at"
MAX_NOTE_LENGTH: Final = 255
