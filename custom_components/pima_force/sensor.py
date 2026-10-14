"""Icepro fork: the last non-zone event the panel sent (e.g. ``3441 01 015``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_PORT
from homeassistant.helpers.restore_state import RestoreEntity

from .const import ATTR_OUTPUTS, DOMAIN
from .entity import PimaForceEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import PimaForceConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    _: HomeAssistant,
    config_entry: PimaForceConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the last-event sensor."""
    async_add_entities([PimaForceLastEventSensor(config_entry)])


class PimaForceLastEventSensor(PimaForceEntity, SensorEntity, RestoreEntity):
    """Last system event as qualifier+code, partition, user/zone."""

    _attr_name = "Last event"
    _attr_icon = "mdi:message-badge-outline"

    def __init__(self, config_entry: PimaForceConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_last_event"
        self.entity_id = f"sensor.{DOMAIN}_{config_entry.options[CONF_PORT]}_last_event"
        self._restored: str | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last value until a new event arrives."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) and (
            last_state.state not in ("unknown", "unavailable")
        ):
            self._restored = last_state.state

    @property
    def native_value(self) -> str | None:
        """Return the last event."""
        return self.coordinator.system.last_event_text or self._restored

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the event's fields and the panel output states."""
        return {
            **(self.coordinator.system.last_event or {}),
            ATTR_OUTPUTS: dict(self.coordinator.system.outputs),
        }
