"""
icepro fork: arm state and system events decoded from the panel's SIA feed.

Upstream only handles ADM-CID 760 (zone status). The panel also reports arming,
disarming, entry delays, alarms and output changes on the same connection; this
module turns those into an alarm-panel state without touching the zone logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from homeassistant.components.alarm_control_panel.const import AlarmControlPanelState
from homeassistant.util import dt as dt_util

from .const import (
    ADM_CID_ALARM_CODE_MAX,
    ADM_CID_ALARM_CODE_MIN,
    ADM_CID_AWAY_ARM_CODES,
    ADM_CID_CANCEL_CODE,
    ADM_CID_ENTRY_DELAY_CODE,
    ADM_CID_EVENT_QUALIFIER_CLOSE,
    ADM_CID_EVENT_QUALIFIER_OPEN,
    ADM_CID_HOME_ARM_CODES,
    ADM_CID_PARTIAL_ARM_CODE,
    ADM_CID_PIMA_OUTPUT_STATUS_CODE,
    ATTR_LAST_EVENT_CODE,
    ATTR_LAST_EVENT_QUALIFIER,
    ATTR_LAST_EVENT_RI,
    ATTR_LAST_EVENT_TIME,
    ATTR_PARTITION,
    LOGGER,
)

if TYPE_CHECKING:
    from pysiaalarm.event import SIAEvent

ARMED_STATES: frozenset[str] = frozenset(
    {AlarmControlPanelState.ARMED_AWAY, AlarmControlPanelState.ARMED_HOME}
)


def _is_alarm_code(code: str) -> bool:
    return (
        code.isdigit()
        and ADM_CID_ALARM_CODE_MIN <= int(code) <= ADM_CID_ALARM_CODE_MAX
        and code != ADM_CID_ENTRY_DELAY_CODE
    )


@dataclass
class PimaSystemState:
    """Arm state machine fed by non-zone ADM-CID events."""

    state: str | None = None
    armed_mode: str | None = None  # armed mode kept through pending/triggered
    user: str | None = None
    partition: str | None = None
    trigger_zone: str | None = None
    trigger_code: str | None = None
    last_event: dict[str, Any] | None = None
    outputs: dict[str, bool] = field(default_factory=dict)
    alarm_zones: set[str] = field(default_factory=set)

    @property
    def last_event_text(self) -> str | None:
        """Return the last event as the panel prints it, e.g. ``3441 01 015``."""
        if not self.last_event:
            return None
        ev = self.last_event
        return (
            f"{ev[ATTR_LAST_EVENT_QUALIFIER]}{ev[ATTR_LAST_EVENT_CODE]} "
            f"{ev[ATTR_PARTITION]} {ev[ATTR_LAST_EVENT_RI]}"
        )

    def handle(self, event: SIAEvent) -> bool:
        """Apply one non-760 event. Return whether anything changed."""
        code = event.event_type or ""
        qualifier = event.event_qualifier or ""
        ri = event.ri or ""
        if code == ADM_CID_PIMA_OUTPUT_STATUS_CODE:
            on = qualifier == ADM_CID_EVENT_QUALIFIER_OPEN
            LOGGER.debug("PIMA output %s -> %s", ri, on)
            if self.outputs.get(ri) == on:
                return False
            self.outputs[ri] = on
            return True

        self.last_event = {
            ATTR_LAST_EVENT_QUALIFIER: qualifier,
            ATTR_LAST_EVENT_CODE: code,
            ATTR_PARTITION: event.partition or "",
            ATTR_LAST_EVENT_RI: ri,
            ATTR_LAST_EVENT_TIME: dt_util.now().isoformat(),
        }
        self.partition = event.partition or self.partition
        self._apply(code, qualifier, ri)
        LOGGER.info(
            "PIMA system event: %s -> state=%s armed_mode=%s",
            self.last_event_text,
            self.state,
            self.armed_mode,
        )
        return True

    def _apply(self, code: str, qualifier: str, ri: str) -> None:  # noqa: PLR0912
        opening = qualifier == ADM_CID_EVENT_QUALIFIER_OPEN
        closing = qualifier == ADM_CID_EVENT_QUALIFIER_CLOSE
        if code in ADM_CID_AWAY_ARM_CODES or code in ADM_CID_HOME_ARM_CODES:
            mode = (
                AlarmControlPanelState.ARMED_AWAY
                if code in ADM_CID_AWAY_ARM_CODES
                else AlarmControlPanelState.ARMED_HOME
            )
            if closing:
                self._arm(mode, ri)
            elif opening:
                self._disarm(ri)
        elif code == ADM_CID_PARTIAL_ARM_CODE:
            if opening:
                self._arm(AlarmControlPanelState.ARMED_HOME, ri)
            elif closing:
                self._disarm(ri)
        elif code == ADM_CID_CANCEL_CODE:
            if opening:
                self._disarm(ri)
        elif code == ADM_CID_ENTRY_DELAY_CODE:
            if opening and self.state in ARMED_STATES:
                self.state = AlarmControlPanelState.PENDING
                self.trigger_zone, self.trigger_code = ri, code
            elif closing:
                self.end_pending()
        elif _is_alarm_code(code):
            if opening:
                self.alarm_zones.add(ri)
                self.state = AlarmControlPanelState.TRIGGERED
                self.trigger_zone, self.trigger_code = ri, code
            elif closing:
                self.alarm_zones.discard(ri)
                if self.state == AlarmControlPanelState.TRIGGERED and not (
                    self.alarm_zones
                ):
                    self.state = self.armed_mode or AlarmControlPanelState.DISARMED

    def _arm(self, mode: str, user: str) -> None:
        self.state = self.armed_mode = mode
        self.user = user
        self.alarm_zones.clear()

    def _disarm(self, user: str) -> None:
        self.state = AlarmControlPanelState.DISARMED
        self.armed_mode = None
        self.user = user
        self.alarm_zones.clear()

    def end_pending(self) -> bool:
        """Leave the entry delay without an alarm. Return whether it changed."""
        if self.state != AlarmControlPanelState.PENDING:
            return False
        self.state = self.armed_mode or AlarmControlPanelState.DISARMED
        return True

    def restore(self, state: str, armed_mode: str | None) -> None:
        """Seed from the last known state after a restart (events win)."""
        if self.state is not None:
            return
        if armed_mode in ARMED_STATES:
            self.armed_mode = armed_mode
        if state == AlarmControlPanelState.PENDING:
            state = self.armed_mode or AlarmControlPanelState.DISARMED
        if state in ARMED_STATES:
            self.armed_mode = state
        if state in ARMED_STATES or state in (
            AlarmControlPanelState.DISARMED,
            AlarmControlPanelState.TRIGGERED,
        ):
            self.state = state
