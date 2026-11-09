# Original source-only packaging review

This records the earlier source-only pass. Dev25 build/install acceptance is
separate; see [BUILD_INSTALL_REVIEW.md](BUILD_INSTALL_REVIEW.md) and the externally
pinned final artifact evidence. Counts and unrun statements below are historical.

Base: `e5396d4d010af73cda439dc79011853b331b148a`, preserved v20 manifest
`df8feaf7a563dd20ec0e554e0dbd6bc0754adc4249a261cc5040a80250d589de`.
Bounded E05 packaging unit; this contract precedes packaging edits. The saved
checkout recovered through one supported administrative reconnect, matching
both identities with a clean worktree. No replacement environment or clone.

## Frozen package behavior

- Treat this directory's pyproject as authoritative. The repository root is a
  different `python-lapsim` distribution with other dependencies. Preserve the
  five existing bundled namespaces together, every current module (including
  fixed worker, field dispatch and field archive), baseline JSON and sidecars.
- Add a machine-readable installation declaration and an explicit sdist source
  file list. Add exact existing public LF FSI source JSON/YAML and its real AMZ
  MIT notice as course package data. Verify raw bytes against the constructor's
  fixed pins; do not normalize line endings, change algorithms or substitute
  this source arc for the independently admitted racing line.
- Derive dependencies by source-text/import/resource inspection. Base runtime
  requires the standard library and bundled source only. Optional cryptography
  stays lazy/explicit; Tk and zlib capabilities are not new pip dependencies.
  No external physics engine is selected by this source.
- Python >=3.11 and setuptools>=68 are declared compatibility requirements.
  Exact interpreter/build/installer artifacts and supported numerical/native ABI
  remain unqualified. Do not guess pins from the broad repository build lock,
  imply that every satisfying Python works, or weaken environment v2. The optional
  Windows CPython 3.13 verifier lock remains verifier-only and uninstalled.
- Preserve the legitimate evidence console entry point and source module command;
  register no native start/worker command or permissive backend. Original provider,
  authenticated inputs, observation, guards, allocations and cleanup stay required.
- Keep source identity sidecars separate from transformed installed-wheel identity.
  A source manifest is not a wheel RECORD, installed-file closure or authentication.
  Metadata must not create a circular self-hash or silently activate old inputs.
- Assemble a deterministic SOURCE ZIP only after the source revision is frozen:
  sorted paths, stored bytes, fixed ZIP timestamps and regular file modes. Include
  all current selected source/data/metadata, plus an outer derived index binding
  source commit, source-manifest raw hash and every payload's raw length/hash.
  Exclude hidden Git state, environment/credentials, private receipts and other
  owners' files. The index excludes itself from its own file hashes; the ZIP is
  pinned externally. No wheel/sdist build, import, resolution or install occurs.
- Keep the earlier 93-file ZIP and all prior revisions/patches byte-identical.
  The user has explicitly confirmed that ZIP has not been downloaded. The new
  local source archive is not a transfer or proof of native materialization.

## Inert acceptance specifications — unrun

| ID | Future separately authorised check | Expected result |
| --- | --- | --- |
| P01 | Unpack the full source archive | Exact sorted inventory, source-manifest hashes and no unexpected files; current worker/field/archive modules present. |
| P02 | Later build wheel and sdist using a reviewed toolchain | All five namespaces and declared data present; source sidecars retained in source distribution; no new runtime imports. |
| P03 | Read packaged baseline and LF FSI resources | Exact retained raw hashes and sizes; real MIT notice retained; no line/reference admission implied. |
| P04 | Later isolated evidence CLI invocation | Existing create-plan/inspect-plan/compare-results behavior only, with current input pins; no tournament Start registered. |
| P05 | Optional verifier profile | Only separately reviewed pinned CPython 3.13 Windows wheel recipe; no resolution/fallback or trust bootstrap inferred. |
| P06 | Attempt native start without providers/current evidence | Refuse through original required integration; source installation supplies no execution/cleanup authority. |

Only source, byte/hash and distribution-inventory inspection is authorised here.
Build/install/runtime/durability/numerical behavior and these checks remain unrun.

## Independent source review

Two read-only reviewers checked actual dependency imports, pyproject/entrypoints,
all 51 Python module paths, the 79-file source selection and all four resources.
They confirmed copied course/cone/notice bytes against the retained public files
and constructor pins. Two documentation findings were repaired: unavailable
repository-relative usage links, and stale wording that public course bytes
were supplied separately. Current source-local usage and rights text distinguish
bundled source inputs from external authenticated racing-line evidence.

Both reviewers also inspected the administrative ZIP packager as text: committed
regular blobs only, strict source/contract/manifest coverage, raw resource pins,
exclusive output, deterministic ZIP metadata, non-circular derived index and
complete byte readback. They found no remaining concrete defect. Actual archive
inventory/hash verification is administrative packaging, not a wheel/sdist build,
candidate import, install, test or runtime qualification. Exact toolchain/native
provider dependencies remain unresolved rather than assigned invented pins.
