"""Bounded data-only QEMU F405 UART backend. No physical port is opened."""

from __future__ import annotations

import json
import queue
import secrets
import struct
import subprocess
import threading
import time
import zlib
from collections import deque
from hashlib import sha256
from math import isfinite
from pathlib import Path
from typing import Any

from lapsim.resources import repository_root

from .controller_backend import PythonController, controller_source_identity

HEADER = struct.Struct("<4sBBHQI")
MAX_FRAME = 512


def encode_frame(kind: int, session: int, sequence: int, payload: bytes = b"") -> bytes:
    if any(
        type(v) is not int or not 0 <= v < 2**bits
        for v, bits in ((kind, 8), (session, 64), (sequence, 32))
    ):
        raise ValueError("bench frame identities require bounded unsigned integers")
    if type(payload) is not bytes:
        raise ValueError("bench frame payload must be bytes")
    if len(payload) > MAX_FRAME - HEADER.size - 4:
        raise ValueError("bench frame is oversized")
    body = HEADER.pack(b"LSC1", 1, kind, len(payload), session, sequence) + payload
    return body + struct.pack("<I", zlib.crc32(body))


def decode_frame(raw: bytes) -> tuple[int, int, int, bytes]:
    if not HEADER.size + 4 <= len(raw) <= MAX_FRAME:
        raise ValueError("bench frame length is invalid")
    magic, version, kind, length, session, sequence = HEADER.unpack_from(raw)
    if magic != b"LSC1" or version != 1 or len(raw) != HEADER.size + length + 4:
        raise ValueError("bench frame header is invalid")
    if zlib.crc32(raw[:-4]) != struct.unpack_from("<I", raw, len(raw) - 4)[0]:
        raise ValueError("bench frame CRC mismatch")
    return kind, session, sequence, raw[HEADER.size : -4]


def _number(value: Any) -> float:
    if type(value) not in (int, float):
        raise ValueError("wire numeric must be an ordinary number")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError("wire numeric exceeds binary64") from error
    if not isfinite(result):
        raise ValueError("wire numeric must be finite")
    return result


def encode_sample(sample: Any) -> bytes:
    a, g = sample.allocation, sample.guard
    if any(
        type(v) is not int or not 0 <= v < 2**64
        for v in (a.now_ms, a.input_timestamp_ms)
    ):
        raise ValueError("wire timestamps require uint64 milliseconds")
    if (
        a.torque_unit != "N*m"
        or len(a.wheel_limits_nm) != 4
        or len(a.wheel_enabled) != 4
    ):
        raise ValueError("unsupported wire unit or wheel vector")
    flags = (
        *a.wheel_enabled,
        g.brake_active,
        g.critical_comms_ok,
        g.sensor_agreement_ok,
        g.external_interlock,
        sample.restart_requested,
    )
    if (
        any(type(v) is not bool for v in flags)
        or a.external_interlock != g.external_interlock
    ):
        raise ValueError("wire booleans/interlocks are invalid")
    mask = sum(int(v) << i for i, v in enumerate(a.wheel_enabled))
    return struct.pack(
        "<QQ7d6B",
        a.now_ms,
        a.input_timestamp_ms,
        *map(
            _number, (g.dt_s, g.accelerator_fraction, a.request_nm, *a.wheel_limits_nm)
        ),
        mask,
        g.brake_active,
        g.critical_comms_ok,
        g.sensor_agreement_ok,
        g.external_interlock,
        sample.restart_requested,
    )


