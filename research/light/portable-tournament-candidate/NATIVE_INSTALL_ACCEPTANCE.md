# Native installation and Start acceptance

This is the cloud library's handoff to the native bootstrap owner. It is not a
registered Windows tournament command. The install and acceptance steps were
exercised on Linux with the recorded release artifacts; Windows acceptance,
original runtime admission and actual tournament completion remain unverified.
No user-written runner or replacement guard is required by this procedure.

## Select exact bytes before importing checker code

Use the new full release's externally retained ZIP, commit, source-manifest and
wheel pins from RELEASE.json and the handoff. Verify those against the trusted
delivery record, not merely a hash supplied by the same unchecked archive.
Keep every older release and existing run directory intact. The failed delivery
route has not been retried, and a local producer package is not main-PC delivery.

The native bootstrap must independently verify/select the checker, CLI and their
helper source bytes before importing them. `verify-release` cannot authenticate
its own executing code or install provenance. It compares supplied immutable
source-manifest, manifest-pinned contract and wheel bytes; it does not read the
source files named by the manifest or reproduce pyproject/build settings.

The pure Python library call is:

```python
verify_source_wheel_binding(
    source_manifest_raw, install_contract_raw, wheel_raw,
    expected_source_manifest_sha256=reviewed_manifest_pin,
    expected_wheel_sha256=reviewed_wheel_pin,
)
```

It checks complete declared src/ module/resource coverage, exact wheel payload,
bounded archive framing and RECORD, version/entrypoint/dependency declarations
and both original license-notice copies. Supported source schemas are v39/v40/v41;
the wheel profile is core metadata 2.4, purelib py3-none-any with the existing
inactive optional verifier. An internally consistent wheel from another revision
must still fail the source association. Unknown native controls are not converted
to ordinary validation errors.

From an independently selected, already installed checker environment, the
equivalent file command is below. REVIEWED_CHECKER_VENV_PYTHON is its explicit
interpreter, not PATH lookup or the as-yet-unverified target environment. With -I,
Python ignores the extracted current directory and PYTHONPATH; merely unpacking
the source does not make this module importable. A native bootstrap using its
separately selected source tooling may call the pure API instead.

```text
REVIEWED_CHECKER_VENV_PYTHON -I -B -m lapsim_light_campaign.tournament_cli verify-release --source-manifest SOURCE_MANIFEST.json --manifest-sha256 REVIEWED_MANIFEST_SHA256 --install-contract INSTALL_CONTRACT.json --wheel EXACT_RELEASE.whl --wheel-sha256 REVIEWED_WHEEL_SHA256
```

The argument names are exact. Replace the named paths/pins from the retained
handoff; this is not an instruction to resolve/download another revision. Exit0
is supplied-byte consistency only. Exit2 rejects inputs without a success
summary. Optional --output must name a fresh file in the caller's existing work/
directory; partial files are retained and never overwritten.

## Isolated installation

The base runtime has no third-party requirements or external physics engine.
Do not install the optional admission-verifier extra implicitly. Build/installer
tools and their official artifact hashes are in requirements-build.lock; the
prebuilt runtime wheel does not need setuptools/wheel/packaging installed into
its runtime environment. The existing Python >=3.11 declaration is a compatibility
floor, not qualification of an arbitrary Windows interpreter or ABI.

The native owner selects the actual reviewed base interpreter, a reviewed
installer environment containing the locked pip26.2.2, and an absent isolated
runtime environment path. Create the runtime with venv --without-pip: the tested
runtime contains only this project distribution. No PATH fallback, implicit
ensurepip, system upgrade or silent reuse is needed. From artifacts/, invoke the
external installer against the runtime's explicit interpreter:

```text
REVIEWED_INSTALLER_VENV_PYTHON -I -B -m pip --python ABSOLUTE_RUNTIME_VENV_PYTHON install --no-cache-dir --no-index --no-deps --no-compile --require-hashes -r install-wheel-relative.lock
```

