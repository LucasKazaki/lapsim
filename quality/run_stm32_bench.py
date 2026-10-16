"""Actually boot linked firmware, compare owners/plant, and inject wire faults."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from hashlib import sha256
from math import nextafter
from pathlib import Path

from lapsim.experiments.closed_loop import (
    ClosedLoopScenario,
    DriverPoint,
    run_closed_loop,
)
from lapsim.experiments.controller_backend import PythonController
from lapsim.experiments.stm32_backend import (
    HEADER,
    QemuController,
    QemuWire,
    encode_frame,
    encode_sample,
)


def verify(qemu: Path, elf: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    transcripts = []
    comparison = []
    reference = PythonController()
    with QemuController(qemu, elf) as target:
        for index in range(20):
            now = index * 10 if index != 15 else 140
            sample = reference.sample(
                now,
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
            expected = reference.step(sample)
            actual = target.step(sample)
            assert actual == expected, (index, actual, expected)
            comparison.append(
                {
                    "sequence": index,
                    "agreement": True,
                    "command": actual["command_nm"],
                    "reason": actual["command_reason"],
                    "latch": actual["guard"]["pedal_overlap_latched"],
                    "state": actual["fault"]["next_state"],
                }
            )
        identity = dict(target.identity)
        transcripts.extend(target.wire.transcript)
    numerical = [
        (0.0, 200.0, 200.0),
        (400.0, 200.0, 200.0),
        (nextafter(0.0, 1.0), 200.0, 200.0),
        (1e-300, 1e-300, 1e-300),
        (1e-9, 200.0, 200.0),
        (nextafter(400.0, 0.0), 200.0, 200.0),
        (nextafter(400.0, 1000.0), 200.0, 200.0),
        (300.0, 0.0, 0.0),
        (300.0, 1e-12, 200.0),
        (1e24, 1e24, 1e-20),
    ]
    reference = PythonController()
    with QemuController(qemu, elf) as target:
        for index, (request, left, right) in enumerate(numerical):
            limits = (0.0, 0.0, left, right)
            sample = reference.sample(
                index * 10,
                index * 10,
                request,
                limits,
                (False, False, True, True),
                0.5,
                False,
                True,
                True,
            )
            expected = reference.step(sample)
            actual = target.step(sample)
            assert actual == expected, ("binary64_boundaries", index, actual, expected)
            comparison.append(
                {
                    "group": "binary64_boundaries",
                    "sequence": index,
                    "request_nm": request,
                    "limits_nm": limits,
                    "agreement": True,
                    "expected": expected,
                    "actual": actual,
                }
            )
        transcripts.extend(target.wire.transcript)
    pairs = []
    for label, driver in [
        ("launch", (DriverPoint(0), DriverPoint(100_000, 0.6))),
        (
            "overlap",
            (
                DriverPoint(0, 0.5),
                DriverPoint(40_000, 0.5, 0.2),
                DriverPoint(70_000, 0),
                DriverPoint(100_000, 0),
            ),
        ),
    ]:
        scenario = ClosedLoopScenario(duration_us=100_000, driver=driver)
        expected = run_closed_loop(scenario)["result"]
        with QemuController(qemu, elf) as target:
            actual = run_closed_loop(
                replace(scenario, controller_backend_id="qemu_stm32f405"), target
            )
            assert actual["result"] == expected, label
            (output / (label + "-qemu-record.json")).write_text(
                json.dumps(
                    actual, sort_keys=True, separators=(",", ":"), allow_nan=False
                )
                + "\n"
            )
            transcripts.extend(target.wire.transcript)
            pairs.append(
                {
                    "scenario": label,
                    "controller_calls": actual["result"]["controller_calls"],
                    "plant_ticks": actual["result"]["plant_ticks"],
                    "python_result_exact_agreement": True,
                    "energy_residual_j": actual["result"]["energy_balance_residual_j"],
                }
            )
    policy = PythonController()
    sample = policy.sample(
        0,
        0,
        100.0,
        (0.0, 0.0, 200.0, 200.0),
        (False, False, True, True),
        0.5,
        False,
        True,
        True,
    )
    packet = encode_sample(sample)
    faults = []
    with QemuWire(qemu, elf) as wire:
        assert wire.exchange(encode_frame(2, 1, 0))[0] == 0x82
        assert wire.exchange(encode_frame(1, 1, 1, packet))[0] == 0x81
        for label, request, code in [
            ("duplicate_sequence", encode_frame(1, 1, 1, packet), 5),
            ("invalidated_session", encode_frame(1, 1, 2, packet), 4),
        ]:
            kind, _, _, payload = wire.exchange(request)
            assert kind == 0xFF and payload == bytes([code])
            faults.append(label)
        assert wire.exchange(encode_frame(2, 2, 0))[0] == 0x82
        bad = bytearray(encode_frame(1, 2, 1, packet))
        bad[-1] ^= 1
        assert wire.exchange(bytes(bad))[3] == b"\x03"
        faults.append("bad_crc")
        assert wire.exchange(encode_frame(2, 3, 0))[0] == 0x82
        oversized = HEADER.pack(b"LSC1", 1, 1, 489, 3, 1)
        assert wire.exchange(oversized)[3] == b"\x02"
        faults.append("oversized_length")
        assert wire.exchange(encode_frame(2, 1, 0))[3] == b"\x04"
        faults.append("old_session_replay")
        assert wire.exchange(encode_frame(2, 4, 0))[0] == 0x82
        bad_flags = bytearray(packet)
        bad_flags[72] = 128
        assert wire.exchange(encode_frame(1, 4, 1, bytes(bad_flags)))[3] == b"\x06"
        faults.append("invalid_bitmask")
        transcripts.extend(wire.transcript)
    with QemuWire(qemu, elf, timeout_s=0.5) as wire:
        assert wire.exchange(encode_frame(2, 10, 0))[0] == 0x82
        try:
            wire.exchange(HEADER.pack(b"LSC1", 1, 1, 78, 10, 1) + packet[:2])
        except TimeoutError:
            pass
        else:
            raise AssertionError("truncated transaction did not time out")
        assert wire.closed and wire.process.poll() is not None
        faults.append("truncation_timeout_and_cleanup")
    with QemuController(qemu, elf) as target:
        target.wire.process.terminate()
        target.wire.process.wait(timeout=2)
        try:
            target.step(sample)
        except (BrokenPipeError, RuntimeError, OSError):
            pass
        else:
            raise AssertionError("dead target returned a command")
        assert target.sequence == 0
        faults.append("target_process_loss_no_fallback")
    with QemuController(qemu, elf) as target:
        first = target.step(sample)
        assert not first["command_allowed"] and first["command_nm"] == [
            0.0,
            0.0,
            0.0,
            0.0,
        ]
        faults.append("explicit_relaunch_starts_recovery")
    encoded = json.dumps(transcripts, sort_keys=True, separators=(",", ":")).encode()
    (output / "protocol-transcript.json").write_bytes(encoded + b"\n")
    (output / "known-vectors.json").write_text(json.dumps(comparison, indent=2) + "\n")
    summary = {
        "schema": "lapsim.actual-stm32-emulation-verification.v1",
        "status": "passed",
        "identity": identity,
        "known_vectors": len(comparison),
        "known_vectors_exact_python_agreement": True,
        "actual_pc_plant_pairs": pairs,
        "protocol_faults_checked": faults,
        "retained_transcript_sha256": sha256(encoded).hexdigest(),
        "limits": "Actual generic QEMU F405 instruction/UART execution; no physical PIL, target deadlines, custom PCB or unsupported peripheral validation.",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = verify(args.qemu.resolve(), args.elf.resolve(), args.output_dir)
    print(json.dumps({k: v for k, v in summary.items() if k != "identity"}))
