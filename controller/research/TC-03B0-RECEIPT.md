# TC-03B0 portable verification receipt

Environment: CPython 3.13.5 on Linux x86_64.

Commands:

    /opt/pyvenv/bin/python -S -m unittest -v test_build_reproduction_receipt.py
    /opt/pyvenv/bin/python -S -m py_compile build_reproduction_receipt.py test_build_reproduction_receipt.py

Observed: 23/23 tests passed, 0 failed, 0 skipped; py_compile exited 0.

Reference SHA-256:
- build_reproduction_receipt.py: 41fdd70099ae561fe09c9652e25b67fd67a6c8ad2d21e31ef1b625bd49e18661
- test_build_reproduction_receipt.py: 5478c3e7ef6d0b420115b6a70900c3bb048d757aa0b9a361d6c181d22ba26404

Coverage includes exact commit syntax, source-commit mismatch, commit-object verification, clean-tree evidence, submodule mismatch/uninitialized/conflict states, working-directory and command binding, nonzero builds, missing/duplicate/unsafe artifacts, hardware/flash/actuation scope flags, repeat-build byte identity, artifact drift, toolchain mismatch, incomplete receipts and deterministic canonical hashing.

These are portable synthetic contract tests only. The executable reference and tests were run in the sandbox and are retained in the attached handoff artifact; this receipt does not claim branch CI, an STM32 build, compiler execution against team firmware, hardware access, flashing or vehicle actuation.
