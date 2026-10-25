"""Gate: undefined names across the whole tree, star imports resolved statically.

Why this exists: ruff F821/F405 is globally ignored for F405 (see pyproject
[tool.ruff.lint] ignore) because the repo's data-bundle star imports
(module/*/assets.py, utils_assets.py) have ~2800 legitimate usage sites that
ruff cannot resolve, so plain `ruff --select F405` drowns in false positives.
That hole shipped a real bug: upstream a722482b swapped a call to color_mask()
inside module/map_detection/grid_predictor.py, whose Joxos-style explicit
import list (56580edb) was never extended - the merge was textually clean and
the NameError only fired at runtime (2026-10-25, opsi_month_boss crash).

Approach: take ruff's F821/F405 findings, then statically resolve the real
top-level exports of every `from X import *` source of the reporting file
(recursively through chained star imports, honouring __all__ and underscore
privacy). A name that exists in any source's exports is legitimate data-bundle
usage; a name that exists nowhere is a confirmed undefined name and fails the
gate. F821 (no star-import context) is always a violation.

Usage:
    python dev_tools/check_undefined_names.py [-v]

Exit code 0 if clean, 1 if any confirmed undefined name (or ruff itself
fails). Scope note: ruff's extend-exclude (campaign/config/submodule) applies,
matching the other python-side gates.
"""

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# `color_mask` may be undefined, or defined from star imports: module.x.y
_NAME_RE = re.compile(r"^`([^`]+)`")


def resolve_module_path(spec: str, relative_to: Path | None = None) -> Path | None:
    """Map a dotted module spec to its file, following import semantics.

    Absolute specs resolve against ROOT; leading dots resolve relative to
    `relative_to`'s package directory. Returns the .py file, the package
    __init__.py, or None when unresolvable (dynamic sys.path tricks etc.).
    """
    if spec.startswith("."):
        if relative_to is None:
            return None
        depth = len(spec) - len(spec.lstrip("."))
        tail = spec.lstrip(".")
        base = relative_to.parent
        for _ in range(depth - 1):
            base = base.parent
        parts = [p for p in base.parts + tuple(tail.split(".")) if p]
        candidate_root = Path(*parts)
    else:
        candidate_root = ROOT.joinpath(*spec.split("."))

    file = candidate_root.with_suffix(".py")
    if file.is_file():
        return file
    init = candidate_root / "__init__.py"
    if init.is_file():
        return init
    return None


def module_exports(path: Path, _cache: dict | None = None, _visiting: frozenset | None = None) -> set[str]:
    """Static export set of a module: star-import-visible top-level names.

    __all__ wins when it is a static list/tuple of strings; otherwise every
    top-level binding (including names re-exported through the module's own
    star imports) minus underscore-private names.
    """
    if _cache is None:
        _cache = {}
    key = str(path)
    if key in _cache:
        return _cache[key]
    if _visiting is None:
        _visiting = frozenset()
    if key in _visiting or not path.is_file():
        return set()
    _visiting = _visiting | {key}

    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    all_names: list[str] | None = None
    star_sources: list[str] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for n in ast.walk(target):
                    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                        names.add(n.id)
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
                try:
                    all_names = [elt.value for elt in node.value.elts]  # type: ignore[attr-defined]
                except AttributeError:
                    all_names = None  # dynamic __all__, fall back to binding scan
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    star_sources.append(node.module or "")
                else:
                    names.add(alias.asname or alias.name)

    if all_names is not None:
        exports = set(all_names)
    else:
        exports = names
        for spec in star_sources:
            src = resolve_module_path(spec, relative_to=path)
            if src is not None:
                exports |= module_exports(src, _cache, _visiting)
        exports = {n for n in exports if not n.startswith("_")}

    _cache[key] = exports
    return exports


def file_star_sources(path: Path) -> list[Path | None]:
    """Star import sources of a file, as resolved paths (None = unresolved)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    sources: list[Path | None] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            level = node.level or 0
            spec = "." * level + (node.module or "")
            sources.append(resolve_module_path(spec, relative_to=path))
    return sources


def run_ruff() -> list[dict]:
    ruff = shutil.which("ruff")  # under `uv run` the venv bin dir leads PATH
    if ruff is None:
        venv_ruff = Path(sys.executable).parent / "ruff"
        ruff = str(venv_ruff) if venv_ruff.is_file() else None
    if ruff is None:
        print("ruff not found in PATH or next to the interpreter", file=sys.stderr)
        raise SystemExit(1)
    proc = subprocess.run(
        [ruff, "check", ".", "--select", "F821,F405",
         "--output-format", "json", "--no-cache", "--exit-zero"],
        cwd=ROOT, capture_output=True, text=True,
    )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(proc.stdout or proc.stderr, file=sys.stderr)
        raise SystemExit(1)


def _rel(path: Path) -> str:
    """Path for messages; tolerant of paths outside ROOT (unit-test trees)."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def classify(findings: list[dict]) -> tuple[list[dict], int, int]:
    """Split ruff findings into (violations, legit_star_uses, unresolved_sources)."""
    cache: dict = {}
    violations: list[dict] = []
    legit = 0
    unresolved = 0
    for finding in findings:
        path = Path(finding["filename"])
        m = _NAME_RE.match(finding["message"])
        name = m.group(1) if m else finding["message"].split("'")[0]
        if finding["code"] == "F821":
            violations.append({"file": path, "row": finding["location"]["row"], "name": name, "why": "no star import can supply it"})
            continue
        # F405: legal iff any star source actually exports the name.
        exports: set[str] = set()
        saw_unresolved = False
        for src in file_star_sources(path):
            if src is None:
                saw_unresolved = True
                unresolved += 1
                continue
            exports |= module_exports(src, cache)
        if name in exports:
            legit += 1
        elif saw_unresolved:
            # Conservative: a source we cannot read might have supplied it.
            legit += 1
        else:
            violations.append({
                "file": path, "row": finding["location"]["row"], "name": name,
                "why": "not defined or imported here, and absent from every star-import source: "
                       + ", ".join(_rel(s) for s in file_star_sources(path) if s is not None),
            })
    return violations, legit, unresolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print per-file statistics for legit star-import uses")
    args = parser.parse_args()

    findings = run_ruff()
    violations, legit, unresolved = classify(findings)

    if args.verbose:
        print(f"ruff findings: {len(findings)} (legit star-import uses: {legit}, unresolved sources: {unresolved})")
    if unresolved:
        print(f"warning: {unresolved} star-import source(s) could not be resolved statically; "
              "their usage sites were conservatively allowed", file=sys.stderr)

    for v in violations:
        loc = f"{v['file'].relative_to(ROOT)}:{v['row']}"
        print(f"undefined name `{v['name']}` at {loc} — {v['why']}")

    if violations:
        print(f"\n{len(violations)} confirmed undefined name(s). These pass textual merge and "
              "import smoke (function bodies only run at runtime) — fix before pushing.")
        return 1
    print(f"OK: no undefined names ({legit} legitimate star-import uses checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
