"""Wake the scheduling worker and the trigger lanes of this process on committed work.

The process's invalidation listener (``platform/events/hub.py``) hands every NOTIFY payload
here before the event hub sees it. A hint marks an organization for the scheduler's due
probe, hands it to the trigger lanes, or both. A ``resync`` (a lost publish, more than 64
public events in one commit) and a listener (re)connect wake everything: work may have been
committed while no listener heard it. Nothing here touches the database.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.systems.platform.events.models import RESYNC_ENTITY, parse_invalidation_payload

# A trigger lane hand-off: the organizations to claim in, or None for every organization.
Handoff = Callable[[frozenset[UUID] | None], None]

WORK_SCHEDULED = "work_scheduled"
WORK_TRIGGERS = "work_triggers"
# Audited entities whose change can make scheduled work due: posts publish through
# ``scheduled_work``; an event or reminder (``board_event_reminders`` publishes as
# ``board_events``) needs its next reminder occurrence materialized.
_PROBE_ENTITIES = frozenset({WORK_SCHEDULED, WORK_TRIGGERS, "board_posts", "board_events"})
_REMINDER_ENTITIES = frozenset({"board_events"})
_TRIGGER_DEFINITIONS = "record_triggers"


@dataclass(frozen=True, slots=True)
class WorkWake:
    """What the scheduler must do on its next round; empty when nothing was signalled."""

    everything: bool = False
    probe: frozenset[UUID] = frozenset()
    reminders: frozenset[UUID] = frozenset()


class WorkSignals:
    """Thread-safe wake state shared by the listener, the scheduler and the trigger lanes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # The one event the scheduler sleeps on; ``interrupt`` (its stop) sets it too.
        self._wakeup = threading.Event()
        self._everything = False
        self._probe: set[UUID] = set()
        self._reminders: set[UUID] = set()
        self._lanes: Handoff | None = None
        self._definitions: Handoff | None = None

    def attach_triggers(self, lanes: Handoff, definitions: Handoff) -> None:
        """Connect the trigger worker: claim work, and re-read schedule definitions."""

        with self._lock:
            self._lanes = lanes
            self._definitions = definitions

    def notify(self, payload: object) -> None:
        """Route one NOTIFY payload; a payload the hub would refuse wakes nothing."""

        try:
            event = parse_invalidation_payload(payload)
        except ValueError:
            return
        if event.entity == RESYNC_ENTITY:
            self.wake_all()
            return
        org_id = event.org_id
        if org_id is None:
            return
        if event.entity == WORK_TRIGGERS:
            self.hand_triggers(frozenset({org_id}))
        if event.entity == _TRIGGER_DEFINITIONS:
            self._hand(self._definitions, frozenset({org_id}))
        if event.entity in _PROBE_ENTITIES:
            self.mark(org_id, reminders=event.entity in _REMINDER_ENTITIES)

    def wake_all(self) -> None:
        with self._lock:
            self._everything = True
            lanes, definitions = self._lanes, self._definitions
        self._wakeup.set()
        self._hand(lanes, None)
        self._hand(definitions, None)

    def mark(self, org_id: UUID, *, reminders: bool = False) -> None:
        """Ask the scheduler to probe this organization at once."""

        with self._lock:
            self._probe.add(org_id)
            if reminders:
                self._reminders.add(org_id)
        self._wakeup.set()

    def hand_triggers(self, organizations: frozenset[UUID] | None) -> None:
        """Wake the trigger lanes for these organizations (None: every organization)."""

        with self._lock:
            lanes = self._lanes
        self._hand(lanes, organizations)

    def take(self) -> WorkWake:
        """Return and clear what was signalled since the last take."""

        with self._lock:
            wake = WorkWake(self._everything, frozenset(self._probe), frozenset(self._reminders))
            self._everything = False
            self._probe.clear()
            self._reminders.clear()
        return wake

    def sleep(self, seconds: float) -> None:
        """Sleep until a wake or the timeout; the caller takes the wake afterwards."""

        self._wakeup.wait(seconds)
        # A mark after this clear sets the event again; one before it is in the sets.
        self._wakeup.clear()

    def interrupt(self) -> None:
        """End the current or next sleep (the scheduler's stop)."""

        self._wakeup.set()

    @staticmethod
    def _hand(target: Handoff | None, organizations: frozenset[UUID] | None) -> None:
        if target is not None:
            target(organizations)
