"""Cross-check the offline map against the Python source it documents."""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MAP = REPO / "docs" / "simulator_flowchart"
spec = importlib.util.spec_from_file_location("flowchart_inventory", MAP / "generate_inventory.py")
inventory_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory_module)


def walk(node):
    yield node
    for child in node.get("children", []):
        yield from walk(child)


@pytest.fixture(scope="module")
def inventory():
    return inventory_module.build_catalog()


def test_source_catalog_is_current(inventory):
    assert inventory_module.TARGET.read_text(encoding="utf-8") == inventory_module.serialize(inventory), (
        "Source catalog is stale; run python docs/simulator_flowchart/generate_inventory.py"
    )


def test_source_catalog_covers_all_modules_declarations_and_exact_expressions(inventory):
    files = sorted([*(REPO / "src").rglob("*.py"), *(REPO / "web").glob("*.py")])
    assert inventory["counts"]["modules"] == len(files)
    assert {item["path"] for item in inventory["sources"]} == {file.relative_to(REPO).as_posix() for file in files}
    nodes = list(walk(inventory["root"]))
    recorded = {
        (node["sources"][0]["path"], expression["line"], expression["text"])
        for node in nodes
        for expression in node.get("expressions", [])
    }
    function_count = 0
    for file in files:
        path = file.relative_to(REPO).as_posix()
        text = file.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
        for item in ast.walk(ast.parse(text)):
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_count += 1
            if isinstance(item, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                assert (path, item.lineno, ast.get_source_segment(text, item)) in recorded, (path, item.lineno)
            if isinstance(item, (ast.If, ast.While)):
                assert (path, item.test.lineno, ast.get_source_segment(text, item.test)) in recorded, (path, item.lineno)
            if isinstance(item, ast.Return) and item.value:
                assert (path, item.lineno, ast.get_source_segment(text, item)) in recorded, (path, item.lineno)
    assert inventory["counts"]["solver"] == function_count


def test_units_do_not_guess_unknown_quantities():
    unit = inventory_module.unit_metadata
    assert unit("normal_load_n")["unit"] == "N"
    assert unit("air_density_kgpm3")["unit"] == "kg/m³"
    assert unit("curvature_per_m")["unit"] == "1/m"
    assert unit("yaw_inertia_kg_m2")["unit"] == "kg·m²"
    assert unit("enabled", "bool")["unit"] == "boolean"
    for name in ("r", "q", "arbitrary", "matrix", "values"):
        assert unit(name)["unit"] == "not declared"


def test_offline_map_integrity_and_equation_disclosure():
    node_exe = shutil.which("node")
    if node_exe is None:
        pytest.skip("Node.js is needed only for map-data integrity, not the simulator")
    scripts = re.findall(r'<script src="([^"]+)"', (MAP / "index.html").read_text(encoding="utf-8"))
    assert all(not script.startswith(("http:", "https:")) for script in scripts)
    code = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert'), path = require('path');
const directory = process.argv[1], scripts = JSON.parse(process.argv[2]);
const context = vm.createContext({window: {}});
for (const script of scripts.filter(p => p !== 'app.js')) vm.runInContext(fs.readFileSync(path.join(directory, script), 'utf8'), context, {filename:script});
const root = context.window.LAPSIM_FLOWCHART_DATA.root, nodes = [];
function visit(n) {nodes.push(n); for(const child of n.children || []) visit(child);}
visit(root);
const ids = new Set();
for (const n of nodes) {assert(n.id && n.title && n.kind && n.status); assert(!ids.has(n.id), `Duplicate id ${n.id}`); ids.add(n.id);}
for (const n of nodes) {
  for (const id of n.related || []) assert(ids.has(id), `Missing related id ${id}`);
  for (const source of n.sources || []) {
    assert(fs.existsSync(path.join(directory, '../..', source.path)), `Missing source ${source.path}`);
    if(source.catalogId) assert(ids.has(source.catalogId));
  }
  if(n.equations && n.equations.length && !/-eq-\d+$/.test(n.id)) {
    assert((n.children || []).some(child => child.id.startsWith(n.id+'-eq-')), `No equation disclosure in ${n.id}`);
  }
}
const find = id => nodes.find(n => n.id===id);
assert(find('aero-pressure-eq-1').children.some(n=>n.variable.name==='rho' && n.variable.unit==='kg/m\u00b3'));
assert(find('planar-slip-eq-2').children.some(n=>n.variable.name==='kappa' && n.variable.unit==='dimensionless'));
assert(find('battery-current-root').equations.some(e=>e.includes('2*P_request')));
assert(!find('rl-objective-eq-2').children.some(n=>n.variable.name==='m'));
assert(find('rl-audit-bound-eq-2').children.some(n=>n.variable.name==='r' && n.variable.unit==='m'));
assert(find('source-catalog').children.length >= 77);
console.log(JSON.stringify({nodes:nodes.length, variables:nodes.filter(n=>n.kind==='variable').length}));
"""
    result = subprocess.run([node_exe, "-e", code, str(MAP), json.dumps(scripts)], text=True, encoding="utf-8", capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["variables"] > 6000
