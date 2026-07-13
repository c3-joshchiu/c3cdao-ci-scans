# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Lint a consumer caller workflow against the published gate contract.

Usage:
    lint_caller.py <caller.yml> --contract <schema.json> [--consumer-root <path>]

Exit 0 when clean; exit 1 with one line per violation on stdout:
    <rule-id>: <offending key/detail>

Rules skipped for a stated reason print to stderr as
``notice: skip: <rule-id>: <reason>``; the values-file rule announces an
active run as ``notice: active: image-values-mismatch: checked <path>``.

Rule ids: no-secrets-inherit, no-caller-concurrency, unknown-input,
type-mismatch, missing-secret-map, image-values-mismatch, unreadable-caller.
An unreadable caller (missing/unparseable file, or no job whose ``uses:``
matches the reusable gate workflow) fails closed.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from extract_contract import load_gha_workflow

GATE_WORKFLOW_BASENAME = "reusable-security-gate.yml"
REQUIRED_SECRETS = (
    "CGR_PULL_TOKEN",
    "CGR_PULL_USERNAME",
    "IRONBANK_TOKEN",
    "IRONBANK_USERNAME",
)


def notice(kind: str, rule: str, detail: str) -> None:
    print(f"notice: {kind}: {rule}: {detail}", file=sys.stderr)


def is_expression(value: Any) -> bool:
    """A GitHub Actions expression value — its literal type is unknowable."""
    return isinstance(value, str) and "${{" in value


def yaml_json_type(value: Any) -> str:
    """JSON Schema type name of a parsed YAML scalar (bool before int!)."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if value is None:
        return "null"
    return type(value).__name__


def load_contract(path: Path) -> dict[str, Any]:
    """Return the contract schema's properties mapping, or exit naming why."""
    try:
        schema = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"error: {path}: {e}") from e
    props = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(props, dict) or not props:
        raise SystemExit(f"error: {path}: contract has no properties mapping")
    return props


def find_gate_job(jobs: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    for job_id, job in jobs.items():
        if isinstance(job, dict) and GATE_WORKFLOW_BASENAME in str(
            job.get("uses") or ""
        ):
            return job_id, job
    return None


def contract_value(with_map: dict[str, Any], props: dict[str, Any], key: str) -> Any:
    """Caller-provided value for ``key``, falling back to the contract default."""
    if key in with_map:
        return with_map[key]
    return (props.get(key) or {}).get("default")


def check_image_values(
    with_map: dict[str, Any],
    props: dict[str, Any],
    consumer_root: Path | None,
) -> list[str]:
    """scan_image must appear in the consumer's values-local file text."""
    rule = "image-values-mismatch"
    if consumer_root is None:
        notice("skip", rule, "--consumer-root not given")
        return []
    scan_image = contract_value(with_map, props, "scan_image")
    values_file = contract_value(with_map, props, "helm_values_local_file")
    expr_keys = [
        key
        for key, value in (
            ("scan_image", scan_image),
            ("helm_values_local_file", values_file),
        )
        if is_expression(value)
    ]
    if expr_keys:
        for key in expr_keys:
            notice("skip", rule, f"{key} is an expression")
        return []
    values_path = consumer_root / str(values_file)
    try:
        text = values_path.read_text()
    except OSError as e:
        return [
            f"{rule}: values file '{values_file}' unreadable under consumer root '{consumer_root}': {e}"
        ]
    notice("active", rule, f"checked {values_path}")
    if str(scan_image) not in text:
        return [f"{rule}: scan_image '{scan_image}' not found in {values_path}"]
    return []


def lint(
    caller_path: Path, props: dict[str, Any], consumer_root: Path | None
) -> list[str]:
    try:
        wf = load_gha_workflow(caller_path)
    except SystemExit as e:
        return [f"unreadable-caller: {e.code}"]

    jobs = wf.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        return [f"unreadable-caller: {caller_path}: no jobs mapping"]
    gate = find_gate_job(jobs)
    if gate is None:
        return [
            f"unreadable-caller: {caller_path}: no job whose 'uses:' matches "
            f"{GATE_WORKFLOW_BASENAME}"
        ]
    gate_id, gate_job = gate

    violations: list[str] = []

    for job_id, job in jobs.items():
        if isinstance(job, dict) and job.get("secrets") == "inherit":
            violations.append(
                f"no-secrets-inherit: job '{job_id}' uses 'secrets: inherit' — "
                "map the four gate secrets explicitly"
            )

    if "concurrency" in wf:
        violations.append(
            "no-caller-concurrency: caller has a top-level 'concurrency:' key — "
            "the reusable workflow owns concurrency"
        )

    with_map = gate_job.get("with")
    if not isinstance(with_map, dict):
        with_map = {}
    for key, value in with_map.items():
        if key not in props:
            violations.append(
                f"unknown-input: with: key '{key}' not in contract properties"
            )
            continue
        if is_expression(value):
            notice("skip", "type-mismatch", f"{key} is an expression")
            continue
        expected = (props[key] or {}).get("type", "string")
        actual = yaml_json_type(value)
        if actual != expected:
            violations.append(
                f"type-mismatch: with: key '{key}' expects {expected}, "
                f"got {actual} ({value!r})"
            )

    if gate_job.get("secrets") != "inherit":
        secrets = gate_job.get("secrets")
        mapped = secrets if isinstance(secrets, dict) else {}
        for name in REQUIRED_SECRETS:
            if name not in mapped:
                violations.append(
                    f"missing-secret-map: secret '{name}' not mapped on job '{gate_id}'"
                )

    violations.extend(check_image_values(with_map, props, consumer_root))
    return violations


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Lint a caller workflow against the gate contract."
    )
    parser.add_argument("caller", type=Path, help="caller workflow YAML to lint")
    parser.add_argument(
        "--contract", required=True, type=Path, help="contract JSON Schema path"
    )
    parser.add_argument(
        "--consumer-root",
        type=Path,
        default=None,
        help="consumer repo root; enables the values-local file rule",
    )
    args = parser.parse_args(argv)
    props = load_contract(args.contract)
    violations = lint(args.caller, props, args.consumer_root)
    for violation in violations:
        print(violation)
    if violations:
        return 1
    print(f"OK: {args.caller}: caller lint clean")
    return 0


if __name__ == "__main__":
    rc = 1
    try:
        rc = main(sys.argv[1:])
        sys.stdout.flush()
    except BrokenPipeError:
        # A downstream reader (e.g. `... | grep -q`) closed the pipe after
        # matching; the verdict in rc is already computed, so keep it.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    sys.exit(rc)
