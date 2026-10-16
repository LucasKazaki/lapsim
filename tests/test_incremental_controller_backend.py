"""Incremental composition must retain the imported replay semantics exactly."""

from dataclasses import replace
import sys

from lapsim.experiments.controller_backend import PythonController, controller_module


def test_private_imports_do_not_change_path_or_use_unrelated_module_names():
    before = list(sys.path)
    allocator = controller_module("allocator")
    assert sys.path == before
    assert allocator.__name__.startswith("_lapsim_enme408_reference.")
    assert sys.modules.get("allocator") is not allocator


def test_incremental_owner_state_matches_frozen_upstream_scenarios():
    source = controller_module("allocator_parity")
    pipeline = controller_module("control_pipeline")
    for label, config, samples in source.composition_scenarios():
        backend = PythonController(config.period_ms, config.allocator.max_input_age_ms)
        backend.config = config
        actual = tuple(backend.step(sample) for sample in samples)
        assert actual == pipeline.replay_control_pipeline(samples, config), label


def test_fault_overlap_clock_reset_and_recovery_sequence_matches_reference():
    backend = PythonController()
    samples = []
    for index in range(20):
        sample = backend.sample(
            index * 10,
            index * 10 if index != 6 else 0,
            300.0,
            (0.0, 0.0, 200.0, 200.0),
            (False, False, True, True),
            0.5 if index not in (10, 11) else 0.0,
            index in (8, 9),
            index != 10,
            True,
            index == 12,
        )
        if index == 15:
            sample = replace(sample, allocation=replace(sample.allocation, now_ms=140))
        samples.append(sample)
    expected = backend.api["control_pipeline"].replay_control_pipeline(
        samples, backend.config
    )
    assert tuple(backend.step(sample) for sample in samples) == expected
