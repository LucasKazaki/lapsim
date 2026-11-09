# Light tournament preparation and startup contract

Status: **source preparation and file workflow implemented but untested;
tournament start is not implemented**. This document records the commands'
frozen behavior. It does not authorize execution during the source-only review.

The intended Windows start command, once this source has reached the main PC, is:

```text
py -3.13 -I -B scripts\prepare_light_tournament.py --start
```

**That command currently refuses before downloads, setup or worker creation.**
The reviewed original runtime integration and its actual entrypoint are absent.
This is an implementation gap, not a claim that running tests will make it work.
No environment flag, local qualification JSON, historical pin or receipt can
enable this command. The original owner must supply the real integration before
the start branch can be implemented and reviewed.

A separate explicit preparation action is intended for later user execution:

```text
py -3.13 -I -B scripts\prepare_light_tournament.py --prepare
```

Preparation stages already-local source and an empty isolated interpreter
environment. It does not install the tournament package or establish a runnable environment.
It never imports the light candidate, executes diagnostics, opens the ordinary
desktop, starts a solver, probes resources/processes or acquires a runtime lease.
This command has not been executed, syntax checked or tested in this session.

## Frozen preparation behavior

The input pins are frozen in the script, not supplied by a local ready flag:

| Input manifest | Expected SHA-256 | Scope |
| --- | --- | --- |
| `research/light/SOURCE_MANIFEST.json` | `4b1b3c712b0e5a31a0670046e13440fde08e903db7df3138c0cf18ee6def6e88` | 16 public archival files from `07ccb4b84138aedcc5b9cb85c2e81d283d6c132e` |
| `research/light/portable-tournament-candidate/SOURCE_MANIFEST.json` | `3e2da770c31aba0feffd5f9b561d8c8cdc15729c561e0ac988c9ef148fb1ab05` | 66 listed local candidate files, excluding that manifest, at `7f57932943ea617fe87b9679cf645eec24ca01f0` |

These pins establish byte consistency only. A different integrated revision
needs a newly reviewed contract and source change; do not regenerate the pins
from an arbitrary local tree to make preparation pass.

- Require Windows, 64-bit CPython **3.13.15**. This provisional preparation pin
  comes from the repository's recorded ordinary Windows setup. It is not the
  missing light numerical environment recipe or a qualification of that runtime.
  Missing prerequisites produce an actionable error. No Git CLI is invoked.
  Do not install Python, Git or an engine globally or change execution policy.
  `py -3.13` selects an installed minor version; the script additionally rejects
  a different patch version. If needed, use the absolute path to an already
  installed 3.13.15 interpreter with the same `-I -B` script arguments.
- Require the already-local candidate at the immutable cloud handoff revision
  `7f57932943ea617fe87b9679cf645eec24ca01f0`. Verify its complete source manifest
  and every listed file without importing anything. Reject extra files, aliases,
  changed line endings, incomplete copies or an unavailable candidate. Do not
  download an unpublished branch or retry a failed private patch transfer.
- Verify the already-local 16-file public light archive against its immutable
  manifest and per-file SHA-256/length. Its provenance is
  `https://github.com/LucasKazaki/lapsim.git` at
  `07ccb4b84138aedcc5b9cb85c2e81d283d6c132e`. This verifies only those archival
  bytes, not the identity of an entire current checkout. Do not fetch a moving
  branch, run checkout filters or treat the archive as the integrated candidate.
  No network/Git operation or alternative source transport is implemented.
  This public archive is deliberately not runnable.
- Create a new attempt under project-local `work/light-tournament-preparation`.
  Never replace an existing checkout/environment, delete evidence, reset a
  branch, acquire the original owner's shared lock or modify its workspace.
  A setup-only exclusive gate prevents concurrent preparation for that root;
  a stale gate is reported, not silently stolen. It is not a tournament lease.
  An existing root must carry this preparer's exact staging marker; an unrelated
  or interrupted unmarked directory is preserved and refused. The marker is
  solely an administrative setup identity, never execution authority.
  There are no Git/network subprocesses whose descendant cleanup can be inferred
  from a parent timeout. An interruption can leave a setup gate for explicit
  reconciliation. Original/global Git and security settings are not changed.
- Copy only the verified local candidate to the fresh attempt. Preserve bytes
  and recheck the copies. Create `.venv` without pip or build helpers. There
  are no mandatory third-party runtime distributions in this extracted candidate.
  The optional verifier extra/lock is not installed or activated by preparation;
  no wildcard pip installation or root-project extras are invoked.
- Preserve failed attempts. Write a local preparation record with the source
  identities, interpreter identity and explicit false runtime/admission flags.
  Successful preparation exits zero solely for source/environment staging.
  Missing/incompatible inputs and partial setup exit nonzero.
  The prepared state never enables `--start` or acts as an admission receipt.

