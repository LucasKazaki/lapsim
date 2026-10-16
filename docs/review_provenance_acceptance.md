# E09 review correction acceptance, 16 October 2026

Frozen before the correction to PR #51's integrated review candidate.

1. A native library must have an adjacent bounded, strict `build.json` from the
   project builder. Before any shared-library load, verify schema, actual binary
   SHA256, the exact complete C/header hash set against the current immutable
   controller closure, and the frozen compiler argument/numeric recipe. Retain
   compiler invocation/version, arguments, source hashes and numeric contract in
   the run's native build identity. Reject missing/malformed/drifted receipts;
   do not invent a toolchain identity or silently fall back. The receipt is
   reproducibility evidence, not a signed attestation against a malicious author.
2. Preserve the propulsive unmet-command metric's existing meaning and add a
   separate nonnegative rejected-regeneration magnitude and time integral. A
   healthy full-pack braking case must show rejected regeneration while pack
   charge remains zero and friction braking remains available. Partial acceptance
   must reconcile requested magnitude = accepted magnitude + rejected magnitude.
   These diagnostic additions and stricter native identity use record v3; earlier
   unreleased v1/v2 records explicitly require their recorded source. The held-RK
   physical solver remains policy 2, with unchanged accepted-case physics.
3. `bootstrap --check` must fail read-only when the ready marker is absent,
   corrupt, or mismatches dependency hash, source, Python or setup options.
   It must preserve the environment and marker bytes/mtime and perform no install
   or runtime certification. A matching marker still runs real offline checks.

Tests must include actual C compilation/execution, a copied compatible binary
with mismatching receipt, hash/source/flags/missing-receipt rejection, full/partial
regen accounting, JSON/replay and real browser metric visibility, plus stale-marker
variants and an actual successful setup/offline repeat. Existing numerical
counterexamples and tolerances remain unchanged.
