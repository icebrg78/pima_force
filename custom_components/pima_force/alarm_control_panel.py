"""Icepro fork: read-only arm state of the panel, decoded from its SIA feed."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.alarm_control_panel import AlarmControlPanelEntity
from homeassistant.components.alarm_control_panel.const import (
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.const import CONF_PORT
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    ATTR_ARMED_MODE,
    ATTR_PARTITION,
    ATTR_TRIGGER_CODE,
    ATTR_TRIGGER_ZONE,
    ATTR_USER,
    DOMAIN,
)
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
    """Add the panel entity."""
    async_add_entities([PimaForcePanel(config_entry)])


class PimaForcePanel(PimaForceEntity, AlarmControlPanelEntity, RestoreEntity):
    """Arm state reported by the panel (no arm/disarm from HA)."""

    _attr_name = "Panel"
    _attr_icon = "mdi:shield-home"
    _attr_code_arm_required = False
    _attr_supported_features = AlarmControlPanelEntityFeature(0)

    def __init__(self, config_entry: PimaForceConfigEntry) -> None:
        """Initialize the panel entity."""
        super().__init__(config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_panel"
        self.entity_id = (
            f"alarm_control_panel.{DOMAIN}_{config_entry.options[CONF_PORT]}_panel"
        )

    async def async_added_to_hass(self) -> None:
        """Restore the last state; live events take precedence."""
        await super().async_added_to_hass()
        if last_state := await self.async_get_last_state():
            self.coordinator.system.restore(
                last_state.state, last_state.attributes.get(ATTR_ARMED_MODE)
            )

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the arm state."""
        state = self.coordinator.system.state
        return AlarmControlPanelState(state) if state else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return who armed, the armed mode kept through alarms, and the trigger."""
        system = self.coordinator.system
        return {
            ATTR_ARMED_MODE: system.armed_mode,
            ATTR_USER: system.user,
            ATTR_PARTITION: system.partition,
            ATTR_TRIGGER_ZONE: system.trigger_zone,
            ATTR_TRIGGER_CODE: system.trigger_code,
        }
