# TC-03H — Portable candidate allocator

**The actual equal-share allocator now has an additive C owner, compared through the existing native guard, trusted-pedal, clock and final gate.** Its five-unit offline path generates candidates in C and reports proposed commands only after those gates. Python owners supply the expected path. The existing Python policy and all earlier C ports remain unchanged.

## Source contract and domain

The [protocol](TC-03H-portable-allocator-protocol.json), SHA-256 `899d3261dbf6542a035833fa6082dca1626ec536c02ea44e63e843a9c9781ce3`, was committed first at `d990053a668acda5838fc5badcf78c0063b5b58e`, based on PR75 `d2e736450f8528356d45641de7a118cd4129ff7e`. It binds the actual source, every validation diagnostic in order, floating operations and supported decoder domain. The first native implementation/case generator was frozen separately before its first compiled attempt; each later caller repair was committed before a new attempt. [The current generator snapshot](TC-03H-allocator-case-generator.json) preserves those earlier failure identities.

`torque_allocator.h/.c` add allocator version 1, fixed-size input/config records and `tc_allocate_propulsive_torque`. Existing ABI version 1 and numeric contract 2 stay unchanged. The interface has no heap, retained controller state, I/O or physical mapping. Inputs, outputs and their storage must be complete, aligned and non-overlapping. Four slots are synthetic scenario positions, not confirmed wheels or motors.

Numeric inputs are ordinary decoded int/float fields projected once to binary64; Booleans are not numbers. The C request distinguishes malformed numeric sources, including unrepresentable integers, from numeric-tagged nonfinite floats so the existing fault names remain exact. The timestamp/age domain is nonnegative ordinary integer no-wrap milliseconds through `UINT64_MAX`. Larger Python timestamp integers are explicitly outside this C domain and the bridge raises a domain error instead of inventing a Python-equivalent fault.

Successful Python results retain the original request's int/float object. C result parity compares its normalized binary64 value, including signed-zero bits, and does not claim preservation of arbitrary Python integer precision or object type. Custom Python subclasses, conversion/equality hooks and arbitrary duck-typed records are excluded. C-only outer record and NULL failures have separate documented diagnostics.

Only the source unit string `N*m` is supported. The bridge rejects source strings containing any embedded NUL; it cannot truncate `N*m\0extra` into a valid unit. A raw valid C `tc_text` has a bounded first terminator and ignores bytes after it. That representation is distinct from original Python string identity. Text semantics of other ports were not changed.

## Exact allocation behavior

The owner has no weighted fairness objective or aggregate-capacity pre-sum. It shares the request equally among enabled positive-cap slots, collects all saturated slots in ascending index order, applies each cap and subtracts each served capacity in that same order. Every saturated round removes at least one of four active slots; a nonsaturated round exits. No dynamically sized storage or unbounded search is needed.

The source contains no builtin `sum` or `fsum`. Its only torque total is numeric-contract-2 `wheel_total`: four separately rounded additions in slot order. Capacity subtraction, division by active count, `share + 1e-12`, output addition and individual remaining subtractions are also preserved. The C source requires binary64 parameters and `FLT_EVAL_METHOD == 0`; host builds disable fast math, finite-only assumptions, contraction and excess precision. Ordinary IEEE nearest rounding and retained subnormals remain explicit environment assumptions. [Python's float documentation](https://docs.python.org/3.12/tutorial/floatingpoint.html) and [GCC's option documentation](https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html) explain the represented-value and compiler concerns; empirical supported-build parity remains necessary.

The port deliberately preserves existing source quirks:

- A positive request at most `1e-12` can return an `ok` zero proposal when a slot is available. Exact zero succeeds before available-slot detection, after all earlier validation; its result is positive zero even for a `-0.0` request.
- Saturation compares capacity with `share + 1e-12`. For request 1 and one cap computed as `1 + 1e-12`, the raw proposal exceeds the request and retains `ok`. The existing shared contract rejects it as `candidate_exceeds_request`; the full proposed command stays positive zero.
- A remaining shortfall at most `1e-9` can retain the `ok` label when capacity is exhausted. No status relabeling is added.
- Some finite extreme-cap/request fixtures produce a nonfinite raw delivered total. Direct parity retains that source result as exact float-bit signatures; the existing validator/guard rejects `invalid_candidate_delivered`. There is no post hoc power/torque clipping or widened acceptance tolerance.

