"""Work hints wake the background workers in this process and never reach a browser."""

import asyncio
import threading
from types import SimpleNamespace
from uuid import UUID

import pytest
from uuid6 import uuid7

from app.systems.platform.events.hub import (
    EventHub,
    EventViewer,
    PostgresInvalidationListener,
)
from app.systems.platform.events.models import (
    WORK_ENTITIES,
    InvalidationEvent,
    parse_invalidation_payload,
    resync_event,
)
from app.systems.platform.events.publisher import MAX_INVALIDATIONS_PER_COMMIT, _bounded
from app.systems.platform.scheduling.work_signals import WorkSignals

ORGANIZATION = uuid7()
BOARD = uuid7()


def _hint(entity: str, org_id: UUID = ORGANIZATION, **values: object) -> str:
    return InvalidationEvent(entity, org_id=org_id, **values).to_transport_json()


class _Lanes:
    """Stands in for the trigger worker: records what each wake handed over."""

    def __init__(self) -> None:
        self.work: list[frozenset[UUID] | None] = []
        self.definitions: list[frozenset[UUID] | None] = []


def _signals() -> tuple[WorkSignals, _Lanes]:
    signals = WorkSignals()
    lanes = _Lanes()
    signals.attach_triggers(lanes.work.append, lanes.definitions.append)
    return signals, lanes


def test_work_hints_parse_with_their_organization_only() -> None:
    assert WORK_ENTITIES == frozenset({"work_scheduled", "work_triggers"})
    for entity in sorted(WORK_ENTITIES):
        event = parse_invalidation_payload(_hint(entity))
        assert (event.entity, event.org_id) == (entity, ORGANIZATION)
        assert event.to_json() == f'{{"entity":"{entity}"}}'


def test_no_subscriber_receives_a_work_hint_not_even_an_administrator() -> None:
    hub = EventHub()

    async def exercise() -> list[object]:
        administrator = await hub.subscribe(
            EventViewer(user_id=uuid7(), role="admin", module_ids=None, org_id=ORGANIZATION)
        )
        member = await hub.subscribe(
            EventViewer(user_id=uuid7(), role="member", module_ids=None, org_id=ORGANIZATION)
        )
        for entity in sorted(WORK_ENTITIES):
            await hub.publish_notification(_hint(entity))
        # A known entity still arrives, so the queue was open.
        await hub.publish_notification(_hint("departments"))
        received = [administrator.queue.get_nowait() for _ in range(administrator.queue.qsize())]
        received += [member.queue.get_nowait() for _ in range(member.queue.qsize())]
        return received

    received = asyncio.run(exercise())

    assert [event.entity for event in received] == ["departments", "departments"]


@pytest.mark.parametrize(
    ("payload", "probe", "reminders", "lanes", "definitions"),
    [
        pytest.param(_hint("work_scheduled"), True, False, [], [], id="scheduled-work"),
        pytest.param(
            _hint("work_triggers"), True, False, [frozenset({ORGANIZATION})], [],
            id="trigger-event",
        ),
        pytest.param(
            _hint("board_events", board_id=BOARD), True, True, [], [], id="event-or-reminder",
        ),
        pytest.param(_hint("board_posts", board_id=BOARD), True, False, [], [], id="post"),
        pytest.param(
            _hint("record_triggers"), False, False, [], [frozenset({ORGANIZATION})],
            id="trigger-definition",
        ),
        pytest.param(_hint("records"), False, False, [], [], id="unrelated"),
        pytest.param("not json", False, False, [], [], id="malformed"),
    ],
)
def test_each_hint_wakes_only_the_work_it_names(
    payload: str,
    probe: bool,
    reminders: bool,
    lanes: list[frozenset[UUID]],
    definitions: list[frozenset[UUID]],
) -> None:
    signals, attached = _signals()

    signals.notify(payload)
    wake = signals.take()

    assert not wake.everything
    assert wake.probe == (frozenset({ORGANIZATION}) if probe else frozenset())
    assert wake.reminders == (frozenset({ORGANIZATION}) if reminders else frozenset())
    assert attached.work == lanes
    assert attached.definitions == definitions
    # Taking a wake consumes it.
    assert signals.take() == signals.take()
    assert not signals.take().probe


