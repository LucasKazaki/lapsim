/* Assemble all branch files into the viewer's public data object. */
(() => {
  "use strict";
  const build=window.LAPSIM_FLOWCHART_BUILD;
  const root=build.N(build.root.id,build.root.title,build.root.kind,build.root.status,build.root.summary,build.root.extra,build.branches);
  window.LAPSIM_FLOWCHART_DATA={meta:build.meta,root};
  delete window.LAPSIM_FLOWCHART_BUILD;
})();
