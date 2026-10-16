# TC-00B portable receipt

Target: 2027-28 Terps Racing EV torque-control research.

Decision: treat producer/consumer signal semantics as an explicit contract. Vehicle-specific readiness requires target-car evidence for transport/message-map reference, quantity, unit, sign convention, scale/offset, raw/physical ranges, producer period, consumer timeout, timestamp domain, source provenance and car year. Public STM32 documentation or 2026-27 reference values do not satisfy 2027-28 interface readiness.

Live source before write:
- branch head: `8c5edd5603e580ebb769faa2dcdfb8f6793d287a`
- PR #66: open, draft, mergeable
- branch compare: 58 ahead / 0 behind `ops/school-focus-20260930`
- PR comments/reviews/inline threads: none
- native ENME408 registration/local worker ACK: unverified

Current source pins:
- ENME408 README: `07723b05ab5201c2bd3c5d0eeb38f5586c3b412e`
- team evidence packet: `79761b624b732ceb8a9567906cdef001941732bf`
- evidence contract: `227aa14acdb9e325ccb0d1d43c36013019514a89`
- TC-03A: `1a90a57645f2ebc5ed7ac2230c6075edadcddefb`
- ST HAL master inspected: `1f6451c3e07728b4c830744de380e56bf5bc0026`
- ST CAN header blob: `b4c229b209c494669ce05cdef1d4e62ad8c9079d`
- ST CAN source blob: `9278c96e1883ea0909c0c10754fed68b41ca0ef2`
- ST HAL license: BSD-3-Clause

Portable verification:
- initial test run: 30 passed / 1 error; preserved externally
- corrected test run: 31/31 passed, 0 failed, 0 skipped
- `py_compile`: exit 0
- reference SHA-256: `40d5dd14ff8f286b711ead92686d5cad5bfb4ed1a2e819f48b25ef3d7b55f5ad`
- test SHA-256: `f67ed8fa7fd997048b7e7805996055a502a60021d989191a6dd86e3afe8f0ca6`

Frozen synthetic counterexample: raw 100 with producer scale 0.1 N*m/raw means 10 N*m; a consumer using 1.0 N*m/raw interprets the same raw value as 100 N*m. This is synthetic and is not a Terps Racing torque scale.

Evidence level: portable interface-contract validation only. No firmware write, CAN traffic, hardware access, flashing, HIL, dyno, track test, Company Runtime mutation or vehicle actuation occurred.
