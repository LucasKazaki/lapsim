(() => {
  "use strict";

  const data = window.LAPSIM_FLOWCHART_DATA;
  if (!data || !data.root) {
    document.body.innerHTML = "<p>Flowchart data could not be loaded.</p>";
    return;
  }

  const SVG_NS = "http://www.w3.org/2000/svg";
  const NODE_WIDTH = 272;
  const NODE_MIN_HEIGHT = 88;
  const DEPTH_GAP = 112;
  const ROW_GAP = 34;
  const VIEW_PADDING = 70;
  const MIN_SCALE = 0.0002;
  const MAX_SCALE = 4.0;

  const svg = document.getElementById("graph");
  const viewportEl = document.getElementById("viewport");
  const treeEdgesEl = document.getElementById("tree-edges");
  const relatedEdgesEl = document.getElementById("related-edges");
  const nodesEl = document.getElementById("nodes");
  const graphPanel = document.getElementById("graph-panel");
  const detailsEl = document.getElementById("details");
  const searchInput = document.getElementById("search-input");
  const searchResultsEl = document.getElementById("search-results");
  const visibleCountEl = document.getElementById("visible-count");
  const totalCountEl = document.getElementById("total-count");
  const showRelatedInput = document.getElementById("show-related");

  const nodesById = new Map();
  const parentById = new Map();
  const depthById = new Map();
  const ancestorsById = new Map();
  const descendantsById = new Map();
  const searchable = [];
  const variableLookup = new Map();

  function flatten(node, parent = null, depth = 0, ancestors = []) {
    if (!node.id || nodesById.has(node.id)) {
      throw new Error(`Duplicate or missing node id: ${node.id || "(missing)"}`);
    }
    nodesById.set(node.id, node);
    if (node.kind === "variable" && node.sources?.[0]) {
      const source = node.sources[0];
      variableLookup.set(`${source.path}:${source.symbol}:${node.title}`, node.id);
      const fallback = `${source.path}:*:${node.title}`;
      if (!variableLookup.has(fallback)) variableLookup.set(fallback, node.id);
    }
    parentById.set(node.id, parent ? parent.id : null);
    depthById.set(node.id, depth);
    ancestorsById.set(node.id, ancestors);

    const sourceText = (node.sources || [])
      .map((source) => `${source.path || ""} ${source.symbol || ""}`)
      .join(" ");
    searchable.push({
      id: node.id,
      node,
      haystack: [
        node.id,
        node.title,
        node.kind,
        node.status,
        node.summary,
        ...(node.inputs || []),
        ...(node.outputs || []),
        ...(node.equations || []),
        ...(node.assumptions || []),
        ...(node.dependencies || []),
        ...(node.expressions || []).map((entry) => entry.text),
        ...Object.values(node.variable || {}),
        sourceText,
      ].join(" ").toLowerCase(),
    });

    const descendants = [];
    for (const child of node.children || []) {
      flatten(child, node, depth + 1, [...ancestors, node.id]);
      descendants.push(child.id, ...(descendantsById.get(child.id) || []));
    }
    descendantsById.set(node.id, descendants);
  }

  flatten(data.root);
  totalCountEl.textContent = `${nodesById.size} total`;
  document.getElementById("subtitle").textContent = data.meta?.subtitle || "";

  const expanded = new Set();
  const manualOffsets = new Map();
  let selectedId = null;
  let currentLayout = null;
  let initialFitComplete = false;
  let searchMatches = [];
  let searchCursor = -1;
  let didDragNode = false;
  let focusedId = data.root.id;
  let viewAnimation = 0;
  let paintFrame = 0;

  const view = { x: 0, y: 0, k: 1 };

  function setDefaultExpanded() {
    expanded.clear();
    const depth = Number(data.meta?.defaultExpandedDepth ?? 1);
    for (const [id, nodeDepth] of depthById) {
      if (nodeDepth < depth && (nodesById.get(id).children || []).length) {
        expanded.add(id);
      }
    }
  }

  setDefaultExpanded();

  function createSvg(tag, attributes = {}, text = null) {
    const element = document.createElementNS(SVG_NS, tag);
    for (const [name, value] of Object.entries(attributes)) {
      if (value !== null && value !== undefined) {
        element.setAttribute(name, String(value));
      }
    }
    if (text !== null) element.textContent = text;
    return element;
  }

  function wrapTitle(text, maxChars = 30, maxLines = 3) {
    const words = String(text).split(/\s+/);
    const lines = [];
    let line = "";
    for (const word of words) {
      const candidate = line ? `${line} ${word}` : word;
      if (candidate.length > maxChars && line) {
        lines.push(line);
        line = word;
        if (lines.length === maxLines - 1) break;
      } else {
        line = candidate;
      }
    }
    const consumedWords = lines.join(" ").split(/\s+/).filter(Boolean).length;
    const remainingWords = words.slice(consumedWords);
    if (line && lines.length < maxLines) {
      const remainingText = remainingWords.join(" ");
      lines.push(remainingText || line);
    }
    if (lines.length > maxLines) lines.length = maxLines;
    const reconstructed = lines.join(" ");
    if (reconstructed.length < text.length && lines.length) {
      lines[lines.length - 1] = `${lines[lines.length - 1].replace(/[.…]$/, "").slice(0, maxChars - 1)}…`;
    }
    return lines;
  }

  function nodeHeight(node) {
    return NODE_MIN_HEIGHT + (wrapTitle(node.title).length - 1) * 17;
  }

  function computeLayout() {
    const visibleNodes = [];
    const visibleEdges = [];
    let cursorY = 0;

    function place(node, depth) {
      const children = expanded.has(node.id) ? (node.children || []) : [];
      const h = nodeHeight(node);
      const position = {
        id: node.id,
        node,
        depth,
        x: depth * (NODE_WIDTH + DEPTH_GAP),
        y: 0,
        width: NODE_WIDTH,
        height: h,
      };

      if (!children.length) {
        position.y = cursorY;
        cursorY += h + ROW_GAP;
      } else {
        const childPositions = [];
        for (const child of children) {
          const childPosition = place(child, depth + 1);
          childPositions.push(childPosition);
          visibleEdges.push([node.id, child.id]);
        }
        const firstCenter = childPositions[0].y + childPositions[0].height / 2;
        const lastCenter = childPositions[childPositions.length - 1].y + childPositions[childPositions.length - 1].height / 2;
        position.y = (firstCenter + lastCenter) / 2 - h / 2;
      }

      const offset = manualOffsets.get(node.id);
      if (offset) {
        position.x += offset.x;
        position.y += offset.y;
      }
      visibleNodes.push(position);
      return position;
    }

    place(data.root, 0);
    const byId = new Map(visibleNodes.map((position) => [position.id, position]));
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const position of visibleNodes) {
      minX = Math.min(minX, position.x);
      minY = Math.min(minY, position.y);
      maxX = Math.max(maxX, position.x + position.width);
      maxY = Math.max(maxY, position.y + position.height);
    }
    return {
      nodes: visibleNodes,
      edges: visibleEdges,
      byId,
      bounds: { minX, minY, maxX, maxY, width: maxX - minX, height: maxY - minY },
    };
  }

  function edgePath(source, target) {
    const sx = source.x + source.width;
    const sy = source.y + source.height / 2;
    const tx = target.x;
    const ty = target.y + target.height / 2;
    const span = Math.max(48, (tx - sx) * 0.52);
    return `M ${sx} ${sy} C ${sx + span} ${sy}, ${tx - span} ${ty}, ${tx} ${ty}`;
  }

  function relatedPath(source, target) {
    const sx = source.x + source.width / 2;
    const sy = source.y + source.height / 2;
    const tx = target.x + target.width / 2;
    const ty = target.y + target.height / 2;
    const bend = Math.max(55, Math.abs(tx - sx) * 0.25);
    return `M ${sx} ${sy} C ${sx + bend} ${sy - 38}, ${tx - bend} ${ty + 38}, ${tx} ${ty}`;
  }

  function statusLabel(status) {
    return String(status || "unknown").replace(/_/g, " ");
  }

  function renderNode(position) {
    const { node } = position;
    const group = createSvg("g", {
      class: `node kind-${node.kind || "data"} status-${node.status || "future"}${selectedId === node.id ? " selected" : ""}`,
      transform: `translate(${position.x} ${position.y})`,
      tabindex: focusedId === node.id ? "0" : "-1",
      role: "treeitem",
      "aria-label": `${node.title}. ${statusLabel(node.status)}. ${(node.children || []).length ? (expanded.has(node.id) ? "Expanded" : "Collapsed") : "Leaf node"}.`,
      "aria-expanded": (node.children || []).length ? String(expanded.has(node.id)) : null,
      "aria-selected": String(selectedId === node.id),
      "aria-level": position.depth + 1,
      "aria-setsize": parentById.get(node.id) ? (nodesById.get(parentById.get(node.id)).children || []).length : 1,
      "aria-posinset": parentById.get(node.id) ? (nodesById.get(parentById.get(node.id)).children || []).findIndex((child) => child.id === node.id) + 1 : 1,
      "data-node-id": node.id,
    });

    group.appendChild(createSvg("rect", {
      class: "node-card",
      width: position.width,
      height: position.height,
      rx: 12,
      ry: 12,
    }));
    group.appendChild(createSvg("rect", {
      class: "node-accent",
      x: 0,
      y: 0,
      width: 7,
      height: position.height,
      rx: 4,
      ry: 4,
    }));

    const lines = wrapTitle(node.title);
    const title = createSvg("text", { class: "node-title", x: 18, y: 25 });
    lines.forEach((line, index) => {
      title.appendChild(createSvg("tspan", { x: 18, dy: index === 0 ? 0 : 17 }, line));
    });
    group.appendChild(title);

    const metaY = 30 + lines.length * 17;
    group.appendChild(createSvg("text", { class: "node-meta", x: 18, y: metaY }, String(node.kind || "node").replace(/_/g, " ")));

    const status = statusLabel(node.status);
    const pillWidth = Math.max(58, status.length * 6.2 + 16);
    group.appendChild(createSvg("rect", {
      class: "status-pill",
      x: 18,
      y: position.height - 25,
      width: pillWidth,
      height: 16,
      rx: 8,
    }));
    group.appendChild(createSvg("text", {
      class: "status-pill-label",
      x: 26,
      y: position.height - 13.5,
    }, status));

    const children = node.children || [];
    if (children.length) {
      group.appendChild(createSvg("text", {
        class: "node-count",
        x: position.width - 38,
        y: position.height - 14,
      }, `${children.length} direct / ${(descendantsById.get(node.id) || []).length} total`));
      const toggle = createSvg("g", {
        class: "node-toggle",
        transform: `translate(${position.width - 17} ${position.height / 2})`,
        role: "button",
        "aria-label": expanded.has(node.id) ? `Collapse ${node.title}` : `Expand ${node.title}`,
      });
      toggle.appendChild(createSvg("circle", { class: "toggle-circle", r: 12 }));
      toggle.appendChild(createSvg("text", { class: "toggle-symbol", x: 0, y: 0 }, expanded.has(node.id) ? "−" : "+"));
      toggle.addEventListener("pointerdown", (event) => event.stopPropagation());
      toggle.addEventListener("click", (event) => {
        event.stopPropagation();
        toggleExpanded(node.id);
      });
      group.appendChild(toggle);
    }

    group.addEventListener("click", () => {
      if (!didDragNode) selectNode(node.id, { updateHash: true });
      didDragNode = false;
    });
    group.addEventListener("dblclick", (event) => {
      event.preventDefault();
      if (children.length) toggleExpanded(node.id);
    });
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        selectNode(node.id, { updateHash: true });
      } else if (event.key === " " && children.length) {
        event.preventDefault();
        toggleExpanded(node.id);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        if (children.length && !expanded.has(node.id)) toggleExpanded(node.id);
        else if (children.length) focusNode(children[0].id);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        if (children.length && expanded.has(node.id)) toggleExpanded(node.id);
        else if (parentById.get(node.id)) focusNode(parentById.get(node.id));
      } else if (["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        const order = navigationOrder();
        const index = order.indexOf(node.id);
        const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? order.length - 1 : Math.max(0, Math.min(order.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)));
        focusNode(order[nextIndex]);
      }
    });
    group.addEventListener("focus", () => {
      focusedId = node.id;
      for (const element of nodesEl.querySelectorAll('.node[tabindex="0"]')) {
        if (element !== group) element.setAttribute("tabindex", "-1");
      }
      group.setAttribute("tabindex", "0");
    });
    group.addEventListener("pointerdown", (event) => beginNodeDrag(event, node.id));
    return group;
  }

  function render() {
    currentLayout = computeLayout();
    if (!currentLayout.byId.has(focusedId)) focusedId = currentLayout.byId.has(selectedId) ? selectedId : data.root.id;
    paintGraph();
    visibleCountEl.textContent = `${currentLayout.nodes.length.toLocaleString()} expanded`;
    applyView();
  }

  function navigationOrder() {
    const order = [];
    function visit(node) {
      order.push(node.id);
      if (expanded.has(node.id)) for (const child of node.children || []) visit(child);
    }
    visit(data.root);
    return order;
  }

  function focusNode(id) {
    focusedId = id;
    centerNode(id, {scale: Math.max(view.k, 0.7)});
    paintGraph();
    nodesEl.querySelector(`[data-node-id="${CSS.escape(id)}"]`)?.focus({preventScroll: true});
  }

  function paintGraph() {
    if (!currentLayout) return;
    const activeId = document.activeElement?.closest?.(".node")?.dataset.nodeId;
    const rect = svg.getBoundingClientRect();
    const margin = 360;
    const inView = (position) => {
      const x = position.x * view.k + view.x, y = position.y * view.k + view.y;
      return x + position.width * view.k >= -margin && x <= rect.width + margin && y + position.height * view.k >= -margin && y <= rect.height + margin;
    };
    treeEdgesEl.replaceChildren();
    relatedEdgesEl.replaceChildren();
    nodesEl.replaceChildren();

    // At overview scale, draw one quiet mark per screen bucket. Full node cards
    // return on zoom; the detail panel and search always expose the complete data.
    const overview = view.k < 0.14;
    const rendered = currentLayout.nodes.filter((position) => inView(position) || position.id === focusedId || position.id === selectedId || position.id === activeId);
    const renderedIds = new Set(rendered.map((position) => position.id));
    for (const [sourceId, targetId] of overview ? [] : currentLayout.edges) {
      if (!renderedIds.has(sourceId) && !renderedIds.has(targetId)) continue;
      const source = currentLayout.byId.get(sourceId);
      const target = currentLayout.byId.get(targetId);
      treeEdgesEl.appendChild(createSvg("path", { class: "tree-edge", d: edgePath(source, target) }));
    }

    if (showRelatedInput.checked) renderRelatedEdges();

    const buckets = new Set();
    const orderedNodes = rendered.sort((a, b) => a.depth - b.depth || a.y - b.y);
    for (const position of orderedNodes) {
      if (overview && ![selectedId, focusedId, activeId].includes(position.id)) {
        const bucket = `${position.depth}:${Math.round((position.y * view.k + view.y) / 5)}`;
        if (buckets.has(bucket)) continue;
        buckets.add(bucket);
        nodesEl.appendChild(createSvg("rect", {class: "overview-mark", x: position.x, y: position.y, width: position.width, height: Math.max(position.height, 2 / view.k), "aria-hidden": "true"}));
      } else nodesEl.appendChild(renderNode(position));
    }
    if (activeId) nodesEl.querySelector(`[data-node-id="${CSS.escape(activeId)}"]`)?.focus({preventScroll: true});
  }

  function renderRelatedEdges() {
    const seen = new Set();
    for (const position of currentLayout.nodes) {
      for (const relatedId of position.node.related || []) {
        const target = currentLayout.byId.get(relatedId);
        if (!target) continue;
        const key = [position.id, relatedId].sort().join("::");
        if (seen.has(key)) continue;
        seen.add(key);
        relatedEdgesEl.appendChild(createSvg("path", {
          class: "related-edge",
          d: relatedPath(position, target),
        }));
      }
    }
  }

  function applyView() {
    viewportEl.setAttribute("transform", `translate(${view.x} ${view.y}) scale(${view.k})`);
    if (!paintFrame) paintFrame = requestAnimationFrame(() => { paintFrame = 0; paintGraph(); });
  }

  function cancelViewAnimation() {
    if (viewAnimation) cancelAnimationFrame(viewAnimation);
    viewAnimation = 0;
  }

  function fitView({ animate = false } = {}) {
    if (!currentLayout) return;
    const rect = svg.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const bounds = currentLayout.bounds;
    const scale = Math.max(
      MIN_SCALE,
      Math.min(
        1.35,
        (rect.width - 2 * VIEW_PADDING) / Math.max(bounds.width, 1),
        (rect.height - 2 * VIEW_PADDING) / Math.max(bounds.height, 1),
      ),
    );
    const x = (rect.width - bounds.width * scale) / 2 - bounds.minX * scale;
    const y = (rect.height - bounds.height * scale) / 2 - bounds.minY * scale;
    if (animate) animateViewTo({ x, y, k: scale });
    else {
      cancelViewAnimation();
      Object.assign(view, { x, y, k: scale });
      applyView();
    }
  }

  function animateViewTo(target) {
    cancelViewAnimation();
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      Object.assign(view, target);
      applyView();
      return;
    }
    const start = { ...view };
    const duration = 220;
    const startTime = performance.now();
    function frame(now) {
      const t = Math.min(1, (now - startTime) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      view.x = start.x + (target.x - start.x) * eased;
      view.y = start.y + (target.y - start.y) * eased;
      view.k = start.k + (target.k - start.k) * eased;
      applyView();
      if (t < 1) viewAnimation = requestAnimationFrame(frame);
      else viewAnimation = 0;
    }
    viewAnimation = requestAnimationFrame(frame);
  }

  function zoomAt(screenX, screenY, factor) {
    cancelViewAnimation();
    const nextK = Math.max(MIN_SCALE, Math.min(MAX_SCALE, view.k * factor));
    const worldX = (screenX - view.x) / view.k;
    const worldY = (screenY - view.y) / view.k;
    view.x = screenX - worldX * nextK;
    view.y = screenY - worldY * nextK;
    view.k = nextK;
    applyView();
  }

  function centerNode(id, { scale = null } = {}) {
    const position = currentLayout?.byId.get(id);
    if (!position) return;
    const rect = svg.getBoundingClientRect();
    const targetK = scale === null ? Math.max(view.k, 0.65) : scale;
    animateViewTo({
      x: rect.width / 2 - (position.x + position.width / 2) * targetK,
      y: rect.height / 2 - (position.y + position.height / 2) * targetK,
      k: Math.min(MAX_SCALE, Math.max(MIN_SCALE, targetK)),
    });
  }

  function toggleExpanded(id) {
    const node = nodesById.get(id);
    if (!(node.children || []).length) return;
    if (expanded.has(id)) expanded.delete(id);
    else expanded.add(id);
    render();
    if (selectedId === id) renderDetails(node);
  }

  function expandAncestors(id) {
    for (const ancestorId of ancestorsById.get(id) || []) expanded.add(ancestorId);
  }

  function selectNode(id, { center = false, updateHash = false } = {}) {
    const node = nodesById.get(id);
    if (!node) return;
    selectedId = id;
    renderDetails(node);
    for (const element of nodesEl.querySelectorAll(".node")) {
      const selected = element.dataset.nodeId === id;
      element.classList.toggle("selected", selected);
      element.setAttribute("aria-selected", String(selected));
    }
    if (center) centerNode(id);
    if (updateHash) {
      const nextHash = `#${encodeURIComponent(id)}`;
      if (window.location.hash !== nextHash) history.replaceState(null, "", nextHash);
    }
  }

  function section(title, values, className = "") {
    if (!values || !values.length) return "";
    const items = values.map((value) => `<li>${escapeHtml(value)}</li>`).join("");
    return `<section class="${className}"><h3>${escapeHtml(title)}</h3><ul>${items}</ul></section>`;
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function renderDetails(node) {
    const breadcrumbIds = [...(ancestorsById.get(node.id) || []), node.id];
    const breadcrumb = breadcrumbIds.map((id, index) => {
      const item = nodesById.get(id);
      const isLast = index === breadcrumbIds.length - 1;
      return isLast
        ? `<span>${escapeHtml(item.title)}</span>`
        : `<button type="button" data-breadcrumb-id="${escapeHtml(id)}">${escapeHtml(item.title)}</button><span> / </span>`;
    }).join("");

    const equations = (node.equations || []).length
      ? `<section><h3>Equations and logic</h3><div class="equation-list">${node.equations.map((equation) => `<pre class="equation"><code>${escapeHtml(equation)}</code></pre>`).join("")}</div></section>`
      : "";

    function dependencyId(name) {
      const source = node.sources?.[0];
      if (!source) return null;
      let scope = String(source.symbol || "");
      const fieldName = name.replace(/^self\./, "");
      while (scope) {
        const match = variableLookup.get(`${source.path}:${scope}:${name}`) || variableLookup.get(`${source.path}:${scope}:${fieldName}`);
        if (match && match !== node.id) return match;
        scope = scope.includes(".") ? scope.slice(0, scope.lastIndexOf(".")) : "";
      }
      return variableLookup.get(`${source.path}:*:${fieldName}`) || null;
    }

    const variableHtml = node.variable
      ? `<section><h3>Individual variable</h3><dl class="variable-definition">${[["Symbol / source name", node.variable.name], ["Meaning", node.variable.meaning], ["Unit", node.variable.unit], ["Unit evidence", node.variable.unitEvidence], ["Declared type", node.variable.type], ["Role", node.variable.role], ["Default expression", node.variable.default]].filter(([, value]) => value !== undefined).map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}</dl></section>`
      : "";
    const expressionsHtml = node.expressions?.length
      ? `<section><h3>Exact source expressions</h3>${node.expressions.map((entry, index) => `<details class="expression-disclosure" ${index === 0 ? "open" : ""}><summary>Definition ${index + 1} · line ${entry.line}</summary><pre class="equation"><code>${escapeHtml(entry.text)}</code></pre></details>`).join("")}</section>`
      : "";
    const dependenciesHtml = node.dependencies?.length
      ? `<section><h3>Referenced variables and calls</h3><p class="small-note">Variable links inspect static definitions. Other names are source dependencies or callables.</p><div class="related-buttons">${node.dependencies.map((name) => {
          const id = dependencyId(name);
          return id && id !== node.id ? `<button type="button" data-related-id="${id}">${escapeHtml(name)}</button>` : `<code class="dependency-name">${escapeHtml(name)}</code>`;
        }).join("")}</div></section>`
      : "";

    const sources = (node.sources || []).length
      ? `<section><h3>Implementation sources</h3><div class="source-list">${node.sources.map((source) => {
          const href = `../../${String(source.path).split("/").map(encodeURIComponent).join("/")}`;
          return `<div class="source-entry"><a class="source-link" href="${href}" target="_blank" rel="noopener"><span>${escapeHtml(source.path)}${source.line ? ` · line ${source.line}` : ""}</span>${source.symbol ? `<span class="source-symbol">${escapeHtml(source.symbol)}</span>` : ""}</a>${source.catalogId ? `<button type="button" data-related-id="${escapeHtml(source.catalogId)}">Inspect source variables</button>` : ""}</div>`;
        }).join("")}</div></section>`
      : "";

    const related = (node.related || []).filter((id) => nodesById.has(id));
    const relatedHtml = related.length
      ? `<section><h3>Related subsystems</h3><div class="related-buttons">${related.map((id) => `<button type="button" data-related-id="${escapeHtml(id)}">${escapeHtml(nodesById.get(id).title)}</button>`).join("")}</div></section>`
      : "";

    const children = node.children || [];
    const childrenHtml = children.length
      ? `<section><h3>Explore this branch</h3><p class="small-note">Open any child directly, even while the graph is collapsed or zoomed out.</p><div class="child-list">${children.map((child) => `<button type="button" data-related-id="${escapeHtml(child.id)}"><strong>${escapeHtml(child.title)}</strong><small>${escapeHtml(child.kind)}${child.variable?.unit ? ` · ${escapeHtml(child.variable.unit)}` : ""}${child.children?.length ? ` · ${child.children.length} children` : ""}</small></button>`).join("")}</div></section>`
      : "";
    const actions = children.length
      ? `<div class="detail-actions"><button type="button" data-detail-action="toggle">${expanded.has(node.id) ? "Collapse branch" : "Expand branch"}</button><button type="button" data-detail-action="expand-descendants">Expand all descendants</button><button type="button" data-detail-action="center">Center node</button></div>`
      : `<div class="detail-actions"><button type="button" data-detail-action="center">Center node</button></div>`;

    detailsEl.innerHTML = `
      <nav class="breadcrumb" aria-label="Node path">${breadcrumb}</nav>
      <h2>${escapeHtml(node.title)}</h2>
      <div class="detail-badges">
        <span class="detail-badge">${escapeHtml(node.kind || "node")}</span>
        <span class="detail-badge status-${escapeHtml(node.status || "future")}">${escapeHtml(statusLabel(node.status))}</span>
        ${children.length ? `<span class="detail-badge">${children.length} direct children</span>` : `<span class="detail-badge">equation/detail leaf</span>`}
      </div>
      <p class="detail-summary">${escapeHtml(node.summary || "")}</p>
      ${actions}
      ${section("Inputs", node.inputs)}
      ${section("Outputs", node.outputs)}
      ${variableHtml}
      ${equations}
      ${node.declaration ? `<section><h3>Source declaration</h3><pre class="equation"><code>${escapeHtml(node.declaration)}</code></pre></section>` : ""}
      ${expressionsHtml}
      ${dependenciesHtml}
      ${childrenHtml}
      ${section("Assumptions and limits", node.assumptions)}
      ${sources}
      ${relatedHtml}
    `;

    detailsEl.querySelectorAll("[data-breadcrumb-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const id = button.dataset.breadcrumbId;
        selectNode(id, { center: true, updateHash: true });
      });
    });
    detailsEl.querySelectorAll("[data-related-id]").forEach((button) => {
      button.addEventListener("click", () => revealNode(button.dataset.relatedId));
    });
    detailsEl.querySelector('[data-detail-action="toggle"]')?.addEventListener("click", () => toggleExpanded(node.id));
    detailsEl.querySelector('[data-detail-action="expand-descendants"]')?.addEventListener("click", () => {
      expanded.add(node.id);
      for (const descendantId of descendantsById.get(node.id) || []) {
        if ((nodesById.get(descendantId).children || []).length) expanded.add(descendantId);
      }
      render();
      renderDetails(node);
      centerNode(node.id);
    });
    detailsEl.querySelector('[data-detail-action="center"]')?.addEventListener("click", () => centerNode(node.id));
  }

  function revealNode(id) {
    if (!nodesById.has(id)) return;
    expandAncestors(id);
    render();
    selectNode(id, { center: true, updateHash: true });
  }

  function matchSearch(query) {
    const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
    if (!terms.length) return [];
    return searchable
      .filter((entry) => terms.every((term) => entry.haystack.includes(term)))
      .sort((a, b) => {
        const aTitle = a.node.title.toLowerCase();
        const bTitle = b.node.title.toLowerCase();
        const exactA = aTitle === query.toLowerCase() ? -2 : aTitle.startsWith(query.toLowerCase()) ? -1 : 0;
        const exactB = bTitle === query.toLowerCase() ? -2 : bTitle.startsWith(query.toLowerCase()) ? -1 : 0;
        return exactA - exactB || depthById.get(a.id) - depthById.get(b.id) || aTitle.localeCompare(bTitle);
      });
  }

  function updateSearchResults() {
    const query = searchInput.value.trim();
    searchMatches = matchSearch(query);
    searchCursor = -1;
    if (!query) {
      searchResultsEl.hidden = true;
      searchInput.setAttribute("aria-expanded", "false");
      searchResultsEl.replaceChildren();
      return;
    }
    searchResultsEl.hidden = false;
    searchInput.setAttribute("aria-expanded", "true");
    if (!searchMatches.length) {
      searchResultsEl.innerHTML = '<div class="search-empty">No matching nodes.</div>';
      return;
    }
    const shown = searchMatches.slice(0, 18);
    searchResultsEl.innerHTML = shown.map((entry) => {
      const parent = parentById.get(entry.id);
      const context = parent ? nodesById.get(parent).title : "Root";
      return `<button class="search-result" type="button" data-search-id="${escapeHtml(entry.id)}"><strong>${escapeHtml(entry.node.title)}</strong><small>${escapeHtml(entry.node.kind)} · ${escapeHtml(context)}</small></button>`;
    }).join("");
    if (searchMatches.length > shown.length) {
      searchResultsEl.insertAdjacentHTML("beforeend", `<div class="search-empty">${searchMatches.length - shown.length} more matches. Refine the query to narrow the list.</div>`);
    }
    searchResultsEl.querySelectorAll("[data-search-id]").forEach((button) => {
      button.addEventListener("click", () => {
        searchResultsEl.hidden = true;
        revealNode(button.dataset.searchId);
      });
    });
  }

  function openNextSearchResult() {
    if (!searchMatches.length) {
      searchMatches = matchSearch(searchInput.value.trim());
      if (!searchMatches.length) return;
    }
    searchCursor = (searchCursor + 1) % searchMatches.length;
    searchResultsEl.hidden = true;
    revealNode(searchMatches[searchCursor].id);
  }

  searchInput.addEventListener("input", updateSearchResults);
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      openNextSearchResult();
    } else if (event.key === "Escape") {
      searchResultsEl.hidden = true;
      searchInput.setAttribute("aria-expanded", "false");
    } else if (event.key === "ArrowDown" && !searchResultsEl.hidden) {
      event.preventDefault();
      searchResultsEl.querySelector("button")?.focus();
    }
  });
  document.getElementById("search-next").addEventListener("click", openNextSearchResult);
  document.addEventListener("pointerdown", (event) => {
    if (!event.target.closest(".search-group")) {
      searchResultsEl.hidden = true;
      searchInput.setAttribute("aria-expanded", "false");
    }
  });
  searchResultsEl.addEventListener("keydown", (event) => {
    const buttons = [...searchResultsEl.querySelectorAll("button")];
    const index = buttons.indexOf(document.activeElement);
    if (["ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      buttons[Math.max(0, Math.min(buttons.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)))]?.focus();
    } else if (event.key === "Escape") {
      searchResultsEl.hidden = true;
      searchInput.setAttribute("aria-expanded", "false");
      searchInput.focus();
    }
  });

  document.getElementById("collapse-all").addEventListener("click", () => {
    expanded.clear();
    render();
    fitView({ animate: true });
    if (selectedId) renderDetails(nodesById.get(selectedId));
  });
  document.getElementById("default-view").addEventListener("click", () => {
    setDefaultExpanded();
    manualOffsets.clear();
    render();
    fitView({ animate: true });
    if (selectedId) renderDetails(nodesById.get(selectedId));
  });
  document.getElementById("expand-level").addEventListener("click", () => {
    for (const position of currentLayout.nodes) {
      if ((position.node.children || []).length) expanded.add(position.id);
    }
    render();
    fitView({ animate: true });
    if (selectedId) renderDetails(nodesById.get(selectedId));
  });
  document.getElementById("expand-all").addEventListener("click", () => {
    for (const [id, node] of nodesById) if ((node.children || []).length) expanded.add(id);
    render();
    fitView({ animate: true });
    if (selectedId) renderDetails(nodesById.get(selectedId));
  });
  document.getElementById("fit-view").addEventListener("click", () => fitView({ animate: true }));
  document.getElementById("zoom-in").addEventListener("click", () => {
    const rect = svg.getBoundingClientRect();
    zoomAt(rect.width / 2, rect.height / 2, 1.24);
  });
  document.getElementById("zoom-out").addEventListener("click", () => {
    const rect = svg.getBoundingClientRect();
    zoomAt(rect.width / 2, rect.height / 2, 1 / 1.24);
  });
  document.getElementById("reset-positions").addEventListener("click", () => {
    manualOffsets.clear();
    render();
    fitView({ animate: true });
  });
  showRelatedInput.addEventListener("change", render);

  svg.addEventListener("wheel", (event) => {
    event.preventDefault();
    const rect = svg.getBoundingClientRect();
    const factor = Math.exp(-event.deltaY * 0.0014);
    zoomAt(event.clientX - rect.left, event.clientY - rect.top, factor);
  }, { passive: false });

  const backgroundPointers = new Map();
  let backgroundGesture = null;

  svg.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".node")) return;
    if (event.button !== 0) return;
    cancelViewAnimation();
    event.preventDefault();
    svg.setPointerCapture(event.pointerId);
    backgroundPointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    svg.classList.add("panning");
    if (backgroundPointers.size === 1) {
      backgroundGesture = {
        type: "pan",
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        viewX: view.x,
        viewY: view.y,
      };
    } else if (backgroundPointers.size === 2) {
      const points = [...backgroundPointers.values()];
      const center = { x: (points[0].x + points[1].x) / 2, y: (points[0].y + points[1].y) / 2 };
      const distance = Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
      const rect = svg.getBoundingClientRect();
      backgroundGesture = {
        type: "pinch",
        distance,
        centerX: center.x - rect.left,
        centerY: center.y - rect.top,
        worldX: (center.x - rect.left - view.x) / view.k,
        worldY: (center.y - rect.top - view.y) / view.k,
        viewK: view.k,
      };
    }
  });

  svg.addEventListener("pointermove", (event) => {
    if (!backgroundPointers.has(event.pointerId)) return;
    backgroundPointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (backgroundPointers.size === 1 && backgroundGesture?.type === "pan") {
      view.x = backgroundGesture.viewX + event.clientX - backgroundGesture.startX;
      view.y = backgroundGesture.viewY + event.clientY - backgroundGesture.startY;
      applyView();
    } else if (backgroundPointers.size >= 2) {
      const points = [...backgroundPointers.values()].slice(0, 2);
      const distance = Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
      const centerClientX = (points[0].x + points[1].x) / 2;
      const centerClientY = (points[0].y + points[1].y) / 2;
      const rect = svg.getBoundingClientRect();
      if (backgroundGesture?.type !== "pinch") return;
      const nextK = Math.max(MIN_SCALE, Math.min(MAX_SCALE, backgroundGesture.viewK * distance / Math.max(backgroundGesture.distance, 1)));
      view.k = nextK;
      view.x = centerClientX - rect.left - backgroundGesture.worldX * nextK;
      view.y = centerClientY - rect.top - backgroundGesture.worldY * nextK;
      applyView();
    }
  });

  function finishBackgroundPointer(event) {
    backgroundPointers.delete(event.pointerId);
    try { svg.releasePointerCapture(event.pointerId); } catch (_) { /* already released */ }
    if (!backgroundPointers.size) {
      backgroundGesture = null;
      svg.classList.remove("panning");
    } else if (backgroundPointers.size === 1) {
      const [pointerId, point] = backgroundPointers.entries().next().value;
      backgroundGesture = {
        type: "pan",
        pointerId,
        startX: point.x,
        startY: point.y,
        viewX: view.x,
        viewY: view.y,
      };
    }
  }
  svg.addEventListener("pointerup", finishBackgroundPointer);
  svg.addEventListener("pointercancel", finishBackgroundPointer);

  let nodeDrag = null;
  function beginNodeDrag(event, id) {
    if (event.button !== 0 || event.target.closest(".node-toggle")) return;
    event.stopPropagation();
    cancelViewAnimation();
    // Capture on the stable SVG, because node cards are regenerated on drag.
    const target = window;
    const current = manualOffsets.get(id) || { x: 0, y: 0 };
    nodeDrag = {
      id,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      offsetX: current.x,
      offsetY: current.y,
      target,
      moved: false,
      captured: false,
    };
    target.addEventListener("pointermove", moveNodeDrag);
    target.addEventListener("pointerup", endNodeDrag);
    target.addEventListener("pointercancel", endNodeDrag);
  }

  function moveNodeDrag(event) {
    if (!nodeDrag || event.pointerId !== nodeDrag.pointerId) return;
    const dx = (event.clientX - nodeDrag.startX) / view.k;
    const dy = (event.clientY - nodeDrag.startY) / view.k;
    if (Math.hypot(event.clientX - nodeDrag.startX, event.clientY - nodeDrag.startY) > 5) nodeDrag.moved = true;
    if (!nodeDrag.moved) return;
    if (!nodeDrag.captured) {
      svg.setPointerCapture(event.pointerId);
      nodeDrag.captured = true;
    }
    didDragNode = true;
    manualOffsets.set(nodeDrag.id, { x: nodeDrag.offsetX + dx, y: nodeDrag.offsetY + dy });
    render();
  }

  function endNodeDrag(event) {
    if (!nodeDrag || event.pointerId !== nodeDrag.pointerId) return;
    const target = nodeDrag.target;
    try { if (nodeDrag.captured) svg.releasePointerCapture(event.pointerId); } catch (_) { /* already released */ }
    target.removeEventListener("pointermove", moveNodeDrag);
    target.removeEventListener("pointerup", endNodeDrag);
    target.removeEventListener("pointercancel", endNodeDrag);
    const moved = nodeDrag.moved;
    nodeDrag = null;
    if (moved) {
      requestAnimationFrame(() => { didDragNode = false; });
    }
  }

  window.addEventListener("keydown", (event) => {
    // Keep native browser zoom and find shortcuts for accessibility. An ordinary
    // slash outside editable controls focuses the map's semantic search.
    if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !event.target.closest?.("input, textarea, [contenteditable]")) {
      event.preventDefault();
      searchInput.focus();
      searchInput.select();
    } else if (event.key === "Escape") {
      searchResultsEl.hidden = true;
    }
  });

  const resizeObserver = new ResizeObserver(() => {
    if (!initialFitComplete) return;
    applyView();
  });
  resizeObserver.observe(graphPanel);

  render();

  let hashId = "";
  try { hashId = decodeURIComponent(window.location.hash.replace(/^#/, "")); }
  catch (_) { /* Ignore a malformed URL fragment; keep the map usable. */ }
  window.addEventListener("hashchange", () => {
    let id = "";
    try { id = decodeURIComponent(window.location.hash.replace(/^#/, "")); }
    catch (_) { /* Invalid external fragments return to the root. */ }
    if (id && nodesById.has(id)) revealNode(id);
    else selectNode(data.root.id, {center: true});
  });
  if (hashId && nodesById.has(hashId)) {
    expandAncestors(hashId);
    render();
    selectNode(hashId, { updateHash: false });
    requestAnimationFrame(() => {
      fitView();
      centerNode(hashId);
      initialFitComplete = true;
    });
  } else {
    selectNode(data.root.id, { updateHash: false });
    requestAnimationFrame(() => {
      fitView();
      initialFitComplete = true;
    });
  }

  window.LAPSIM_FLOWCHART = {
    get visibleNodeCount() { return currentLayout?.nodes.length || 0; },
    get totalNodeCount() { return nodesById.size; },
    get selectedId() { return selectedId; },
    revealNode,
    fitView,
    collapseAll() {
      expanded.clear();
      render();
      fitView();
    },
    expandAll() {
      for (const [id, node] of nodesById) if ((node.children || []).length) expanded.add(id);
      render();
      fitView();
    },
  };
})();
