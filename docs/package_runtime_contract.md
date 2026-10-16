# Installed resources and source startup (E05/E09)

Acceptance contract recorded before the repair on 16 October 2026.

The current wheel installs Python modules without controller/data/help assets;
an actual isolated install fails the closed-loop demo with "controller source
is unavailable". The new frozen executable also reproduces a Windows path-limit
failure while copying retained controller evidence into durable help storage.
Retain both counterexamples. Do not remove evidence or change global Windows
settings to obtain a passing package.

Resource ownership must be explicit for three contexts: source checkout,
installed wheel, and frozen extraction. Source discovery follows the module's
own checkout; an installed package uses its bundled resource directory; frozen
execution uses its captured extraction bundle. Never use the caller's working
directory, a sibling repository, or an ambient Git checkout as package identity.
Installed/frozen build information records source commit, dirty state, selected
file hashes and source hash. A source distribution retains that identity only
when its selected source bytes still agree. A modified no-Git snapshot must be
marked dirty. Runtime package resources are read-only; saves use user storage.

Package only declared source/resource patterns, the canonical controller
inventory and explicit data fixtures. Preserve the browser frontend/replay
allowlist and reject private captures or substituted reviewed examples. Native
toolchains, QEMU binaries, build directories, caches and user runs are excluded.
This is an internal package workflow while public release is deferred.

Test an actual wheel and a wheel rebuilt from an sdist in fresh environments,
from a different working directory and without editable-source imports. Check
bundled source/controller identities, a synthetic bicycle run/replay, the actual
closed loop/comparison replay, required course/help resources and the desktop
self-test where a GUI is available. These tests must execute installed code.
An archive listing or mocked path helper is insufficient.

Durable frozen help keeps the full content identity and all retained evidence.
Use Windows extended filesystem paths for the copy so long approved filenames
work without a machine-wide long-path setting or shortened historical names.
Return ordinary paths for browser links. Do not create a completion marker
until the copy succeeds.

The source bootstrap is a standard-library entry point from any CWD, with one
setup-and-launch command. It owns only an explicit project-local environment;
it never deletes/replaces an existing environment. Existing incomplete or
incompatible environments fail with an actionable message. Installation may
need internet; a subsequent check/launch must work without network after setup.
Keep flexible source dependency ranges separate from the exact Windows release
build lock. Optional native/firmware/emulator tools are never required for the
ordinary synthetic demo. Check mode is read-only and runs bounded synthetic
physics/controller checks; GUI availability is checked separately for launch.

Bootstrap subprocess arguments are arrays, paths may contain spaces/non-ASCII,
timeouts are explicit, failures return nonzero, and success is recorded only
after actual checks. No device discovery, serial/CAN access, credentials,
administrator installation or physical hardware action is part of startup.

Additional reproduced identity case: an extracted source tree inside an
unrelated Git repository must use its own source capture, never the ancestor's
commit. Verify current selected bytes and mark changed/missing source dirty;
keep the captured source hash separately. Without its own Git/capture, report
unknown identity. Use normal library paths for inherited `..` operations and
extended paths only for controlled leaf-file reads/copies.
