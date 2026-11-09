# E07 stepping and staged-dispatch source contract

Base: `8248069735c25d93a37221aaeb28be4e8786c305`. Status: **UNTESTED / NO
IMPORTS / NO EXECUTION**. The admission/fixture tranche received an independent
source review with no concrete findings before this work began. Original source
directories, branches, evidence, guards and security settings remain intact.

## Frozen contract before implementation

- Clock planning uses the archive's integer global ticks: 1 ms plant/DRS/thermal
  and brake blend, driver at ticks divisible by 50, allocator divisible by 10,
  scheduled output at completed boundaries divisible by 20 and progress at 100.
  Chunk boundaries never reset phases. Initial/terminal rows remain separate
  mandatory runner responsibilities, not a replacement sampling policy.
- A chunk plan accepts a canonical, pinned raw checkpoint with the exact raw
  journal identity, running one-lap state, component clocks, controller counts
  and cumulative work bounds. It stages at most 10000 ticks/50000 work units,
  bounded by remaining mission limits. It advances no state and claims no full
  physical/checkpoint validation or authenticated execution.
- Staged dispatch composes that plan with the existing external-signature
  adapter, exact environment comparison and explicit finite resource request.
  Both purpose-separated input statements bind the same fresh request challenge
  and source/config/course/cones/line/environment. The original owner still
  owns challenge consumption/non-reuse and later fresh execution admission.
- No input may nominate a command, module, provider, device, fallback backend or
  local trust anchor. A staged request has no execution/qualification authority;
  no original guard is invoked or replaced, no provider is registered, and no
  worker or automatic retry/resume is started. Actual dispatch stays unavailable.
- Supported-tool receipt semantics, trusted key/verifier provenance, actual
  environment observations, full line/physical validation, activity/session/game/
  memory guards, exclusive lease, deadline/watchdog and owned cleanup remain
  external, unavailable prerequisites. No success booleans replace them.

The newly added numerical planning functions and external verifier calls must
not be invoked while Lucas's no-testing instruction remains in force. Review
remains source-only.

## Independent reviews and source findings

An independent reviewer first inspected admission, environment, fixture, input
contracts, tick arithmetic and packaging at
`8248069735c25d93a37221aaeb28be4e8786c305`. It found no concrete defect, confirmed
the exact 6021-byte baseline and its SHA-256, and confirmed the archived driver
overrides and work-counter operations. It did not infer trusted verifier/time/
nonce/receipt provenance from local declarations.

After that review, the same independent reviewer inspected `stepping.py`,
`dispatch_request.py` and this frozen source contract. It found no concrete
defect. Its source comparisons confirmed global ceil-based controller counts,
20/100-tick output boundaries, cumulative mission/chunk work ceilings, cloned
resource proposals, purpose-separated input signatures with the same subject/
challenge and earliest expiry, and the absence of execution authority.

Root manual review also checked origin handling and terminal rejection, booleans rejected
as tick/work/resource integers, remaining horizon/work exhaustion, global-phase
behavior across chunk seams and the distinction between declarations and actual
environment observations. It clarified that returned dictionaries are hash-bound
proposals, not immutable capabilities, and listed source/runtime before/after
identity and single-use challenge/expiry among still-required original services.
No missing service is replaced by a local pass/fail flag or registered provider.

No new parser, clock planner, dispatcher-staging function, verifier callback or
numerical function has been called. Independent inspection does not establish
imports, schema behavior, signature acceptance, physical/checkpoint validity,
installed resource inclusion, numerical parity or actual runtime guard behavior.
No candidate code, imports, syntax checks, tests, simulation, inference or build ran.

A final independent wording review found one documentation inconsistency:
"origin/terminal rejection" incorrectly suggested that a valid running tick-zero
origin was rejected. It was corrected to "origin handling and terminal rejection".
The reviewer confirmed the hash-bound wording and additional pending-service
labels; no code defect or execution-readiness claim was identified.

## Current boundary and next dependency

This tranche implements metadata planning and staged-request composition, not
the complete numerical driver/allocator/gate/checkpoint stepping bridge. It
does not consume a request challenge, acquire a lease, measure actual resources,
start a worker, handle active Stop/Close, admit owned cleanup, retry or continue.
The original actual guard/provider and authenticated producer/numerical evidence
remain unavailable. A future owner must revalidate exact loaded source/runtime,
input expiry, once-only challenge use and physical state, then obtain the original
fresh guarded allocation before dispatch. Output/source/owned-tool/cleanup
admission must follow before any stored result is promoted. There is no new
lap, winner, environment qualification or execution approval.
