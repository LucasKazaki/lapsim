"""Exercise the actual source-to-proposed-command chain, not component mocks."""
from dataclasses import replace
from itertools import repeat
import json
from pathlib import Path
import tempfile
import unittest

from allocator import AllocationInput, AllocatorConfig
from bench_replay import load_scenario, main, make_receipt
from command_guard import CommandGuardConfig, CommandGuardInput
from control_pipeline import ControlSample, PipelineConfig, replay_control_pipeline
from fault_state import FaultPolicy

CFG = PipelineConfig(AllocatorConfig(50), CommandGuardConfig(100., .6, .2), FaultPolicy(2), 50)
ZERO = [0.] * 4


def sample(tick, request=40., **guard_changes):
    inp = AllocationInput(tick, tick, request, (100.,) * 4, (True,) * 4, True)
    guard = replace(CommandGuardInput(.05, .3, False, True, True, True), **guard_changes)
    return ControlSample(inp, guard)


def scenario():
    from dataclasses import asdict
    return {"schema": "enme408-control-scenario/v1", "label": "Synthetic smoke",
            "provenance": "Synthetic fixture; no vehicle capture",
            "config": asdict(CFG), "samples": [asdict(sample(0)), asdict(sample(50)), asdict(sample(100))]}


class PipelineTests(unittest.TestCase):
    def test_startup_requalification_does_not_precharge_slew(self):
        rows = replay_control_pipeline((sample(0), sample(50), sample(100)), CFG)
        self.assertEqual([r["fault"]["next_state"] for r in rows], ["recovery_pending", "ready", "ready"])
        self.assertEqual([r["command_nm"] for r in rows], [ZERO, [5.] * 4, [10.] * 4])

    def test_guard_fault_inhibits_and_requires_recovery(self):
        rows = replay_control_pipeline((sample(0), sample(50),
                                       sample(100, critical_comms_ok=False), sample(150), sample(200)), CFG)
        self.assertEqual([r["command_allowed"] for r in rows], [False, True, False, False, True])
        self.assertEqual(rows[2]["command_reason"], "critical_communication_loss")
        self.assertEqual(rows[-1]["command_nm"], [5.] * 4)

    def test_upstream_stale_fault_retains_precise_reason(self):
        stale = sample(100)
        stale = replace(stale, allocation=replace(stale.allocation, input_timestamp_ms=0))
        rows = replay_control_pipeline((sample(0), sample(50), stale), CFG)
        self.assertEqual(rows[-1]["command_nm"], ZERO)
        self.assertEqual(rows[-1]["fault"]["reason"], "stale_input")

    def test_restart_zeroes_and_requalifies_while_preserving_pedal_latch(self):
        tripped = sample(100, accelerator_fraction=.8, brake_active=True)
        restarted = replace(sample(150), restart_requested=True)
        rows = replay_control_pipeline((sample(0), sample(50), tripped, restarted,
                                       sample(200, accelerator_fraction=.1), sample(250)), CFG)
        self.assertEqual(rows[3]["command_nm"], ZERO)
        self.assertTrue(rows[3]["guard"]["pedal_overlap_latched"])
        self.assertEqual(rows[3]["fault"]["generation"], 1)
        self.assertEqual(rows[4]["fault"]["next_state"], "recovery_pending")
        self.assertEqual(rows[5]["command_nm"], [5.] * 4)

    def test_duplicate_backward_and_gapped_clock_cycles_inhibit(self):
        for tick, reason in ((50, "nonmonotonic_cycle_timestamp"),
                             (25, "nonmonotonic_cycle_timestamp"), (150, "cycle_period_mismatch")):
            with self.subTest(tick=tick):
                rows = replay_control_pipeline((sample(0), sample(50), sample(tick)), CFG)
                self.assertEqual(rows[-1]["clock_fault"], reason)
                self.assertEqual(rows[-1]["command_nm"], ZERO)

    def test_large_forged_guard_dt_cannot_accelerate_rise(self):
        rows = replay_control_pipeline((sample(0), sample(50), sample(100, dt_s=100.)), CFG)
        self.assertEqual(rows[-1]["clock_fault"], "guard_period_mismatch")
        self.assertEqual(rows[-1]["command_nm"], ZERO)

    def test_timing_fault_cannot_be_the_only_low_pedal_latch_clear(self):
        for tick, dt in ((150, .05), (50, .05), (100, 100.)):
            with self.subTest(tick=tick, dt=dt):
                next_tick = max(50, tick) + 50
                rows = replay_control_pipeline((
                    sample(0, accelerator_fraction=.8, brake_active=True),
                    sample(50, accelerator_fraction=.8),
                    sample(tick, accelerator_fraction=.1, dt_s=dt),
                    sample(next_tick, accelerator_fraction=.8),
                    sample(next_tick + 50, accelerator_fraction=.8),
                    sample(next_tick + 100, accelerator_fraction=.1),
                    sample(next_tick + 150, accelerator_fraction=.8),
                ), CFG)
                self.assertIsNotNone(rows[2]["clock_fault"])
                self.assertTrue(rows[2]["guard"]["pedal_overlap_latched"])
                self.assertEqual(rows[4]["command_nm"], ZERO)
                self.assertTrue(rows[4]["guard"]["pedal_overlap_latched"])
                self.assertEqual(rows[-1]["command_nm"], [5.] * 4)

    def test_saturated_cycles_do_not_qualify_recovery(self):
        rows = replay_control_pipeline((sample(0, 500.), sample(50, 500.), sample(100), sample(150)), CFG)
        self.assertEqual([r["command_allowed"] for r in rows], [False, False, False, True])

    def test_infinite_replay_is_bounded_and_rejected(self):
        with self.assertRaisesRegex(ValueError, "4096"):
            replay_control_pipeline(repeat(sample(0)), CFG)

    def test_replay_is_deterministic_and_strict_json(self):
        inputs = (sample(0), sample(50), sample(100, external_interlock=False), sample(150), sample(200))
        a = replay_control_pipeline(inputs, CFG)
        self.assertEqual(a, replay_control_pipeline(inputs, CFG))
        json.dumps(a, allow_nan=False)

    def test_restart_type_and_period_config_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "boolean"):
            replay_control_pipeline((replace(sample(0), restart_requested="false"),), CFG)
        for value in (True, 0, -1, 1.5, 60001):
            with self.subTest(period=value), self.assertRaises(ValueError):
                replace(CFG, period_ms=value)


