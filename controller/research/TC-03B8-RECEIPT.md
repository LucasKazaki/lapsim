# TC-03B8 portable verification receipt

Date: 2026-10-02.

Environment:
- CPython 3.13.5
- Linux x86_64
- standard library only

Commands:
- `python -S -m unittest -v test_stack_evidence_gate.py`
- `python -S -m py_compile stack_evidence_gate.py test_stack_evidence_gate.py`

Results:
- tests run: 37
- passed: 37
- failed: 0
- skipped: 0
- unittest exit: 0
- py_compile exit: 0

Reference SHA-256:
`034cdd71f685f5cb55d8f607a1b5e0375437e17133384308c1a742366c78c374`

Test SHA-256:
`e4225bbcc3ceb0bedf9c154635be5c8d238dac9cbf1bdf36581d1f5a6af75e34`

Evidence level: portable synthetic stack-evidence contract only.

No Terps Racing compiler, firmware, linker script, MSP/PSP register, runtime
watermark, debugger, HIL, dyno, track test, flashing, or vehicle action was
used.

GitHub persistence note:
- `TC-03B8.md` and `reference/stack_evidence_gate.py` were persisted.
- creation of `reference/test_stack_evidence_gate.py` was blocked before
  mutation by the connected safety check, so the exact tested suite is retained
  in the external handoff archive rather than claimed as a repository file.
