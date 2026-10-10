# LapSim interactive simulator flowchart

The [GitHub Pages viewer](https://lucaskazaki.github.io/lapsim/) publishes the
repository's Pages revision. The team browser release combines the complete
source catalog with the simulator; see [the browser guide](../web_simulator.md).
Share a node's URL fragment to open its equations directly.

The public Pages checks in `.github/workflows/flowchart-web.yml` validate static
assets, graph integrity, source links, and a real Chromium load. The separate
live smoke workflow verifies the published Pages revision. Locally, run
`python scripts/check_flowchart_site.py` and
`node scripts/check_flowchart_data.mjs` before publication.

Open [`index.html`](index.html) from a local checkout or the share bundle. No
package installation, build step, server, account, or network connection is
required. The viewer also works as a static GitHub Pages site.

The root represents the complete simulator as one node. Each branch expands
through subsystem responsibilities and execution order to equations and
individual variables. Select an equation's child to inspect its symbol, meaning,
units, and unit evidence. **Inspect source variables** opens the exact
implementation catalog for that file or function.

The nine curated branches cover entry points, inputs and provenance, the
distance-domain lap solver, one-cell vehicle update, component physics,
racing-line and road-grip workflows, the separate time-domain four-wheel model,
results/replay/scoring, and verification limits. A tenth branch, **Source
variables and exact expressions**, is generated from every Python module under
`src/` and the Python browser bridge under `web/`. The browser entry-point
branch also exposes each JSON input's units and limits. The catalog covers
module/class fields, constants, function parameters, local
assignment/iteration/context bindings, exact definitions, returns, and branch
or loop bounds. Default expressions and Python types are shown without importing
or executing simulator code.

The physics view and source view complement each other. A source assignment is
not automatically a physical law. Units from name suffixes are labeled as naming
evidence; unknown units remain **not declared**. Static inspection cannot
enumerate dynamically created dictionary keys, array elements, or attributes.
Indexed bindings remain explicit expressions. Comprehension-internal and lambda
parameter names remain inspectable within source expressions. Imports appear as
referenced calls/dependencies rather than independent physical quantities.

## Controls

- Click a node to inspect its summary, inputs, outputs, equations, assumptions,
  source files, individual quantities, and related subsystems.
- Double-click, press Space on a focused node, or use its `+` / `−` control to
  expand or collapse it.
- With a node focused, Right expands or enters its first child, Left collapses or
  returns to its parent, Up/Down traverse visible hierarchy, Home/End move to its
  ends, and Enter inspects it. Focus survives expansion and layout changes.
- The detail panel's **Explore this branch** buttons open any child directly,
  including children outside the viewport or in a collapsed branch.
- Drag empty space to pan. Scroll or pinch to zoom. Drag a node to rearrange it;
  **Reset positions** restores generated layout.
- Search includes variable names, units, types, defaults, source expressions,
  equations, descriptions, assumptions, dependencies, and source paths. Enter or
  **Next** cycles through every match, including matches beyond the short list.
- Press `/` outside a text field to focus map search. Down enters the result list,
  Up/Down navigate it, and Escape closes it. Native browser text zoom and find
  shortcuts remain available.
- **Related links** adds dashed links between visible interacting subsystems.
- **Collapse all** reduces the map to one node. **Expand all** exposes every
  documented node. At very small zoom, grouped overview marks replace thousands
  of tiny cards; zoom in or search to inspect the complete expanded hierarchy.
  Counts report expanded logical nodes. Viewport rendering keeps it responsive.

A URL fragment selects a node directly, for example
`index.html#battery-current-root`. Source links open repository-relative files in
a new tab. Line numbers are explicit in the detail panel. Embedded exact
expressions remain available offline even when a browser downloads rather than
displays a Python link. The viewer follows system light/dark appearance,
reduced-motion, increased-contrast, and reduced-transparency preferences.

## Maturity labels

| Label | Meaning |
|---|---|
| `implemented` | Present in the described repository path. |
| `optional` | Implemented but disabled or bypassed in the default route. |
| `experimental` | Implemented research/diagnostic route with explicit limits. |
| `assumption` | Scenario input or inherited parameter, not measured evidence. |
| `limitation` | Boundary on interpreting a result. |
| `future` | Replacement seam or evidence gate, not current physics. |

These labels describe software status and evidence, not predictive accuracy.
Passing implementation or numerical checks does not validate the team car.

## Files and maintenance

- `data/core.js` defines the compact constructor and metadata. The nine numbered
  branch files under `data/` contain the curated hierarchy.
- `data/equation-variables.js` adds per-equation and per-symbol disclosure with
  context-dependent notation for curvature/slip, battery, planar mechanics,
  scoring, and racing-line geometry.
- `generate_inventory.py` creates `data/source-inventory.js` from source syntax
  trees and records SHA-256 digests of UTF-8 source with LF line endings. This
  normalization keeps identical Windows/Linux checkouts equivalent.
- `data.js` assembles `window.LAPSIM_FLOWCHART_DATA` and connects curated source
  references to catalog declarations. Ordinary script tags allow `file://` use
  without browser fetch requests.
- `app.js` handles hierarchy, viewport layout/rendering, search, pan/zoom,
  interruptible view transitions, node dragging, links, and the detail panel.
- `styles.css` supplies responsive layout, accessibility preferences, and labels.
- `index.html` is the dependency-free shell.

Every node needs a unique `id`, `title`, `kind`, `status`, and `summary`. Optional
fields include `inputs`, `outputs`, `equations`, `assumptions`, `sources`,
`related`, `children`, `variable`, `expressions`, `dependencies`, and `declaration`.
Sources use `path` and optionally `symbol`, `line`, or `catalogId`. Related links
contain node IDs. Equations remain plain, searchable text. Python `**` means
exponentiation; `^` in curated mathematical notation means exponentiation too,
rather than Python's bitwise exclusive-or operator.

After changing source behavior:

1. Update the relevant curated branch, source references, and maturity labels.
2. Run `python docs/simulator_flowchart/generate_inventory.py`.
3. Run `python -m pytest tests/test_simulator_flowchart.py -q`. It checks catalog
   freshness, every module/declaration/assignment/return/decision, valid source
   paths, unique IDs, related targets, unit evidence, and equation disclosure.
4. Open the map, expand the changed branch, search its main symbol, and inspect
   its sources. Update the root README overview if a subsystem boundary changed.

Use `python docs/simulator_flowchart/generate_inventory.py --check` as a read-only
freshness gate. `node docs/simulator_flowchart/browser_check.cjs` is an optional
real-browser regression check requiring Playwright and installed Microsoft Edge.
It verifies an offline `file://` load, individual units, source search, keyboard
focus/hierarchy, reduced motion, complete expansion, bounded overview DOM size,
and console errors. `NODE_PATH` can point to preinstalled Playwright packages.
See [QA.md](QA.md) for the release verification record.

## Why this format

The root README supplies a compact Mermaid overview. This repository-owned SVG
viewer supplies deeper disclosure, source evidence, variable inspection,
movable nodes, search, model-maturity labels, and related links. It remains usable
on a machine without Node.js or internet access; those tools are only needed to
run maintenance checks.
