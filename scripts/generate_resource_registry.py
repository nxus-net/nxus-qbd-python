#!/usr/bin/env python3
"""
Regenerate nxus_qbd/resources.py _RESOURCE_DEFS from the OpenAPI contract.

This keeps the Python SDK route registry aligned with the backend instead of
hand-maintaining every tuple when route conventions evolve.

Usage:
    python scripts/generate_resource_registry.py --file spec/openapi.json --check
    python scripts/generate_resource_registry.py --file spec/openapi.json --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RESOURCES_FILE = REPO_ROOT / "nxus_qbd" / "resources.py"
BEGIN_MARKER = "# BEGIN AUTO-GENERATED RESOURCE DEFS"
END_MARKER = "# END AUTO-GENERATED RESOURCE DEFS"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nxus_qbd.resources import _MODELS, _RESOURCE_DEFS  # noqa: E402

TAG_OVERRIDES: dict[str, str] = {
    "time_trackings": "TimeTrackingActivity",
    "bill_to_pay": "BillToPay",
    "qbd_classes": "Class",
}

METHOD_ORDER = ("list", "retrieve", "create", "update", "delete")


def resolve_tag(namespace: str) -> str:
    if namespace in TAG_OVERRIDES:
        return TAG_OVERRIDES[namespace]

    model = _MODELS.get(namespace)
    if model is not None:
        name = model.__name__
        if name.endswith("Ret"):
            name = name[:-3]
        return name

    parts = namespace.split("_")
    if parts and parts[-1].endswith("ies"):
        parts[-1] = parts[-1][:-3] + "y"
    elif parts and parts[-1].endswith("s"):
        parts[-1] = parts[-1][:-1]
    return "".join(part.capitalize() for part in parts if part)


def normalize_methods(entry: dict[str, str]) -> tuple[str, ...]:
    methods: list[str] = []
    for method in METHOD_ORDER:
        if method in entry:
            methods.append(method)
    return tuple(methods)


def build_registry(spec: dict[str, Any]) -> list[tuple[str, str, str, str, tuple[str, ...]]]:
    paths = spec.get("paths", {})
    tag_index: dict[str, dict[str, str]] = {}

    for path, operations in paths.items():
        if not isinstance(operations, dict):
            continue

        for http_method, operation in operations.items():
            if http_method.lower() not in {"get", "post", "delete"}:
                continue
            if not isinstance(operation, dict):
                continue

            tags = operation.get("tags") or []
            if not tags:
                continue

            tag = str(tags[0])
            op_id = str(operation.get("operationId", ""))
            entry = tag_index.setdefault(tag, {})
            is_detail = "{id}" in path

            if http_method.lower() == "get" and not is_detail and op_id.startswith("List"):
                entry["list"] = path
            elif http_method.lower() == "get" and is_detail and op_id.startswith("Retrieve"):
                entry["retrieve"] = path
            elif http_method.lower() == "post" and not is_detail and op_id.startswith("Create"):
                entry["create"] = path
            elif http_method.lower() == "post" and is_detail and op_id.startswith("Update"):
                entry["update"] = path
            elif http_method.lower() == "delete" and is_detail and op_id.startswith("Delete"):
                entry["delete"] = path

    generated: list[tuple[str, str, str, str, tuple[str, ...]]] = []
    for namespace, current_list, current_singular, current_create, current_methods in _RESOURCE_DEFS:
        tag = resolve_tag(namespace)
        discovered = tag_index.get(tag)
        if not discovered:
            generated.append((namespace, current_list, current_singular, current_create, current_methods))
            continue

        list_path = discovered.get("list", current_list)
        singular_path = discovered.get("retrieve", current_singular)
        create_path = discovered.get("create", current_create)
        methods = normalize_methods(discovered) or current_methods
        generated.append((namespace, list_path, singular_path, create_path, methods))

    return generated


def render_registry(entries: list[tuple[str, str, str, str, tuple[str, ...]]]) -> str:
    lines = [BEGIN_MARKER, "_RESOURCE_DEFS: list[tuple[str, str, str, str, tuple[str, ...]]] = ["]
    for namespace, list_path, singular_path, create_path, methods in entries:
        rendered_methods = ", ".join(f'"{method}"' for method in methods)
        if len(methods) == 1:
            rendered_methods += ","
        lines.append(
            f'    ("{namespace}", "{list_path}", "{singular_path}", "{create_path}", ({rendered_methods})),'
        )
    lines.append("]")
    lines.append(END_MARKER)
    return "\n".join(lines)


def replace_registry_block(source: str, new_block: str) -> str:
    pattern = re.compile(
        rf"{re.escape(BEGIN_MARKER)}.*?{re.escape(END_MARKER)}",
        re.DOTALL,
    )
    if not pattern.search(source):
        raise RuntimeError("Could not find registry markers in resources.py")
    return pattern.sub(new_block, source)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Python SDK resource routes from OpenAPI")
    parser.add_argument("--file", type=Path, required=True, help="Path to the OpenAPI spec json file")
    parser.add_argument("--apply", action="store_true", help="Write changes back to nxus_qbd/resources.py")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if generated block differs")
    args = parser.parse_args()

    spec = json.loads(args.file.read_text(encoding="utf-8"))
    generated_entries = build_registry(spec)
    new_block = render_registry(generated_entries)

    current_source = RESOURCES_FILE.read_text(encoding="utf-8")
    updated_source = replace_registry_block(current_source, new_block)
    changed = updated_source != current_source

    if args.check:
        if changed:
            print("Resource registry is out of sync with the OpenAPI contract.")
            sys.exit(1)
        print("Resource registry matches the OpenAPI contract.")
        return

    if args.apply:
        RESOURCES_FILE.write_text(updated_source, encoding="utf-8")
        print(f"Updated {RESOURCES_FILE}")
        return

    print(new_block)


if __name__ == "__main__":
    main()