The lock names this exact local wheel and its hash. Run from artifacts/ because
its wheel path is relative to the working directory. A failed/uncertain install
is retained for inspection; it is not an excuse to switch release or retry into
the same environment blindly. This command installs the library and starts no
campaign. The runtime interpreter does not need its own pip. Calling the runtime
with -m pip fails for this default profile and must not trigger an automatic
ensurepip or fallback. A separately selected pip-present runtime is a different
installation profile, requiring its own inventory/acceptance. Any actual
installation permission remains with the native owner.

For this exact offline installation, the native bootstrap must scope the child
pip process: remove inherited PIP_* options, set its PIP_CONFIG_FILE to the
platform's os.devnull and disable the version check. This prevents ambient
target/log/configuration settings from redirecting writes outside the selected
runtime. Preserve required OS/proxy/CA state; change no user pip files, persistent
environment or machine policy. Python -I alone does not isolate pip settings.

## Installed acceptance before native Start

Drive module, resource and test selections from INSTALL_CONTRACT.json and its
source manifest rather than counts copied from an older release. Check exact
version, complete module/resource bytes, wheel-to-installed payload and RECORD,
not merely import success or matching distribution name. The source-manifest,
wheel and installed RECORD have different digests and must remain separate.
Reject missing, changed, extra or unsupported installer payload/profile; preserve
the original evidence instead of repairing files during acceptance.

The existing observe_wheel_installation API is a separately authorized original-
owner operation with an independently retained installed RECORD pin. It is not
invoked by verify-release, a bootstrap authentication shortcut or permission to
probe the main PC. It cannot supply complete environment-v2/loaded-native closure.
Native installation checks and original source/environment authentication must
be supplied by the native bootstrap through its actual reviewed mechanisms.

The release evidence records a fresh noneditable Linux installation, exact
module/resource/RECORD readback, CLI help/invalid-input refusal, source and
installed tests, and a byte-identical wheel rebuild from the sdist. Positive
numerical tests still use explicitly UNTRUSTED predicate fixtures. These records
do not qualify Windows filesystem durability, an original predicate closure,
native process controls, full-course trajectories or actual car data.

## Preserve the real campaign on failure

The installed source interfaces remain campaign.CampaignProgram and
campaign.start_tournament. A native host requiring failure evidence must retain
CampaignProgram before invoking run(), rather than calling the convenience
start_tournament wrapper and expecting it to return a failed-program handle.
Constructor failures create no campaign output. run() is single-use.

After a returned or raised run, snapshot() exposes the accepted in-memory field
separately from successfully read-back persisted checkpoint pins. It does not
perform file recovery or call the native provider, but decoding/allocation can
still fail. Keep any snapshot-capture error separate from the original run error.
Apply the native owner's actual fatal-control precedence; do not blanket-suppress
FatalCreatorExit, repeated asynchronous interruption or failed cleanup just to
obtain a snapshot. No generic post-failure callback/catch-all helper is supplied.
Never put automatic file finalization/recovery in a finally block after failure.

The host must retain returned and unreturned worker output under original
ownership, finite deadlines and cleanup rules. A provider cleanup receipt does
not itself authorize later host writes; the native owner must establish actual
compatible writer/lease ordering through finalization. Archive/hash consistency
is not authenticated admission. Cancellation recorded before local finalization
cannot be reinterpreted as a resumable budget pause. Partial/orphan journal data
requires original-owner reconciliation and cannot be restarted or reappended.

## Remaining native acceptance

Before wiring a genuine single-command Start, the native owner still supplies
the fixed worker/request/result registration, authenticated original source and
input/line/history/environment closure, fresh ownership/activity/resource checks,
exclusive lease, finite enclosing deadline, active Stop and genuine terminal/
cleanup evidence. No default provider or synthetic receipt may fill those gaps.
The current short FSG replay profile is not full-event continuation. Supported
delivery, Windows installation/GUI acceptance and actual tournament execution
remain separate unmet or unverified gates, not consequences of a green unit test.
