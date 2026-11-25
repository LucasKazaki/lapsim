"""Round-state semantics only; actual physics proof lives in verify_round.py."""
import unittest
from lapsim.experiments.finite_cycle_ledger import CyclicGateLedger
from lapsim.experiments.finite_gate_observer import FiniteGateObserver
from test_finite_observer import PREFIX, contract, gate

FIRST = PREFIX + [((.2, 0.), 12.2)]
SECOND = [(xy, s + 12.) for xy, s in FIRST[1:]]
TWICE = FIRST + SECOND


def append(ledger, seq, start=0, reject_tick=None):
    for i, (xy, s) in enumerate(seq, start):
        ledger.observe(i, xy, 1000. - i, s, boundary_ok=i != reject_tick)
        if ledger.done or ledger.failure:
            break
    return ledger


def trial(seq, reject_tick=None):
    return append(CyclicGateLedger(contract()), seq, reject_tick=reject_tick)


class CyclicTests(unittest.TestCase):
    def check_failed(self, ledger, reason, completed=1):
        self.assertFalse(ledger.done)
        self.assertEqual(ledger.completed_count, completed)
        self.assertEqual(ledger.failure["reason"], reason)
        self.assertEqual(ledger.failure["lap"], completed + 1)
        self.assertIsNone(ledger.receipt()["finish_event"])
        self.assertIsNone(ledger.receipt()["incomplete_lap"]["lap_time_s"])

    def test_two_separate_complete_gate_lists_and_clock(self):
        a = trial(TWICE)
        self.assertTrue(a.done)
        self.assertEqual([z["lap"] for z in a.rows], [1, 2])
        self.assertEqual([e["gate"] for e in a.events], list(range(1, 6)) * 2)
        self.assertEqual([e["lap"] for e in a.events], [1] * 5 + [2] * 5)
        self.assertEqual(a.confirmed_gate_count, 10)
        self.assertEqual(a.finish["interval_end_tick"], 28)
        self.assertEqual(a.finish["time_s"], .275)
        self.assertIsNone(a.receipt()["incomplete_lap"])

    def test_first_finish_time_identical_to_v35(self):
        ref = FiniteGateObserver(contract())
        for i, (xy, s) in enumerate(FIRST):
            ref.observe(i, xy, 1000. - i, s)
        a = trial(TWICE)
        self.assertEqual(a.rows[0]["finish_event"], ref.finish)
        self.assertEqual(a.rows[0]["gate_events"], ref.events)
        self.assertEqual(a.rows[0]["lap_time_s"], ref.finish["time_s"])

    def test_energy_interpolation_telescopes(self):
        a = trial(TWICE)
        first, second = a.rows
        self.assertEqual(first["finish_interpolated_pack_energy_j"], 986.5)
        self.assertEqual(second["start_interpolated_pack_energy_j"], 986.5)
        self.assertEqual(second["finish_interpolated_pack_energy_j"], 972.5)
        self.assertAlmostEqual(first["lap_net_energy_wh"] + second["lap_net_energy_wh"],
                               second["cumulative_crossing_net_energy_wh"], places=16)
        self.assertAlmostEqual(first["lap_time_s"] + second["lap_time_s"],
                               second["cumulative_crossing_time_s"], places=16)

    def test_handoff_is_prior_actual_boundary_not_spawn(self):
        a = trial(FIRST)
        self.assertFalse(a.done)
        self.assertEqual(a.completed_count, 1)
        self.assertEqual(a.receipt()["incomplete_lap"]["observer"]["events"], [])
        self.assertEqual(a.receipt()["last_accepted_tick"], 14)
        self.assertEqual(a._active.xy.tolist(), [ .2, 0.])
        self.assertEqual(a._active.energy, 986.)
        self.assertEqual(a._active.prev[-1], .2)
        self.assertRaises(ValueError, a.observe, 14, (.2, 0.), 986., 12.2)
        self.assertRaises(ValueError, a.observe, 16, (.3, 0.), 985., 12.3)
        append(a, SECOND, 15)
        self.assertTrue(a.done)

    def test_no_recredit_of_first_crossing_from_station_wrap(self):
        a = trial(FIRST)
        append(a, [((.3, 0.), .3), ((.4, 0.), 12.4)], 15)
        self.assertFalse(a.done)
        self.assertEqual(a.completed_count, 1)
        self.assertEqual(a.confirmed_gate_count, 5)
        self.assertIsNone(a.failure)

    def test_projected_second_lap_missing_prior_is_rejected(self):
        a = trial(FIRST + [((.3, 0.), 24.)])
        self.check_failed(a, "projected_seam_missing_prior_ordered_gate")

    def test_backward_return_through_first_finish_cannot_credit_again(self):
        a = trial(FIRST + [((-.2, 0.), 12.1)])
        self.check_failed(a, "backward_finite_gate")
        self.assertEqual(a.failure["detail"]["gate"], 5)
        self.assertEqual(a.confirmed_gate_count, 5)

    def test_premature_repeat_finish_from_another_path(self):
        a = trial(FIRST + [((.5, 0.), 12.5), ((.5, .7), 12.7),
                           ((-.5, .7), 12.8), ((-.5, 0.), 12.9),
                           ((.5, 0.), 13.)])
        self.check_failed(a, "premature_finite_finish")

    def test_missed_first_gate_of_second_lap(self):
        a = trial(FIRST + [((.6, .7), 12.6), ((1.4, .7), 13.4)])
        self.check_failed(a, "missed_expected_gate_outside_aperture")
        self.assertEqual(a.failure["detail"]["gate"], 1)
        self.assertEqual(a.confirmed_gate_count, 5)

    def test_stock_failure_on_second_finish_withholds_second_lap(self):
        a = trial(TWICE, reject_tick=len(TWICE) - 1)
        self.check_failed(a, "stock_boundary_rejected")
        self.assertEqual(a.confirmed_gate_count, 10)  # observed, not lap credit
        self.assertFalse(a.failure["stock_boundary_ok"])

    def test_stock_failure_on_first_finish_withholds_first_lap(self):
        a = trial(FIRST, reject_tick=len(FIRST) - 1)
        self.check_failed(a, "stock_boundary_rejected", completed=0)
        self.assertEqual(a.completed_count, 0)

    def test_exact_seam_touch_is_not_a_lap_until_confirmed(self):
        a = trial(PREFIX + [((0., 0.), 12.)])
        self.assertFalse(a.done)
        self.assertEqual(a.completed_count, 0)
        a.observe(15, (.1, 0.), 985., 12.1)
        self.assertEqual(a.completed_count, 1)
        self.assertEqual(a.rows[0]["finish_event"]["time_s"], .14)
        self.assertEqual(a.rows[0]["confirming_accepted_tick"], 15)
        self.assertEqual(a._active.xy.tolist(), [.1, 0.])
        self.assertEqual(a._active.tick, 15)

    def test_exact_second_finish_touch_reversal_is_rejected(self):
        a = trial(TWICE[:-1] + [((0., 0.), 24.), ((-.01, 0.), 24.)])
        self.check_failed(a, "finite_gate_touch_reversed")

    def test_seam_interval_with_another_finite_gate_is_not_credited(self):
        # Gate 1 is close enough to the seam to share an interval in this
        # artificial fixture. v35 conservatively rejects such ambiguity.
        c = contract()
        c["gates"][0] = gate(1, 1., (.1, 0), (1, 0), (0, 1))
        a = append(CyclicGateLedger(c), FIRST)
        self.check_failed(a, "additional_finite_gate_in_finish_interval", completed=0)

    def test_rows_and_contract_are_detached_from_external_writes(self):
        c = contract()
        a = CyclicGateLedger(c)
        c["gates"][0]["center_half_width_m"] = 0.
        append(a, FIRST)
        rows = a.rows
        rows[0]["finish_event"]["time_s"] = 123.
        a.receipt()["events"][0]["gate"] = 99
        self.assertEqual(a.rows[0]["lap_time_s"], .135)
        self.assertEqual(a.rows[0]["finish_event"]["time_s"], .135)
        self.assertEqual(a.events[0]["gate"], 1)
        append(a, SECOND, 15)
        self.assertTrue(a.done)

    def test_terminal_and_rejected_ledger_absorbing(self):
        for a in (trial(TWICE), trial(FIRST + [((-.2, 0.), 12.1)])):
            self.assertRaises(ValueError, a.observe, 29, (.4, 0.), 970., 24.4)

    def test_no_arbitrary_elapsed_cut_between_laps(self):
        a = trial(FIRST)
        for tick in range(15, 1115):
            a.observe(tick, (.2, 0.), 970., 12.2)
        self.assertEqual(a.completed_count, 1)
        self.assertFalse(a.done)
        self.assertIsNone(a.failure)
        # True stall, resource and cancellation still belong to the runner.

    def test_other_counts_and_non_boolean_boundary_are_rejected(self):
        for n in (True, 0, 1, 3, 10):
            self.assertRaises(ValueError, CyclicGateLedger, contract(), n)
        a = CyclicGateLedger(contract())
        self.assertRaises(ValueError, a.observe, 0, (0, 0), 1000., 0., boundary_ok=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
