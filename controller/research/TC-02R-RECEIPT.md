# TC-02R portable verification receipt

Environment: CPython 3.13.5 on Linux x86_64, standard library only.

Commands:

- `python -S -m unittest -v test_can_tx_publication_evidence.py`
- `python -S -m py_compile can_tx_publication_evidence.py test_can_tx_publication_evidence.py`

Observed portable result: 24/24 tests passed, 0 failed, 0 skipped; py_compile exited 0.

Portable SHA-256:
- `can_tx_publication_evidence.py`: `cd130d2b19c464f98b3f2a9787f1be15d74e8dc71cc2ec3a9980f6fe6ea7cc6b`
- `test_can_tx_publication_evidence.py`: `350cadf6afaeac990deb8b6a0b7ac53fa0454b6cba38facbf46e5a86d7c748ec`

Coverage includes intent-vs-enqueue-vs-completion separation, explicit no-free-mailbox rejection, arbitration-loss/transmit-error/abort terminal failures, mailbox occupancy/reuse, invalid completion ordering, contiguous evidence sequence, free-level bounds, latest-intent versus latest-transmitted lag, deterministic JSON, and zero action authority.

Evidence level: portable synthetic host-language evidence only. No Terps Racing firmware, CAN traffic, STM32 target, inverter, HIL, dyno, track test, firmware flash, watchdog/shutdown change, or vehicle actuation was exercised.

The full test file was retained in the external handoff packet because the connected GitHub safety check blocked its create-file write. The reference implementation and TC-02R research note were persisted to the branch.
