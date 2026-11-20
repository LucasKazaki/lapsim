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


/* Pages projection: immutable public evidence URLs; original source paths/catalog bytes remain inspectable. */
(() => {
  "use strict";
  const sourceCommit = "6d6f355221c66047a83003ff6ccc8ccc63467c75";
  const directories = new Set([".github",".github/workflows",".vscode","analysis","analysis/accel","analysis/aero","analysis/archive","analysis/archive/docs","analysis/archive/scripts","analysis/archive/scripts/data_preparation","analysis/archive/scripts/data_preparation/imu","analysis/archive/scripts/data_preparation/lap","analysis/archive/scripts/data_preparation/telemetry","analysis/archive/scripts/data_preparation/track","analysis/archive/scripts/legacy","analysis/autox_corr","analysis/comp-scoring","analysis/controller_import","analysis/data","analysis/data/brakes","analysis/data/imu","analysis/data/lap","analysis/data/telemetry","analysis/data/track","analysis/endurance","analysis/events","analysis/native-bench-evidence","analysis/numerical_invariants","analysis/numerical_invariants/results","analysis/performance","analysis/tires","configs","configs/courses","configs/courses/upstream","configs/courses/upstream/amz-fssim","configs/team_specs","configs/torque_profiles","controller","controller/integration","controller/integration/upstream-originals","controller/integration/upstream-originals/reference","controller/reference","controller/reference/native","controller/research","controller/research/TC-03E-evidence","controller/research/TC-03G-evidence","controller/research/TC-03H-evidence","controller/research/TC-03I-evidence","controller/research/TC-03J-evidence","controller/research/TC-03J-evidence/accounting-repair-v1","controller/research/TC-03J-evidence/independent-auditor","controller/research/TC-03J-evidence/logs","controller/research/TC-03J-evidence/native-snapshot","controller/research/TC-03J-evidence/objects","controller/research/TC-03J-evidence/pre-call-review-v1","controller/research/TC-03J-evidence/windows-checkout-repair-v1","data","data/tires","docs","docs/evidence","docs/full-simulator","docs/future","docs/research","docs/research/evidence","docs/research/professional_racing","docs/simulator_flowchart","docs/simulator_flowchart/data","environments","firmware","firmware/bench","output","output/pdf","packaging","quality","research","research/light","research/light/awd-standing-v15","research/light/kernels","research/light/portable-core-candidate","research/light/portable-core-candidate/src","research/light/portable-core-candidate/src/lapsim_light_core","research/light/portable-course-inputs","research/light/public-light-wasd-gear-ab-20261119","research/light/public-light-wasd-gear-ab-20261119/drag91","research/light/public-light-wasd-gear-ab-20261119/drag91/data","research/light/public-light-wasd-gear-ab-20261119/drag91/src","research/light/public-light-wasd-gear-ab-20261119/drag91/src/ev_parent","research/light/public-light-wasd-gear-ab-20261119/drag91/src/lapsim","research/light/public-light-wasd-gear-ab-20261119/drag91/src/lapsim/core","research/light/public-light-wasd-gear-ab-20261119/drag91/src/lapsim/courses","research/light/public-light-wasd-gear-ab-20261119/drag91/src/lapsim/learning","research/light/public-light-wasd-gear-ab-20261119/drag91/src/lapsim/learning/live","research/light/public-light-wasd-gear-ab-20261119/drag91/src/lapsim_light_core","research/light/public-light-wasd-gear-ab-20261119/drag91/src/utils","research/light/public-light-wasd-gear-ab-20261119/drag96","research/light/public-light-wasd-gear-ab-20261119/drag96/data","research/light/public-light-wasd-gear-ab-20261119/drag96/src","research/light/public-light-wasd-gear-ab-20261119/drag96/src/ev_parent","research/light/public-light-wasd-gear-ab-20261119/drag96/src/lapsim","research/light/public-light-wasd-gear-ab-20261119/drag96/src/lapsim/core","research/light/public-light-wasd-gear-ab-20261119/drag96/src/lapsim/courses","research/light/public-light-wasd-gear-ab-20261119/drag96/src/lapsim/learning","research/light/public-light-wasd-gear-ab-20261119/drag96/src/lapsim/learning/live","research/light/public-light-wasd-gear-ab-20261119/drag96/src/lapsim_light_core","research/light/public-light-wasd-gear-ab-20261119/drag96/src/utils","research/light/public-light-wasd-gear-ab-20261119/manual","research/light/public-light-wasd-gear-ab-20261119/manual/data","research/light/public-light-wasd-gear-ab-20261119/manual/src","research/light/public-light-wasd-gear-ab-20261119/manual/src/lapsim","research/light/public-light-wasd-gear-ab-20261119/manual/src/lapsim/core","research/light/public-light-wasd-gear-ab-20261119/manual/src/lapsim/courses","research/light/public-light-wasd-gear-ab-20261119/manual/src/lapsim/learning","research/light/public-light-wasd-gear-ab-20261119/manual/src/lapsim/learning/live","research/light/public-light-wasd-gear-ab-20261119/manual/src/lapsim_light_core","research/light/public-light-wasd-gear-ab-20261119/manual/src/utils","scripts","src","src/lapsim","src/lapsim/backends","src/lapsim/core","src/lapsim/courses","src/lapsim/data","src/lapsim/dynamics","src/lapsim/events","src/lapsim/experiments","src/lapsim/optimization","src/lapsim/profiles","src/lapsim/solvers","src/lapsim/torque_configurator","src/lapsim/ui","src/utils","src/vehicle_model","src/vehicle_model/aero","src/vehicle_model/electrical","src/vehicle_model/mech","src/vehicle_model/powertrain","tests","tests/fixtures","web","web/examples","web/tournament-review","web/tournament-review/fixtures","web/vendor"]);
  const walk = node => {
    for (const source of node.sources || []) {
      const normalizedPath = String(source.path).replace(/\/+$/, "");
      const kind = directories.has(normalizedPath) ? "tree" : "blob";
      const anchor = kind === "blob" && Number.isInteger(source.line) && source.line > 0 ? "#L" + source.line : "";
      source.publicationHref = "https://github.com/LucasKazaki/lapsim/" + kind + "/" + sourceCommit + "/" + normalizedPath.split("/").map(encodeURIComponent).join("/") + anchor;
    }
    for (const child of node.children || []) walk(child);
  };
  walk(window.LAPSIM_FLOWCHART_DATA.root);
  window.LAPSIM_FLOWCHART_DATA.meta.publicationSourceCommit = sourceCommit;
})();
