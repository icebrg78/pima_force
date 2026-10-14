"""Tests for the icepro fork: arm state, last event and outputs from the SIA feed."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from homeassistant.components.alarm_control_panel import AlarmControlPanelState
from homeassistant.const import CONF_NAME, CONF_PORT
from homeassistant.core import State
from pysiaalarm.event import SIAEvent
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.pima_force.const import (
    CONF_ZONES,
    DEFAULT_LISTENING_PORT,
    DOMAIN,
    ENTRY_DELAY_TIMEOUT_SECONDS,
)
from custom_components.pima_force.system_events import PimaSystemState

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant

PANEL = f"alarm_control_panel.{DOMAIN}_{DEFAULT_LISTENING_PORT}_panel"
LAST = f"sensor.{DOMAIN}_{DEFAULT_LISTENING_PORT}_last_event"
ZONE1 = f"binary_sensor.{DOMAIN}_{DEFAULT_LISTENING_PORT}_zone1"


def ev(text: str) -> SIAEvent:
    """Build an event from the panel's printed form, e.g. ``3441 01 015``."""
    head, partition, ri = text.split()
    return SIAEvent(
        event_qualifier=head[0], event_type=head[1:], partition=partition, ri=ri
    )


def run(*events: str, system: PimaSystemState | None = None) -> PimaSystemState:
    """Feed events to a state machine and return it."""
    system = system or PimaSystemState()
    for text in events:
        system.handle(ev(text))
    return system


# --- state machine, with sequences recorded from the real panel ---------------


def test_auto_arm_home_and_scheduled_disarm() -> None:
    """Panel auto-arm (user 000) is home, the scheduled disarm clears it."""
    s = run("3441 01 000")
    assert (s.state, s.armed_mode, s.user) == ("armed_home", "armed_home", "000")
    assert s.last_event_text == "3441 01 000"
    run("1400 01 000", system=s)
    assert (s.state, s.armed_mode) == ("disarmed", None)


def test_key_switch_full_and_home() -> None:
    """Key-switch full arm (3409) and home arm/disarm (3441 / 1409)."""
    assert run("3409 01 014").state == "armed_away"
    s = run("3441 01 015", "1409 01 015")
    assert (s.state, s.user) == ("disarmed", "015")


def test_entry_delay_then_disarm() -> None:
    """Coming home: 138 starts the entry delay, the keypad disarm ends it."""
    s = run("3409 01 014", "1138 01 001")
    assert (s.state, s.armed_mode, s.trigger_zone) == ("pending", "armed_away", "001")
    run("1401 01 001", system=s)
    assert s.state == "disarmed"


def test_entry_delay_then_alarm_keeps_armed_mode() -> None:
    """An expired entry delay alarms; the armed mode survives until disarm."""
    s = run("3441 01 000", "1138 01 001", "1130 01 001")
    assert (s.state, s.armed_mode) == ("triggered", "armed_home")
    assert (s.trigger_zone, s.trigger_code) == ("001", "130")
    run("1401 01 001", "3130 01 001", system=s)
    assert s.state == "disarmed"


def test_alarm_restore_returns_to_armed_mode() -> None:
    """Without a disarm, the alarm restore goes back to the armed mode."""
    s = run("3441 01 000", "1130 01 002")
    assert s.state == "triggered"
    run("3130 01 002", system=s)
    assert s.state == "armed_home"


def test_alarm_restore_waits_for_all_zones() -> None:
    """Triggered stays until every alarming zone has restored."""
    s = run("3409 01 014", "1130 01 007", "1130 01 006", "3130 01 007")
    assert s.state == "triggered"
    run("3130 01 006", system=s)
    assert s.state == "armed_away"


def test_alarm_while_disarmed_restores_to_disarmed() -> None:
    """A 24 h zone alarm while disarmed returns to disarmed."""
    s = run("1130 01 003")
    assert (s.state, s.armed_mode) == ("triggered", None)
    run("3130 01 003", system=s)
    assert s.state == "disarmed"


def test_entry_delay_ignored_when_disarmed_and_restore() -> None:
    """138 does nothing while disarmed; 3138 ends a pending delay."""
    s = run("1400 01 000", "1138 01 001")
    assert s.state == "disarmed"
    s = run("3409 01 014", "1138 01 001", "3138 01 001")
    assert s.state == "armed_away"
    assert not s.end_pending()


def test_partial_and_cancel_codes() -> None:
    """456 opening arms home, its closing disarms; 406 cancels."""
    assert run("1456 01 001").state == "armed_home"
    assert run("1456 01 001", "3456 01 001").state == "disarmed"
    assert run("3409 01 014", "1406 01 001").state == "disarmed"
    assert run("3409 01 014", "3406 01 001").state == "armed_away"


def test_other_codes_and_qualifiers_only_record() -> None:
    """Unknown codes and qualifiers change nothing but the last event."""
    s = run("3409 01 014", "1602 01 000", "6409 01 014", "6130 01 001", "6138 01 1")
    assert s.state == "armed_away"
    assert s.last_event_text == "6138 01 1"


def test_outputs_do_not_overwrite_last_event() -> None:
    """770 output events update outputs only and report unchanged repeats."""
    s = run("3441 01 015")
    assert s.handle(ev("1770 01 004"))
    assert not s.handle(ev("1770 01 004"))
    assert s.handle(ev("3770 01 004"))
    assert s.outputs == {"004": False}
    assert s.last_event_text == "3441 01 015"


def test_missing_fields() -> None:
    """Events without code/qualifier/partition are recorded safely."""
    s = PimaSystemState()
    assert s.last_event_text is None
    assert s.handle(SIAEvent(event_type="602"))
    assert s.last_event_text == "602  "
    assert s.state is None


