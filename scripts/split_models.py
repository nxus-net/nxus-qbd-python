#!/usr/bin/env python3
"""
Split a single-file datamodel-codegen output into per-tag modules.

Reads:
    spec/openapi.json           — to learn which schemas belong to which tag
    nxus_qbd/models/_preview    — single-file generated Pydantic models

Writes:
    nxus_qbd/models/<tag>.py    — one module per OpenAPI tag
    nxus_qbd/models/_shared.py  — schemas referenced by 2+ tags
    nxus_qbd/models/__init__.py — re-exports every public class
"""

from __future__ import annotations

import ast
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPEC = REPO / "spec" / "openapi.json"
SOURCE = REPO / "nxus_qbd" / "models" / "_preview"
OUT_DIR = REPO / "nxus_qbd" / "models"
CORE_DIR = OUT_DIR / "core"
QBD_DIR = OUT_DIR / "qbd"
DATETIME_HELPER = OUT_DIR / "_datetime.py"

# Tags that live under models/core/ (platform/connection/auth), not QBD resources.
CORE_TAGS = {"Connections", "AuthSession", "QwcAuthSetup"}


import keyword


def tag_to_module(tag: str) -> str:
    """Convert 'VendorCredit' → 'vendor_credit'. Suffix Python keywords with '_'."""
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", tag).lower()
    if keyword.iskeyword(s):
        s = s + "_"
    return s


