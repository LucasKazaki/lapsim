"""Build an offline, source-exact catalog without importing simulator modules.

Run from any directory: python docs/simulator_flowchart/generate_inventory.py
Use --check in CI to reject a stale catalog after source edits.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import Counter, OrderedDict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGET = Path(__file__).parent / "data" / "source-inventory.js"

# A suffix is evidence about the author's naming convention, not dimensional
# analysis. Unknown names deliberately receive no guessed physical unit.
UNIT_SUFFIXES = (
    ("_kgpm3", "kg/m³"), ("_n_per_psi", "N/psi"), ("_nm_per_psi", "N·m/psi"),
    ("_n_per_rad", "N/rad"), ("_nm_per_rad", "N·m/rad"), ("_nm_per_deg", "N·m/°"),
    ("_kg_m2", "kg·m²"), ("_radps2", "rad/s²"), ("_radps", "rad/s"),
    ("_rad_s", "rad/s"), ("_mps2", "m/s²"), ("_per_m", "1/m"),
    ("_mps", "m/s"), ("_kwh", "kWh"), ("_wh", "Wh"), ("_ah", "Ah"),
    ("_ohm", "Ω"), ("_rpm", "rev/min"), ("_psi", "psi"), ("_pa", "Pa"),
    ("_nm", "N·m"), ("_m2", "m²"), ("_kg", "kg"), ("_rad", "rad"),
    ("_deg", "°"), ("_n", "N"), ("_w", "W"), ("_v", "V"),
    ("_a", "A"), ("_s", "s"), ("_m", "m"),
)


def unit_metadata(name: str, annotation: str = "") -> dict:
    lower = name.rsplit(".", 1)[-1].lower()
    if annotation == "bool":
        return {"unit": "boolean", "unitEvidence": "Declared Python type"}
    for suffix, unit in UNIT_SUFFIXES:
        if lower.endswith(suffix):
            return {"unit": unit, "unitEvidence": f"Source naming convention: {suffix}; not independently inferred from the expression"}
    if "capacitance" in lower and lower.endswith("_f"):
        return {"unit": "F", "unitEvidence": "Capacitance name and _f suffix"}
    if lower.endswith(("_fraction", "_multiplier", "_ratio", "_coefficient", "_scale")) or lower in {"state_of_charge", "initial_state_of_charge"}:
        return {"unit": "dimensionless", "unitEvidence": "Source naming convention; verify the model context"}
    return {"unit": "not declared", "unitEvidence": "No dimensional claim: inspect its type, exact expression, and enclosing function"}


def ident(path: str, scope: str, label: str, line: int = 0) -> str:
    token = f"{path}:{scope}:{label}:{line}".encode()
    return "code-" + hashlib.sha256(token).hexdigest()[:18]


def refs(expression: ast.AST | None) -> list[str]:
    if expression is None:
        return []
    found = set()
    for node in ast.walk(expression):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            found.add(ast.unparse(node))
    # Keep a full attribute instead of both self and self.field. Calls remain
    # visible as code dependencies; they are not called physical quantities.
    return sorted(name for name in found if not any(other.startswith(name + ".") for other in found))


def targets(target: ast.AST) -> list[str]:
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for item in target.elts for name in targets(item)]
    if isinstance(target, ast.Starred):
        return targets(target.value)
    return [ast.unparse(target)]


class Catalog:
    def __init__(self, path: str, source: str):
        self.path, self.source = path, source
        self.counts = Counter()
        self.bindings: dict[tuple[str, str], str] = {}

    def node(self, scope: str, label: str, kind: str, summary: str, line: int = 0, **extra) -> dict:
        self.counts[kind] += 1
        return {"id": ident(self.path, scope, label, line), "title": label, "kind": kind,
                "status": "implemented", "summary": summary,
                "sources": [{"path": self.path, "symbol": scope or "module", "line": line or 1}], **extra}

    def snippet(self, node: ast.AST) -> str:
        return ast.get_source_segment(self.source, node) or ast.unparse(node)

    def scope(self, body: list[ast.stmt], scope: str, parameters: list[dict] | None = None) -> list[dict]:
        variables: OrderedDict[str, dict] = OrderedDict()
        equations = []
        nested = []
        for param in parameters or []:
            variables[param["name"]] = param

        def bind(name, statement, annotation="", role="local binding", value=None):
            variable = variables.setdefault(name, {"name": name, "annotation": annotation, "role": role, "line": statement.lineno, "expressions": [], "dependencies": []})
            if annotation:
                variable["annotation"] = annotation
            variable["expressions"].append({"line": statement.lineno, "text": self.snippet(statement)})
            variable["dependencies"] += refs(value)

        def walk(statement):
            if isinstance(statement, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                nested.append(self.definition(statement, scope))
                return
            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    for name in targets(target):
                        bind(name, statement, role="field/constant" if not scope or scope.endswith("[class]") else "local binding", value=statement.value)
            elif isinstance(statement, ast.AnnAssign):
                bind(ast.unparse(statement.target), statement, ast.unparse(statement.annotation),
                     "field/constant" if not scope or scope.endswith("[class]") else "local binding", statement.value)
            elif isinstance(statement, ast.AugAssign):
                bind(ast.unparse(statement.target), statement, value=statement.value)
            elif isinstance(statement, (ast.For, ast.AsyncFor)):
                for name in targets(statement.target):
                    bind(name, statement.target, role="iteration binding", value=statement.iter)
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                for item in statement.items:
                    if item.optional_vars:
                        for name in targets(item.optional_vars):
                            bind(name, item.optional_vars, role="context binding", value=item.context_expr)
            elif isinstance(statement, ast.ExceptHandler) and statement.name:
                bind(statement.name, statement, role="exception binding")
            if isinstance(statement, ast.Return) and statement.value:
                equations.append(self.expression(statement, scope, "Return expression", statement.value))
            elif isinstance(statement, (ast.If, ast.While)):
                equations.append(self.expression(statement.test, scope, "Decision / bound", statement.test))
            # Nested defs own their bodies. All control blocks remain in this scope.
            for field in ("body", "orelse", "finalbody", "handlers", "cases"):
                for child in getattr(statement, field, []):
                    if isinstance(child, ast.match_case):
                        for item in child.body:
                            walk(item)
                    elif isinstance(child, (ast.stmt, ast.ExceptHandler)):
                        walk(child)

        for statement in body:
            walk(statement)

        variable_nodes = []
        for name, item in variables.items():
            line = item["line"]
            annotation = item.get("annotation", "")
            node = self.node(scope, name, "variable", f"{item['role'].capitalize()} in {scope or 'module'}. Meaning follows the source name and enclosing documentation; expressions below are exact source text.", line,
                             variable={"name": name, "meaning": name.replace("_", " "), "type": annotation or "not annotated", "role": item["role"], **unit_metadata(name, annotation)},
                             expressions=item.get("expressions", []), dependencies=sorted(set(item.get("dependencies", []))))
            if "default" in item:
                node["variable"]["default"] = item["default"]
            self.bindings[(scope, name)] = node["id"]
            variable_nodes.append(node)

        children = []
        if variable_nodes:
            children.append(self.node(scope, "Individual variables", "data", "Parameters, declared fields, constants, and assignment/iteration/context bindings. Every variable exposes type, unit evidence, default or defining expressions, and line references.", variable_nodes[0]["sources"][0]["line"], children=variable_nodes))
        if equations:
            children.append(self.node(scope, "Returns and decisions", "equation", "Exact return expressions and branch/loop bounds, including numerical guards. Assignment expressions appear under the variable they define.", equations[0]["sources"][0]["line"], children=equations))
        return children + nested

    def expression(self, statement, scope, label, expression):
        return self.node(scope, f"{label} · line {statement.lineno}", "equation", "Exact Python source. This may be numerical logic, a guard, or data handling rather than a physical equation.", statement.lineno,
                         expressions=[{"line": statement.lineno, "text": self.snippet(statement)}], dependencies=refs(expression))

    def definition(self, definition, parent):
        label = definition.name
        scope = f"{parent}.{label}".strip(".")
        if isinstance(definition, ast.ClassDef):
            scope += "[class]"
            children = self.scope(definition.body, scope)
            kind = "data"
        else:
            args = definition.args
            defaults = [None] * (len(args.posonlyargs + args.args) - len(args.defaults)) + list(args.defaults)
            params = []
            for argument, default in zip(args.posonlyargs + args.args + args.kwonlyargs, defaults + args.kw_defaults):
                if argument.arg in {"self", "cls"}:
                    continue
                item = {"name": argument.arg, "annotation": ast.unparse(argument.annotation) if argument.annotation else "", "role": "parameter", "line": argument.lineno, "expressions": [], "dependencies": []}
                if default is not None:
                    item["default"] = ast.unparse(default)
                params.append(item)
            for argument in (args.vararg, args.kwarg):
                if argument:
                    params.append({"name": argument.arg, "annotation": ast.unparse(argument.annotation) if argument.annotation else "", "role": "variadic parameter", "line": argument.lineno, "expressions": [], "dependencies": []})
            children = self.scope(definition.body, scope, params)
            kind = "solver"
        doc = ast.get_docstring(definition) or "No source docstring; inspect the declaration and exact definitions below."
        return self.node(scope, label, kind, doc, definition.lineno,
                         declaration=self.source.splitlines()[definition.lineno - 1].strip(), children=children)


def source_files() -> list[Path]:
    return sorted([*(REPO / "src").rglob("*.py"), *(REPO / "web").glob("*.py")])


def build_catalog() -> dict:
    modules, counts, sources = [], Counter(), []
    for file in source_files():
        path = file.relative_to(REPO).as_posix()
        raw = file.read_bytes()
        # Git checkouts may use LF or CRLF on different systems. Normalize only
        # line endings/BOM so identical source produces an identical catalog.
        text = raw.decode("utf-8-sig").replace("\r\n", "\n")
        tree = ast.parse(text, filename=path)
        catalog = Catalog(path, text)
        children = catalog.scope(tree.body, "")
        modules.append(catalog.node("", path.removeprefix("src/"), "data", ast.get_docstring(tree) or "Python module. Expand declarations and individual bindings below.", children=children))
        counts.update(catalog.counts)
        sources.append({"path": path, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
    return {"version": 1, "counts": {"modules": len(modules), **dict(counts)}, "sources": sources,
            "root": {"id": "source-catalog", "title": "Source variables and exact expressions", "kind": "data", "status": "implemented",
                     "summary": "Generated directly from every Python model module under src/ and the browser bridge under web/. Expand a module, class or function to inspect individual variables, exact assignments, returns, and decision bounds. This static catalog complements the curated physics map; it does not validate the model or infer undocumented units.",
                     "assumptions": ["Units are declared naming/type evidence, not automatic dimensional analysis. Unknown units are marked not declared.", "Expressions are source text; Python ** means exponentiation. Numerical decisions and data expressions are not automatically physical laws.", "Static declarations cannot enumerate dynamically created runtime dictionary keys, array elements, or attributes. Indexed bindings remain explicit source expressions.", "Imports, comprehension-internal bindings, and anonymous lambda parameters are visible within expressions but are not separate declaration nodes."],
                     "children": modules}}


def serialize(catalog: dict) -> str:
    return "/* Generated by generate_inventory.py; do not edit. Source SHA-256 checks enforce freshness. */\nwindow.LAPSIM_SOURCE_INVENTORY = " + json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + ";\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    catalog = build_catalog()
    content = serialize(catalog)
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            print("Source inventory is stale. Run generate_inventory.py after source edits.")
            return 1
    else:
        TARGET.write_text(content, encoding="utf-8", newline="\n")
    print(json.dumps(catalog["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
