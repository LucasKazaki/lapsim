# Light startup source review — 6 November 2026

Review base: `8ee433d7395b4b69b04b0d08228d29a32b3c7463` on
`cloud/lite-tournament-integration-20261105`. Status: **source inspection only**.
No candidate imports, parsers, syntax checks, installs, builds, tests, simulations,
resource/process probes, leases or tournament launches ran during this work.

The existing `scripts/bootstrap.py` always calls `check()` after installation,
including in `--check` mode. `lapsim.diagnostics` executes synthetic bicycle,
controller and component runs/replays. That bootstrap installs the root project,
not the separate light distribution. `setup_lapsim.cmd`, `setup_lapsim.ps1`
and `launch_lapsim.cmd` therefore cannot serve as source-only light preparation.
Both desktop paths lead to the ordinary `lapsim.ui.app`; the legacy web server
starts `controller_tournament` or `tournament_sweep`, not this light backend.

The separate `scripts/prepare_light_tournament.py` does not call those paths.
Start/preparation use only standard-library utilities; the separate `--evidence`
branch imports the exact verified portable metadata command modules. There is no
network/Git/HTTP, solver, browser, numerical bridge, private adapter, provider
registration or simulation dispatch. `--start` returns 2 with concrete missing requirements
before setup. `--prepare` verifies two already-local inventories, creates only
fresh staging attempts, and creates an empty venv without pip or package builds.
It refuses unknown/extra candidate files and never regenerates a source pin.
Its setup marker/gate cannot act as original admission or acquire a shared lease.

The provisional preparation interpreter is Windows 64-bit CPython 3.13.15,
recorded by existing ordinary Windows documentation/evidence. That is not a
recovered exact light runtime. The candidate contains five namespaces, no
mandatory third-party runtime requirements, an explicit optional Ed25519 verifier
extra and a metadata-only `lapsim-light-evidence`
console declaration. It has no native campaign/GUI start entrypoint.
Its setuptools build floor is not a complete pinned install contract. NumPy/
SciPy belong to the separately invoked archived producer. The optional native
Chrono study does not supply this light plant or close its missing contracts.

## Feature coverage of the frozen cloud candidate

All source in this table is unexecuted/unqualified in this integration session.
"Present source" does not mean runtime acceptance. This table makes no claim
about unseen main-PC r02/r03 adapter code or all historical feature requests.

