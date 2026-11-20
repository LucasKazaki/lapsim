/* Source-only publication checks. Runs in GitHub Actions, never a simulator. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const vm = require("node:vm");
const {execFileSync} = require("node:child_process");
const root = path.resolve(__dirname, "..");
const source = path.join(root, ".r11-reviewed-source");
const manifest = JSON.parse(fs.readFileSync(path.join(root, "map-publication.json"), "utf8"));
const pinned = "6d6f355221c66047a83003ff6ccc8ccc63467c75";
const base = "0b301109921857bbbffbf23411831bfd634415b8";
const prefix = "docs/simulator_flowchart/";
const git = (...args) => execFileSync("git", args, {cwd:root,encoding:"utf8",maxBuffer:8*1024*1024}).trim();
const blob = bytes => crypto.createHash("sha1").update(Buffer.from("blob "+bytes.length+"\0")).update(bytes).digest("hex");
const sha256 = bytes => crypto.createHash("sha256").update(bytes).digest("hex");
assert.equal(manifest.schema, "lapsim.static-map-publication.v1");
assert.equal(manifest.sourceCommit,pinned);
assert.equal(manifest.integrationBase,base);
assert.equal(manifest.runtime.length,26);
assert.equal(new Set(manifest.runtime.map(x=>x.path)).size,26);
assert.equal(execFileSync("git",["rev-parse","HEAD"],{cwd:source,encoding:"utf8"}).trim(),pinned);
git("merge-base","--is-ancestor",base,"HEAD");
const allowed = new Set([...manifest.runtime.map(x=>prefix+x.path), ...manifest.auxiliaryChangedPaths]);
const changed = git("diff","--name-only",base,"HEAD").split("\n").filter(Boolean);
for (const file of changed) assert(allowed.has(file),"Unexpected changed path outside publication allowlist: "+file);
assert(!changed.some(x=>x.startsWith("tournament/")),"R11 projection must remain unchanged");
const stage = path.join(root,"audit","map-runtime");
assert(!fs.existsSync(stage),"Refuse to mix a previous staged artifact");
fs.mkdirSync(stage,{recursive:true});
const receipt = {schema:"lapsim.static-map-source-receipt.v1",sourceCommit:pinned,
  integrationBase:base,checkoutCommit:git("rev-parse","HEAD"),changedPaths:changed,
  runtimeAssetCount:manifest.runtime.length,sourceBytes:0,publishedBytes:0,assets:[]};
for (const entry of manifest.runtime) {
  assert(!entry.path.includes("..") && !path.isAbsolute(entry.path),"Unsafe runtime path");
  const original = fs.readFileSync(path.join(source,prefix,entry.path));
  const published = fs.readFileSync(path.join(root,prefix,entry.path));
  assert.equal(blob(original),entry.sourceGitBlob,"Source identity mismatch: "+entry.path);
  assert.equal(original.length,entry.sourceBytes);
  assert.equal(blob(published),entry.publishedGitBlob,"Published identity mismatch: "+entry.path);
  assert.equal(published.length,entry.publishedBytes);
  if (!manifest.projectionChangedRuntime.includes(entry.path)) assert(original.equals(published),"Unexplained runtime transformation");
  if (entry.path === "data/source-inventory.js") {
    assert.equal(entry.sourceGitBlob,"11ab6ad104dc4d9fbfecad2f3b6fc2c4ff076288");
    assert(original.equals(published),"Generated source inventory must remain byte-identical");
  }
  const target = path.join(stage,entry.path);
  fs.mkdirSync(path.dirname(target),{recursive:true});
  fs.writeFileSync(target,published,{flag:"wx"});
  receipt.sourceBytes += original.length; receipt.publishedBytes += published.length;
  receipt.assets.push({...entry,sha256:sha256(published)});
}
function walk(directory) {
  return fs.readdirSync(directory,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(directory,e.name)):[path.relative(stage,path.join(directory,e.name)).split(path.sep).join("/")]);
}
assert.deepEqual(walk(stage).sort(),manifest.runtime.map(x=>x.path).sort());
assert.equal(receipt.sourceBytes,11930557);
let pinnedDocumentLinks=0;
function checkDocumentHref(href) {
  if (href.startsWith("#")) return;
  if (!href.startsWith("https://github.com/LucasKazaki/lapsim/")) return;
  const url=new URL(href);
  const expectedPrefix="/LucasKazaki/lapsim/blob/"+pinned+"/";
  const treePrefix="/LucasKazaki/lapsim/tree/"+pinned+"/";
  assert(url.pathname.startsWith(expectedPrefix) || url.pathname.startsWith(treePrefix),"Unpinned repository evidence: "+href);
  const relative=decodeURIComponent(url.pathname.slice(url.pathname.startsWith(expectedPrefix)?expectedPrefix.length:treePrefix.length));
  const target=path.join(source,relative);
  assert(fs.existsSync(target),"Missing pinned document/source link: "+href);
  const isDirectory=fs.statSync(target).isDirectory();
  assert.equal(url.pathname.startsWith(treePrefix),isDirectory,"Wrong blob/tree evidence link: "+href);
  pinnedDocumentLinks++;
}
const html=fs.readFileSync(path.join(stage,"index.html"),"utf8");
for (const match of html.matchAll(/<a\b[^>]*\bhref="([^"]+)"/g)) {
  const href=match[1];
  if (!href.startsWith("#") && !/^https?:\/\//.test(href))
    assert(["../../","../../tournament/"].includes(href),"Unexpected local document/source link: "+href);
  checkDocumentHref(href);
}
const sandbox={window:{}};
vm.createContext(sandbox);
for(const file of ["anatomy-lap-data.js","anatomy-car-data.js"])
  vm.runInContext(fs.readFileSync(path.join(stage,file),"utf8"),sandbox,{filename:file,timeout:5000});
for(const catalog of [sandbox.window.LAP_ANATOMY_CATALOG,sandbox.window.CAR_ANATOMY_CATALOG])
  for(const entry of Object.values(catalog))
    for(const [,href] of entry.links)
      checkDocumentHref(href.startsWith("#") || /^https?:\/\//.test(href)?href:new URL(href,"https://github.com/LucasKazaki/lapsim/blob/"+pinned+"/docs/simulator_flowchart/").href);
receipt.pinnedDocumentLinks=pinnedDocumentLinks;
fs.writeFileSync(path.join(root,"audit","map-publication-source.json"),JSON.stringify(receipt,null,2)+"\n");
console.log(JSON.stringify({...receipt,assets:receipt.assets.map(x=>({path:x.path,sha256:x.sha256}))},null,2));
