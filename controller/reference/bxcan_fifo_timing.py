"""TC-03B29 deterministic bxCAN receive-FIFO timing replay.

Portable/offline reference only.

The STM32 bxCAN receive FIFO stores at most three pending messages. This model
replays only two abstract event types:

- ``arrival``: one filter-accepted CAN frame reaches the selected FIFO.
- ``service``: software releases one FIFO output mailbox after processing it.

If an arrival occurs at depth three, the synthetic replay records one overrun
event and one lost accepted frame. The depth remains three. ``receive_fifo_locked``
changes the modeled loss mechanism only:

- locked: the newly arriving frame is discarded;
- unlocked: a previously buffered frame is overwritten.

The replay counts synthetic loss events because the entire synthetic event
stream is known. Real hardware FOVR is a one-bit observation and does not by
itself prove the exact number or identity of lost frames.

Events at the same tick are processed in the caller-provided sequence order.
That choice is deliberate: without the target firmware/interrupt timing, this
reference does not invent whether a dequeue or a new frame wins a tie.

This model does not define Terps Racing CAN IDs, traffic rates, interrupt
priorities, service latency, FIFO routing, recovery policy, torque response, or
vehicle authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Iterable

FIFO_CAPACITY = 3
EVENT_KINDS = {"arrival", "service"}
SOURCE_KINDS = {"scenario", "team_verified"}


class FifoTimingError(ValueError):
    pass


def _tick(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise FifoTimingError(f"{name} must be a non-negative integer")
    return value


def _strict_bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise FifoTimingError(f"{name} must be boolean")
    return value


def _source_kind(value: object) -> str:
    if value not in SOURCE_KINDS:
        raise FifoTimingError("source_kind must be scenario or team_verified")
    return str(value)


@dataclass(frozen=True)
class FifoEvent:
    tick: int
    kind: str
    label: str = ""

    def checked(self) -> "FifoEvent":
        t = _tick(self.tick, "tick")
        if self.kind not in EVENT_KINDS:
            raise FifoTimingError("kind must be arrival or service")
        if not isinstance(self.label, str):
            raise FifoTimingError("label must be a string")
        return FifoEvent(t, self.kind, self.label)


@dataclass(frozen=True)
class FifoStep:
    sequence: int
    tick: int
    kind: str
    label: str
    depth_before: int
    depth_after: int
    full_after: bool
    overrun: bool
    lost_accepted_frame: bool
    loss_mechanism: str | None
    service_on_empty: bool


@dataclass(frozen=True)
class FifoReplay:
    schema: str
    capacity: int
    receive_fifo_locked: bool
    initial_depth: int
    final_depth: int
    max_depth: int
    arrival_count: int
    service_count: int
    effective_service_count: int
    empty_service_count: int
    synthetic_overrun_count: int
    synthetic_lost_frame_count: int
    first_overrun_tick: int | None
    safe_by_replay: bool
    steps: tuple[FifoStep, ...]
    source_kind: str

    team_traffic_proven: bool = False
    team_service_timing_proven: bool = False
    team_fifo_mode_proven: bool = False
    recovery_selected: bool = False
    torque_response_selected: bool = False
    shutdown_response_selected: bool = False
    vehicle_acceptance_proven: bool = False
    action_authority: bool = False

    def to_json(self) -> str:
        payload = asdict(self)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def replay_fifo(
    events: Iterable[FifoEvent],
    *,
    receive_fifo_locked: bool,
    initial_depth: int = 0,
    source_kind: str = "scenario",
) -> FifoReplay:
    locked = _strict_bool(receive_fifo_locked, "receive_fifo_locked")
    if type(initial_depth) is not int or not 0 <= initial_depth <= FIFO_CAPACITY:
        raise FifoTimingError("initial_depth must be an integer in [0, 3]")
    provenance = _source_kind(source_kind)

    checked = tuple(event.checked() if isinstance(event, FifoEvent) else None for event in events)
    if any(event is None for event in checked):
        raise FifoTimingError("events must contain FifoEvent instances")

    last_tick = -1
    for event in checked:
        if event.tick < last_tick:
            raise FifoTimingError("events must be ordered by nondecreasing tick")
        last_tick = event.tick

    depth = initial_depth
    max_depth = depth
    arrivals = 0
    services = 0
    effective_services = 0
    empty_services = 0
    overruns = 0
    first_overrun = None
    steps: list[FifoStep] = []

    for seq, event in enumerate(checked):
        before = depth
        overrun = False
        loss = False
        mechanism = None
        empty_service = False

        if event.kind == "arrival":
            arrivals += 1
            if depth < FIFO_CAPACITY:
                depth += 1
            else:
                overrun = True
                loss = True
                overruns += 1
                if first_overrun is None:
                    first_overrun = event.tick
                mechanism = (
                    "incoming_frame_discarded"
                    if locked
                    else "buffered_frame_overwritten"
                )
        else:
            services += 1
            if depth > 0:
                depth -= 1
                effective_services += 1
            else:
                empty_service = True
                empty_services += 1

        max_depth = max(max_depth, depth)
        steps.append(
            FifoStep(
                sequence=seq,
                tick=event.tick,
                kind=event.kind,
                label=event.label,
                depth_before=before,
                depth_after=depth,
                full_after=depth == FIFO_CAPACITY,
                overrun=overrun,
                lost_accepted_frame=loss,
                loss_mechanism=mechanism,
                service_on_empty=empty_service,
            )
        )

    return FifoReplay(
        schema="enme408-tc03b29-bxcan-fifo-replay/v1",
        capacity=FIFO_CAPACITY,
        receive_fifo_locked=locked,
        initial_depth=initial_depth,
        final_depth=depth,
        max_depth=max_depth,
        arrival_count=arrivals,
        service_count=services,
        effective_service_count=effective_services,
        empty_service_count=empty_services,
        synthetic_overrun_count=overruns,
        synthetic_lost_frame_count=overruns,
        first_overrun_tick=first_overrun,
        safe_by_replay=overruns == 0,
        steps=tuple(steps),
        source_kind=provenance,
    )


def periodic_service_events(start_tick: int, period_ticks: int, end_tick: int) -> tuple[FifoEvent, ...]:
    start = _tick(start_tick, "start_tick")
    period = _tick(period_ticks, "period_ticks")
    end = _tick(end_tick, "end_tick")
    if period == 0:
        raise FifoTimingError("period_ticks must be positive")
    if end < start:
        raise FifoTimingError("end_tick must be >= start_tick")
    return tuple(
        FifoEvent(tick, "service", f"service@{tick}")
        for tick in range(start, end + 1, period)
    )


def merge_events(
    *groups: Iterable[FifoEvent],
    same_tick_order: tuple[str, str] = ("arrival", "service"),
) -> tuple[FifoEvent, ...]:
    """Stable merge with an explicit tie policy for scenario construction."""
    if set(same_tick_order) != EVENT_KINDS or len(same_tick_order) != 2:
        raise FifoTimingError(
            "same_tick_order must contain arrival and service exactly once"
        )
    priority = {kind: i for i, kind in enumerate(same_tick_order)}
    flattened: list[tuple[int, FifoEvent]] = []
    seq = 0
    for group in groups:
        for event in group:
            if not isinstance(event, FifoEvent):
                raise FifoTimingError("groups must contain FifoEvent instances")
            checked = event.checked()
            flattened.append((seq, checked))
            seq += 1
    flattened.sort(key=lambda pair: (pair[1].tick, priority[pair[1].kind], pair[0]))
    return tuple(event for _, event in flattened)


def frozen_burst_average_counterexample() -> dict[str, object]:
    """Average offered load can be below service opportunity rate yet still overrun.

    Synthetic 100-tick horizon:
    - four accepted frames arrive at ticks 0, 1, 2, 3;
    - software has one service opportunity every 10 ticks starting at tick 10.

    Offered average over the horizon is 4/100 = 0.04 frame/tick.
    Service opportunities are 10/100 = 0.10 service/tick.

    The fourth frame still arrives before the first release and overruns a
    depth-three FIFO.
    """
    arrivals = tuple(
        FifoEvent(t, "arrival", f"frame-{i}")
        for i, t in enumerate((0, 1, 2, 3), 1)
    )
    services = periodic_service_events(10, 10, 100)
    events = merge_events(arrivals, services)
    result = replay_fifo(events, receive_fifo_locked=True)
    return {
        "schema": "enme408-tc03b29-burst-average-counterexample/v1",
        "scenario_only": True,
        "horizon_ticks": 100,
        "arrival_count": 4,
        "service_opportunity_count": len(services),
        "mean_arrivals_per_tick": 4 / 100,
        "mean_service_opportunities_per_tick": len(services) / 100,
        "replay": json.loads(result.to_json()),
        "team_traffic_proven": False,
        "action_authority": False,
    }


def frozen_same_tick_order_counterexample() -> dict[str, object]:
    """A full FIFO plus simultaneous arrival/service depends on event order."""
    arrival = (FifoEvent(10, "arrival", "new-frame"),)
    service = (FifoEvent(10, "service", "dequeue"),)

    arrival_first = replay_fifo(
        merge_events(arrival, service, same_tick_order=("arrival", "service")),
        receive_fifo_locked=True,
        initial_depth=FIFO_CAPACITY,
    )
    service_first = replay_fifo(
        merge_events(arrival, service, same_tick_order=("service", "arrival")),
        receive_fifo_locked=True,
        initial_depth=FIFO_CAPACITY,
    )
    return {
        "schema": "enme408-tc03b29-same-tick-order-counterexample/v1",
        "scenario_only": True,
        "arrival_first_overruns": not arrival_first.safe_by_replay,
        "service_first_overruns": not service_first.safe_by_replay,
        "arrival_first": json.loads(arrival_first.to_json()),
        "service_first": json.loads(service_first.to_json()),
        "team_ordering_proven": False,
        "action_authority": False,
    }