| Requested area | Concrete source | Scope and remaining gap |
| --- | --- | --- |
| Four-drive AWD and seven policies | `lapsim_light_policies/core_registry.py`, `policy_layers.py`, `core_adapter.py` | Present source: seven synthetic four-channel AWD candidates, front steering, regen OFF. Qualification remains UNRUN and campaign eligibility false. No verified actual-car maps. |
| Coupled motion/electrical/aero/load/DRS/thermal | `lapsim_light_core/planar.py`, `powered_planar.py`, `torque_light_*.py` | Copied scientific kernel source. Common lumped tire temperature, not detailed per-tire thermal/CFD or an external physics engine. No measured calibration or runtime equivalence proven. |
| Course construction and input identity | `lapsim_light_course/course.py`, `_fsi_geometry.py`, `racing_geometry.py` | Present source for the exact map-derived FSI approximation, input encodings and geometry/frame checks. No nine-course/event-map implementation or admitted racing-line bundle. |
| Synthetic standing fixture | `lapsim_light_campaign/fixture.py` and baseline JSON | Present byte-bound parameter/DTO construction. Source preparation does not advance or admit the plant. |
| Fixed clocks and complete one-lap numerical loop | `stepping.py`, `plant_tick.py`, `numerical_bridge.py` | Present source: 1 ms plant/blend, 50 ms driver, 10 ms allocator, 20 ms scheduled logging, 100 ms nominal progress. Actual `make_context` accepts only one FSI course and `one_lap`; dormant ten-lap labels are not a ten-lap implementation. Real observer/predicate bindings still required before initialization. |
| Source/input admission and environment | `admission.py`, `input_contracts.py`, `environment_contract.py`, `numerical_inputs.py` | Present declaration/signature interface checks. Actual key/verifier provenance, challenge/time services, observed source/runtime and exact binary environment are not established by those comparisons or the optional verification primitive. |
| Optional Ed25519 verification primitive | `detached_verifier.py`, optional extra and verifier wheel lock | New real public-library verification of exact bounded existing-domain bytes; no signing/key generation, default policy, installation or registration. Official metadata pins the optional Windows CPython 3.13 wheel recipe. Cryptographic behavior and loaded-library/native provenance remain untested/unqualified; this is not original receipt authentication or complete runtime admission. |
| Deferred runtime/distribution measurement | `runtime_observation.py`, `distribution_observation.py` | New actual selected interpreter API reads and bounded wheel/installed-RECORD byte verification, for later authorized invocation. Unsupported facts/layouts refuse. Raw schemas are incompatible with environment v2; no full SourceObserver, current rounding/ABI/loaded-native closure, authentication, registration or observation command is supplied. Entirely uninvoked and untested. |
| Guarded dispatch and cleanup | `guarded_dispatch.py`, `dispatch_request.py` | Present v2 boundary requiring real external original providers. Missing providers refuse before work. No actual guard, resource lease, watchdog, supported-tool authentication or cleanup adapter supplied. |
| Raw storage, rejected attempts and failures | `raw_journal.py`, `raw_failures.py`, numerical loop | Present source for immutable origin/chunk/terminal chains, exact rejected candidates and bounded cooperative quarantine. Actual I/O, interruption, crash/power-loss retention and owned exception cleanup are unverified. |
| Continuation | `continuation.py`, `continuation_archive.py` | Present source for fresh outer ancestry, copied history accounting and child archives. Genuine original continuation admission/provider is absent. A terminal journal is never silently reopened or given new credit. |
| Replay and export | `raw_evidence.py`, `numerical_replay.py` | Present storage-chain verification/export and exact numerical replay program source. Numerical replay needs fresh real owned admission and original v2 requests/provider; no numerical replay has run. |
| Run/progress/active Stop/Close | `ui_model.py` | Passive saved-evidence model/panel only, no registered application. All runtime controls are disabled. Missing implementation: active lifecycle mapping and actual source-bound UI updates/cleanup. V2 worker callbacks are explicitly `None`. |
| Seven-policy fair tournament and scheduling | `tournament_plan.py`, `tournament_results.py`, registry and cell program | New reusable source freezes complete matched origins/order/limits and reduces full-field raw coverage. A next-cell metadata proposal needs a completed prefix and missing suffix. Actual admitted multi-cell dispatch, concrete runtime launcher, qualification progression and original-owner integration are still missing. |
| Scores, ranking and winner | `tournament_results.py` and raw chunk/summary awards | New source computes descriptive exact-tie time/energy orders, Pareto sets and display-collision flags only for a complete comparable RAW field. Points/winners remain `None`, eligibility false; no numerical validation or hidden-attempt authentication. Applicable scoring rules/reference field/penalties and a qualified matched comparison are not integrated. |
| Broader requested displays/research | No active light G-G/replay dashboard, GA/multi-course or detailed full-backend mapping in this candidate | These features cannot be marked implemented from the existing passive panel, old tournament viewer or full-simulator plans. Their concrete contracts and acceptance remain open. |
| Plan/comparison file workflow | `tournament_cli.py` and preparation-script `--evidence` dispatcher | Implemented source for create-plan, inspect-plan and compare-results using real pinned files. Exclusive new outputs, complete missing/failure reporting, incomplete-report exit3. User-facing source and installed-console paths remain unexecuted; no evidence command starts or admits a worker. |
| One-command download/install/start | Offline preparer and hard-refusing start branch | Source staging and metadata file commands implemented for later execution. Automatic acquisition, complete dependency installation and guarded tournament start remain unavailable. The native HANDOFF explicitly confirms that the start provider and exact dependency recipe do not exist yet. |

The later independent main-PC audit reports 16/16 public archive hashes matched,
12 missing required paths, zero feature tests/launches, and 26 acceptance gates
untested. Its Git permission denial and the unresolved process-ownership review
restriction remain in force. Neither that audit nor this source review qualifies
the cloud candidate or establishes current admission. The sole proposed runtime/
test execution owner is main-PC task `<PRIVATE_SOURCE_OWNER_ID>`;
the original source owner retains its adapter/frozen-contract work. This cloud
task does not mutate either main-PC workspace or duplicate their work.

## Readiness handoff

The [startup contract](light_tournament_startup.md) states the exact commands,
immutable input identities and refusal behavior. The earlier official candidate
transfer failed terminally and no patch was found in the bounded Downloads check.
It was not retried. Main-PC Git access separately returned Permission denied and
was not retried here. No alternative download/private-transfer mechanism exists
in the preparer. No private original bytes were uploaded or published.

The frozen native HANDOFF API report has now arrived and confirms that the
native campaign-start provider and exact installable recipe do not exist yet.
Reaching a usable start command requires their implementation using actual
original source/receipt/guard closure and exact numerical/producer/authentication artifacts. Source
access/transfer and the process-observation restriction need supported resolution.
Then map the actual interfaces without guessed adapters, freeze a new integrated
source/install identity, and have the sole main-PC execution owner perform the
separately authorized finite guarded installation/acceptance and UI lifecycle
checks. None of those steps is authorized by a source hash or setup marker.

