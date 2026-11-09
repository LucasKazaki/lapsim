# Wheel and installation acceptance

Portable dev38 adds Windows component spelling preflight and a seventeenth test
file: 63 modules, six resources, 129 selected source paths and 273 bounded cases.
No dependency or runtime resource change. This is a new runtime source/wheel
identity; the frozen dev37 binary and installer-recipe correction remain intact.
Windows path-flavour tests do not qualify actual Win32 execution or native Start.

Portable dev37 adds source/contract/wheel association, the verify-release command,
one runtime module and a sixteenth test file: 63 modules, six resources,
128 selected source paths and 264 bounded cases. Two metadata review findings
and CLI owner-control propagation have reproducing regressions. Current source
and installed artifact acceptance is recorded against the final commit.
[NATIVE_INSTALL_ACCEPTANCE.md](NATIVE_INSTALL_ACCEPTANCE.md) distinguishes the
trusted checker environment, target installation and genuine native Start gates.

Portable dev36 adds campaign status/recovery and evidence-CLI regressions:
62 runtime modules, six resources, 125 selected source paths, 15 test files and
245 bounded source cases. No dependency or runtime resource changes. Installed
acceptance and artifact identities are recorded externally after the final commit.

Portable dev35 adds cooperative cancellation to the existing raw replay worker,
a fourteenth test file and review: 62 runtime modules, six resources, 124 selected
source paths and 233 bounded cases. Source-provenance updates distinguish the
reported native source hashes from cloud bytes and current authentication.
No dependencies or runtime data are added, and no native Start/Stop is registered.

Portable dev34 adds two standard-library checkpoint/worker modules, a thirteenth
test file and review: 62 runtime modules, six resources, 122 selected source
paths and 222 bounded cases. The existing byte-returning advance API is preserved;
literal endpoint capture shares its locked core. No dependencies or runtime data
are added. Replay is development consistency only, not original authentication
or native Start/continuation/Stop registration.

Portable dev33 adds one standard-library numerical consumer, a twelfth test
file and review: 60 runtime modules, six resources, 118 selected source paths
and 204 bounded cases. No dependencies, extras or runtime data are added. The
consumer is development-only; the required original residual predicate, source/
environment authentication and native FSG worker/Start registration remain external.
Source and isolated installed acceptance are recorded against the final commit.

Portable dev32 adds one standard-library gate/phase module, an eleventh test
file, a second source-test JSON fixture and review: 59 runtime modules, six
runtime resources, 115 selected source paths and 182 bounded cases. Fractions
and heapq are standard-library imports; no dependency or package-data change
is required. The phase fixture is not installed runtime data or an admission.

Portable dev31 adds one standard-library smoothing module, a tenth test file,
its development JSON fixture and review: 58 runtime modules, six runtime
resources, 111 selected source paths and 159 bounded cases. The fixture is
source-test data only; it is not installed runtime package data. No dependency
or optional extra is added. Source and native/reference identities stay distinct.

Portable dev30 adds a separate source-arc pose/proxy diagnostic and ninth test
file: 57 runtime modules, six resources, 107 source paths and 139 bounded cases.
Positive body clearance and preserved steering-proxy failure are distinct from
native admission. Prior artifact and ordinary `.9` identities remain frozen.

Portable dev29 adds one diagnostic module, an eighth test file and its review:
56 runtime Python modules, six resources, 104 selected source paths and 127
bounded cases. The unchanged ordinary `.9` snapshot still refers to dev28.
This separate source candidate requires distinct artifact/manifest pins.

Dev28 adds one runtime module and a seventh test file: 55 Python modules, six
resources and 110 bounded cases. The separate source-chord diagnostic is not a
native reference or completion receipt. Current artifact acceptance is external.

Dev27 added the two exact public FSG data resources and a sixth test file. Its
selection contained 54 runtime Python modules and six runtime resources; installed
acceptance ran 93 tests. FSG was source preparation only, with no driving-reference
or numerical admission. The [source review](FSG_SOURCE_REVIEW.md) records that
boundary and the unchanged legacy FSI checks.

Dev26 retained the build/runtime dependency recipe and added two allocator-domain
guards plus a fifth bounded test file. That release's acceptance ran all 78 tests,
including 16 component/domain cases; the real short policy/plant probes remain
separate from course, original-provider and native qualification. See
[the exact scope](POLICY_DYNAMICS_REVIEW.md). The historical dev25 notice repair
and its frozen evidence below remain unchanged.

Dev25 preserves dev24 runtime source and adds the project rights notice and AMZ
notice to standardized wheel license-file metadata without inventing a uniform
license grant. A real dev24 build omitted CORE_NOTICE.md; the artifact regression
failed before this change. The five packages and four runtime resources remain
unchanged. Setuptools 77 introduced project.license-files, so the build floor is
raised to 77; the tested toolchain is pinned separately.

## Build and install procedure

Use a new isolated virtual environment and a verified extracted source bundle.
The lock supplies exact official-PyPI wheel hashes for setuptools 84.2.1, wheel
0.48.0, packaging 26.3 and pip 26.2.2. These are build/installer tools, not runtime
dependencies. Their individual Requires-Python constraints are recorded; the
project's >=3.11 declaration does not promise every tool works on every such
interpreter. No system-wide upgrade is required.

Install tools into the build environment with pip --require-hashes and the lock.
For offline use, first obtain the four exact pinned wheels from the listed
official sources and use --no-index --find-links with the local wheel directory.
Invoke setuptools.build_meta.build_sdist(output_directory) and build_wheel with
that environment from the extracted project. SOURCE_DATE_EPOCH fixes wheel
timestamps; exact artifact bytes must still be retained and checked independently.

Create another empty runtime environment with venv --without-pip. Use the
reviewed external installer interpreter to invoke pip --python with that runtime
interpreter, then install the resulting wheel with its explicit SHA256 using
--no-cache-dir --no-index --no-deps --require-hashes --no-compile. Scope child pip
options/configuration as described in NATIVE_INSTALL_ACCEPTANCE.md; Python -I
does not isolate pip settings. Pip belongs to the installer,
not this runtime. Do not invoke runtime -m pip or silently add ensurepip to repair
the pip-free target. The resulting
noneditable distribution requires only Python's standard library and bundled
modules. Do not install the admission-verifier extra implicitly. Its existing
Windows CPython 3.13 lock is a separate unsupported-on-other-platforms recipe.

Acceptance checks every selected source path in the sdist; all wheel RECORD
entries; every Python module and resource selected by INSTALL_CONTRACT.json; both license notices;
name/version/dependencies/entry point; and the separate installed RECORD/CLI.
Run all test files declared by that same contract against the installed wheel outside the
source tree with cleared PYTHONPATH, plus CLI help and invalid-input refusal.
Raw byte inventory is administrative artifact verification, not invocation of
SourceObserver or distribution_observation, and supplies no runtime/admission
authority. Wheel, installed RECORD and source-manifest hashes remain distinct.

## Evidence boundary

The release acceptance JSON and logs live outside the source distribution and
bind the final source commit, manifest, build tools, wheel, sdist and installed
checks. They are not included in their own hashed input. A Linux build/install
does not qualify native Windows process containment, complete environment v2,
original line admission, cleanup, seven-policy numerical execution, nine courses,
a car calibration or the separately owned Start/launcher. The installed command
is lapsim-light-evidence; no tournament shell command is manufactured here.

Official packaging references: [setuptools build backend](https://setuptools.pypa.io/en/latest/build_meta.html)
and [license-files support](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html).
