import json
import random
import unittest

from can_tx_age_evidence import (
    HALF_RANGE,
    MAX_COUNTER,
    TimebaseEvidence,
    TxAgeEvidenceError,
    TxPublicationAgeObservation,
    assess_publication_age,
    frozen_fresh_but_superseded_counterexample,
    frozen_wrap_counterexample,
)


def tb(**overrides):
    values = dict(
        domain="scenario_hal_tick_ms",
        width_bits=32,
        ticks_per_second=1000.0,
        monotonic=True,
        can_pause=False,
        source_kind="scenario",
    )
    values.update(overrides)
    return TimebaseEvidence(**values)


def obs(**overrides):
    values = dict(
        command_seq=1,
        latest_intent_seq_at_terminal=1,
        intent_tick=100,
        terminal_tick=120,
        max_age_ticks=50,
        terminal_result="transmitted",
        command_bound_terminal_evidence=True,
        timebase=tb(),
        max_age_source_kind="scenario",
    )
    values.update(overrides)
    return TxPublicationAgeObservation(**values)


class ValidationTests(unittest.TestCase):
    def test_u32_bounds(self):
        self.assertEqual(
            assess_publication_age(obs(intent_tick=0, terminal_tick=MAX_COUNTER)).status,
            "ambiguous_age",
        )

    def test_tick_overflow_rejected(self):
        with self.assertRaises(TxAgeEvidenceError):
            assess_publication_age(obs(terminal_tick=MAX_COUNTER + 1))

    def test_sequence_order_rejected(self):
        with self.assertRaises(TxAgeEvidenceError):
            assess_publication_age(
                obs(command_seq=3, latest_intent_seq_at_terminal=2)
            )

    def test_max_age_half_range_rejected(self):
        with self.assertRaises(TxAgeEvidenceError):
            assess_publication_age(obs(max_age_ticks=HALF_RANGE))

    def test_bad_terminal_result_rejected(self):
        with self.assertRaises(TxAgeEvidenceError):
            assess_publication_age(obs(terminal_result="pending"))

    def test_bad_timebase_width_rejected(self):
        with self.assertRaises(TxAgeEvidenceError):
            assess_publication_age(obs(timebase=tb(width_bits=16)))

    def test_nonfinite_tick_rate_rejected(self):
        with self.assertRaises(TxAgeEvidenceError):
            assess_publication_age(
                obs(timebase=tb(ticks_per_second=float("nan")))
            )

    def test_bad_source_kind_rejected(self):
        with self.assertRaises(TxAgeEvidenceError):
            assess_publication_age(obs(max_age_source_kind="guessed"))


