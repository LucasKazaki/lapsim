# TC-02BS: Offline guard request/delivery contract (2026-10-10)

**Status:** additive Python reference candidate requiring independent review. Owner's 2027–28 Terps Racing EV torque-control project only, not the team's 2026–27 car or any vehicle safety system. No hardware/CAN/firmware or Company Runtime authority.

## Published-source counterexample

On PR #66, `reference/command_guard.py` blob `5d69a1195abdda814ab3ba3d5db0e99d640db8a6` checks `delivered_nm == sum(wheel_torque_nm)` but does not compare with `requested_nm`. A synthetic `AllocationResult((10.0,)*4, 0.0, 40.0, "ok", None)` passes at a permissive hypothetical rise limit and outputs 10 N*m per wheel despite a declared zero aggregate request. This malformed candidate does **not** arise from ordinary correctly typed published allocator operation; it tests a downstream trust boundary. A non-string `status` with custom equality can also impersonate `"ok"` in Python.

## Additive candidate

`reference/guard_request_contract.py` checks ordinary/finite request and delivery numbers, canonical status, four ordinary finite wheel values, and that delivered torque does not exceed requested torque (8 ULP comparison allowance, **zero allowed at exactly zero request**). Invalid inputs produce a synthetic inhibited/zero output. Otherwise it delegates to the unchanged `command_guard.py`, preserving existing pedal, comms, interlock, slew and fault semantics. This is **not** a real safety limiter, an accepted motor deadband, or a measured threshold.

`reference/test_guard_request_contract.py` exercises zero/nonzero overrequest, invalid numeric/status/vector fields, interlocks, fault zeroing, relative float roundoff and 1,000 seeded valid allocator scenarios. The exact published `reference/allocator.py` blob is `43706e593e9485ec264babafd72ec6d3955577e0`.

## Portable evidence / pending review

Linux CPython 3.13.5, stdlib only: `python -B -S -m unittest discover -p 'test_*.py' -v` over a frozen reference snapshot and new tests: **63/63 passed**, including **16/16 new tests**. A deliberate mutant bypassing the candidate's request check produces **3 expected failures in 16 tests** (underlying exit 1); final verifier exits 0. The local snapshot of original `command_guard.py` was Git-blob checked against the linked source. **The full live PR #66 suite, published test_command_guard.py, independent review, Company Runtime ACK/registration, native STM32F405, CAN and vehicle tests have NOT been run/verified by this pass.**

**Next:** independent reviewer reproduces zero-request mismatch, executes entire live reference suite, and decides keep/revert of this small additive candidate. Before applying to firmware, verify actual team signals, sample period, units, limits, shutdown ownership, interface signs and test authorization. No automatic PR merge.

## Sources (accessed October 10, 2026)

- Exact private source/review thread: https://github.com/LucasKazaki/lucas-agent-studio/pull/66; published `reference/command_guard.py` SHA above.
- Python 3.13 language data model, equality/hash customization: https://docs.python.org/3.13/reference/datamodel.html
- Python 3.13 `math.ulp`: https://docs.python.org/3.13/library/math.html#math.ulp. The 8-ULP multiplier is a proposed synthetic numerical policy, not a hardware specification.