The successful finite direct corpus contains 85 over-request candidates and eight invalid-delivered candidates, alongside accepted and explicit source-fault records. These are raw producer classifications, not allowed command counts. A faithful producer port is not proof that every producer candidate passes its separate acceptance contract.

## Actual verification and caller boundaries

The first successful receipt at runtime commit `e93124c82634eaf6f907a20ac329780c6a8bc463` contains 13,273 direct cases: 4,608 fixed request/cap/enable combinations, 8,192 seeded finite-bit cases, and named threshold/schema/time/mixed-fault cases. It checks every raw field and downstream contract diagnosis against the untouched Python owner. An additional 9,229 checks exercise ABI tags, initialized results, NULLs, text and the uint64 decoder boundary. Both complete finite passes agree.

The actual five-unit composition compares 5,120 cycles, including 1,024 healthy and 4,096 recovery/trust/clock/restart cycles. It verifies raw candidate bits, base/effective guard output and metadata, the full clock anchor, latch, actually proposed slew history, recovery state/streak/generation, reason and final command bits. Observed coverage includes 1,534 positive allowed cycles, 3,330 held cycles, 193 positive allowed limited cycles, 384 clock faults, 256 latch clearances and 128 restarts. Every held command is exact positive-zero bytes. Coverage assertions prevent an all-inhibited fixture from masquerading as a passing pipeline.

The new caller follows the existing four-unit owner order and leaves all owners unchanged. One explicit interface projection is needed: after an inhibited C guard it supplies the Python pipeline's effective zero/fault candidate to the native recovery gate. Otherwise, a contradictory raw candidate would be diagnosed by the gate's earlier generic validity check instead of preserving the source's more precise guard fault reason. The raw allocator and guard remain recorded separately.

On a clock-only fault, the C gate already owns an explicit clock-fault field and validates its paired candidate/guard first. The caller therefore retains the valid raw pair and lets that native clock field inhibit it. Passing a zero candidate beside a positive guard would violate that API's pair-validity precondition. The expected source reason, full clock state and final proposed command are still compared exactly. No Python allocator or guard result is substituted into the native proposed path.

Two initial caller failures are retained in [the evidence](TC-03H-evidence/README.md). Both held positive zero, but reason/state parity correctly failed: the first passed a contradictory raw candidate to the gate, and the second zeroed its candidate on a clock-only fault while retaining a positive guard. Their executed driver/generator bytes, receipts and exact repairs remain explicit. The C allocator/header/probe, old C units and compiled library hash were unchanged across all three attempts. The repairs altered caller projection and diagnostic regression assertions; source policy and fixture inputs were not tuned.

The full local reference suite passes **500 tests** in 22.531 seconds; two local temporary five-unit host builds have identical hashes. A plain local host probe compiles and exits zero. Actual ASAN/UBSan CI must pass at the pushed source head before the draft is published; it is not inferred from that plain probe. None of these durations is a controller timing measurement.

An [independent practical review](TC-03H-evidence/independent-review.json) found no actionable defect in the supported scope. It used its own encoder/ABI definitions and frozen seed, one separate host build, 11,039 bit-exact direct cases twice, 4,663 ABI assertions and 5,120 full-state composed cycles. A same-library follow-up passed all 296 independently generated invalid raw candidates through both clear and retained latch paths: 592 correctly inhibited proposals. It checked the earlier caller reason regressions, signed-zero fault diagnostics and the source/raw-C text boundary. The independent DLL used a different basename and hash; no cross-worker binary identity is claimed. Its exact receipt preserves source/case hashes and limitations, separately from final-head CI metadata.

## Reproduce the offline checks

From the repository root with a supported GCC/Clang host compiler:

```powershell
py -3.12 -B projects/enme408-torque-control/reference/allocator_parity.py --output .\artifacts\allocator-new-attempt.json
py -3.12 -B -m unittest discover -s projects/enme408-torque-control/reference -p test_allocator_parity.py -v
```

The output receipt must be new. It binds the protocol, generator, source, ABI sizes, compiler/version/arguments, library and result digests; attempted verification failures retain their own status and traceback. The prior three-/four-unit host builders and historical ARM experiment cohorts remain separate. This increment makes no ARM compiler/object or target-execution call.

The full proposed path still uses offline Python orchestration and caller-owned normalized data. It does not establish sensor provenance, physical motor calibration, traction/slip/yaw performance, regeneration, firmware linkage, MCU numerical parity, resource fit, timing/WCET, HIL, CAN behavior or independent shutdown authority. This is Codex-assisted engineering evidence for review, with no hardware actuation or safety-certification claim.
