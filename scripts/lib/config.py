# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
# ///
"""Load an onboarding config YAML, validate it against config/schema.json,
and print it as JSON (the contract load-config.sh always had).

Also importable by sibling scripts:
    load_config(path)  -> dict (validated)
    gate_value(config, key) -> config value or the schema default, exact
                               types preserved (False stays False — the jq
                               `// empty` helper could never represent that).
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
    return config


def gate_value(config: dict, key: str):
    """security_gate value with the schema default as single source of truth."""
    gate = config.get("security_gate") or {}
    if key in gate:
        return gate[key]
    prop = _schema()["properties"]["security_gate"]["properties"].get(key, {})
    return prop.get("default")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: config.py <config.yaml>", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(load_config(sys.argv[1])))
