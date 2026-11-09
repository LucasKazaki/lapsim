# Pip free dev37 installation validation

This bounded development check reproduces the install-procedure gap and validates
the corrected external-installer route. It is not the tournament launcher and
does not replace original native admission, ownership, deadlines or cleanup.
The production/native owners retain those responsibilities.

The profile is deliberately frozen to source commit
`0ba674bc9960335cd3d96a01c533d9ca9eb7d12b`, its manifest
`85f56f361f2596e918c13c1271c08629d968537f23284e513ef64113b22f2456`
and the 311345-byte dev37 wheel with SHA256
`13655550284cd2abbfda591d20bbbc93b0bc4dd46a8ccd060b00d764c77218aa`.
Use the original frozen source copy for this regression, preserving it alongside
any later documentation edition. No wheel, numerical source or test payload is
rebuilt or changed by the recipe correction.

validate_install.py requires explicit absolute --base-python, --installer-python,
--wheel, --source-root and --output paths. The output must not exist. The native
owner must independently select trusted interpreters and provide actual native
controls before any later native invocation. The script checks external pip
version26.2.2; this is not authentication of that interpreter's source/runtime.

The check creates a fresh venv --without-pip, retains the old target -m pip
failure, installs the exact local wheel with external pip --python and a hash
lock, verifies only the project distribution and all69 declared payload files,
confirms the target still lacks pip, and runs the actual installed verify-release
command. It downloads/resolves no packages and runs no numerical simulation.

Child pip options/configuration are isolated from ambient PIP_* settings while
required OS/proxy/CA environment remains available. No user config files or
machine policy are changed. Safe owned PIP_TARGET/PIP_LOG/config traps reproduce
the original write-redirection problem and verify the repair leaves traps absent.

Each attempted command is recorded before launch. Returned commands retain
stdout/stderr and actual exits. If launch, timeout, control or decoding fails,
the prewritten attempt remains unresolved and the original exception propagates;
no successful result or descendant-cleanup proof is manufactured. Unreturned
output, actual OS containment/cleanup and any storage-failure reconciliation
remain the outer owner's responsibility. Never retry that output namespace.

test_attempts.py takes --wheel and --source-root for the same frozen profile.
Three inert fixtures inject launch/timeout/unknown controls without creating a
subprocess, then verify attempted argv and unresolved status survive unchanged.
They are failure-path tests, not native control or cleanup evidence.

The installer correction is documentation source edition dev37-install-r02;
the distribution version and binary wheel remain dev37. Its updated source
manifest has a distinct pin. The original dev37 ZIP and earlier test evidence
remain immutable. Linux installation evidence does not qualify Windows Start,
the real original provider or a completed tournament.
