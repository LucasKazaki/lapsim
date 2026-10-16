# Generic QEMU F405 bench protocol v1

Frozen 16 October 2026 before target protocol implementation. Bench-only,
no CAN, USB, ADC, DMA, watchdog, GPIO/pin mapping or physical-device transport.
The original five binary64 C owners execute under a minimal generic startup
and linker map. This is not the custom team PCB or target timing validation.

The installed Windows QEMU identifies as 11.1.0
`v11.1.0-12130-ge470268ff4`; `-machine help` actually lists `netduinoplus2`
and `olimex-stm32-h405`. Choose `netduinoplus2` (F405/Cortex-M4), with its
documented 1 MB flash/128 KB normal SRAM subset. Use software binary64
(`-mfloat-abi=soft`), ordinary rounding, no fast math; never narrow to float32.
Arm GNU Toolchain 12.3.Rel1, GCC 12.3.1, is the pinned local build tool.

### Host resource contract

The host starts TCG with `-accel tcg,tb-size=16`, bounding each translation
cache to 16 MiB. The installed Windows emulator otherwise attempted a
1,073,741,824-byte JIT allocation per process. An actual eight-worker batch
on a 32-logical-processor, 31 GiB Windows host produced paging-file allocation
failures despite sufficient memory for an individual experiment. Keep those
failed logs; increasing a global page-file setting is not the repair.

The cache option controls host translation storage, not target SRAM, controller
precision, scenario clocks or the firmware image. QEMU documents `tb-size` in
MiB in its [invocation reference](https://www.qemu.org/docs/master/system/invocation.html)
(accessed 16 October 2026). Verify the installed release with actual execution.

Acceptance for this repair: run the ten frozen study cases under both allocation
strategies through Python, native C and QEMU; require exact Python-result
agreement and replay each record through its actual backend. Execute independent
cases in at most eight processes with one BLAS thread each, retain process exits
and sampled CPU/memory, and run the real desktop self-test during the batch.
Within each case, preserve causal lockstep and the existing timeouts. Independent
sessions have different protocol transcript hashes; replay must preserve the
firmware/build/source identity and numerical result, not reuse a session hash.
Host throughput is not physical STM32 deadline or WCET evidence.

USART1 register access is an explicit emulation transport. No production pin
or clock setup is asserted. QEMU's board supplies its generic clock; UART baud
and wall-clock exchange do not establish physical serial timing. A minimal
image has booted and echoed a known vector. Burst delivery lost input in this
setup; raw Windows stdio also stalled on carriage-return byte 0x0d. The bounded
transport therefore encodes each frame byte as two lowercase hexadecimal ASCII
characters, with **one-character credit**: the target echoes each received
request character, and the host verifies that echo before sending the next.
Reply frames use the same hexadecimal encoding after the final credit. Maximum
encoded frame length is 1024 ASCII characters. This
is an emulator adapter, with a whole-transaction timeout, not a vehicle protocol.

All integers are unsigned little-endian. Doubles use IEEE binary64 little-endian
bit patterns, explicit byte conversion, never compiler struct padding. Maximum
whole frame is 512 bytes. Header: magic `LSC1` (4 bytes), version (u8=1), type
(u8), payload length (u16), session (u64 nonzero), sequence (u32). Trailer:
CRC32/ISO-HDLC over header+payload, reflected polynomial 0xedb88320, initial
0xffffffff and final xor 0xffffffff; encode u32. CRC detects corruption, not
authentication.

SESSION type 2 has empty payload and sequence zero. It requires a strictly
increasing nonzero session (no wrap within a process) and resets all target
controller state. Reply type 0x82 carries
the 64 ASCII hexadecimal build-ID characters, controller period u32 ms=10,
maximum sensor age u32 ms=50 and numerical-contract u32=2. The build ID hashes
source/toolchain/flags/configuration; the separate host receipt hashes the final
ELF/map. New sessions never reuse a prior nonzero command. Physical reconnect
semantics are outside this bench-only adapter.

STEP type 1 has exactly 78 payload bytes: logical now_ms u64, sensor_timestamp_ms
u64, dt_s f64, accelerator f64, aggregate propulsive wheel-torque request f64,
four wheel limits f64 in FL/FR/RL/RR order, availability bitmask u8 (only low
four bits), brake u8, comms-valid u8, sensors-valid u8, interlock u8, soft-restart
u8. Booleans must be 0/1. Sequence starts at one and increments exactly. The
fixed guard has rise 8000 N m/s, trip fraction 0.25, clear fraction 0.05 and
two healthy samples to recover. Soft restart preserves an existing pedal latch
and normalized clock history, matching the imported pipeline.

STEP reply type 0x81 payload is 391 bytes: now_ms u64; raw allocation wheel
torques, requested and delivered torque (six f64); guarded wheel torques (four
f64); final command (four f64); allocator status, guard status, next gate state,
previous gate state, latch, allowed, restart (seven u8); recovery streak and
generation (two u32); clock fault, allocator fault, guard reason and final-gate
reason (four 64-byte NUL-terminated ASCII fields, all-zero means absent).
Status/state numeric IDs are the unchanged original C header definitions.

Protocol failures reply type 0xff with one diagnostic u8 and invalidate the
session before further steps: malformed header/length/version/type, CRC,
session, sequence, or invalid wire Boolean/bitmask. No stale command is reused.
The host aborts on error, incompatible identity, timeout, truncation or echo
mismatch; it never switches backend. Oversize frames are rejected at the header
without allocating or consuming an unbounded body. Target reset requires a
new explicit SESSION; a lost/truncated reply ends the host experiment.

Acceptance: actual ELF link/map, boot/handshake, known-vector Python comparison,
fault/clock/latch/recovery/soft-restart comparisons, bad CRC/duplicate/sequence/
length/session tests, process timeout/reset tests, and the same PC plant run.
Retain command/tool/source/ELF identities, actual logs and peripheral coverage.
Source references: QEMU STM32 manual and v11.1.0 `netduinoplus2.c`,
`stm32f2xx_usart.c`; Arm's official 12.3.Rel1 binary archive. Tool binaries stay
outside Git and ordinary demo startup. Physical PIL remains unexecuted.

The linked-target numeric cohort also freezes zero/subnormal/tiny requests,
adjacent representable values at 400 N·m, zero capacity, very unequal capacity,
and a large finite allocation request. Compare every returned owner state and
raw/guarded/final value with the binary64 host reference; retain the inputs and
both results. These are numerical vectors outside the car-calibration claim.
