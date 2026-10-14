# Flow map verification — 2026-10-09

The map was checked against the final local source checkout, including the
portable desktop launcher, frozen-application resources, and physics fixes.

## Coverage

- 79 Python modules under `src/`.
- 900 function/method declarations.
- 6,616 individual parameter, field/constant, and local binding nodes.
- 3,253 source return-expression and branch/loop-bound nodes. Assignment
  expressions appear within the variable they define.
- Nine curated subsystem branches plus the complete source catalog; curated
  physics equations expand into individual mathematical quantities.
- 13,048 total map nodes in this release. Unknown unit metadata is labeled
  explicitly. Dynamic runtime keys/array elements are outside static enumeration.

The source catalog records normalized UTF-8/LF SHA-256 digests, allowing the
freshness gate to distinguish source changes from Windows/Linux line endings.

## Automated verification

`python -m pytest tests/test_simulator_flowchart.py -q`: **4 passed**.

These checks validate catalog freshness, source-module and declaration coverage,
every assignment/return/decision expression, units without invented dimensions,
unique node IDs, related-link targets, existing source files, and equation-to-
variable disclosure. The notation checks include curvature versus slip, corridor
audit dimensions, and dimensional literals versus the vehicle-mass symbol.

`node docs/simulator_flowchart/browser_check.cjs`: **passed** in installed
Microsoft Edge using a real offline `file://` page with reduced motion enabled.

Verified root load, equation-to-variable inspection, air-density unit disclosure,
exact-source search, keyboard result selection, double-click disclosure,
arrow-key hierarchy and surviving focus, node dragging and position reset,
complete expansion, narrow mobile layout without page overflow, malformed URL
fragment recovery, and absence of JavaScript console errors.

All 13,048 nodes expanded in approximately **20 ms** on the test machine. The
small-zoom overview painted **605** grouped marks rather than creating thousands
of full cards. This is an observed local result, not a performance guarantee.
A team member can still inspect every child through search and branch buttons.

## Corrections made during review

- Replaced two stale file references with current implementation/test paths.
- Corrected the one-cell brake conversion notation so already-converted axle
  force is not described as divided by tire radius again.
- Documented zero torque when battery discharge power is unavailable, the stable
  low-current battery root, and bounded coulomb-counted SOC.
- Fixed overlapping view animations, drag capture on replaced nodes, lost
  keyboard focus, malformed fragments, and clipped long source identifiers.
- Kept native browser zoom/find available and added reduced-motion/contrast/
  transparency behavior, searchable unit/type/default metadata, and direct
  detail-panel navigation into hidden branches.

These are implementation, source-consistency, numerical-notation, and interface
checks. They do not constitute tire/battery/vehicle predictive validation.

