# TC-03E evidence map

- [summary.json](summary.json): six unique ABI/unit rows, both repeated builds, source/tool identities and limitations.
- [original-receipt.json](original-receipt.json): unchanged twelve-object attempt. Its status remains `failed_retained` because the original metadata reader mishandled Windows dependency paths, despite all compiler/inspection exit codes being zero.
- [executed-cortex_m4_objects.py.txt](executed-cortex_m4_objects.py.txt): exact original executed source, distinct from the post-run active utility.
- [file-only-reaccount.json](file-only-reaccount.json): corrected dependency accounting over the existing twelve objects; no compiler/tool rerun.
- [independent-file-review.json](independent-file-review.json): separately implemented checks of the twelve objects and retained evidence; no compiler/tool/model calls.
- [toolchain-provenance.json](toolchain-provenance.json): official archive/checksum/runtime/license provenance and exact tool identities.
- [software-checks.json](software-checks.json): the seventeen focused software checks and source hashes.
- [ci-canonical-path-repair.json](ci-canonical-path-repair.json): later Windows owner-alias fix, reproduced before/after failure and eighteen-check result; it does not rewrite the earlier audit.
- [manifest.json](manifest.json): byte hashes for the committed evidence and current source/protocol files.

The original objects, all raw tool logs and the large verified-toolchain manifest remain local under the original attempt directory. The committed metadata binds their hashes; those generated binaries and the toolchain are deliberately absent. Public review does not imply that a fresh checkout contains every private artifact required for the exact file-only audit.

Read the [feasibility report](../TC-03E-cortex-m4-object-feasibility.md) before using the size or stack numbers. There is no full firmware link, memory fit, complete stack bound, target execution, WCET, hardware result or team ABI approval.
