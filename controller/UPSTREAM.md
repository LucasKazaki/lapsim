# ENME408 controller import

Imported 16 October 2026 from
`https://github.com/LucasKazaki/lucas-agent-studio`, commit
`73cc2e2bbbf3fdae4a4fed1cc6e7b3df8bbb110e` (reviewed lineage #77 -> #78).
The exact path mapping is `projects/enme408-torque-control/` -> `controller/`.
`import-manifest.json` binds all 419 original Git blobs (4,089,087 bytes) by
original path, size and SHA-256. No original source or historical receipt was
rewritten. `.gitattributes` preserves those bytes on Windows.

The dependency audit covers Python local imports, C translation units and
headers, parity/build adapters, synthetic fixtures, frozen protocols, tests,
reference citations and retained evidence. Python requires only the standard
library plus neighboring reference modules. Host C requires a GCC/Clang
compatible compiler and its normal C/math runtime. No Studio application,
agent scheduler, model, online service, private evidence bundle or sibling
checkout is a runtime dependency. No compiler archive or installed toolchain
is redistributed. Retained `.o` files are historical generated object evidence,
not a linked image or an executed target.

The original README/research describe their historical portfolio and future
AWD work. They are preserved evidence, not this repository's current work
instructions. The current 2026-27 car is RWD; the future 2027-28 AWD concept
and original abstract four-slot allocator do not establish physical actuator
count. See `docs/controller_testing_contract.md` for the current contracts.

Numerical owners: Python allocation, base guard/pedal reconciliation, normalized
clock and final recovery/inhibit; matching C owners live in `reference/native/`.
The common numerical policy uses binary64. Keep raw rejected proposals and
state-machine reasons visible. Host replay is separate from a closed-loop plant,
linked firmware, emulator, physical PIL and real-time timing evidence.

Licensing: Lucas explicitly authorized this scoped import from his repository.
Neither repository declares an overall redistribution license at import time;
this import does not invent one. Existing third-party citations and tool/header
license provenance remain in the original research/evidence. No ST HAL/CMSIS
implementation or third-party toolchain is added to the portable C core.
Public binary/source licensing and recorded-data publication remain release gates.

Historical receipts keep their original paths, hashes and conclusions. New
relocation/build evidence must use a new receipt and identify this LapSim source;
an old successful receipt cannot prove that these relocated sources executed.
Run `python scripts/check_controller_import.py` to audit the import, then follow
`docs/controller_source.md` for fresh reference and native execution.