The earlier `8ee433d7395b4b69b04b0d08228d29a32b3c7463` cumulative patch's
official transfer to the main PC failed
terminally; a subsequent bounded Downloads check found no patch. No new transfer
confirmation exists. This command neither retries that transport nor invents
another way to retrieve the unpublished candidate. Until the local candidate
arrives through a supported authorized transfer or is separately integrated by
its owner, `--prepare` also stops before staging and environment creation.
The new frozen-field source revision has not been transferred by this cloud
task. Updating the exact local source pin does not establish delivery or runtime
readiness and does not enable `--start`.

The later independent main-PC audit located `C:\AI\lapsim`, matched all 16
public archive files, and found **12 missing required dependency/artifact paths**.
Git access returned **Permission denied** and was not retried. Zero feature tests
and zero launches ran; all **26 acceptance gates remain untested**. The original
process-ownership observation review restriction remains unresolved. These are
reported audit findings, not fresh measurements by this preparer. Accordingly,
automatic source downloading is not supplied in this revision: the main-PC
execution owner must resolve supported source access without bypassing that
denial, and the original owner must supply its frozen integration contract.
The frozen native HANDOFF text and reported r02/r03/helper pins have now reached
this task; see the [owner report](../research/light/portable-tournament-candidate/ORIGINAL_OWNER_REPORT_HANDOFF.md).
Module bodies remain untransferred. The report explicitly confirms that native
campaign start and an exact installable dependency recipe do not exist yet;
selected helper APIs do not fill those gaps. Neither cloning current main nor
copying the public archive closes the missing private chain.

The bounded source-availability reconciliation identifies the existing archived
`line_binding.py` as an exact match to its native pin. Its required original
validator/helper/guard closure remains unavailable; no private source was
transferred and no module was imported or integrated by that correction.

The candidate now contains deferred interpreter-API and wheel/installed-RECORD
measurement code. It has no observation command and is not invoked by this
preparer, metadata CLI or Start. Those raw schemas are incompatible with the
required exact-environment v2 identity. Complete ABI, stdlib/installed/native
loaded-code closure, current rounding/ties and independent authentication still
need actual supported providers/artifacts under the original owner's controls.
These uninvoked primitives do not clear the recorded observation restriction.

## Matched-plan and raw-result file commands

The existing preparation script now exposes the actual reviewed field modules
through `--evidence`. These are implemented file operations for later execution,
not a second simulator or a Start workaround. They have not been executed,
imported, syntax checked or tested here. Run from the repository root with real
input files; replace each uppercase digest label with the correct 64-character
lowercase SHA-256. The command's existing `work/` output directory must exist.
Use ordinary local-disk paths; UNC, device and extended namespaces are unsupported.

```text
py -3.13 -I -B scripts\prepare_light_tournament.py --evidence create-plan --origins work\origins.json --origins-sha256 ORIGINS_FILE_SHA256 --output work\field-plan.json
py -3.13 -I -B scripts\prepare_light_tournament.py --evidence inspect-plan --plan work\field-plan.json --plan-sha256 PLAN_BODY_SHA256
py -3.13 -I -B scripts\prepare_light_tournament.py --evidence compare-results --plan work\field-plan.json --plan-sha256 PLAN_BODY_SHA256 --results-index work\results\index.json --index-sha256 INDEX_FILE_SHA256 --output work\field-comparison.json
```

`origins.json` is the existing field builder's canonical object mapping all
seven actual policy IDs to exactly `{identity, origin}`. Each `origin` is the
real source checkpoint envelope, with its complete state/memory and digest.
The CLI does not invent or initialize origins. The default order is the source
registry order; `--policy-order` accepts exactly seven policy IDs to freeze a
different explicit order. A plan is written as the original canonical
`{plan, plan_sha256}` envelope, and stdout prints its body hash and output-file
hash. Inspection validates that body hash and shows membership/input identities,
not completed laps. `--output` is optional for inspection.

The results index is canonical JSON with exactly `schema` and `cells`.
`schema` is `lapsim.light-field-result-files.v1`; `cells` maps zero through seven
frozen policy IDs to these exact descriptor fields:

| Descriptor field | Required input |
| --- | --- |
| `path` | Relative POSIX-style path beneath the index directory, including on Windows |
| `raw_sha256` | SHA-256 of the complete canonical raw-export file bytes |
| `bundle_sha256` | Existing raw export's bundle-body digest |
| `manifest_sha256` | Existing raw journal manifest's digest |

No absolute/drive/backslash/ADS/traversal/reserved paths or symlink/junction
aliases are accepted. Every named file must exist and match all pins. Missing,
malformed or hash-wrong named files fail the command; they are never dropped
from the field. Only an omitted policy key becomes a missing cell. An actual
failed/paused/invalid journal remains an excluded row in the full report.
Canonical JSON here means sorted keys, compact separators, finite numbers and
no leading/trailing whitespace or newline. The command never rewrites inputs
to make them canonical or regenerates a source pin from them.

