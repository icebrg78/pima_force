"""Constants for the pima_force integration."""

import logging
from typing import Final

DOMAIN: Final = "pima_force"
TITLE: Final = "Pima Force"
LOGGER = logging.getLogger(__package__)

DEFAULT_LISTENING_PORT: Final = 10001
CONF_ZONES: Final = "zones"
SERVICE_GET_ZONES: Final = "get_zones"
SERVICE_SET_ZONES: Final = "set_zones"
SERVICE_SET_OPEN: Final = "set_open"
SERVICE_SET_CLOSED: Final = "set_closed"

DEVICE_MANUFACTURER: Final = "Pima"
DEVICE_MODEL: Final = "Force"

ATTR_LAST_OPEN: Final = "last_open"
ATTR_LAST_CLOSE: Final = "last_close"
ATTR_LAST_SET: Final = "last_set"
ATTR_ZONE: Final = "zone"

SIA_PIMA_KEEP_CONNECTED_QUALIFIER: Final = "KC"
ADM_CID_PIMA_ZONE_STATUS_CODE: Final = "760"
ADM_CID_EVENT_QUALIFIER_OPEN: Final = "1"
ADM_CID_EVENT_QUALIFIER_CLOSE: Final = "3"

# --- icepro fork: system events from the same SIA/ADM-CID feed ---------------
# Contact ID codes the panel sends besides 760 (zone status). Qualifier "1" is a
# new event / opening (disarm), "3" is a restore / closing (arm).
ADM_CID_PIMA_OUTPUT_STATUS_CODE: Final = "770"
ADM_CID_AWAY_ARM_CODES: Final = frozenset(
    {"400", "401", "402", "403", "404", "405", "407", "408", "409"}
)
ADM_CID_HOME_ARM_CODES: Final = frozenset({"441", "442"})
ADM_CID_PARTIAL_ARM_CODE: Final = "456"
ADM_CID_CANCEL_CODE: Final = "406"
# Pima sends 138 ("near alarm") when an entry/exit-delay zone opens while armed:
# the entry delay has started. A real alarm follows as 13x when it expires.
ADM_CID_ENTRY_DELAY_CODE: Final = "138"
ADM_CID_ALARM_CODE_MIN: Final = 100
ADM_CID_ALARM_CODE_MAX: Final = 146
# Fallback if neither a disarm nor an alarm follows an entry delay.
ENTRY_DELAY_TIMEOUT_SECONDS: Final = 120

ATTR_ARMED_MODE: Final = "armed_mode"
ATTR_USER: Final = "user"
ATTR_PARTITION: Final = "partition"
ATTR_TRIGGER_ZONE: Final = "trigger_zone"
ATTR_TRIGGER_CODE: Final = "trigger_code"
ATTR_LAST_EVENT_CODE: Final = "code"
ATTR_LAST_EVENT_QUALIFIER: Final = "qualifier"
ATTR_LAST_EVENT_RI: Final = "ri"
ATTR_LAST_EVENT_TIME: Final = "time"
ATTR_OUTPUTS: Final = "outputs"