class AgeTests(unittest.TestCase):
    def test_nominal_within_limit(self):
        r = assess_publication_age(obs())
        self.assertEqual(r.status, "publication_within_age_limit")
        self.assertEqual(r.age_ticks, 20)
        self.assertAlmostEqual(r.age_seconds, 0.020)
        self.assertTrue(r.publication_within_age_limit)

    def test_exact_limit_is_within(self):
        r = assess_publication_age(obs(terminal_tick=150))
        self.assertEqual(r.age_ticks, 50)
        self.assertTrue(r.publication_within_age_limit)

    def test_age_over_limit(self):
        r = assess_publication_age(obs(terminal_tick=151))
        self.assertEqual(r.status, "publication_age_exceeds_limit")
        self.assertFalse(r.publication_within_age_limit)

    def test_wraparound_age(self):
        r = assess_publication_age(
            obs(intent_tick=0xFFFFFFF0, terminal_tick=0x20)
        )
        self.assertEqual(r.age_ticks, 48)
        self.assertTrue(r.publication_within_age_limit)

    def test_half_range_is_ambiguous(self):
        r = assess_publication_age(
            obs(intent_tick=0, terminal_tick=HALF_RANGE)
        )
        self.assertEqual(r.status, "ambiguous_age")
        self.assertIsNone(r.age_ticks)

    def test_future_or_old_sample_is_ambiguous(self):
        r = assess_publication_age(
            obs(intent_tick=1000, terminal_tick=999)
        )
        self.assertEqual(r.status, "ambiguous_age")

    def test_unbound_terminal_event_has_no_age(self):
        r = assess_publication_age(
            obs(command_bound_terminal_evidence=False)
        )
        self.assertEqual(r.status, "terminal_event_unbound_to_command")
        self.assertIsNone(r.age_ticks)

    def test_nontransmit_terminal_has_no_publication_age(self):
        r = assess_publication_age(obs(terminal_result="arbitration_lost"))
        self.assertEqual(r.status, "terminal_nonpublication")
        self.assertIsNone(r.age_ticks)

    def test_pausing_timebase_invalid(self):
        r = assess_publication_age(obs(timebase=tb(can_pause=True)))
        self.assertEqual(r.status, "invalid_timebase")
        self.assertEqual(r.reason, "timebase_can_pause")

    def test_nonmonotonic_timebase_invalid(self):
        r = assess_publication_age(obs(timebase=tb(monotonic=False)))
        self.assertEqual(r.status, "invalid_timebase")
        self.assertEqual(r.reason, "timebase_not_monotonic")

    def test_team_ready_needs_both_provenance_fields(self):
        r = assess_publication_age(
            obs(
                timebase=tb(source_kind="team_verified"),
                max_age_source_kind="team_verified",
            )
        )
        self.assertTrue(r.ready_for_team_timing_use)

    def test_scenario_not_ready_for_team_use(self):
        self.assertFalse(assess_publication_age(obs()).ready_for_team_timing_use)

    def test_seeded_wrap_equivalence(self):
        rng = random.Random(408)
        for _ in range(5000):
            start = rng.randint(0, MAX_COUNTER)
            delta = rng.randint(0, 1_000_000)
            now = (start + delta) & MAX_COUNTER
            r = assess_publication_age(
                obs(
                    intent_tick=start,
                    terminal_tick=now,
                    max_age_ticks=1_000_000,
                )
            )
            self.assertEqual(r.age_ticks, delta)
            self.assertTrue(r.publication_within_age_limit)


class SupersessionTests(unittest.TestCase):
    def test_latest_publication_not_superseded(self):
        r = assess_publication_age(obs())
        self.assertFalse(r.superseded_publication_observed)

    def test_older_transmitted_command_is_superseded(self):
        r = assess_publication_age(
            obs(command_seq=1, latest_intent_seq_at_terminal=2)
        )
        self.assertTrue(r.superseded_publication_observed)

    def test_supersession_and_age_are_orthogonal(self):
        c = frozen_fresh_but_superseded_counterexample()
        self.assertTrue(c["publication_within_age_limit"])
        self.assertTrue(c["superseded_publication_observed"])

    def test_nontransmit_is_not_superseded_publication(self):
        r = assess_publication_age(
            obs(
                command_seq=1,
                latest_intent_seq_at_terminal=2,
                terminal_result="transmit_error",
            )
        )
        self.assertFalse(r.superseded_publication_observed)

    def test_unbound_success_is_not_supersession_proof(self):
        r = assess_publication_age(
            obs(
                command_seq=1,
                latest_intent_seq_at_terminal=2,
                command_bound_terminal_evidence=False,
            )
        )
        self.assertFalse(r.superseded_publication_observed)


class BoundaryTests(unittest.TestCase):
    def test_wrap_counterexample(self):
        c = frozen_wrap_counterexample()
        self.assertFalse(c["naive_terminal_ge_intent"])
        self.assertEqual(c["modular_age_ticks"], 48)
        self.assertTrue(c["publication_within_age_limit"])

    def test_no_policy_or_vehicle_authority(self):
        r = assess_publication_age(
            obs(command_seq=1, latest_intent_seq_at_terminal=2)
        )
        self.assertFalse(r.abort_policy_selected)
        self.assertFalse(r.retransmission_policy_change_selected)
        self.assertFalse(r.inverter_delivery_proven)
        self.assertFalse(r.inverter_application_proven)
        self.assertFalse(r.torque_response_selected)
        self.assertFalse(r.shutdown_response_selected)
        self.assertFalse(r.vehicle_acceptance_proven)
        self.assertFalse(r.action_authority)

    def test_deterministic_json(self):
        r = assess_publication_age(obs())
        self.assertEqual(r.to_json(), r.to_json())
        self.assertFalse(json.loads(r.to_json())["action_authority"])


if __name__ == "__main__":
    unittest.main()