class BenchReceiptTests(unittest.TestCase):
    def test_hardlinked_outputs_cannot_overwrite_source_or_each_other(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output, csv_path = (root / name for name in ("scenario.json", "receipt.json", "trace.csv"))
            raw = json.dumps(scenario()).encode()
            source.write_bytes(raw)
            os.link(source, output)
            with self.assertRaises(SystemExit):
                main([str(source), "--output", str(output)])
            self.assertEqual(source.read_bytes(), raw)
            with self.assertRaises(SystemExit):
                main([str(source), "--output", str(csv_path), "--csv", str(output)])
            self.assertEqual(source.read_bytes(), raw)
            self.assertFalse(csv_path.exists())
            output.unlink()
            output.write_text("preserved")
            os.link(output, csv_path)
            with self.assertRaises(SystemExit):
                main([str(source), "--output", str(output), "--csv", str(csv_path)])
            self.assertEqual(output.read_text(), "preserved")

    def test_deeply_nested_json_has_clean_cli_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "deep.json"
            output = Path(folder) / "receipt.json"
            source.write_bytes(b'[' * 2000 + b'0' + b']' * 2000)
            with self.assertRaises(SystemExit) as failure:
                main([str(source), "--output", str(output)])
            self.assertEqual(failure.exception.code, 2)
            self.assertFalse(output.exists())

    def test_receipt_hashes_sources_and_matches_replay(self):
        raw = json.dumps(scenario()).encode()
        receipt = make_receipt(raw)
        self.assertEqual(receipt, make_receipt(raw))
        self.assertEqual(receipt["summary"], {"cycles": 3, "allowed_cycles": 2, "zero_command_cycles": 1,
                                               "inhibited_cycles": 0, "recovery_pending_cycles": 1})
        self.assertEqual(len(receipt["scenario_sha256"]), 64)
        self.assertEqual(len(receipt["source_sha256"]), 11)
        self.assertEqual(receipt["numeric_contract_version"], 2)
        self.assertEqual(receipt["clock_contract_version"], 1)
        json.dumps(receipt, allow_nan=False)

    def test_duplicate_nonfinite_and_unknown_fields_rejected(self):
        cases = (b'{"schema":1,"schema":2}', b'{"a":NaN}', b'{"a":1e999}',
                 json.dumps({**scenario(), "surprise": 1}).encode())
        for raw in cases:
            with self.subTest(raw=raw[:50]), self.assertRaises(ValueError):
                load_scenario(raw)

    def test_nested_unknown_field_and_empty_or_oversize_cycles_rejected(self):
        value = scenario()
        value["samples"][0]["allocation"]["surprise"] = 1
        with self.assertRaises(ValueError):
            load_scenario(json.dumps(value).encode())
        for count in (0, 4097):
            value = scenario()
            value["samples"] = [value["samples"][0]] * count
            with self.subTest(count=count), self.assertRaises(ValueError):
                load_scenario(json.dumps(value).encode())

    def test_cli_emits_consistent_json_csv_and_preserves_source(self):
        import csv
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "scenario.json"
            raw = json.dumps(scenario()).encode()
            source.write_bytes(raw)
            self.assertEqual(main([str(source), "--output", str(root / "receipt.json"),
                                   "--csv", str(root / "trace.csv")]), 0)
            receipt = json.loads((root / "receipt.json").read_text())
            with (root / "trace.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), receipt["summary"]["cycles"])
            self.assertEqual(float(rows[-1]["command_0_nm"]), receipt["records"][-1]["command_nm"][0])
            self.assertEqual(source.read_bytes(), raw)
            with self.assertRaises(SystemExit):
                main([str(source), "--output", str(source)])
            self.assertEqual(source.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
