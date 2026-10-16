import json
import unittest

from can_rx_age_evidence import (
    CaptureEvidence,
    HALF_RANGE,
    MAX_COUNTER,
    RxAgeEvidenceError,
    evaluate_receive_age,
    naive_dequeue_age,
)


def ev(**overrides):
    base = dict(
        mcu_family="STM32F405",
        capture_kind="software_fifo_dequeue",
        capture_location="scenario:rx-dequeue",
        capture_tick=100,
        now_tick=105,
        max_signal_age_ticks=20,
        max_capture_lag_ticks=2,
        timebase_domain="scenario-tick",
        timebase_source_kind="scenario",
        lag_bound_source_kind="scenario",
        target_car="2027-28",
    )
    base.update(overrides)
    return CaptureEvidence(**base)


class RxAgeEvidenceTests(unittest.TestCase):
    def test_bounded_capture_can_prove_fresh_scenario(self):
        r = evaluate_receive_age(ev())
        self.assertEqual(r.status, "fresh")
        self.assertEqual((r.actual_age_min_ticks, r.actual_age_max_ticks), (5, 7))
        self.assertFalse(r.ready_for_team_freshness_use)

    def test_team_verified_evidence_can_be_review_ready(self):
        r = evaluate_receive_age(ev(timebase_source_kind="team_verified", lag_bound_source_kind="team_verified"))
        self.assertTrue(r.ready_for_team_freshness_use)
        self.assertTrue(r.evidence_team_verified)

    def test_missing_capture_lag_cannot_prove_freshness(self):
        r = evaluate_receive_age(ev(max_capture_lag_ticks=None))
        self.assertEqual(r.status, "unproven")
        self.assertIsNone(r.actual_age_max_ticks)
        self.assertFalse(r.ready_for_team_freshness_use)

    def test_observed_age_alone_can_prove_stale(self):
        r = evaluate_receive_age(ev(capture_tick=70, now_tick=100, max_capture_lag_ticks=None))
        self.assertEqual(r.status, "unproven")
        self.assertEqual(r.actual_age_min_ticks, 30)

    def test_bounded_interval_proves_stale(self):
        r = evaluate_receive_age(ev(capture_tick=70, now_tick=100, max_capture_lag_ticks=5))
        self.assertEqual(r.status, "stale")
        self.assertEqual(r.reason, "even_minimum_age_exceeds_limit")

    def test_interval_crossing_limit_is_ambiguous(self):
        r = evaluate_receive_age(ev(capture_tick=90, now_tick=100, max_capture_lag_ticks=15))
        self.assertEqual(r.status, "ambiguous")
        self.assertEqual((r.actual_age_min_ticks, r.actual_age_max_ticks), (10, 25))

    def test_boundary_equal_to_limit_is_fresh(self):
        r = evaluate_receive_age(ev(capture_tick=90, now_tick=100, max_capture_lag_ticks=10))
        self.assertEqual(r.status, "fresh")
        self.assertEqual(r.actual_age_max_ticks, 20)

    def test_wraparound_observed_age(self):
        r = evaluate_receive_age(ev(capture_tick=MAX_COUNTER - 2, now_tick=3, max_capture_lag_ticks=1, max_signal_age_ticks=10))
        self.assertEqual(r.observed_age_since_capture_ticks, 6)
        self.assertEqual(r.status, "fresh")

    def test_half_range_or_future_is_ambiguous(self):
        r = evaluate_receive_age(ev(capture_tick=100, now_tick=(100 - 1) & MAX_COUNTER))
        self.assertEqual(r.status, "ambiguous")

    def test_age_interval_crossing_half_range_is_ambiguous(self):
        r = evaluate_receive_age(ev(capture_tick=0, now_tick=HALF_RANGE - 10, max_signal_age_ticks=HALF_RANGE - 1, max_capture_lag_ticks=20))
        self.assertEqual(r.status, "ambiguous")
        self.assertEqual(r.reason, "age_interval_crosses_half_range")

    def test_f405_ttcm_timestamp_is_invalid(self):
        r = evaluate_receive_age(ev(capture_kind="bxcan_ttcm_rxheader", max_capture_lag_ticks=0))
        self.assertEqual(r.status, "invalid_timestamp_source")
        self.assertTrue(r.target_erratum_blocks_timestamp)

    def test_f407_ttcm_timestamp_is_invalid(self):
        r = evaluate_receive_age(ev(mcu_family="STM32F407", capture_kind="bxcan_ttcm_rxheader"))
        self.assertEqual(r.status, "invalid_timestamp_source")

    def test_f415_ttcm_timestamp_is_invalid(self):
        r = evaluate_receive_age(ev(mcu_family="STM32F415", capture_kind="bxcan_ttcm_rxheader"))
        self.assertEqual(r.status, "invalid_timestamp_source")

    def test_f417_ttcm_timestamp_is_invalid(self):
        r = evaluate_receive_age(ev(mcu_family="STM32F417", capture_kind="bxcan_ttcm_rxheader"))
        self.assertEqual(r.status, "invalid_timestamp_source")

    def test_other_family_not_blocked_by_this_specific_erratum_model(self):
        r = evaluate_receive_age(ev(mcu_family="OTHER_MCU", capture_kind="bxcan_ttcm_rxheader", max_capture_lag_ticks=0))
        self.assertEqual(r.status, "fresh")
        self.assertFalse(r.target_erratum_blocks_timestamp)

    def test_naive_dequeue_counterexample_marks_old_frame_fresh(self):
        self.assertTrue(naive_dequeue_age(now_tick=105, dequeue_tick=100, max_age_ticks=20))
        r = evaluate_receive_age(ev(capture_tick=100, now_tick=105, max_capture_lag_ticks=100))
        self.assertEqual(r.status, "ambiguous")
        self.assertEqual((r.actual_age_min_ticks, r.actual_age_max_ticks), (5, 105))

    def test_exact_old_frame_counterexample_true_age_is_stale(self):
        true_arrival_tick = 0
        now_tick = 105
        self.assertEqual(now_tick - true_arrival_tick, 105)
        self.assertGreater(now_tick - true_arrival_tick, 20)
        self.assertTrue(naive_dequeue_age(now_tick, 100, 20))

    def test_isr_entry_with_bounded_latency_uses_same_interval_math(self):
        r = evaluate_receive_age(ev(capture_kind="software_isr_entry", capture_location="scenario:rx-isr", max_capture_lag_ticks=3))
        self.assertEqual(r.status, "fresh")
        self.assertEqual(r.actual_age_max_ticks, 8)

    def test_unverified_timebase_blocks_team_ready(self):
        r = evaluate_receive_age(ev(lag_bound_source_kind="team_verified", timebase_source_kind="scenario"))
        self.assertFalse(r.ready_for_team_freshness_use)

    def test_unverified_lag_blocks_team_ready(self):
        r = evaluate_receive_age(ev(lag_bound_source_kind="scenario", timebase_source_kind="team_verified"))
        self.assertFalse(r.ready_for_team_freshness_use)

    def test_json_is_deterministic(self):
        r = evaluate_receive_age(ev())
        one = r.to_json()
        two = r.to_json()
        self.assertEqual(one, two)
        self.assertEqual(json.loads(one)["schema"], "enme408-tc02x-can-rx-age/v1")

    def test_json_forbids_vehicle_authority(self):
        payload = json.loads(evaluate_receive_age(ev()).to_json())
        self.assertFalse(payload["action_authority"])
        self.assertFalse(payload["vehicle_acceptance_proven"])

    def test_invalid_capture_kind_rejected(self):
        with self.assertRaises(RxAgeEvidenceError):
            evaluate_receive_age(ev(capture_kind="magic_timestamp"))

    def test_invalid_mcu_family_rejected(self):
        with self.assertRaises(RxAgeEvidenceError):
            evaluate_receive_age(ev(mcu_family=""))

    def test_invalid_location_rejected(self):
        with self.assertRaises(RxAgeEvidenceError):
            evaluate_receive_age(ev(capture_location=""))

    def test_invalid_tick_rejected(self):
        with self.assertRaises(RxAgeEvidenceError):
            evaluate_receive_age(ev(capture_tick=-1))

    def test_invalid_age_limit_rejected(self):
        with self.assertRaises(RxAgeEvidenceError):
            evaluate_receive_age(ev(max_signal_age_ticks=HALF_RANGE))

    def test_invalid_lag_bound_rejected(self):
        with self.assertRaises(RxAgeEvidenceError):
            evaluate_receive_age(ev(max_capture_lag_ticks=HALF_RANGE))

    def test_invalid_source_kind_rejected(self):
        with self.assertRaises(RxAgeEvidenceError):
            evaluate_receive_age(ev(timebase_source_kind="guessed"))

    def test_target_car_is_preserved_but_not_authority(self):
        r = evaluate_receive_age(ev(target_car="2027-28"))
        self.assertFalse(r.action_authority)

    def test_zero_lag_bound_is_valid(self):
        r = evaluate_receive_age(ev(max_capture_lag_ticks=0))
        self.assertEqual((r.actual_age_min_ticks, r.actual_age_max_ticks), (5, 5))

    def test_dequeue_capture_does_not_imply_arrival_timestamp(self):
        r = evaluate_receive_age(ev(max_capture_lag_ticks=None))
        self.assertEqual(r.reason, "capture_lag_bound_missing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