def collect_schema_refs(node, out: set[str]) -> None:
    """Walk a JSON object collecting every $ref schema name."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            out.add(ref.rsplit("/", 1)[-1])
        for v in node.values():
            collect_schema_refs(v, out)
    elif isinstance(node, list):
        for v in node:
            collect_schema_refs(v, out)


def transitive_refs(seed: set[str], schemas: dict) -> set[str]:
    """Expand a set of schema names to include everything they reference."""
    seen: set[str] = set()
    stack = list(seed)
    while stack:
        name = stack.pop()
        if name in seen or name not in schemas:
            continue
        seen.add(name)
        refs: set[str] = set()
        collect_schema_refs(schemas[name], refs)
        stack.extend(refs - seen)
    return seen


def build_tag_index(spec: dict) -> dict[str, set[str]]:
    """For each tag, return the set of schemas (transitively) used by its operations."""
    schemas = spec.get("components", {}).get("schemas", {})
    tag_to_schemas: dict[str, set[str]] = defaultdict(set)
    for path, ops in spec.get("paths", {}).items():
        if not isinstance(ops, dict):
            continue
        for method, op in ops.items():
            if not isinstance(op, dict):
                continue
            tags = op.get("tags") or []
            seed: set[str] = set()
            collect_schema_refs(op, seed)
            for t in tags:
                tag_to_schemas[t].update(seed)
    # Expand transitively
    return {t: transitive_refs(s, schemas) for t, s in tag_to_schemas.items()}


def parse_classes(source_file: Path) -> tuple[list[ast.stmt], dict[str, ast.stmt], list[ast.stmt]]:
    """Parse the generated file and split into (header_stmts, class_map, alias_stmts).

    header_stmts = imports + future + module docstring
    class_map    = class name → ClassDef node
    alias_stmts  = top-level type aliases / Annotated assignments
    """
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    header: list[ast.stmt] = []
    classes: dict[str, ast.stmt] = {}
    aliases: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            header.append(node)
        elif isinstance(node, ast.ClassDef):
            classes[node.name] = node
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            # module docstring
            header.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            aliases.append(node)
        else:
            # Skip trailing model_rebuild() calls etc. — we regenerate those
            # per-module after split, so any expression statements at module
            # level that reference class names are dropped.
            continue
    return header, classes, aliases


def class_dependencies(cls: ast.ClassDef, all_names: set[str]) -> set[str]:
    """Find every other class name this class references in its body."""
    deps: set[str] = set()
    for n in ast.walk(cls):
        if isinstance(n, ast.Name) and n.id in all_names and n.id != cls.name:
            deps.add(n.id)
    return deps


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"Source file not found: {SOURCE}")
    if not SPEC.exists():
        raise SystemExit(f"Spec not found: {SPEC}")

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    tag_index = build_tag_index(spec)
    print(f"Loaded {len(tag_index)} tags from spec")

    header, classes, aliases = parse_classes(SOURCE)
    all_class_names = set(classes.keys())
    print(f"Parsed {len(classes)} classes from {SOURCE.name}")

    # Map: schema name (from spec) → which tags use it
    schema_to_tags: dict[str, set[str]] = defaultdict(set)
    for tag, schema_set in tag_index.items():
        for s in schema_set:
            schema_to_tags[s].add(tag)

    # Each class gets a (package, module) target.
    #   package ∈ {"core", "qbd", ""}  — "" means top-level (_shared only)
    #   module  = file stem (e.g. "vendor", "_shared")
    #
    # Rules:
    #   - Used by exactly 1 tag → goes in that tag's package/module
    #   - Used by 2+ tags (or by zero) → goes in top-level _shared.py
    assignments: dict[str, tuple[str, str]] = {}
    class_tag_sets: dict[str, set[str]] = {}
    for class_name in all_class_names:
        tags = schema_to_tags.get(class_name, set())
        class_tag_sets[class_name] = tags
        if len(tags) == 1:
            tag = next(iter(tags))
            pkg = "core" if tag in CORE_TAGS else "qbd"
            assignments[class_name] = (pkg, tag_to_module(tag))
        else:
            assignments[class_name] = ("", "_shared")

    # Some helper/page models are not directly referenced by operations, so they
    # have zero tag ownership even though they depend on exactly one tag-owned
    # model. Colocate those helpers with that module instead of forcing a
    # _shared -> qbd/core import edge that creates a circular import.
    for class_name, target in list(assignments.items()):
        if target != ("", "_shared"):
            continue
        if class_tag_sets.get(class_name):
            continue

        deps = class_dependencies(classes[class_name], all_class_names)
        dep_targets = {
            assignments[dep]
            for dep in deps
            if assignments.get(dep) not in (None, ("", "_shared"))
        }
        if len(dep_targets) == 1:
            assignments[class_name] = next(iter(dep_targets))

    # Group classes by (package, module)
    module_classes: dict[tuple[str, str], list[str]] = defaultdict(list)
    for cname, target in assignments.items():
        module_classes[target].append(cname)

    # Wipe old generated files but keep __init__.py and _preview artifact
    for f in OUT_DIR.glob("*.py"):
        if f.name == "__init__.py":
            continue
        f.unlink()
    for sub in (CORE_DIR, QBD_DIR):
        if sub.exists():
            shutil.rmtree(sub)
        sub.mkdir(parents=True)

    # Shared helper for the generated models: accepts both timezone-aware and
    # naive datetime strings, which the live API currently returns for many
    # business-date fields.
    DATETIME_HELPER.write_text(
        "\n".join(
            [
                '"""Auto-generated support helpers. Do not edit by hand."""',
                "",
                "from __future__ import annotations",
                "",
                "from datetime import date, datetime, time",
                "from typing import Annotated",
                "",
                "from pydantic import BeforeValidator",
                "",
                "",
                "def _coerce_flexible_datetime(value):",
                "    if value is None or isinstance(value, datetime):",
                "        return value",
                "    if isinstance(value, date):",
                "        return datetime.combine(value, time.min)",
                "    if isinstance(value, str):",
                "        normalized = value.replace('Z', '+00:00')",
                "        return datetime.fromisoformat(normalized)",
                "    return value",
                "",
                "",
                "FlexibleDatetime = Annotated[datetime, BeforeValidator(_coerce_flexible_datetime)]",
                "",
                "__all__ = ['FlexibleDatetime']",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Render header (imports) as text — we'll prepend to every file
    header_src = "\n".join(ast.unparse(n) for n in header)

    def import_path_for(from_target: tuple[str, str], to_target: tuple[str, str]) -> str:
        """Build a relative import path from one module to another.

        Layout:
            models/__init__.py
            models/_shared.py           target = ("", "_shared")
            models/core/__init__.py
            models/core/vendor.py       target = ("core", "vendor")
            models/qbd/__init__.py
            models/qbd/vendor.py        target = ("qbd", "vendor")
        """
        from_pkg, _ = from_target
        to_pkg, to_mod = to_target
        if from_pkg == to_pkg:
            return f"from .{to_mod} import"
        if from_pkg == "" and to_pkg in ("core", "qbd"):
            return f"from .{to_pkg}.{to_mod} import"
        if from_pkg in ("core", "qbd") and to_pkg == "":
            return f"from .. import {to_mod}; from ..{to_mod} import"  # placeholder
        # cross-subpackage (core → qbd or vice versa)
        return f"from ..{to_pkg}.{to_mod} import"

    # Build per-module source
    written = 0
    for target, class_names in sorted(module_classes.items()):
        pkg, mod_name = target

        # Determine cross-module imports needed + intra-module dep graph
        needed_external: dict[tuple[str, str], set[str]] = defaultdict(set)
        intra_deps: dict[str, set[str]] = {cn: set() for cn in class_names}
        local_set = set(class_names)
        for cn in class_names:
            for dep in class_dependencies(classes[cn], all_class_names):
                dep_target = assignments.get(dep)
                if dep_target is None:
                    continue
                if dep_target == target:
                    if dep in local_set:
                        intra_deps[cn].add(dep)
                else:
                    needed_external[dep_target].add(dep)

        # Topological sort so dependencies come before dependents
        ordered: list[str] = []
        visited: set[str] = set()
        temp: set[str] = set()

        def visit(n: str) -> None:
            if n in visited or n not in intra_deps:
                return
            if n in temp:
                return  # cycle — fall back to insertion order
            temp.add(n)
            for d in sorted(intra_deps[n]):
                visit(d)
            temp.discard(n)
            visited.add(n)
            ordered.append(n)

        for cn in sorted(class_names):
            visit(cn)

        import_lines: list[str] = []
        for dep_target in sorted(needed_external):
            names = ", ".join(sorted(needed_external[dep_target]))
            dep_pkg, dep_mod = dep_target
            if pkg == dep_pkg:
                import_lines.append(f"from .{dep_mod} import {names}")
            elif pkg == "" and dep_pkg in ("core", "qbd"):
                import_lines.append(f"from .{dep_pkg}.{dep_mod} import {names}")
            elif pkg in ("core", "qbd") and dep_pkg == "":
                import_lines.append(f"from ..{dep_mod} import {names}")
            else:  # cross-subpackage
                import_lines.append(f"from ..{dep_pkg}.{dep_mod} import {names}")

        body = "\n\n\n".join(ast.unparse(classes[cn]) for cn in ordered)

        module_header = header_src
        needs_flexible_datetime = "AwareDatetime" in body or any(
            "AwareDatetime" in line for line in import_lines
        )
        if needs_flexible_datetime:
            module_header = module_header.replace("AwareDatetime, ", "")
            module_header = module_header.replace(", AwareDatetime", "")
            body = body.replace("AwareDatetime", "FlexibleDatetime")
            if pkg == "":
                import_lines.insert(0, "from ._datetime import FlexibleDatetime")
            else:
                import_lines.insert(0, "from .._datetime import FlexibleDatetime")

        parts = [module_header]
        if import_lines:
            parts.append("\n".join(import_lines))
        parts.append(body)
        text = "\n\n".join(parts) + "\n"

        if pkg == "":
            dest = OUT_DIR / f"{mod_name}.py"
        elif pkg == "core":
            dest = CORE_DIR / f"{mod_name}.py"
        else:
            dest = QBD_DIR / f"{mod_name}.py"
        dest.write_text(text, encoding="utf-8")
        written += 1

    # Build core/__init__.py and qbd/__init__.py subpackage indexes
    def write_subpkg_init(pkg_name: str, pkg_dir: Path) -> None:
        lines = ['"""Auto-generated. Do not edit by hand."""', ""]
        exported: list[str] = []
        for (p, m), names in sorted(module_classes.items()):
            if p != pkg_name:
                continue
            sorted_names = sorted(names)
            lines.append(f"from .{m} import {', '.join(sorted_names)}")
            exported.extend(sorted_names)
        lines.append("")
        lines.append("__all__ = [")
        for n in sorted(exported):
            lines.append(f"    {n!r},")
        lines.append("]")
        (pkg_dir / "__init__.py").write_text("\n".join(lines) + "\n", encoding="utf-8")

    write_subpkg_init("core", CORE_DIR)
    write_subpkg_init("qbd", QBD_DIR)

    # Tactical compatibility fix: the live BarCode response currently omits
    # revisionNumber even though the schema marks it required. This endpoint is
    # list/retrieve/delete only, so making the field optional in Python keeps
    # the SDK usable while the backend/spec contract is corrected.
    bar_code_file = QBD_DIR / "bar_code.py"
    if bar_code_file.exists():
        bar_code_text = bar_code_file.read_text(encoding="utf-8")
        bar_code_text = bar_code_text.replace(
            "revision_number: Annotated[str, Field(alias='revisionNumber')]",
            "revision_number: Annotated[str | None, Field(alias='revisionNumber')] = None",
        )
        bar_code_file.write_text(bar_code_text, encoding="utf-8")

    # Build top-level models/__init__.py that re-exports everything flat
    init_lines = ['"""Auto-generated. Do not edit by hand."""', ""]
    # _shared first (no dependencies on subpackages)
    shared_target = ("", "_shared")
    if shared_target in module_classes:
        names = sorted(module_classes[shared_target])
        init_lines.append(f"from ._shared import {', '.join(names)}")
    init_lines.append("from .core import *  # noqa: F401,F403")
    init_lines.append("from .qbd import *  # noqa: F401,F403")
    init_lines.append("from . import core, qbd")
    init_lines.append("")
    all_names = sorted(all_class_names)
    init_lines.append("__all__ = [")
    init_lines.append("    'core',")
    init_lines.append("    'qbd',")
    for n in all_names:
        init_lines.append(f"    {n!r},")
    init_lines.append("]")
    init_lines.append("")
    init_lines.append("# Resolve forward references across split modules")
    init_lines.append("for _name in __all__:")
    init_lines.append("    _cls = globals().get(_name)")
    init_lines.append("    if _cls is not None and hasattr(_cls, 'model_rebuild'):")
    init_lines.append("        try:")
    init_lines.append("            _cls.model_rebuild()")
    init_lines.append("        except Exception:")
    init_lines.append("            pass")
    init_lines.append("")
    (OUT_DIR / "__init__.py").write_text("\n".join(init_lines), encoding="utf-8")

    print(f"Wrote {written} module files to {OUT_DIR}")
    shared = len(module_classes.get(("", "_shared"), []))
    core_count = sum(1 for (p, _) in module_classes if p == "core")
    qbd_count = sum(1 for (p, _) in module_classes if p == "qbd")
    print(f"  _shared.py: {shared} classes")
    print(f"  core/: {core_count} files")
    print(f"  qbd/: {qbd_count} files")


if __name__ == "__main__":
    main()
