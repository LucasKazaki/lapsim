"""Two ordered finite laps, sharing one continuous accepted trajectory.

Each gate list is the *same* canonical finite contract, instantiated once per lap.
Global ticks and pack energy are never rebased by the ledger. A new list is
armed at the prior accepted confirmation boundary, with its actual signed
distances/position/energy; only the expected gate index changes. A lap is not
issued for projection, a mere touch, or a conflicting stock boundary fault.
The single-lap observer is the crossing owner.
"""
from copy import deepcopy
from .finite_gate_observer import FiniteGateObserver


class CyclicGateLedger:
    def __init__(self, contract, target_laps=2):
        if type(target_laps) is not int or target_laps != 2:
            raise ValueError("Finite-round mode requires exactly two laps")
        self._contract = deepcopy(contract)
        self._active = FiniteGateObserver(self._contract)
        self.target_laps = target_laps
        self.gates_per_lap = self._active.n
        self.n = self.gates_per_lap * target_laps
        self._rows = []
        self._closed = []
        self._failure = None
        self._start_energy = None

    @property
    def completed_count(self):
        return len(self._rows)

    @property
    def failure(self):
        return deepcopy(self._failure)

    @property
    def done(self):
        return self.completed_count == self.target_laps and self._failure is None

    @property
    def finish(self):
        return deepcopy(self._rows[-1]["finish_event"]) if self.done else None

    @property
    def confirmed_gate_count(self):
        return self.gates_per_lap * self.completed_count + (
            len(self._active.events) if self.completed_count < self.target_laps else 0
        )

    @property
    def events(self):
        events = [
            {**event, "lap": row["lap"]}
            for row in self._rows for event in row["gate_events"]
        ]
        if self.completed_count < self.target_laps:
            events.extend({**event, "lap": self.completed_count + 1} for event in self._active.events)
        return deepcopy(events)

    @property
    def rows(self):
        return deepcopy(self._rows)

    def observe(self, tick, xy, energy_j, projected_station_m, *, boundary_ok=True):
        if self.done or self._failure is not None:
            raise ValueError("Cannot append after finite round terminal")
        if type(boundary_ok) is not bool:
            raise ValueError("Boolean accepted stock boundary required")
        old = self._active
        # Projection remains unwrapped in the actual runner; the observer's
        # lap-relative station is a missed-prerequisite diagnostic only.
        local_station = float(projected_station_m) - self.completed_count * old.length
        passed = old.observe(tick, xy, energy_j, local_station)
        if self._start_energy is None:
            self._start_energy = old.energy
        if old.failure is not None or not boundary_ok:
            fault = old.failure or {
                "reason": "stock_boundary_rejected", "accepted_tick": tick,
                "expected_gate": old.next_gate, "detail": None,
            }
            self._failure = {**deepcopy(fault), "lap": self.completed_count + 1,
                             "stock_boundary_ok": boundary_ok}
            return False
        if not passed:
            return False
        finish, signed, position, pack = old.finish, old.prev, old.xy, old.energy
        if finish is None or signed is None or position is None or pack is None or self._start_energy is None:
            raise ValueError("Confirmed lap lacks its actual accepted seam state")
        event = deepcopy(finish)
        if (old.next_gate != old.n + 1 or signed[-1] <= 0.
                or any(v["inside"] for v in old.pending.values())):
            # v35 refuses ambiguous additional in-interval finite events and
            # unconfirmed exact-plane touches at a finish; fail closed here
            # rather than arming a second ledger from an ambiguous sample.
            self._failure = {
                "reason": "ambiguous_seam_carry", "lap": self.completed_count + 1,
                "accepted_tick": tick, "expected_gate": old.next_gate,
                "stock_boundary_ok": boundary_ok, "detail": event,
            }
            return False
        prior = self._rows[-1] if self._rows else None
        time0 = prior["finish_event"]["time_s"] if prior else 0.
        energy0 = prior["finish_event"]["interpolated_pack_energy_j"] if prior else self._start_energy
        energy1 = event["interpolated_pack_energy_j"]
        lap = self.completed_count + 1
        self._rows.append({
            "lap": lap, "lap_time_s": event["time_s"] - time0,
            "cumulative_crossing_time_s": event["time_s"],
            "start_interpolated_pack_energy_j": energy0,
            "finish_interpolated_pack_energy_j": energy1,
            "lap_net_energy_wh": (energy0 - energy1) / 3600.,
            "cumulative_crossing_net_energy_wh": (self._start_energy - energy1) / 3600.,
            "finish_event": event, "gate_events": deepcopy(old.events),
            "confirming_accepted_tick": tick, "confirming_pack_energy_j": pack,
            "confirming_xy_m": position.tolist(),
            "confirmed_gate_count": old.n,
        })
        self._closed.append(deepcopy(old.receipt()))
        if lap < self.target_laps:
            new = FiniteGateObserver(self._contract)
            # This is an observation handoff, not a vehicle respawn, a second
            # observation at this tick, or a crossing from the projection.
            new.prev = signed.copy()
            new.xy = position.copy()
            new.energy = pack
            new.tick = old.tick
            # No unresolved *finite* event can be present. Already excluded
            # remote extensions belong to the old lap; their signed samples
            # are retained but they never become credited next-lap events.
            self._active = new
        return self.done

    def receipt(self):
        active = self._active.receipt()
        return {
            "schema": "lapsim.ordered-finite-round.v1",
            "geometry_sha256": self._active.geometry,
            "corridor_sha256": self._active.corridor,
            "target_laps": self.target_laps,
            "accepted_lap_count": self.completed_count,
            "gates_per_lap": self.gates_per_lap, "gate_count": self.n,
            "confirmed_gate_count": self.confirmed_gate_count,
            "events": self.events, "lap_rows": self.rows,
            "closed_lap_receipts": deepcopy(self._closed),
            "incomplete_lap": None if self.done else {
                "lap": self.completed_count + 1, "observer": deepcopy(active),
                "lap_time_s": None,
            },
            "last_accepted_tick": active["last_accepted_tick"],
            "last_signed_finish_m": active["last_signed_finish_m"],
            "first_projected_seam": active["first_projected_seam"],
            "finish_event": self.finish, "failure": self.failure,
            "ordered_finite_complete": self.done,
            "scope": "Continuous accepted numerical CG chords in same pinned finite apertures; "
                     "one credit per completed ordered list with existing stock accepted-boundary checks. "
                     "Independent full body, tire, reserve and whole-round checks remain required.",
        }
