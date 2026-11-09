# E01/E05 source integration review — 5 November 2026

Status: **INSPECTION ONLY / UNTESTED / UNBUILT / UNQUALIFIED**. No candidate
module, parser, geometry routine, import, syntax check, test, simulation,
inference, resource probe, lease, application or hardware action was run.
Administrative file-transfer helpers, source-text processing, Git operations,
byte comparisons and hashing are the evidence here. Nothing was pushed,
published, merged on GitHub or used to change security settings.

## Recovered sources and preservation

- Base main: `07ccb4b84138aedcc5b9cb85c2e81d283d6c132e`.
- Original policy/guidance patch: `lite-policy-guidance-20261105.patch`,
  237359 bytes, independently recovered SHA-256
  `73172ccb8d20931878c12df091d6f0eb343d1c159f871280720b12bf60484952`.
  It is reported to originate at commit
  `9cf2db6646d3cc293756d0612e81ebf9b9beb912`; that commit object was not
  transferred and is not claimed to exist locally.
- Original course patch: commit
  `6f30a14a47d95ca81949bbd9ed3f36cd92db49a2`, patch SHA-256
  `8976de192a2127a33f9ebb6c8b693dff539e95b5f603c0884aec92d03d271530`.

The Library signed-URL transfer failed before installing a local file. The
supported Library reader then supplied all 4937 patch lines, but normalized
line endings. The five retained core files `_validation.py`, `actuation.py`,
`conditions.py`, `planar.py` and `powered_planar.py` were restored to their
original per-line bytes from PR #166 commit
`eda45185a4debeae7239dce906b72cfdf3909da9`. The recovered whole patch matched
the expected SHA-256 and byte count **before applying it**. This recovers exact
content, not just an inferred equivalent diff. Library identity metadata was
retained on that recovered local patch.

The unchanged patch was applied to a new recovery worktree and committed as
`4667513` on `cloud/recovered-policy-guidance-20261105`. Regenerating that
commit's binary diff against main reproduced the exact expected patch hash.
Git reported 1759 whitespace warnings from preserved carriage returns; those
bytes were retained, not silently fixed. The course commit then cherry-picked
without conflicts as `d9b3aa6` on the separate
`cloud/lite-tournament-integration-20261105` branch/worktree. Both original
branches, patches and candidate directories remain preserved. The old course
review's unavailable-patch note records its earlier state and is superseded
by this recovery record.

## Interface and copy review

The new `portable-tournament-candidate` distribution copies 21 policy/core/
guidance/journal Python files and three course Python files. Source-byte `cmp`
inspection found all 24 copies identical to their inputs. The core notice is
also retained. All five namespaces are included explicitly in the proposed
packaging metadata, with no external runtime dependency or console entrypoint.
This is not an executed package-discovery, import or build result.

The guidance `ReferenceTrack` protocol requires station, x/y, curvature, cell
length/count, total length and closed-state attributes. The course DTO supplies
those inspected names. The guidance reads no additional track method in this
extraction. This establishes an inspected structural match only: the course's
arc reference is not the producer's sampled racing line, and no caller is
connected to use it as one. Source-course and line-admission roles stay distinct.

The shared policy/guidance imports bind the same included `PlanarControls`
definition. Guidance produces its scalar demand, normalizes once to four equal
AWD requests, then leaves allocation/actuation to the same retained core. None
of those scientific files or clock formulas changed in this integration.
Journal checkpoint/chunk schemas remain the archived v1 raw schema; a new
stepping bridge and its complete state/physical validation are still missing.
New source identities cannot inherit historical checkpoint qualifications.

## New verification/export review

`raw_evidence.py` adds bounded lossless export of canonical journal values and
in-memory storage-chain replay. It imports only the standard library and its
pinned adjacent raw-journal module, and invokes no plant/controller/geometry
code. Its internal use of journal validation helpers is deliberate and requires
the exact included journal source; a later independent API/version change
needs review, rather than an implicit alternate implementation.

Manual review passes covered:

1. Envelope/manifest/source identities, strict field sets and size bounds;
   every receipt/object digest and contiguous sequence; exact raw checkpoint
   transitions using the retained journal gate; rejection of missing and
   unreferenced objects; terminal-to-tail linkage. No physical validation or
   external authentication is inferred from hashes.
2. Storage quota and losslessness. Review found that replay initially checked
   the export cap but omitted the original journal's declared byte quota.
   The source now sums canonical manifest, unique object, receipt and optional
   terminal bytes, enforces the original quota and compares this total with
   snapshot inventory. No telemetry is rounded, decimated or rescored.
3. File lifecycle and authority. Snapshot rejects recovery candidates and
   reinspects the source for observed changes. Output uses exclusive creation
   and retains partial files on I/O failure. An existing original writer lease
   is still required: a second inspection is not a new lock or atomic snapshot
   against hostile/concurrent writers. All output remains raw, unqualified and
   explicitly marked as having no numerical replay or execution authority.

