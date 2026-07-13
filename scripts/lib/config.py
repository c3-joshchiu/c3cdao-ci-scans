# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
# ///
"""Load an onboarding config YAML, validate it against config/schema.json,
and print it as JSON (the contract load-config.sh always had).

Also importable by sibling scripts:
    load_config(path)  -> dict (validated)
"""

import json
import sys
from pathlib import Path

import jsonschema
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "config" / "schema.json"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def load_config(path: str | Path) -> dict:
    with open(path) as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict):
        raise SystemExit(f"error: {path}: config must be a YAML mapping")
    validator = jsonschema.Draft202012Validator(_schema())
    errors = sorted(validator.iter_errors(config), key=lambda e: list(e.absolute_path))
    if errors:
        for e in errors:
            where = ".".join(str(p) for p in e.absolute_path) or "<root>"
            print(f"error: {path}: {where}: {e.message}", file=sys.stderr)
        raise SystemExit(1)
    if "security_gate" in config:
        print(
            f"warning: {path}: 'security_gate' is deprecated and ignored — "
            "gate values now live in the consumer's caller workflow (see README); "
            "remove this block from the config",
            file=sys.stderr,
        )
    return config


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: config.py <config.yaml>", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(load_config(sys.argv[1])))