Comparison output is a canonical `{comparison, comparison_sha256}` envelope.
It retains both input-file identities and the unchanged reducer's `raw_report`,
including every slot, failure, exclusion and descriptive ordering limitation.
All inputs are checked before any output is created. Output files are exclusive
new regular files under the command's `work/` root, outside the immutable code
tree; existing and interrupted files are preserved. This uses ordinary file
fsync requests, not a claim of tested Windows crash/power-loss durability.

Exit 0 means a metadata operation succeeded (or all seven raw cells were
comparable); 3 means a valid comparison report was written with missing or
excluded cells; 2 means invalid input or an I/O/refusal error; 130 means
interruption. Neither exit 0 nor a raw ordering establishes admitted execution,
authenticated evidence, independently verified completed laps, awards, retry
permission or cleanup. `--start` still refuses before candidate imports.

The repository wrapper verifies the full pinned local candidate before importing
its metadata commands, rejects preloaded light namespaces, disables bytecode
writes and checks loaded module paths/bytes. These are local import-hygiene
checks, not the absent original complete `SourceObserver` or runtime measurement.
The optional declared `lapsim-light-evidence` installed console entrypoint calls
the same commands; installation alone does not perform those whole-source or
runtime checks. Its default output root is the current directory's existing
`work/`; the repository wrapper uses this repository's `work/`. File commands
need Python 3.11+ and standard-library modules; only environment preparation
retains the separate provisional Windows CPython 3.13.15 pin.

## Dependencies and next integration gate

The included planar/electrical/DRS/thermal light kernel and extracted policy,
guidance, course and evidence modules use the Python standard library. The
optional passive panel lazily imports Tk from the Python distribution. This is
a CPU Python model, not PyChrono, Bullet, MuJoCo, a GPU search backend or a game
engine. Downloading an engine does not integrate the original light model.

The optional `detached_verifier.CryptographyEd25519Verifier` now implements the
existing admission protocol's verification primitive using `cryptography`
50.0.2. The source includes an optional wheel-only Windows CPython 3.13 lock for
that library, CFFI 2.1.1 and pycparser 3.12, with hashes reported by official
PyPI release metadata. It does not download/install anything or select a key.
The default runtime and metadata commands do not import that library. Published
wheel hashes and version checks are not observed installed/native closure or
authentication. No verifier, key policy or Start provider is registered here.
The lock excludes the interpreter, installer/build tools, original producer and
full numerical runtime; it is a bounded optional dependency recipe only.

The archived, separately invoked `line_generator.generate` explicitly imports
**NumPy and SciPy** for CubicSpline/SLSQP. Its installed binary/backend inventory
and versions are part of independently reviewed producer evidence. Their exact
light-producer lock is unavailable here. The root `requirements-build.lock`
contains exact ordinary Windows build versions, without hashes; those versions
are not automatically a light-producer or signature-verifier lock. The optional
Chrono suspension study has separate native locks and remains separate.

The light candidate's `setuptools>=68` build requirement is provisional and
unlocked. Preparation avoids invoking it. A later package install requires an
owner-reviewed exact interpreter/stdlib/ABI, installer/build wheel hashes where
used, every required wheel and installed-file inventory, the real authentication
implementation, and the exact numerical environment v2 identity. An empty venv
and a source hash do not satisfy those requirements.
The [Python venv documentation](https://docs.python.org/3.13/library/venv.html)
defines the isolated environment and `with_pip=False` behavior. The environment
still depends on its base Python installation; it is not a portable release.

Before a start implementation is possible, the main-PC owner must map its
actual original predicate, validators, observer, producer and guard/worker APIs
to the candidate. It must supply the actual reviewed entrypoint and contracts
for authenticated producer/input evidence; independent trust anchor/verifier;
trusted time and single-use challenges; exact source/runtime observation;
finite current admission/allocation; original activity/session/game/memory
guards; exclusive ownership; deadline/watchdog; durable raw failure retention;
and authenticated cleanup on every exit. No historical 180-second accounting,
reported 120-second contract or retired allocation becomes current permission.
Actual active UI and admitted tournament orchestration remain missing
implementation, separate from these file commands and the frozen native helpers.
See the [exact handoff](../research/light/portable-tournament-candidate/INTEGRATION_HANDOFF.md).

## Feature evidence

Coverage is described in the [source review](light_tournament_startup_review.md). Source that implements
a boundary remains unexecuted/unqualified; absent adapters and application
orchestration remain missing implementation. No completed standing-start lap,
fair comparison, verified official scoring or tournament winner is claimed.
