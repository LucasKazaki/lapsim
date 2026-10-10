# LapSim interactive simulator flowchart

**Public web view:** [https://lucaskazaki.github.io/lapsim/](https://lucaskazaki.github.io/lapsim/)

The same viewer remains available offline at [`index.html`](index.html) from a
local checkout. No package installation, build step, account, or network
connection is required for local use.

The root represents the complete simulator as one node. Each branch can expand
through subsystem responsibilities and execution order to equation-level leaves.
The current map contains the desktop and programmatic entry points, configuration
and provenance, the distance-domain lap solver, one-cell vehicle update,
component physics, optional racing-line and road-grip workflows, the separate
time-domain four-wheel model, outputs, replay, scoring, and validation limits.

## Controls

- Click a node to inspect its summary, inputs, outputs, equations, assumptions,
  source files, and related subsystems.
- Double-click a node, press Space while it has keyboard focus, or use its `+` / `−`
  control to expand or collapse it.
- Drag empty space to pan. Use the mouse wheel or a two-finger pinch to zoom.
- Drag an individual node to make a temporary layout adjustment. **Reset positions**
  restores the generated tree layout.
- Search indexes titles, descriptions, equations, assumptions, and source paths.
  Press Enter or **Next** to cycle through all matches.
- **Related links** shows optional dashed cross-links between visible nodes that
  interact but are not in the same parent-child branch.
- **Collapse all** reduces the complete map to the single `LapSim simulator` node.
  **Expand all** exposes every documented node.

A URL fragment selects a node directly, for example
[`https://lucaskazaki.github.io/lapsim/#battery-current-root`](https://lucaskazaki.github.io/lapsim/#battery-current-root).
Source links are repository-relative when opened locally. The published site is
served from the complete public repository tree, so the same links remain valid
on GitHub Pages.

## Publication and automated checks

- `main` is the source of truth for the site and simulator documentation.
- The repository-root `index.html` preserves query strings and URL fragments,
  then redirects to `docs/simulator_flowchart/`.
- The public `gh-pages` branch points to a reviewed `main` commit so GitHub Pages
  can serve the same files without a separate generated copy.
- `.github/workflows/flowchart-web.yml` runs static-file, JavaScript syntax,
  graph-integrity, source-link, and headless-Chromium smoke checks for changes to
  the viewer.
- `scripts/check_flowchart_site.py` and `scripts/check_flowchart_data.mjs` can be
  run locally before publishing.

## Maturity labels

The map deliberately distinguishes model maturity:

| Label | Meaning |
|---|---|
| `implemented` | Present in the current repository path described by the node. |
| `optional` | Implemented but disabled or bypassed in the ordinary default route. |
| `experimental` | Implemented research/diagnostic route with explicit scope limits. |
| `assumption` | Scenario input or inherited parameter, not measured evidence. |
| `limitation` | Important boundary on interpreting a result. |
| `future` | Documented replacement seam or evidence gate, not current physics. |

These labels describe software status and evidence, not predictive accuracy.
A passing implementation or numerical check does not by itself validate the
2026–27 or 2027–28 team car.

## Files and maintenance

- `data/core.js` defines the compact node constructor and map metadata. The nine
  branch-aligned files under `data/` contain the maintained hierarchy.
- `data.js` assembles those branch files into `window.LAPSIM_FLOWCHART_DATA`, so
  the viewer can run from `file://` without a browser fetch request.
- `app.js` builds the hierarchy, layout, search index, pan/zoom interaction,
  node dragging, cross-links, and detail panel.
- `styles.css` owns the responsive layout and maturity/kind presentation.
- `index.html` is the dependency-free shell.

Each node must have a unique `id`, `title`, `kind`, `status`, and `summary`.
Optional fields are `inputs`, `outputs`, `equations`, `assumptions`, `sources`,
`related`, and `children`. A source object uses `path` and may add `symbol`.
`related` contains node IDs. Keep equations in plain text so they remain
searchable, diffable, and readable when JavaScript is unavailable.

When simulator behavior changes:

1. Update the relevant branch file under `data/` in the same pull request as the
   code change.
2. Add or revise source paths and maturity labels.
3. Run `python scripts/check_flowchart_site.py` and
   `node scripts/check_flowchart_data.mjs` from the repository root.
4. Open `index.html`, expand the changed branch, search for its primary symbol,
   and verify source links.
5. Update the compact Mermaid overview in the repository root `README.md` only
   when a top-level subsystem boundary changes.

## Why this format

The design uses two complementary representations:

1. The root README contains a compact Mermaid overview because GitHub renders
   Mermaid code blocks natively in Markdown.
2. This repository-owned SVG viewer provides the deeper interaction Mermaid
   does not need to carry: progressive disclosure to equations, movable nodes,
   source metadata, search, maturity labels, related links, and offline use.

The following current tools were evaluated from their official documentation:

- [Mermaid](https://mermaid.js.org/intro/) is text-based, versionable, and
  rendered by GitHub, making it the best compact README overview.
- [Eraser](https://docs.eraser.io/docs/git-sync) offers AI/codebase diagrams and
  Git synchronization, but its repository embedding workflow publishes a
  rendered image and keeps a tool-specific diagram document.
- [React Flow](https://reactflow.dev/examples/layout/expand-collapse) provides a
  polished node editor and an expand/collapse example, but that example is a Pro
  template and the library adds a JavaScript build/runtime dependency.
- [Markmap](https://markmap.js.org/docs/markmap) is excellent for collapsible
  Markdown hierarchies, but this map needs richer per-node metadata, source
  links, maturity labels, and cross-system relations.
- [D3](https://d3js.org/d3-zoom) supplies general tree, drag, and zoom primitives,
  but a small native SVG implementation avoids an external dependency while
  preserving the required interaction.

The viewer therefore remains inspectable and usable after cloning the repository,
including on a machine without Node.js or internet access.
