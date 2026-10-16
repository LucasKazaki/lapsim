# Native scenario replay for team review

An explicit normalized scenario can now run through the five compiled C owners: allocation, base guard, trusted pedal reconciliation, clock and final recovery gate. The consumer proposes four abstract slot commands offline. It compares every cycle against the unchanged Python reference, including reasons, output bits, latch, recovery state and full clock anchor, then repeats on the same library.

The built-in synthetic demonstration has 18 cycles: 9 allow a command, 9 hold zero, and 5 are recovering. These are scenario results, not vehicle measurements. The viewer shows the request, proposed command and the reason for each held interval. Its loaded title and provenance explicitly identify the compiled C host source.

From `projects/enme408-torque-control/reference`, with a GCC/Clang-compatible host compiler available:

```text
python -B native_bench_replay.py --example --output-dir PATH_TO_NEW_DIRECTORY
python -B native_bench_replay.py --scenario normalized-scenario.json --output-dir ANOTHER_NEW_DIRECTORY
```

The output must be outside this source checkout and must not already exist or descend from a previous attempt. `--cc PATH` selects an installed host compiler. No compiler is downloaded. Each successful attempt records one real compiler-version call and one five-unit compile; the resulting library runs twice in one bounded child process. The parent records that child's completion and exit status and never loads its DLL.

The existing strict scenario decoder is reused. This presentation consumer requires finite binary64-convertible ordinary JSON numerics, JavaScript-safe integer timestamps/age, a uint32 recovery count, actual Boolean restarts and visible text within the viewer's post-prefix UTF-16 limits. It executes original typed fields, so representable malformed input still reaches the source owners' fault checks. This is narrower than the allocator's standalone uint64 API.

`run.json` seals the actual numerical evidence once. It includes original scenario declarations, original bytes' hash, before/after source and input hashes, actual command logs, library identity, exact bit traces and reference/repeat outcomes. Floats in the diagnostic trace use binary64 strings, so an overflow cannot make the evidence invalid JSON. A native failure or timeout remains a failed attempt.

After numerical agreement, representation and encoding are checked before export. The viewer receipt references the sealed run hash; the run contains no viewer/CSV/HTML hashes. `export-status.json` separately records completed files and any actual export error. Thus an export failure cannot revise the run it references or claim a missing CSV exists. A downstream bundle manifest can bind run, receipt, CSV and standalone HTML without a hash cycle.

Independent review found that the first export error recorded only type/message. The narrow repair adds the failed stage and file, with focused checks using identical error text for different failures. If writing `export-status.json` fails, `export-failure.json` retains that actual failure and the prior export state. If even this fallback cannot be written, the CLI reports structured failure on stderr and exits 2. It never rewrites the sealed numerical run. The final shipped demonstration is a distinct v3 attempt; original v2 receipts and browser evidence remain retained.

Some finite scenarios produce a nonfinite raw allocator total. The retained five-cycle overflow example confirms the raw result, inhibition and subsequent recovery trace against Python, but exits with an explicit unrepresentable status and creates neither a viewer receipt nor CSV. It does not clip, relabel the allocator, discard later cycles or substitute Python decisions.

For the standalone presentation, use the separately scoped LapSim exporter:

```text
python scripts/export_bench_viewer.py --receipt PATH_TO_VIEWER_RECEIPT --output NEW_REVIEW_HTML
```

The viewer checks presentation structure and gate consistency. It does not authenticate a file or reproduce the controller. Reproduction requires the matching source identities and host build in the paired run. The existing Python example, validator policy, chart arithmetic and styling remain unchanged. An optional supplied receipt changes only embedded data and generic embedded-file wording.

The original 9-test attempt failed overall with two Windows DLL cleanup errors. Its semantic assertions completed, but that result was not a test pass. Exact executed source, generator freeze and log are retained. Child isolation fixed the handle lifetime; the later full suite passed 509 tests. The current LapSim viewer/export tests passed 10 cases, and scoped lint passed. Actual desktop and 390×844 browser checks used a loopback URL, including keyboard selection and a latched zero-command event; no direct-file UI test is claimed.

Independent practical review matched 119 cycles across 18 explicit scenarios, checked 32 preflight and 8 UTF-16 cases, and exercised actual owned-child crash/error/timeout cleanup. It verified the narrow IO repair and the final v3 run/receipt/source bindings without rerunning unchanged numerical cohorts. Its exact consolidated receipt is retained in `TC-03I-evidence/independent-review.json`; reviewer-only fixture failures remain labeled separately. Final CI evidence accompanies publication.

This is a host demonstration with synthetic assumptions. No transport, CAN, target linking/execution, firmware flashing, physical motor mapping, hardware validation or safety approval is provided.
