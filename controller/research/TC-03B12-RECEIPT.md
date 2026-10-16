# TC-03B12 portable verification receipt

Date: 2026-10-02.

Evidence level: portable synthetic clock-uncertainty contract only.

Commands:
- `python -S -m unittest -v test_clock_uncertainty_gate.py`
- `python -S -m py_compile clock_uncertainty_gate.py test_clock_uncertainty_gate.py`

Results:
- 41/41 tests passed;
- 0 failed;
- 0 skipped;
- py_compile exit 0.

Reference SHA-256:
`7ec921007c02edf5514d281ac4be829ce5cc81949823079670750b87083bad8a`

Test SHA-256:
`e0e488092af4a0eff50434a1e29dcb3f28bda7c7aa2ba9ac7508edc42e348c15`

The tests cover bound ordering/provenance, elapsed-time interval propagation, conservative minimum-persistence and maximum-age conversions, nominal-threshold early/late counterexamples, cross-domain rate separation, stability gating, deterministic serialization, and explicit non-claims.

No Terps Racing compiler, firmware, RCC register, oscillator, timer, debugger, CAN interface, HIL system, dyno, track test, flashing, Company Runtime or vehicle action was used.
