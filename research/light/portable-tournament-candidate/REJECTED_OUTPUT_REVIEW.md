# Rejected-attempt and quarantined-output source review

Base: `4fbd738855b407b2a8daaa63ceb04e86384120e5`.
Bounded E07 source tranche. **UNTESTED / UNBUILT / UNQUALIFIED.**

## Findings and source basis

Independent read-only review identified two P2 consistency/evidence defects:

1. On post-step domain or physical-gate rejection, `advance_chunk` correctly
   rolls back accepted state/memory but records only the prospective physical
   state. Newly calculated requested/proposed/limited/friction commands,
   steering, driver command and allocation diagnostics in `m` are discarded.
   This conflicts with AGENTS.md's rejected-raw-candidate preservation contract.
2. `resume` forbids rejection data only at the initialized origin. An advanced
   running/completed/time-limit checkpoint can carry an arbitrary rejection
   object or string; endpoint telemetry ignores it. This permits phantom fault
   evidence to propagate through otherwise successful outcomes.

An additional handoff gap is present: final source observation happens before
the chunk is assembled/returned, and replay's final observation precedes report
return. A mismatch or observer exception correctly blocks success but exposes
no supported payload for the already-produced output. Durable crash/exception
storage is explicitly external; giving the genuine provider bounded diagnostic
bytes can improve cooperative failure preservation without supplying a guard.

## Frozen repair contract, before implementation

- Preserve all scientific kernels, policies, state evolution, thresholds,
  rollback behavior and earlier artifacts. Add no observer, producer, provider,
  resource allocation, writer, launcher, override or actual admission.
- Retain accepted state/memory unchanged on rejection. The existing
  `rejected_state` slot becomes an explicitly versioned NEW nested RAW attempt
  record: stage, interval clocks, exact accepted-state/memory hashes, full
  prospective typed state and full provisional memory/controls/diagnostics.
  Its `committed` and authority flags are false. This is not the original
  bare-state format, and no legacy rejection record is silently migrated.
  Outer raw v1 journal/checkpoint/chunk containers retain their existing fields.
- Non-invalid checkpoints must carry no rejection record. An invalid outcome
  may carry no candidate when an initial observation, driver/allocation or
  integrator failed before producing one. Present records must match the exact
  bounded nested schema, accepted-state/memory hashes and next interval clocks.
  They are diagnostics, never a state/controller resume path.
- Do not require rejected physical data to pass the domain checks that caused
  rejection. Check structural dataclass identity/clock bindings and recorded
  counter relationships only; preserve the complete raw values without clipping.
- Assemble a bounded chunk/report before its final source observation. If that
  observation refuses or raises cooperatively, continue to raise, using a
  dedicated exception carrying canonical quarantined diagnostic bytes. Those
  bytes explicitly prohibit admission, retry, continuation and qualification.
  No successful output or ordinary journal append follows a failed source gate.
- Quarantine serialization is bounded and does not truncate originals. It
  performs no I/O. The genuine original owner must retain those bytes, original
  errors, partial/crash evidence and actual cleanup under its existing controls.
  Memory exhaustion, process death, arbitrary earlier exceptions and unsupported
  receipt/lifecycle integration are not solved by a library exception payload.
- No candidate execution, imports, syntax checks, tests, simulations, inference,
  build, installation, pushes or public publication.

Original predicate, producer/numerical evidence, actual loaded-source/runtime
observer, environment lock and genuine guard/receipt/cleanup implementations
remain missing. No new original-source access became available in this tranche.
Their exact inventory and earlier bounded lookup outcomes remain in
[INTEGRATION_HANDOFF.md](INTEGRATION_HANDOFF.md).

## Source repairs and independent follow-up

The two rejection sites now capture `lapsim.portable-light-rejected-attempt.raw.v1`
in the existing slot. Accepted state/memory hashes bind the rolled-back output;
the versioned record retains stage, start/candidate clocks, prospective state,
full provisional memory and false commit/authority flags. Validation explicitly
forbids records on non-invalid outcomes and reconstructs known state/control
types. It checks next-tick identity/counter consistency without calling
`_observe` or reapplying the failed physical-domain gate. Invalid outcomes with
no produced candidate may still retain `None`.

`raw_failures.RawOutputQuarantined` supplies a new metadata-only raw transport
with a 3 MiB artifact cap and 4 MiB complete envelope cap. It retains original
error type/message and a chained original exception. Its false observation,
authority and retry/continuation flags remain explicit. The decoder verifies
transport consistency only. Both chunk and replay paths assemble and bound
their raw output before final source observation, and still raise on failure.
Genuine provider contracts now explicitly require retaining diagnostic bytes,
real cleanup and failure propagation rather than promoting the nested artifact.

Independent follow-up source review found both P2 findings addressed and no
concrete defect/regression. It confirmed the stage-specific memory captures,
typed next-tick/configuration/counter bindings, no physical-domain reacceptance
of failed candidates, continued raising after failed source observation, and
no import cycle or I/O in quarantine transport. The reviewer found no emitted
rejection that the inspected validation would falsely refuse. This is source
inspection only, not runtime or regression-test evidence.

The raw v1 outer field inventory is unchanged. The new nested rejection record
is not the archived bare-state representation; fresh source identity is required
and old raw/qualified histories are not silently migrated. Complete accepted
and rejected data remain raw and unqualified, without any retry capability.

No candidate parser, helper, state/control constructor, signature/observer/
provider callback, numerical step, replay, file-writing or Tk function was
invoked. No candidate import, syntax check, test, simulation, inference, build or
installation ran. Original producer/observer/guard evidence, actual exception/
crash durability, cleanup and app acceptance remain unresolved dependencies.
