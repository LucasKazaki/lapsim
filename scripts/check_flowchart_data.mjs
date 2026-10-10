#!/usr/bin/env node
/** Validate the assembled LapSim flowchart graph without a browser. */

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptDirectory, "..");
const siteRoot = path.join(repositoryRoot, "docs", "simulator_flowchart");
const dataScripts = [
  "data/core.js",
  "data/01-entrypoints.js",
  "data/02-inputs.js",
  "data/03-distance-pipeline.js",
  "data/04-vehicle-cell.js",
  "data/05-component-physics.js",
  "data/06-racing-line.js",
  "data/07-planar-model.js",
  "data/08-results.js",
  "data/09-verification.js",
  "data.js",
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const sandbox = { window: {} };
vm.createContext(sandbox);
for (const relativePath of dataScripts) {
  const absolutePath = path.join(siteRoot, relativePath);
  const source = fs.readFileSync(absolutePath, "utf8");
  vm.runInContext(source, sandbox, { filename: relativePath });
}

const data = sandbox.window.LAPSIM_FLOWCHART_DATA;
assert(data && data.root && data.meta, "Data scripts did not assemble LAPSIM_FLOWCHART_DATA.");
assert(data.root.id === "lapsim", `Unexpected root id: ${data.root.id}`);
assert(data.meta.repository === "LucasKazaki/lapsim", "Repository metadata is incorrect.");
assert(Array.isArray(data.root.children), "The root must contain top-level branches.");
assert(data.root.children.length === 9, `Expected 9 top-level branches, found ${data.root.children.length}.`);

const validStatuses = new Set([
  "implemented",
  "optional",
  "experimental",
  "assumption",
  "limitation",
  "future",
]);
const ids = new Set();
const relatedReferences = [];
const missingSources = new Map();
let nodeCount = 0;
let equationCount = 0;
let sourceCount = 0;
let deepestLevel = 0;
let emptySummaryCount = 0;

function validateStringArray(value, label, nodeId) {
  if (value === undefined) return;
  assert(Array.isArray(value), `${nodeId}.${label} must be an array.`);
  for (const item of value) {
    assert(typeof item === "string" && item.trim(), `${nodeId}.${label} contains an empty or non-string item.`);
  }
}

function recordMissingSource(nodeId, sourcePath) {
  if (!missingSources.has(sourcePath)) missingSources.set(sourcePath, []);
  missingSources.get(sourcePath).push(nodeId);
}

function visit(node, depth) {
  assert(node && typeof node === "object", "Every child must be a node object.");
  for (const field of ["id", "title", "kind", "status"]) {
    assert(typeof node[field] === "string" && node[field].trim(), `Node is missing ${field}: ${JSON.stringify(node)}`);
  }
  assert(typeof node.summary === "string", `Node ${node.id} must define summary as a string.`);
  if (!node.summary.trim()) emptySummaryCount += 1;
  assert(!ids.has(node.id), `Duplicate node id: ${node.id}`);
  assert(validStatuses.has(node.status), `Unknown status ${node.status} on ${node.id}.`);
  ids.add(node.id);
  nodeCount += 1;
  deepestLevel = Math.max(deepestLevel, depth);

  for (const field of ["inputs", "outputs", "equations", "assumptions", "related"]) {
    validateStringArray(node[field], field, node.id);
  }
  equationCount += (node.equations || []).length;
  for (const relatedId of node.related || []) relatedReferences.push([node.id, relatedId]);

  if (node.sources !== undefined) {
    assert(Array.isArray(node.sources), `${node.id}.sources must be an array.`);
    for (const source of node.sources) {
      assert(source && typeof source.path === "string" && source.path.trim(), `${node.id} has an invalid source entry.`);
      assert(!path.isAbsolute(source.path) && !source.path.includes(".."), `${node.id} source escapes the repository: ${source.path}`);
      const sourcePath = path.join(repositoryRoot, source.path);
      if (!fs.existsSync(sourcePath)) recordMissingSource(node.id, source.path);
      if (source.symbol !== undefined) {
        assert(typeof source.symbol === "string" && source.symbol.trim(), `${node.id} has an invalid source symbol.`);
      }
      sourceCount += 1;
    }
  }

  if (node.children !== undefined) {
    assert(Array.isArray(node.children), `${node.id}.children must be an array.`);
    for (const child of node.children) visit(child, depth + 1);
  }
}

visit(data.root, 0);
const unresolvedRelated = relatedReferences.filter(([, targetId]) => !ids.has(targetId));
assert(
  unresolvedRelated.length === 0,
  "Unresolved related-node references: " +
    unresolvedRelated.map(([sourceId, targetId]) => `${sourceId} -> ${targetId}`).join(", "),
);
for (const [sourceId, targetId] of relatedReferences) {
  assert(sourceId !== targetId, `${sourceId} cannot relate to itself.`);
}
assert(
  missingSources.size === 0,
  "Missing repository source paths: " +
    [...missingSources.entries()]
      .map(([sourcePath, nodeIds]) => `${sourcePath} (nodes: ${nodeIds.join(", ")})`)
      .join("; "),
);

assert(nodeCount >= 50, `The map unexpectedly shrank to ${nodeCount} nodes.`);
assert(equationCount >= 25, `The map unexpectedly shrank to ${equationCount} equation/logic entries.`);
assert(sourceCount >= 40, `The map unexpectedly shrank to ${sourceCount} source references.`);
assert(deepestLevel >= 4, `The map no longer reaches equation-level depth (depth=${deepestLevel}).`);

console.log(
  JSON.stringify(
    {
      nodes: nodeCount,
      equations: equationCount,
      sources: sourceCount,
      relatedReferences: relatedReferences.length,
      maximumDepth: deepestLevel,
      topLevelBranches: data.root.children.length,
      emptySummaries: emptySummaryCount,
    },
    null,
    2,
  ),
);
