# Finite battery charge over one cell

The default battery could satisfy the entry power/voltage limit while its
held-current interval removed more charge than the pack contained. The old
SOC endpoint clamp concealed that excess. This change explicitly narrows the
supported interval domain; the previous model did not promise continuous
within-cell charge or voltage feasibility.

The retained small case starts at 5 m/s and SOC 0.000001, requests 100 Nm,
and advances 0.5 m. PR15 accepts 0.09884059746607142 s at
2958.3962589648895 W and 9.78305641192093 A. The resulting unclamped SOC is
-0.00001644161509376886, but stored SOC is zero. The new source rejects this
interval before committing vehicle state. The initial serialized vehicle is
unchanged, including the suspension's pending load-query fields.

For the repository's positive-discharge convention, the policy is
`delta_Q_Ah = I_A * dt_s / 3600`. Discharge cannot exceed `SOC * capacity_Ah`;
charge cannot exceed `(1-SOC) * capacity_Ah`. Eight binary64 ULPs at the charge
scale accommodate comparison roundoff. All built-in batteries expose a pure,
optional preflight capability. The stateful batteries enforce the same bound
again in their own update. The ideal battery retains its infinite-charge model.
No force, terminal power, current, duration, or energy is clipped after the
force solve. No cell subdivision or control retuning is introduced.

The frozen protocol was committed as `cd99a6b` before production edits. The
initial regression run on unchanged source recorded 14 failures and 9 passes;
the first repair exposed suspension query staging in complete-state snapshots.
The final bounded suite has 116 tests and 722 subtests passing, including 30
new regression cases. The existing generated numerical contracts add 14 passing
property tests. Source inventory/static-site checks and the critical Ruff gate
pass. Relative to the exact PR15 baseline, Pyright introduces no diagnostic
fingerprints; its existing 267 errors and 49 warnings remain visible.

The same 2,160-cell grid ran on the original and repaired source with eight CPU
workers and one native-library thread per worker:

| Outcome | PR15 baseline | Charge-budget candidate |
|---|---:|---:|
| Accepted | 1,448 | 1,344 |
| Rejected | 712 | 816 |
| Accepted interval Coulomb overruns | 104 | 0 |
| Rejected telemetry mutations | 0 | 0 |

The 104 newly rejected IDs are exactly the 104 old overrun IDs. All 1,344
retained accepted result rows are identical, and all 712 original rejection
rows are identical. The named healthy control also retains identical complete
telemetry. These are separate evidence scopes: complete telemetry equality is
not asserted for every grid cell. The repaired sweep used 2.929 s wall time
and 12.297 worker CPU seconds across eight processes; maximum observed worker
peak working set was 71,872,512 bytes. This small run demonstrates actual CPU
parallelism, without claiming a throughput benchmark.

An actual local Qwen GPU review proposed two adversarial cases. Both were
rejected because they reversed available-charge reasoning and equated power
with current without voltage. The raw response, reviewed source hashes, and
explicit dispositions are retained. Model suggestions do not set acceptance.

See `results/charge-budget-2026-10-15.json` for source/evidence hashes, exact
case IDs, observations, and the comparison. The source-bound local-model
assessment is `results/charge-budget-local-model-review-2026-10-15.json`.
The frozen physical/domain policy and primary references are in
`charge-budget-protocol-2026-10-15.json`; the public contract is documented in
[`docs/battery_model.md`](../../docs/battery_model.md).

This is a synthetic held-operating-point model repair. It does not establish
continuous voltage feasibility, real-pack capacity, calibration, target timing,
hardware validation, or safety certification. Existing custom components keep
their structural interfaces; arbitrary failures after custom commit methods
begin are outside the preflight rollback guarantee.