No newly added function has been called. Source review cannot demonstrate
successful imports, schema behavior, I/O/crash recovery, Windows durability,
numerical equivalence, actual app behavior or absence of defects.

## Unresolved integration

Authenticated producer/line admission; the physical fixture and exact numerical
environment; a fixed-clock stepping bridge; guarded dispatch and original
execution/cleanup admission; complete continuation; numerical replay; UI
Run/Stop/Close; and matched standing-start laps remain open. Terminal journals
are still immutable, including `paused_budget`. This tranche adds no automatic
resume, fallback reference, owner handoff, run command, official score or winner.
The historical execution restriction was not retried or cleared.

## Deferred observation primitives — 6 November 2026

From `28c11d8a229f11cbba5a0b1e48fde5af555b9a1d`, two real deferred
measurement modules supply a bounded part of the missing observer implementation.
No candidate imports, calls, parsers, syntax checks, tests, installs, resource
observations or simulations were invoked to develop or review them.

`runtime_observation.observe_python_api_facts(required_facts=...)` reads exactly
the requested supported facts: implementation/version/cache tag, language
version, byte order, float format, startup `FLT_ROUNDS`, reported executable
path and optional `sys.abi_info` build traits. Unsupported requirements or
missing/malformed APIs raise `ObservationUnavailable`, with no partial output.
The [Python sys API](https://docs.python.org/3/library/sys.html) documents
`abi_info` starting with 3.15 and identifies `float_info.rounds` as startup
information. Neither establishes complete native ABI or current rounding/ties.
The provisional preparation interpreter remains 3.13.15; requiring `abi_info`
there refuses rather than inferring traits or upgrading the interpreter.

`distribution_observation.observe_wheel_installation(...)` requires explicit
absolute local artifact/root/dist-info paths and independently reviewed wheel
and installed RECORD digests. It hashes and inspects the same immutable wheel
snapshot; measures every supported ZIP payload against wheel RECORD; hashes
every installed RECORD target, even when declared hash/size is blank; compares
all unrelocated wheel payload bytes; and separately reports generated/additional
recorded files. The actual installed RECORD self bytes must match the captured
pin. Metadata names/versions remain labelled declarations, not trusted identity.

The frozen profile supports ordinary single-disk Wheel 1.0 ZIPs without ZIP64,
comments, wrappers, encryption, symlink/reparse aliases or relocated `.data` payloads. Only
stored/deflated entries, canonical ASCII portable member names and SHA-256/384/512
RECORD digests are supported. It refuses case/normalized-path collisions, path-extension
and detected editable layouts. Absolute or `../` installed paths are resolved
from the containing site directory and confined to the explicit installation
root. Normalized relative installed paths also use the portable ASCII/device/
trailing-dot/space profile; short-name/hard-link/native alias closure is not
established. No discovery hook, wheel extraction, observed-distribution/payload import
or installer runs. Standard-library readers may load compression extensions;
their actual native closure remains unobserved by this raw measurement.
Caps are 128 MiB wheel input, 4 MiB central directory, 4096 entries, 256 MiB per
file, 512 MiB cumulative expanded/installed bytes, 1 MiB RECORD/metadata and
4 MiB canonical observation output. Exact known parser/decompressor/I/O error
types normalize to `ObservationUnavailable`; unknown exception classes/subclasses,
`MemoryError` and `BaseException` propagate unchanged to the original owner.

The [installed-project specification](https://packaging.python.org/en/latest/specifications/recording-installed-packages/)
allows missing hashes and omitted corresponding bytecode. Therefore even a
complete successful RECORD check is not full installed/stdlib/loaded-native
closure. The [wheel format](https://packaging.python.org/en/latest/specifications/binary-distribution-format/)
also permits layouts outside this deliberately strict profile; these refuse,
they are not silently transformed. ZIP reading uses the documented
[zipfile API](https://docs.python.org/3.13/library/zipfile.html) and ordinary
EOCD framing from the [PKWARE format specification](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT).
The inspected [CPython 3.13 implementation](https://github.com/python/cpython/blob/3.13/Lib/zipfile/__init__.py)
retains `ZipInfo.orig_filename` before name normalization. The verifier requires
that attribute and exact equality with the usable name; absence or normalization
refuses rather than hiding NUL truncation/separator changes. This explicit
implementation dependency is not assumed available on every Python runtime.

Both outputs have distinct raw schemas with false environment-v2 compatibility,
complete-observer, authentication and execution-authority claims. They are not
`SourceObserver` implementations, not exposed through CLI and not connected to
Start or numerical initialization. File checks assume original owner writer
exclusion; they are sequential observations with bounded consistency checks,
not atomic snapshots or hostile-writer protection. Original ownership/session/
activity/resource admission, lease, enclosing hard deadline, original guard,
before/after observation order and cleanup/authentication remain mandatory.
No existing contract, provider registration, trust predicate or guard is changed.

Complete ABI, stdlib/installed/native loaded-image closure, current-thread
rounding/tie observation and genuine external source authentication remain
unimplemented dependencies. The reported r02 selected-binding helper cannot
supply them. These raw schemas intentionally cannot be substituted into v2;
any later reduced contract requires explicit new semantics/version and consumer,
signature and challenge compatibility review. This tranche implements no downgrade.

Independent source review found two concrete defects. ZIP names initially used
only Python's normalized spelling, hiding NUL truncation; the original-name
equality/availability check above repairs that boundary. Blanket exception
normalization could also change an unknown original owner's fatal control
exception into an ordinary unavailable observation. Both readers now normalize
only exact known stdlib error types and preserve unknown classes/subclasses;
the distribution reader explicitly includes the actual optional `zlib.error`.
Follow-up inspection extended exact-type preservation to the optional compression
import and added the real `JSONDecodeError` parser type to the closed error set.
No original fatal-control class/base is inferred or reimplemented. The two
repairs and the final installed-path check were closed by independent follow-up
inspection. No further concrete source defect was identified. This is not an
import, parser, schema, I/O, Windows, decompression or fault-path test result.

## Optional detached verification primitive — 6 November 2026

From `c6bb2d680712eb2322032e7b111196c4c4134d6c`, `detached_verifier.py`
implements the concrete existing `DetachedVerifier` API, rather than an inferred
original-owner guard. Its explicit immutable adapter-source pin is separate
from dependency artifacts and does not authenticate loaded code. Import and
construction do not load the crypto library; only an explicit future verify
call imports `cryptography` 50.0.2. Input keys/signatures must be exact 32/64-byte
values; messages must be bounded exact bytes with the unchanged admission
domain. The adapter passes those bytes unchanged to public-key verification,
returns only `None` after library success and supplies no signing/key/policy/
receipt/nonce/time/guard service. It is not discovered or registered by Start.

The [versioned public API](https://cryptography.io/en/50.0.2/hazmat/primitives/asymmetric/ed25519/)
specifies `from_public_bytes` and `verify`, including invalid-signature and
unsupported-algorithm failures. Only exact known crypto/import failure types are
normalized; unknown classes/subclasses, `MemoryError` and `BaseException` remain
unchanged. Source inspection found the existing admission callback catch-all
could transform an original owner's fatal control exception into an ordinary
admission error. It now lets verifier exceptions propagate unchanged. Failed
verification still cannot construct an authenticated input result.

The optional package extra declares `cryptography==50.0.2`. The source-only
`requirements-verifier-win-cp313.lock` pins published wheel SHA-256 values for
`cryptography-50.0.2-cp311-abi3-win_amd64.whl`,
`cffi-2.1.1-cp313-cp313-win_amd64.whl` and `pycparser-3.12-py3-none-any.whl`.
The exact metadata sources are [cryptography](https://pypi.org/project/cryptography/50.0.2/#files),
[CFFI](https://pypi.org/project/cffi/2.1.1/#files) and
[pycparser](https://pypi.org/project/pycparser/3.12/#files). The pinned release
source declares [cryptography's dependencies](https://raw.githubusercontent.com/pyca/cryptography/50.0.2/pyproject.toml)
and [CFFI's dependency](https://raw.githubusercontent.com/python-cffi/cffi/v2.1.1/pyproject.toml).
For the stated CPython 3.13 with GIL, Windows x86-64 target this adds no
typing-extensions requirement. The lock permits only these hashed binary
artifacts and does not support source builds or silently broaden the platform.

These are remotely reported artifact pins, not hashes of downloaded local
bytes, publisher-attestation verification, installed-file observations or a full
interpreter/stdlib/installer/producer/native-runtime lock. No artifact was
downloaded, installed or imported. The separately authorized original owner must
qualify actual loaded dependencies before using the primitive under its exact
source/environment and cleanup controls; version checks cannot replace that.
Trusted key provenance, original tool/cleanup/review receipt semantics, fresh
trusted time/challenge services, full SourceObserver and owned worker/start
integration remain missing. Existing v2 and its admission order are unchanged.
Independent source review found no additional concrete defect in the verifier,
admission repair, optional extra or lock. It confirmed unchanged-byte verification,
bounds/deferred imports, success/failure semantics, unknown control propagation
and absence of signing/key defaults/registration. It matched the lock to the
primary agent's supplied official-metadata baseline; no local artifact bytes,
publisher attestations, dependency resolution or native closure were verified.
The prior callback finding is closed by inspection. Final documentation/manifest
review found a stale admission-file origin label claiming unchanged source;
the label now explicitly records the control-exception repair. That provenance
finding is closed, with no remaining concrete documentation finding. Post-commit
repinning remains separate; no cryptographic or other behavior has been exercised.