class QemuWire:
    """One owned QEMU process, bounded buffers and a whole-frame deadline."""

    def __init__(self, qemu: Path, elf: Path, timeout_s: float = 5.0):
        if not 0.05 <= timeout_s <= 30:
            raise ValueError("bench timeout must be 0.05–30 s")
        self.timeout_s = timeout_s
        self.closed = False
        self.stopped = threading.Event()
        self.bytes = queue.Queue(maxsize=4096)
        self.errors = deque(maxlen=16)
        self.transcript = []
        self.digest = sha256()
        self.command = [
            str(qemu.absolute()),
            "-M",
            "netduinoplus2",
            "-display",
            "none",
            "-monitor",
            "none",
            "-serial",
            "stdio",
            "-kernel",
            str(elf.absolute()),
        ]
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdin, stdout, stderr = (
            self.process.stdin,
            self.process.stdout,
            self.process.stderr,
        )
        if stdin is None or stdout is None or stderr is None:
            self.process.terminate()
            raise RuntimeError("QEMU standard pipes were not created")
        self.stdin, self.stdout, self.stderr = stdin, stdout, stderr
        self.reader = threading.Thread(target=self._read_stdout, daemon=True)
        self.reader.start()
        self.error_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self.error_reader.start()
        try:
            deadline = time.monotonic() + timeout_s
            boot = bytearray()
            while not boot.endswith(b"\n"):
                if len(boot) > 100:
                    raise ValueError("unexpected bench boot text")
                boot.extend(self.read_exact(1, deadline))
            if bytes(boot) != b"LAPSIM_F405_BENCH_v1\n":
                raise ValueError("unexpected firmware boot identity")
            self.boot = boot.decode().strip()
        except BaseException:
            self.close()
            raise

    def _read_stdout(self):
        try:
            while not self.stopped.is_set():
                value = self.stdout.read(1)
                if not value:
                    return
                while not self.stopped.is_set():
                    try:
                        self.bytes.put(value, timeout=0.1)
                        break
                    except queue.Full:
                        pass
        except (OSError, ValueError):
            return

    def _read_stderr(self):
        try:
            while not self.stopped.is_set():
                value = self.stderr.read(1024)
                if not value:
                    return
                self.errors.append(value.decode(errors="replace"))
        except (OSError, ValueError):
            return

    def read_exact(self, count, deadline):
        result = bytearray()
        while len(result) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    "QEMU bench transaction timed out; no stale command reused"
                )
            try:
                result.extend(self.bytes.get(timeout=min(remaining, 0.1)))
            except queue.Empty:
                if self.process.poll() is not None:
                    raise RuntimeError(
                        "QEMU ended before a complete reply: " + "".join(self.errors)
                    )
        return bytes(result)

    def exchange(self, request: bytes) -> tuple[int, int, int, bytes]:
        if self.closed:
            raise RuntimeError("QEMU backend is closed")
        if not HEADER.size <= len(request) <= MAX_FRAME:
            raise ValueError("bench request transport length is invalid")
        deadline = time.monotonic() + self.timeout_s
        index, value = -1, 0
        try:
            for index, value in enumerate(request.hex().encode("ascii")):
                self.stdin.write(bytes([value]))
                self.stdin.flush()
                if self.read_exact(1, deadline) != bytes([value]):
                    raise ValueError("QEMU byte-credit mismatch")
            encoded_header = self.read_exact(HEADER.size * 2, deadline)
            if any(c not in b"0123456789abcdef" for c in encoded_header):
                raise ValueError(
                    "QEMU reply contains invalid hexadecimal transport bytes"
                )
            header = bytes.fromhex(encoded_header.decode("ascii"))
            length = HEADER.unpack(header)[3]
            if length > MAX_FRAME - HEADER.size - 4:
                raise ValueError("QEMU reply is oversized")
            encoded_body = self.read_exact((length + 4) * 2, deadline)
            if any(c not in b"0123456789abcdef" for c in encoded_body):
                raise ValueError(
                    "QEMU reply contains invalid hexadecimal transport bytes"
                )
            raw = header + bytes.fromhex(encoded_body.decode("ascii"))
            result = decode_frame(raw)
            self.digest.update(request)
            self.digest.update(raw)
            if len(self.transcript) >= 4097:
                raise ValueError("QEMU transaction budget exceeded")
            self.transcript.append(
                {"request_hex": request.hex(), "reply_hex": raw.hex()}
            )
            return result
        except BaseException as error:
            self.transcript.append(
                {
                    "request_hex": request.hex(),
                    "status": "failed",
                    "last_credit_index": index,
                    "last_byte": value,
                    "error": str(error),
                }
            )
            self.close()
            raise

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.stopped.set()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream:
                stream.close()
        self.reader.join(timeout=0.2)
        self.error_reader.join(timeout=0.2)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class QemuController(PythonController):
    backend_id = "qemu_stm32f405"

    def __init__(
        self,
        qemu: Path,
        elf: Path,
        period_ms: int = 10,
        maximum_age_ms: int = 50,
        timeout_s: float = 5.0,
    ):
        if period_ms != 10 or maximum_age_ms != 50:
            raise ValueError("this bench firmware has a fixed 10 ms/50 ms policy")
        super().__init__(period_ms, maximum_age_ms)
        receipt_path = elf.parent / "build.json"
        if receipt_path.stat().st_size > 1_000_000:
            raise ValueError("firmware receipt exceeds size limit")
        receipt = json.loads(receipt_path.read_bytes())
        digest = sha256(elf.read_bytes()).hexdigest()
        if (
            receipt["schema"] != "lapsim.stm32-bench-build.v1"
            or receipt["elf_sha256"] != digest
        ):
            raise ValueError("firmware ELF/build identity mismatch")
        for relative, expected in receipt["source_files_sha256"].items():
            path = repository_root() / relative
            if (
                not path.resolve().is_relative_to(repository_root().resolve())
                or sha256(path.read_bytes()).hexdigest() != expected
            ):
                raise ValueError("firmware source drift; rebuild the bench image")
        version = subprocess.run(
            [str(qemu), "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        ).stdout.splitlines()[0]
        self.session = secrets.randbits(64) or 1
        self.wire = QemuWire(qemu, elf, timeout_s)
        try:
            kind, sid, seq, payload = self.wire.exchange(
                encode_frame(2, self.session, 0)
            )
            if (kind, sid, seq) != (0x82, self.session, 0) or len(payload) != 76:
                raise ValueError("incompatible QEMU session reply")
            if payload[:64].decode("ascii") != receipt[
                "build_id"
            ] or struct.unpack_from("<III", payload, 64) != (10, 50, 2):
                raise ValueError("incompatible firmware build/numerical policy")
        except BaseException:
            self.wire.close()
            raise
        self.identity = {
            **controller_source_identity(),
            "backend": self.backend_id,
            "emulator_version": version,
            "emulator_executable_sha256": sha256(qemu.read_bytes()).hexdigest(),
            "firmware_build_id": receipt["build_id"],
            "firmware_elf_sha256": digest,
            "boot": self.wire.boot,
            "transport": "QEMU USART1 stdio, bounded lowercase hexadecimal frame bytes with verified character credit; no physical port",
            "limits": "Generic F405 instruction/interface model; no PCB, peripheral-complete or real-time timing validation",
        }

    def step(self, sample: Any) -> dict:
        if self.sequence >= 4096:
            raise ValueError("QEMU controller cycle budget exceeded")
        wire_sequence = self.sequence + 1
        kind, sid, seq, payload = self.wire.exchange(
            encode_frame(1, self.session, wire_sequence, encode_sample(sample))
        )
        if (kind, sid, seq) != (0x81, self.session, wire_sequence) or len(
            payload
        ) != 391:
            self.close()
            raise ValueError(
                "QEMU rejected or mismatched the step; no fallback or stale reuse"
            )
        now, *values = struct.unpack_from("<Q14d", payload)
        raw = tuple(values[:4])
        requested, delivered = values[4:6]
        guarded = list(values[6:10])
        command = list(values[10:14])
        if not all(isfinite(v) for v in values):
            self.close()
            raise ValueError("nonfinite QEMU output")
        status, guard_status, next_state, previous_state, latch, allowed, restart = (
            struct.unpack_from("<7B", payload, 120)
        )
        streak, generation = struct.unpack_from("<II", payload, 127)

        def text(offset):
            value = payload[offset : offset + 64]
            if b"\0" not in value:
                raise ValueError("unterminated QEMU diagnostic")
            return value.split(b"\0", 1)[0].decode("ascii") or None

        clock_fault, allocator_fault, guard_reason, reason = (
            text(135 + 64 * i) for i in range(4)
        )
        statuses = {1: "ok", 2: "saturated", 3: "fault"}
        guards = {1: "ok", 2: "limited", 3: "inhibited"}
        states = {1: "ready", 2: "limited", 3: "inhibited", 4: "recovery_pending"}
        if (
            status not in statuses
            or guard_status not in guards
            or next_state not in states
            or previous_state not in states
            or any(v > 1 for v in (latch, allowed, restart))
        ):
            self.close()
            raise ValueError("unknown QEMU status/state")
        candidate = {
            "wheel_torque_nm": raw,
            "requested_nm": requested,
            "delivered_nm": delivered,
            "status": statuses[status],
            "fault": allocator_fault,
        }
        inhibited = bool(clock_fault) or guard_status == 3
        effective_status = "fault" if inhibited else statuses[status]
        effective_fault = (
            (clock_fault or (allocator_fault if status == 3 else guard_reason))
            if inhibited
            else allocator_fault
        )
        row = {
            "sequence": self.sequence,
            "now_ms": now,
            "restart_requested": bool(restart),
            "allocator": candidate,
            "guard": {
                "status": guards[guard_status],
                "reason": guard_reason,
                "output_nm": guarded,
                "pedal_overlap_latched": bool(latch),
            },
            "fault": {
                "sequence": self.sequence,
                "generation": generation,
                "restart_requested": bool(restart),
                "previous_state": states[previous_state],
                "next_state": states[next_state],
                "allocator_status": effective_status,
                "allocator_fault": effective_fault,
                "requested_nm": requested,
                "delivered_nm": 0.0 if inhibited else delivered,
                "wheel_torque_nm": [0.0] * 4 if inhibited else list(raw),
                "recovery_streak": streak,
                "reference_gate_allowed": bool(allowed),
                "reason": reason,
            },
            "clock_fault": clock_fault,
            "command_allowed": bool(allowed),
            "command_nm": command,
            "command_reason": guard_reason if allowed else reason,
        }
        self.sequence += 1
        self.identity.update(
            transactions=len(self.wire.transcript),
            protocol_transcript_sha256=self.wire.digest.hexdigest(),
        )
        return row

    def close(self):
        self.closed = True
        self.wire.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