def test_restore() -> None:
    """Restore seeds only before live events; pending falls back to armed mode."""
    s = PimaSystemState()
    s.restore("pending", "armed_away")
    assert (s.state, s.armed_mode) == ("armed_away", "armed_away")
    s = PimaSystemState()
    s.restore("pending", None)
    assert s.state == "disarmed"
    s = PimaSystemState()
    s.restore("triggered", "armed_home")
    assert (s.state, s.armed_mode) == ("triggered", "armed_home")
    s = PimaSystemState()
    s.restore("armed_home", "bogus")
    assert (s.state, s.armed_mode) == ("armed_home", "armed_home")
    s = PimaSystemState()
    s.restore("unavailable", None)
    assert s.state is None
    s = run("1400 01 000")
    s.restore("armed_away", "armed_away")
    assert s.state == "disarmed"


# --- entities through Home Assistant ------------------------------------------


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        options={CONF_PORT: DEFAULT_LISTENING_PORT, CONF_ZONES: [{CONF_NAME: "Door"}]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _send(hass: HomeAssistant, entry: MockConfigEntry, *events: str) -> None:
    for text in events:
        await entry.runtime_data.coordinator.process_event(ev(text))
    await hass.async_block_till_done()


async def test_entities_follow_panel(hass: HomeAssistant) -> None:
    """Panel and last-event entities exist, follow events, and zones still work."""
    entry = await _setup(hass)
    assert hass.states.get(PANEL).state == "unknown"
    assert hass.states.get(LAST).state == "unknown"

    await _send(hass, entry, "3441 01 000", "1770 01 004", "1138 01 001")
    panel = hass.states.get(PANEL)
    assert panel.state == AlarmControlPanelState.PENDING
    assert panel.attributes["armed_mode"] == "armed_home"
    assert panel.attributes["user"] == "000"
    assert panel.attributes["partition"] == "01"
    assert panel.attributes["trigger_zone"] == "001"
    assert panel.attributes["trigger_code"] == "138"
    last = hass.states.get(LAST)
    assert last.state == "1138 01 001"
    assert last.attributes["outputs"] == {"004": True}
    assert last.attributes["code"] == "138"

    await _send(hass, entry, "1760 01 001")
    assert hass.states.get(ZONE1).state == "on"
    await _send(hass, entry, "1401 01 001")
    assert hass.states.get(PANEL).state == AlarmControlPanelState.DISARMED

    # The zone cleanup of the binary_sensor platform keeps the fork's entities.
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_ZONES: [{CONF_NAME: "Front"}]}
    )
    await hass.async_block_till_done()
    assert hass.states.get(PANEL) is not None
    assert hass.states.get(LAST) is not None


async def test_entry_delay_timeout(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Pending falls back to the armed mode when nothing follows the delay."""
    entry = await _setup(hass)
    await _send(hass, entry, "3409 01 014", "1138 01 001")
    assert hass.states.get(PANEL).state == "pending"
    freezer.tick(timedelta(seconds=ENTRY_DELAY_TIMEOUT_SECONDS + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(PANEL).state == "armed_away"


async def test_entry_delay_timer_cancelled(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A disarm cancels the timer; the timer firing after a state change is a no-op."""
    entry = await _setup(hass)
    await _send(hass, entry, "3409 01 014", "1138 01 001", "1401 01 001")
    freezer.tick(timedelta(seconds=ENTRY_DELAY_TIMEOUT_SECONDS + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(PANEL).state == "disarmed"

    coordinator = entry.runtime_data.coordinator
    await _send(hass, entry, "3409 01 014", "1138 01 001")
    coordinator._async_cancel_entry_delay()  # noqa: SLF001
    coordinator.system.end_pending()
    coordinator._async_entry_delay_expired(None)  # noqa: SLF001
    assert coordinator._cancel_entry_delay is None  # noqa: SLF001

    await _send(hass, entry, "1138 01 001")  # repeated while pending is a no-op
    await _send(hass, entry, "3409 01 014", "1138 01 001")
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert coordinator._cancel_entry_delay is None  # noqa: SLF001


async def test_event_without_type_ignored(hass: HomeAssistant) -> None:
    """An event without a code (e.g. a keep-alive) changes nothing."""
    entry = await _setup(hass)
    await entry.runtime_data.coordinator.process_event(SIAEvent(code="RP", ri="0"))
    await hass.async_block_till_done()
    assert hass.states.get(LAST).state == "unknown"


@pytest.mark.parametrize(
    ("stored", "armed_mode", "expected"),
    [
        ("armed_home", "armed_home", "armed_home"),
        ("pending", "armed_away", "armed_away"),
        ("triggered", "armed_home", "triggered"),
    ],
)
async def test_restore_after_restart(
    hass: HomeAssistant, stored: str, armed_mode: str, expected: str
) -> None:
    """The panel and the last event survive a restart."""
    mock_restore_cache(
        hass,
        [
            State(PANEL, stored, {"armed_mode": armed_mode}),
            State(LAST, "3441 01 000"),
        ],
    )
    await _setup(hass)
    panel = hass.states.get(PANEL)
    assert panel.state == expected
    assert panel.attributes["armed_mode"] == armed_mode
    assert hass.states.get(LAST).state == "3441 01 000"


async def test_restore_unknown_last_event(hass: HomeAssistant) -> None:
    """An unknown stored last event is not restored."""
    mock_restore_cache(hass, [State(LAST, "unknown")])
    await _setup(hass)
    assert hass.states.get(LAST).state == "unknown"
