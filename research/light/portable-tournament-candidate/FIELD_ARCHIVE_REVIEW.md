# Finalized field packet archive — source only

Base: `a47c3a552370ebd8d48bd7175737b5ef08fb9f72`. Bounded E05 source unit.
This contract precedes implementation. No candidate imports, syntax checks,
tests, file-writing execution, resource probes, leases or simulation are allowed.

Implement a create-only packet archive for an idle finalized field snapshot:
locally sealed, or all seven numerical cells completed. Retain its complete
canonical plan/origins, every consumed request, every returned raw chunk/linked
checkpoint/opaque receipt byte packet, all missing/failed/unadopted slots, original
proposal caps and accepted/unknown accounting. Reconstruct metadata from those
bytes using existing request, checkpoint and field contracts. A directly created
DTO and matching hashes establish no execution/authentication provenance.

Adopted packets must match the exact parent/identity/request-specific transition
and mission limits. Returned unadopted packets receive bounded transport/hash
checks only: retain even malformed numerical payload bytes without parsing or
promoting them. No-result attempts stay explicit. No missing worker output is
reconstructed; the original provider still retains output that never returned.

Use raw-byte content-addressed objects and a canonical data inventory written
last. This is a storage transport for existing DTOs, not a new execution identity,
admission/cleanup receipt or journal format. Preflight every encoded byte and
object count before mkdir. New root/files only, no overwrite, rename, append,
deletion, implicit repair or retry. Keep all partial files on any exception.
Reuse original raw-journal path/sync/canonical-write helpers where applicable.

Readback requires the independently pinned raw inventory hash and an external
byte cap. Verify canonical metadata, the exact regular non-aliased file layout,
every raw object's size/hash and complete reconstructed snapshot/accounting.
Refuse incomplete inventory, torn objects, orphan/unknown files, wrong pins or
unsupported layouts. Return immutable snapshot data only. Readback never creates
or restores a coordinator, reopens a terminal, dispatches or grants continuation.

File and POSIX-directory fsync are optional requests under the existing helper;
Windows directory flushing and arbitrary power-loss durability are not supplied.
Final inventory bytes may exist after a write/flush exception: outcome is
uncertain until separate pinned readback under original controls. Commit-last
readability is not crash recovery or hostile-writer atomicity. Source inspection
does not verify real filesystem behavior. The native owner must separately own
writer/path exclusion, finite allocation/deadline, durable storage qualification
and original admission/cleanup. No such authority or native provider is added.

No `RawJournal`, storage terminal or `RawCellExport` is synthesized from snapshot
flags. Local `dispatch_failed` can coexist with an adopted completed checkpoint;
both survive unchanged. Actual v1 journal closure/export and original outer
paused-budget continuation remain native integration steps. Those exports still
have 63 MiB source/64 MiB transport limits; this archive does not bypass them,
aggregate opaque receipt bytes into invented history, or promise every archived
field fits a later export. This code preserves data needed for that later review.

## Inert regression specifications — not executed

| ID | Future separately authorised check | Required result |
| --- | --- | --- |
| A01 | Finalized empty, partial, failed and seven-completed snapshots | Preserve all seven cells, exact plan/packets and caps; no invented terminal or completion. |
| A02 | Altered parent, policy order, adopted result, counters, nonce or summary | Refuse inconsistent data before mkdir; no authentication claim from reconstruction. |
| A03 | Unadopted result with bounded non-JSON numerical payload | Preserve bytes exactly without numerical decoding or committed-parent adoption. |
| A04 | Unreturned result | Keep request/reservation/unknown exposure; never fabricate a packet. |
| A05 | Archive budget/object/metadata limit or existing root | Refuse without overwriting or truncating old evidence; preflight budgets before mkdir. |
| A06 | Partial object write, flush failure or inventory-write failure | Preserve all partial bytes; no cleanup/delete, automatic retry or success claim. |
| A07 | Inventory exists after a failed final flush | Treat outcome as uncertain until explicit external-pin readback; no assumed successful return. |
| A08 | Torn inventory/object, orphan file, alias, nonregular file, wrong raw hash | Refuse committed readback; retain reconciliation candidates unchanged. |
| A09 | Caller snapshot sealed after an adopted completed result was interrupted | Preserve local dispatch_failed and numerical completed separately. |
| A10 | Successful source-path round trip on a separately qualified filesystem | Same immutable DTO bytes/accounting, data-only result; no automatic dispatch/resume. |
| A11 | Finalization interruption, OOM, process death or hostile concurrent writer | No universal recovery/atomicity/durability guarantee; original controls remain required. |
| A12 | Native journal/export/outer continuation later requested | Require real writer/closure/history/current admission and existing consumer limits; never reinterpret this inventory as original receipts. |

All checks remain unrun. Earlier worker/field revisions, the frozen 93-file ZIP,
native/launcher/full/model areas and all denied transfer routes remain untouched.

## Independent source review

Two read-only reviewers found no concrete defect in this bounded unit. They
inspected snapshot reconstruction, adopted-parent joins, opaque unadopted packet
retention, complete byte/count preflight, create-only writes, commit-last inventory,
pinned strict readback and partial/uncertain outcome handling. No original native
writer/authentication, journal/export, coordinator restoration or universal
durability claim was inferred. This is source inspection only; actual filesystem,
interruption, allocation, numerical and native-integration behavior is untested.

## Dev38 Windows output component spelling

Raw journal _no_alias now calls a pure Windows-flavour spelling check before
lstat. It rejects leading/trailing ASCII spaces and trailing periods in
non-anchor components, rather than rewriting a requested namespace. Actual
WindowsPath inherits PureWindowsPath. POSIX spelling, ordinary interior spaces,
hidden names, Unicode and existing dot/parent semantics are unchanged. The
existing symlink/reparse checks still follow this preflight.

Microsoft's [file naming guidance](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file)
and [whitespace support](https://learn.microsoft.com/en-us/troubleshoot/windows-client/shell-experience/file-folder-name-whitespace-characters)
document these ordinary Windows naming restrictions/normalizations. This fix
refuses an ambiguous requested component before creation; it does not establish
actual Win32, filesystem durability, hostile-writer or original-owner acceptance.
UNC/share/device anchors and other alias mechanisms are explicitly unqualified,
not rewritten or newly admitted. Their qualification stays with the original
native owner, along with writer exclusion, deadlines and cleanup.

Eight inert Windows-flavour regressions cover invalid names, refusal before any
filesystem call, valid spaced/hidden/Unicode names, unchanged anchor/parent and
POSIX semantics, journal/campaign preflight before request or dispatch, and the
original reparse refusal. NoIOWindowsPath raises on any attempted filesystem
access. Positive campaign metadata/provider values remain UNTRUSTED doubles.
These tests prove source ordering and pure spelling behavior, not Windows API
execution. Initial fixture syntax was corrected before the meaningful red run;
that corrected8case run produced10failed subcases/16errors against the missing
guard. Red and green logs are retained externally.

The source-manifest v41 uses the same complete release-binding structure with
this reviewed source addition. The binder explicitly accepts v41 while retaining
v39/v40 and all pin, coverage, payload, metadata and license checks. One new case
verifies both acceptance and incomplete-module rejection for v41. This version
addition supplies neither authentication nor permission to run a native worker.

Two independent reviewers passed the runtime and regression bytes. Final source,
clean-installed and archive evidence is tied externally to the exact dev38
commit/manifest. No original guard, numerical physics, policy data or previous
receipt/checkpoint is changed. Existing native admission requirements are intact;
new source pins require genuine current native observation before use.
