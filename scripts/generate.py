#!/usr/bin/env python3
"""
Generate typed Pydantic v2 models from the Nxus OpenAPI spec.

Pipeline:
    1. Fetch spec (URL or local file)
    2. Run datamodel-code-generator → single-file preview
    3. Run scripts/split_models.py → split into core/ + qbd/ subpackages

Usage:
    # From live production API
    python scripts/generate.py

    # From local dev server (TLS cert bypass is automatic for localhost)
    python scripts/generate.py --url https://localhost:7242/openapi/v1.json

    # From a local spec file
    python scripts/generate.py --file spec/openapi.json
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "nxus_qbd" / "models"
PREVIEW_FILE = MODELS_DIR / "_preview"
SPLIT_SCRIPT = REPO_ROOT / "scripts" / "split_models.py"
RESOURCE_REGISTRY_SCRIPT = REPO_ROOT / "scripts" / "generate_resource_registry.py"
CODEGEN_SPEC_FILE = MODELS_DIR / "_codegen_openapi.json"
DEFAULT_URL = "https://api.nx-us.net/openapi/v1.json"
LOCAL_FALLBACK_URL = "https://localhost:7242/openapi/v1.json"


def _fetch_spec(url: str) -> bytes:
    """Fetch the OpenAPI spec, bypassing TLS verification for localhost."""
    try:
        import httpx
    except ImportError:
        print("httpx is required to download the spec. Install with: uv pip install httpx")
        sys.exit(1)

    verify = "localhost" not in url and "127.0.0.1" not in url
    print(f"Downloading spec from {url} (verify_tls={verify})")
    response = httpx.get(url, verify=verify, timeout=30)
    response.raise_for_status()
    return response.content


def download_spec(url: str, *, allow_default_fallback: bool = False) -> Path:
    """Download the OpenAPI spec, optionally falling back to localhost for the default URL."""
    try:
        content = _fetch_spec(url)
        source_url = url
    except Exception as exc:
        if allow_default_fallback and url == DEFAULT_URL:
            print(
                f"Production spec unavailable, falling back to local dev spec at {LOCAL_FALLBACK_URL}"
            )
            try:
                content = _fetch_spec(LOCAL_FALLBACK_URL)
                source_url = LOCAL_FALLBACK_URL
            except Exception:
                raise exc
        else:
            raise

    spec_dir = REPO_ROOT / "spec"
    spec_dir.mkdir(exist_ok=True)
    spec_file = spec_dir / "openapi.json"
    spec_file.write_bytes(content)
    print(f"Downloaded {len(content):,} bytes from {source_url} → {spec_file}\n")
    return spec_file


def _normalize_nullable_allof_arrays(node):
    """Inline `allOf: [{type: array, ...}]` schemas before Python model generation.

    The backend OpenAPI emitter sometimes wraps array properties as
    `allOf: [{type: array, ...}]` (with or without `nullable: true`).
    datamodel-code-generator treats that shape as an empty wrapper model,
    so live array responses fail Pydantic validation. Inlining the array
    schema produces the expected `list[T]` / `list[T] | None` annotations.
    """
    if isinstance(node, dict):
        all_of = node.get("allOf")
        if (
            isinstance(all_of, list)
            and len(all_of) == 1
            and isinstance(all_of[0], dict)
            and all_of[0].get("type") == "array"
        ):
            array_schema = all_of[0]
            node.pop("allOf")
            for key, value in array_schema.items():
                node.setdefault(key, value)

        for value in node.values():
            _normalize_nullable_allof_arrays(value)
    elif isinstance(node, list):
        for value in node:
            _normalize_nullable_allof_arrays(value)


def prepare_codegen_spec(spec_file: Path) -> Path:
    """Write a normalized OpenAPI copy for datamodel-code-generator."""
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    _normalize_nullable_allof_arrays(spec)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    CODEGEN_SPEC_FILE.write_text(json.dumps(spec, separators=(",", ":")), encoding="utf-8")
    return CODEGEN_SPEC_FILE


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SDK models from OpenAPI spec")
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"URL to fetch the OpenAPI spec from (default: {DEFAULT_URL})",
    )
    source.add_argument(
        "--file",
        type=Path,
        help="Path to a local OpenAPI spec file",
    )
    args = parser.parse_args()

    # Resolve spec file — download if URL provided
    if args.file:
        spec_file = args.file
    else:
        spec_file = download_spec(
            args.url,
            allow_default_fallback=args.url == DEFAULT_URL,
        )

    # Clean previous preview artifacts
    if PREVIEW_FILE.exists():
        PREVIEW_FILE.unlink()
    if CODEGEN_SPEC_FILE.exists():
        CODEGEN_SPEC_FILE.unlink()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    codegen_spec_file = prepare_codegen_spec(spec_file)

    cmd = [
        sys.executable, "-m", "datamodel_code_generator",
        "--input", str(codegen_spec_file),
        "--input-file-type", "openapi",
        "--output", str(PREVIEW_FILE),
        "--output-model-type", "pydantic_v2.BaseModel",
        "--target-python-version", "3.12",
        "--use-standard-collections",
        "--use-union-operator",
        "--strict-nullable",
        "--field-constraints",
        "--capitalise-enum-members",
        "--snake-case-field",
        "--allow-population-by-field-name",
        "--use-default",
        "--reuse-model",
        "--use-annotated",
    ]

    print(f"Generating Pydantic v2 models → {PREVIEW_FILE}")
    print(f"Source: {spec_file}")
    print(f"Codegen source: {codegen_spec_file}")
    print(f"Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        # Filter out FutureWarning about formatters
        for line in result.stderr.splitlines():
            if "FutureWarning" not in line and "formatters" not in line:
                print(line, file=sys.stderr)

    if result.returncode != 0:
        PREVIEW_FILE.unlink(missing_ok=True)
        print(f"\n[fail] Generation failed (exit code {result.returncode})")
        sys.exit(result.returncode)

    line_count = len(PREVIEW_FILE.read_text(encoding="utf-8").splitlines())
    print(f"\n[ok] Generated {line_count:,} lines → {PREVIEW_FILE.relative_to(REPO_ROOT)}")

    # Chain into splitter
    print("\nSplitting into core/ + qbd/ subpackages...")
    split_result = subprocess.run(
        [sys.executable, str(SPLIT_SCRIPT)],
        capture_output=True,
        text=True,
    )
    if split_result.stdout:
        print(split_result.stdout)
    if split_result.stderr:
        print(split_result.stderr, file=sys.stderr)
    if split_result.returncode != 0:
        print(f"\n[fail] Split failed (exit code {split_result.returncode})")
        sys.exit(split_result.returncode)

    # Regenerate resource route registry from the same spec
    print("\nSyncing resource route registry from OpenAPI...")
    registry_result = subprocess.run(
        [sys.executable, str(RESOURCE_REGISTRY_SCRIPT), "--file", str(spec_file), "--apply"],
        capture_output=True,
        text=True,
    )
    if registry_result.stdout:
        print(registry_result.stdout)
    if registry_result.stderr:
        print(registry_result.stderr, file=sys.stderr)
    if registry_result.returncode != 0:
        print(f"\n[fail] Resource registry sync failed (exit code {registry_result.returncode})")
        sys.exit(registry_result.returncode)

    # Clean up preview artifact
    PREVIEW_FILE.unlink(missing_ok=True)
    CODEGEN_SPEC_FILE.unlink(missing_ok=True)
    print("\n[ok] Done.")


if __name__ == "__main__":
    main()