## Independent inspection

The independent reviewer inspected the original setup paths, then the new source
preparer and frozen behavior contract. An initial Git-based preparation draft
had two concrete issues: inherited Git configuration could redirect transport or
invoke configured commands, and killing a timed-out Git parent did not establish
cleanup of its descendants. All Git/network/subprocess paths were removed. The
parent's later main-PC Git denial separately reinforced keeping acquisition out
of this revision. No draft command was ever invoked.

The reviewer inspected the final offline source, including the local inventory
pins, fresh-copy checks, workspace marker, setup gate, interruption handling,
directory-queue bound and source feature matrix. It reported no remaining
concrete findings. No reviewer edits, candidate parsing/imports, syntax checks,
tests or runtime execution occurred. Windows filesystem/venv/interruption
behavior, complete dependency installation and real startup remain unvalidated.

The subsequent source implementation from `7533a0f987b6264b17e3b1c39ec7c26794b4bc39`
adds the reusable frozen-field builder and raw field reducer described in the
coverage table. It performs actual metadata matching, full-field coverage,
finish-based metric extraction, exact ties and Pareto comparisons; it adds no
runtime provider or scoring formula from another model family. Independent
inspection found two concrete gaps: zero-declared origins could retain actual
component clocks/controller memory, and finish fractions were not joined to
their recorded gate poses/clocks. The repairs require the pinned bridge's full
zero-start memory and component/work ledgers and reuse its original gate-record
validator, with strict adjacent component clock checks. This checks stored
event consistency only; physical trajectory/admission validation remains open.
The independent follow-up matched all 31 Memory defaults and the actual
initializer/component ledger defaults, then rechecked the fixed gate and result
joins. Both findings were closed by inspection; no further concrete code defect
was identified. Packaging, Windows behavior, algorithms and refusal paths have
not been imported, executed, syntax checked or tested.

The file-workflow implementation from `e81513dd1c33a956b42a1920d87f65b187ead85e`
adds `tournament_cli.py`, its metadata-only console declaration, and the existing
preparation script's pinned `--evidence` dispatcher. The dispatcher checks the
complete source inventory and loaded metadata namespace paths/bytes before
calling the actual CLI; it imports no numerical bridge or original native helper.
The file commands require explicit digest pins and regular local inputs, validate
all inputs before exclusive output creation, retain all incomplete/failing slots,
and write a valid incomplete comparison before returning exit 3. They do not
modify raw journals, establish completed laps, admit workers or grant awards.

Independent source inspection found two standalone-console path issues: an
aliased code origin could conceal the immutable candidate's actual root from
the output check. The code-origin chain is now checked before deriving that
protected root. A relative input could also become UNC when made absolute from
a share working directory; the absolute namespace is now rechecked before any
filesystem checks. The independent follow-up closed both findings. The wrapper
already required a non-aliased frozen candidate. No CLI, import, parser, syntax
check, file-I/O exercise or test was run to establish these behaviors.
The follow-up identified no remaining concrete code/documentation findings.
CLI help/refusals, Windows regular-file/fsync behavior, installed console
generation and end-to-end command execution remain untested.

The next source tranche from `28c11d8a229f11cbba5a0b1e48fde5af555b9a1d`
adds deferred selected-interpreter facts and bounded wheel/installed-RECORD
measurement. It does not expose a probe command or register a SourceObserver.
Independent inspection found ZIP normalized-name identity loss and owner-control
exception normalization; original-name equality and closed exact error-type
filters repair them. Follow-up also covered the optional compression import,
actual JSON parser error and normalized installed-path profile. The reviewer
closed those findings by source inspection and identified no further concrete
defect. Actual observation, platform behavior and all runtime acceptance remain
untested. Full ABI/current rounding/stdlib/native loaded-code closure and
authentication remain absent; the preparer only receives updated source pins.

The subsequent source tranche from `c6bb2d680712eb2322032e7b111196c4c4134d6c`
implements the existing detached Ed25519 verification API with an explicit
optional public-library backend and a hashed Windows CPython 3.13 wheel recipe.
The implementation remains unconfigured and imports crypto only on an explicit
future verify call. Admission now preserves verifier/control exceptions rather
than converting every exception into a local failure type. Independent source
review closed that callback finding and identified no new concrete defect in
the adapter, optional extra or lock. It checked the supplied metadata baseline;
no artifact, dependency-resolution, native-runtime or cryptographic behavior was
exercised. Trusted key/receipt/challenge/time/environment/worker/start integration
remains unfinished and Start still refuses before optional imports.
Final documentation/manifest review also repaired the admission entry's stale
unchanged-source provenance label. It found no remaining concrete finding;
post-commit source repinning is an administrative check, not runtime validation.
