# TC-02E receipt

Evidence level: portable synthetic host-language evidence only. No STM32, CAN, HIL, dyno, track, or vehicle execution.

## Repository state at publication

- PR: #66, draft
- Base: `ops/school-focus-20260930@254b7453ea2802f7d17e6758a52419de0dded110`
- TC-02E design commit: `5cf89ca8ee6ecbaa2746ba321adb4cd4ac1fe051`
- Timebase reference commit: `74c8d82cc274f4b5bbd3ff9737969d3ec9af640f`
- Remote reference blob: `cfa7bf78644093e06858d6cd40b9c434b9095756`
- The companion test-file write was blocked by the connected GitHub safety check before mutation; it is retained in the external handoff artifact and is not claimed as remote branch content.

## Portable verification

Environment: CPython 3.13.5, Linux x86_64, standard library only.

Commands:

```text
python -S -m unittest -v test_timebase_freshness.py
python -S -m py_compile timebase_freshness.py test_timebase_freshness.py
```

Observed: 15/15 tests passed, 0 failed, 0 skipped; `py_compile` exited 0.

Local tested SHA-256:

- `timebase_freshness.py`: `750a146011f0c305cf39f906b609e654a1233920191cab16b1ffcbf573e63517`
- `test_timebase_freshness.py`: `19585720a9f9e588376227245489fdfa5c86c931867f72a27a1981122e6c6029`
- captured test output: `47d505fe52b7e8e5045d22ff20fa4580d4776c7213cfb7465347f5d5f90f3176`
- captured compile output: `bde294368bfed77c2cddf8cec271d398aee9cdbab3b26e1059281bd33adb0120`

The tested local reference and the published reference implement the same contract; the remote file was reformatted during publication, so these SHA-256 values must not be represented as hashes of the remote blob.

## Upstream provenance

- STMicroelectronics/cmsis-core `afc5ca6af0a49232fde7eb4548dd0962d119ce14`; `CMSIS/Core/Include/core_cm4.h` blob `770908a619b47e43d9bdbaf909b83a9b917d095b`; Apache-2.0.
- STMicroelectronics/stm32f4xx-hal-driver `1f6451c3e07728b4c830744de380e56bf5bc0026`; `Src/stm32f4xx_hal.c` blob `862ec732ee46eec100fd2678bb500bcdb5d732c9`; BSD-3-Clause.
- Accessed 2026-10-01.

No upstream source code was copied into the reference; upstream files were used to establish candidate clock semantics and provenance requirements.

## Native/runtime status

Issue #61 still contains no inspected native `APPLY_RECEIPT`. This pass did not register or start a local project and did not alter Company Runtime scheduling.

## Next action

Obtain the actual firmware clock/timestamp source and bind each critical input to one verified domain before translating freshness results into source-specific embedded tests.
