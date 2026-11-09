# Bounded seven-policy component integrity, dev26

This E03 controller increment repairs two direct API boundaries and exercises
the existing real allocator/plant components. It does not enable a second course,
qualify a policy or supply an original native provider. The exact committed
source, manifest, wheel, installed test results and raw probe hashes are retained
in the external release acceptance record.

`core_adapter.allocate_core` now rejects simultaneous positive drive and brake
demand, matching `awd_contracts.validate_driver_command`. Seven negative subcases
reproduced acceptance before the repair. The current bridge already normalizes
its driver command, so no corrupted campaign trajectory was demonstrated.

The positive-demand eco solver now rejects negative wheel speed before solving.
Its quadratic-plus-linear cost matches the real electrical converter's forward
propulsive branch; signed mechanical/DC power selects different conversion
branches. No new piecewise optimizer or fallback is invented. The direct policy
previously accepted that unsupported input; the direct adapter could optimize it
before a later actuation rejection. The real plant initializer already rejected
negative wheel speed. An initial test setup encountered that existing guard;
its log is retained separately from the corrected boundary regressions.

The frozen baseline resource and all car parameters, physics components, clocks,
registry IDs, campaign eligibility, original guards and source/environment
admission checks are unchanged. The policy and adapter file pins have changed;
native integration requires newly reviewed source/configuration identities.

## Actual finite verification

The five test files pass 78 cases, zero failures/errors/skips, on Linux CPython
3.12.14. The 16 new cases use actual typed fixture, force, allocation, actuation
and integration functions. No load-observation, source-observer, original-rule
or guard double is used by the new component tests. Older metadata/factory tests
retain their explicitly untrusted doubles and unchanged scope.

The matched rolling probes reset the same synthetic state for each of seven
policies: 5 m/s, 50% pack energy, 70 degrees C, held 100 Nm total drive, parallel
front steering 0.08 rad, zero friction braking. Each runs exactly 20 one-ms plant
ticks with allocator updates at ticks 0 and 10. Their 140 complete endpoints,
initial states and 14 allocator records are retained without ranking. Seven
additional one-tick standing probes and two high-counter parity steps bring the
new tests' committed plant intervals to 149 per complete run. Each integration
call has a 100-work-unit cap; the external test command has a 20-second ceiling.

Other checks cover actual nonuniform load feedback, overspeed slip shedding,
combined slip/PI freeze, PI saturation/unwind, feedforward sign/speed behavior,
eco cost parity with real forward electrical conversion, infeasible allocation,
zero-load rejection, drive-free braking and work-counter rebasing. One explicit
5 W pack-limit stress variant tests actuator-limit antiwindup; it is not a car
calibration. Initializer and direct invalid-input checks are not trajectories.

The source run completed in 3.870 seconds. An external runner retains exact raw
probe JSON and test logs; installed-wheel acceptance is recorded separately.
Independent source/test review passed without another numerical run. These
finite probes leave all seven registry entries `UNRUN` and ineligible.

## Course, profile and admission boundary

The test fixture uses an arbitrary 100 m reference-length field and an all-zero
geometry-hash marker solely to construct typed parameters. No reference track,
original line, course gate or original evidence is supplied or authenticated.
There is no source/environment observer, native worker, process lease, cleanup
receipt or award. No held-out result is read and no test result promotes a policy.
Rolling fixed-control probes and a one-ms launch do not qualify standing laps,
mission continuation, driver tracking, skidpad order or any real car profile.

The best-supported next source course is FSG: its public bundle raw SHA256 is
`c6e4c47a3a4e5aa6efd3c1e4b93d332dc9cd1796f8ae88d02d4a970f6e6525af`,
and its complete cone YAML SHA256 is
`7b3351cd9db27912131b9f5de427861061e2144ed6795498fe980adcd905c30d`.
Its geometry hash is
`0863d0fe882a9e7d756e35b211ee510e829f1dde3384ec85d26d4737e748c0ee`.
The 724-cell clockwise source grid is 306.45041872992834 m long. A complete
sampled driving-reference artifact with canonical frame, physical gate and
reviewed producer/admission chain is still absent. The existing constructors,
raw-reference reader, registry, plan and numerical bridge remain FSI-bound;
removing those checks or fabricating a centerline artifact would not close this
dependency. Portable ordered-skidpad integration also remains unfinished.

The separate ordinary `.6` release still provides its nine-course/four-controller
nominal development suite and skidpad field. Its data-only portable-policy audit
continues to describe the frozen dev25 snapshot explicitly. It is not silently
rebound to dev26 and cannot dispatch or qualify these seven policies.
