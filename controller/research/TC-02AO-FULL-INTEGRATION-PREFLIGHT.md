# TC-02AO: complete fifteen-file integration preflight (research receipt)

Source inspected: ENME408 draft PR #66, `research/enme408-tc00-20261001`, head `c7f0172b431dc1084969ccde44c68c77acaaab75`. All fifteen filenames in the TC-02AN handoff were independently fetched from the exact branch and returned 404 on this inspection. Existing PR contains other reference implementations that must remain untouched. No submitted reviews or reviewer comments were observed. This note does **not** assert any live Company Runtime ACK, local project registration, native tests, or merged source.

## Integration gap and reversible fix

The TC-02AN archive declares **15** exact destination files in `INTEGRATION-MANIFEST.json`, but its inherited `tools/integration_preflight.py` verifies **eight** older files only. Its passing checks cannot by themselves establish collision-free staging for the other seven. A new **local-only** `tools/full_integration_preflight.py` validates the complete explicit fifteen-file allowlist, the pinned manifest revision, all source SHA-256 digests, absent destination paths, and symlink ancestors. It rejects changes to the fixed destination set, source tampering, branch/head mismatches supplied by the worker, target collisions, and symlinked paths. It is read-only, does not stage/push, and reports explicitly that GitHub's **live** remote head and git status still require independent reads before publication.

## Portable results (CPython 3.13.5, Linux, standard library)

- Prior TC-02AN reference tests: **157/157 passed**, exit 0.
- Existing eight-file preflight tests: **18/18 passed**.
- New complete-manifest preflight tests: **20/20 passed**.
- Combined tooling tests: **38/38 passed**, exit 0. Total **195** distinct tests; zero final failures/skips.
- Compile: `python -S -m compileall -q reference tools` exit 0.
- Full fifteen-file manifest SHA-256 verification: exit 0.
- New preflight implementation SHA-256: `2e94a7b717aaefc74c0b0648f3b6b87a8cd385a944f9fac25240abae85e893f0`.
- New test SHA-256: `1bb044c444ebb920f855e60dcd1bee6a4182ebd0d08b8706ad65422d07e665bd`.

This verifies package integrity and portable tests, **not** integration against the complete 99-file PR, firmware execution, real inverter behavior, or vehicle safety.

## Primary hardware source and narrow relevance

STMicroelectronics ES0182, Revision 19 (July 2026), section 2.13.1, PDF page 29: STM32F405-family bxCAN time-triggered mode is unsupported and hardware timestamps are unavailable; TTCM must remain cleared; no workaround. Source: https://www.st.com/resource/en/errata_sheet/es0182-stm32f405407xx-and-stm32f415417xx-device-limitations-stmicroelectronics.pdf. Existing repository `reference/can_rx_age_evidence.py` already preserves this hardware limitation; do not overwrite it.

## Next integration action and stop conditions

An authorized, isolated ENME408 writer should reread PR #66 head/reviews/ownership, confirm clean `git status` and `git rev-parse HEAD`, run the packaged full preflight with `--target-repo` and independently supplied `--expected-checkout-sha`, stage **only** missing 15 manifest-listed files, run all old/new Python reference tests in the actual repository context, and request independent review. Stop on head drift, active writer, existing target path, modified SHA, missing evidence, integration failure, or ambiguous merge ownership. No force, main merge, runtime configuration, firmware, hardware actuation or external contact. The new two-file preflight implementation and receipts are retained as an external archive until an authorized integration step; this note alone is not source integration.
