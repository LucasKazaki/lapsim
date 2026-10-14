/* Assemble all branch files into the viewer's public data object. */
(() => {
  "use strict";
  const build=window.LAPSIM_FLOWCHART_BUILD;
  const inventory = window.LAPSIM_SOURCE_INVENTORY;
  if (inventory?.root) {
    const sourceNodes = new Map();
    function index(node) {
      for (const source of node.sources || []) {
        if (!sourceNodes.has(source.path)) sourceNodes.set(source.path, []);
        sourceNodes.get(source.path).push({node, symbol: String(source.symbol).replaceAll("[class]", "")});
      }
      for (const child of node.children || []) index(child);
    }
    index(inventory.root);
    function connect(node) {
      for (const source of node.sources || []) {
        const candidates = sourceNodes.get(source.path) || [];
        const target = source.symbol
          ? candidates.find((entry) => entry.node.kind !== "variable" && (entry.symbol === source.symbol || entry.symbol.endsWith(`.${source.symbol}`)))
          : candidates.find((entry) => entry.symbol === "module" && entry.node.kind === "data");
        if (target) source.catalogId = target.node.id;
      }
      for (const child of node.children || []) connect(child);
    }
    for (const branch of build.branches) connect(branch);
    build.branches.push(inventory.root);
    build.meta.sourceCatalog = inventory.counts;
    build.meta.version = 2;
    build.meta.subtitle = "Explore the simulator, equations, and every declared source variable offline";
  }
  const root=build.N(build.root.id,build.root.title,build.root.kind,build.root.status,build.root.summary,build.root.extra,build.branches);
  window.LAPSIM_FLOWCHART_DATA={meta:build.meta,root};
  delete window.LAPSIM_FLOWCHART_BUILD;
})();
