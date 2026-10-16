# TC-03B20 portable verification receipt

Accessed 2026-10-04.

Topic: cross-clock timestamp alignment evidence.

Portable commands:

- `python3 -S -m unittest -v test_cross_clock_alignment.py`
- `python3 -S -m py_compile cross_clock_alignment.py test_cross_clock_alignment.py`

Observed:

- tests: 33
- passed: 33
- failed: 0
- skipped: 0
- compile: pass

SHA-256:

- reference `510e64479b4e9e1b5d3f4e916b128c0e9f0bf3333fea967e93928ffeb57cfe7f`
- tests `ca4a3470a85bcd1f303aebc00dea3033537638fde138dd8976c3809b51266e57`

Frozen synthetic counterexample:

- direct subtraction of independent raw clocks: 30 ms
- reviewed offset estimate: +20 ms
- absolute alignment uncertainty after a 10 s holdover at the supplied 100 ppm
  bound: 6 ms
- mapped sample-age interval: 4–16 ms
- synthetic 10 ms threshold relation: indeterminate

These values are scenario inputs only, not Terps Racing measurements or
requirements.

Repository discovery before the write:

- PR #66 head `4440eba0f47b3a1ba1bb17d8ae30ee92a5d9db8a`
- 73 commits ahead / 0 behind `ops/school-focus-20260930`
- no submitted PR reviews or discussion items
- issue #61 has no native APPLY_RECEIPT
- Company Runtime registration and local worker ACK remain unverified

GitHub persistence in this pass:

- `SOURCES-TC-03B20.md` created in commit
  `2ecacbb9bdcbe3ad0e573b0a939d6dce8baafe3b`
- the full research-note create was blocked before mutation by the connected
  safety check
- no lower-level Git write bypass was attempted

Evidence level: portable synthetic timing analysis only. No native MCU timing,
CAN capture, source-specific synchronization, firmware flashing, HIL, dyno,
track, or vehicle execution was performed.
