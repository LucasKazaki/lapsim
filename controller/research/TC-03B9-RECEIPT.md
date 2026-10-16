# TC-03B9 portable verification receipt

Date: 2026-10-02

Portable synthetic interrupt-priority/preemption analysis only.

Commands:
- `python -S -m unittest -v test_interrupt_preemption_gate.py`
- `python -S -m py_compile interrupt_preemption_gate.py test_interrupt_preemption_gate.py`

Results:
- 42/42 tests passed
- 0 failed
- 0 skipped
- py_compile exit 0

Reference SHA-256:
`953861e509821724d3f8bbd15feb9b4049ccdc636bffedc5292eb019d7580fdf`

Test SHA-256:
`8c65bbfdc1b16ba33395b8443447ea055d6d01d1c8fafeddc492ea80d836e532`

No project firmware or hardware was exercised. This receipt is not vehicle, safety, timing, or acceptance evidence.
