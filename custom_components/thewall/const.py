"""Constants for THE WALL."""

from datetime import timedelta
import logging
from typing import Final

DOMAIN: Final = "thewall"
LOGGER = logging.getLogger(__package__)

MANUFACTURER: Final = "THE WALL"
DEFAULT_SERVER: Final = "https://thewall.godart.lu"
API_PATH: Final = "/api/ha/v1"
ZEROCONF_TYPE: Final = "_thewall._tcp.local."

# Config entry data. The entry stores exactly these three keys.
CONF_UID: Final = "uid"
CONF_SERVER: Final = "server"
CONF_TOKEN: Final = "token"

# Name under which this Home Assistant appears in the list of linked
# instances on the website.
PAIRING_NAME: Final = "Home Assistant"

UPDATE_INTERVAL: Final = timedelta(seconds=15)
# Extra refresh this many seconds after a timer end or the alarm time.
EVENT_REFRESH_DELAY: Final = 1

NOTE_MAX_DEFAULT: Final = 21
TIMER_LABEL_MAX: Final = 12
TIMER_MAX_SECONDS: Final = 86400
TIMER_DEFAULT_MINUTES: Final = 5
TIMER_MAX_MINUTES: Final = 240

# Modes the server knows today. Entities read the available ones from the
# state, this list only decides which ones have translated names.
KNOWN_MODES: Final = ("flight", "clock", "weather", "transit", "spotify", "notes")
# Values of panel.showing that are not modes.
SHOWING_SPECIAL: Final = ("ring", "pairing", "hello", "off")

TIMER_EVENT_STARTED: Final = "started"
TIMER_EVENT_FINISHED: Final = "finished"
TIMER_EVENT_CANCELLED: Final = "cancelled"
