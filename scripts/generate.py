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
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "nxus_qbd" / "models"
PREVIEW_FILE = MODELS_DIR / "_preview"
SPLIT_SCRIPT = REPO_ROOT / "scripts" / "split_models.py"
DEFAULT_URL = "https://api.nx-us.net/openapi/v1.json"


def download_spec(url: str) -> Path:
    """Download the OpenAPI spec, bypassing TLS verification for localhost."""
    try:
        import httpx
    except ImportError:
        print("httpx is required to download the spec. Install with: uv pip install httpx")
        sys.exit(1)

    verify = "localhost" not in url and "127.0.0.1" not in url
    print(f"Downloading spec from {url} (verify_tls={verify})")
    r = httpx.get(url, verify=verify, timeout=30)
    r.raise_for_status()

    spec_dir = REPO_ROOT / "spec"
    spec_dir.mkdir(exist_ok=True)
    spec_file = spec_dir / "openapi.json"
    spec_file.write_bytes(r.content)
    print(f"Downloaded {len(r.content):,} bytes → {spec_file}\n")
    return spec_file


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
        spec_file = download_spec(args.url)

    # Clean previous preview artifact
    if PREVIEW_FILE.exists():
        PREVIEW_FILE.unlink()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "datamodel_code_generator",
        "--input", str(spec_file),
        "--input-file-type", "openapi",
        "--output", str(PREVIEW_FILE),
        "--output-model-type", "pydantic_v2.BaseModel",
        "--target-python-version", "3.10",
        "--use-standard-collections",
        "--use-union-operator",
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

    # Clean up preview artifact
    PREVIEW_FILE.unlink(missing_ok=True)
    print("\n[ok] Done.")


if __name__ == "__main__":
    main()