def test_a_commit_over_the_limit_becomes_a_resync_that_wakes_every_organization() -> None:
    events = [
        InvalidationEvent("work_scheduled", org_id=uuid7())
        for _ in range(MAX_INVALIDATIONS_PER_COMMIT + 1)
    ]
    (sent,) = _bounded(events)
    assert sent == resync_event()
    signals, attached = _signals()

    signals.notify(sent.to_transport_json())
    wake = signals.take()

    assert wake.everything
    assert attached.work == [None] and attached.definitions == [None]


def test_a_wake_ends_the_scheduler_sleep_at_once_and_a_stale_flag_never_sleeps_through() -> None:
    signals = WorkSignals()
    woke = threading.Event()

    def sleeper() -> None:
        signals.sleep(30)
        woke.set()

    thread = threading.Thread(target=sleeper)
    thread.start()
    signals.notify(_hint("work_scheduled"))
    # A hang guard only: the sleep ends on the wake, not on its 30 s timeout.
    assert woke.wait(10)
    thread.join(10)
    assert signals.take().probe == frozenset({ORGANIZATION})


def test_the_listener_hands_each_notification_to_the_workers_and_wakes_all_on_connect() -> None:
    signals, attached = _signals()
    delivered = threading.Event()

    class Connection:
        def __enter__(self) -> "Connection":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _statement: str) -> None:
            return None

        def close(self) -> None:
            return None

        def notifies(self, **_kwargs: object):
            calls.append(1)
            if len(calls) == 1:
                yield SimpleNamespace(payload=_hint("work_triggers"))
            else:
                # The listener asked again, so it handled the first notification.
                delivered.set()
                listener._stop.wait(0.5)

    calls: list[int] = []

    listener = PostgresInvalidationListener(
        EventHub(),
        "postgresql://user:secret@db/slateops",
        connect=lambda *_a, **_k: Connection(),
        connect_timeout_seconds=3,
        statement_timeout_ms=15_000,
        work_signals=signals,
    )
    listener.start()
    try:
        assert delivered.wait(10)
    finally:
        assert listener.stop()

    # The connect woke everything (work may have been missed while disconnected); the
    # notification then handed its organization to the lanes.
    assert attached.work[:2] == [None, frozenset({ORGANIZATION})]
    assert signals.take().everything


def test_a_failing_work_signal_never_stops_the_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    # P3: only database errors restart the connection; any other error in a wake must
    # not end the thread, or no page would get another invalidation.
    import app.systems.platform.events.hub as hub_module

    asked = threading.Event()
    published: list[object] = []
    reasons: list[object] = []
    monkeypatch.setattr(
        hub_module,
        "log_event",
        lambda *_a, **values: reasons.append((values.get("reason_code"), values.get("cause"))),
    )

    class Broken:
        def wake_all(self) -> None:
            raise RuntimeError("wake failed")

        def notify(self, _payload: object) -> None:
            raise RuntimeError("notify failed")

    hub = SimpleNamespace(
        publish_resync_from_listener=lambda: published.append("resync"),
        publish_from_listener=published.append,
    )
    calls: list[int] = []

    class Connection:
        def __enter__(self) -> "Connection":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _statement: str) -> None:
            return None

        def close(self) -> None:
            return None

        def notifies(self, **_kwargs: object):
            calls.append(1)
            if len(calls) == 1:
                yield SimpleNamespace(payload=_hint("work_triggers"))
            else:
                # The listener asked again, so the failed wake did not end it.
                asked.set()
                listener._stop.wait(0.5)

    listener = PostgresInvalidationListener(
        hub,
        "postgresql://user:secret@db/slateops",
        connect=lambda *_a, **_k: Connection(),
        connect_timeout_seconds=3,
        statement_timeout_ms=15_000,
        work_signals=Broken(),
    )
    listener.start()
    try:
        assert asked.wait(10)
    finally:
        assert listener.stop()

    assert published == ["resync", _hint("work_triggers")]
    # The exception's class only (NB5), never its message.
    assert reasons == [
        ("work_signal_failed", "RuntimeError"), ("work_signal_failed", "RuntimeError")
    ]
