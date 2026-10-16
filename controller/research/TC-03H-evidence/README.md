# Portable allocator evidence

The two failed caller attempts are preserved separately from the passing result. Their raw C allocator, prior ports and compiled five-unit library hash are identical. Driver projection and diagnostic regression assertions changed; the fixture input corpus and owner policy did not.

- `attempt-1-failed.json` records the raw-invalid-candidate diagnostic mismatch. Its executed driver is `executed-driver-1.py.txt`; the first frozen generator manifest is retained alongside it.
- `attempt-2-failed.json` records the clock-only candidate/guard pair-validity mismatch. Its executed driver and second generator manifest are also exact copies.
- `caller-repair-2.diff` and `caller-repair-3.diff` retain the exact driver/test changes before their respective reruns. The corresponding commits and all source hashes remain in the handoff and Git history.
- `attempt-3-passed.json` is the exact successful repeated parity receipt, SHA-256 `9a9ccd559dcffa27d359ff07dc2b1087bc5c88a25b2d4c79d47ec4618d2b2aa5`. The active driver and generator manifest are separately hash-bound by it.
- `full-reference-tests.txt` is the actual 500-test output, including expected CLI rejection messages. `local-plain-probe.json` records a successful ordinary host compile/run, explicitly distinct from sanitizer execution.
- `review-handoff.json` binds the runtime head, unchanged native inputs, all three attempts, generator and caller repair hashes. `summary.json` reports scope and check status without rewriting original receipts.
- `independent-review.json` is the exact bounded independent source/compiled review receipt, SHA-256 `29b685981d7c9713ce89d685ffaf72e7ce781aa17bd6530692b0e2c50f750c6a`. It separates direct/ABI/stateful results, the 592 invalid-candidate gate paths, independent build identity and limitations. Exact-head sanitizer CI is a later publication gate.

All candidate values in strict JSON parity signatures use exact binary64 bit strings. That preserves signed zero and represents raw nonfinite delivered results without emitting invalid JSON numbers. The shared validator and guard reject contradictory raw candidates; only the complete final gate can report an offline proposed command.

No generated binary, ARM toolchain, model or hardware artifact is committed. This is source-bound host evidence for a normalized synthetic domain, not target-runtime, physical-input, timing or safety approval.
