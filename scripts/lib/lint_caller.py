# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Lint a consumer caller workflow against the published gate contract.

Usage:
    lint_caller.py <caller.yml> --contract <schema.json> [--consumer-root <path>]
    lint_caller.py --emit-containers

``--emit-containers`` prints the normalized containers matrix (a single-line
JSON array) built from resolved gate inputs passed via GATE_* env vars —
primary entry first (derived from scan_image/dockerfile/context/target/APP_*),
then one entry per extra_containers element. The gate's caller-lint job pipes
it into GITHUB_OUTPUT; the build and image-scan jobs matrix over it.

Exit 0 when clean; exit 1 with one line per violation on stdout:
    <rule-id>: <offending key/detail>

Rules skipped for a stated reason print to stderr as
``notice: skip: <rule-id>: <reason>``; the values-file rule announces an
active run as ``notice: active: image-values-mismatch: checked <path>``.

Rule ids: no-secrets-inherit, no-caller-concurrency, unknown-input,
type-mismatch, missing-secret-map, image-values-mismatch, unreadable-caller,
extra-containers-json, extra-containers-name, extra-containers-duplicate,
extra-containers-dockerfile, extra-containers-template-path,
extra-containers-target, extra-containers-build-arg, smoke-secrets-json,
smoke-secrets-name, smoke-secrets-duplicate, smoke-secrets-literals.
When the caller sets ``use_ci_contract: true``, the consumer contract file
is validated WARN-ONLY (stderr ``notice: warn: ...``, never a violation):
ci-contract-file, ci-contract-target, ci-contract-manifest.
An unreadable caller (missing/unparseable file, or no job whose ``uses:``
matches the reusable gate workflow) fails closed.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

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


def _image_mapping_pins(mapping: dict[str, Any], scan_image: str) -> bool:
    """True when a Helm-style image map joins to ``scan_image``."""
    repo = mapping.get("repository")
    tag = mapping.get("tag")
    if not isinstance(repo, str) or tag is None or isinstance(tag, (dict, list)):
        return False
    return f"{repo}:{tag}" == scan_image


def values_pin_scan_image(node: Any, scan_image: str) -> bool:
    """True if parsed values pin ``scan_image`` via ``image`` string or map.

    Accepts ``image: repo:tag`` strings and ``image: {repository, tag}`` maps
    (including nested ``*.image``). Comments are invisible to the YAML parse.
    """
    if isinstance(node, dict):
        image = node.get("image")
        if isinstance(image, str) and image == scan_image:
            return True
        if isinstance(image, dict) and _image_mapping_pins(image, scan_image):
            return True
        return any(values_pin_scan_image(v, scan_image) for v in node.values())
    if isinstance(node, list):
        return any(values_pin_scan_image(v, scan_image) for v in node)
    return False


def check_image_values(
    with_map: dict[str, Any],
    props: dict[str, Any],
    consumer_root: Path | None,
) -> list[str]:
    """scan_image must be pinned in the consumer's values-local YAML."""
    rule = "image-values-mismatch"
    image_only = contract_value(with_map, props, "image_only")
    if image_only is True:
        notice("skip", rule, "image_only is true")
        return []
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
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return [f"{rule}: values file '{values_path}' is not valid YAML: {e}"]
    if values_pin_scan_image(data, str(scan_image)):
        return []
    return [f"{rule}: scan_image '{scan_image}' not found in {values_path}"]


# extra_containers per-entry validation. The contract only sees the flat
# `extra_containers` string input, so structure is enforced here (mirrors what
# the deleted renderer used to check). Cookiecutter/scaffold trees are never
# buildable targets: reject dockerfile/context under these dirs or containing
# a `{{` template token.
_EXTRA_ALLOWED_KEYS = {
    "name",
    "dockerfile",
    "context",
    "image",
    "target",
    "build_args",
}
_EXTRA_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,38}[a-z0-9]$")
_EXTRA_BUILD_ARG_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_TEMPLATE_DENY_DIRS = ("packages/templates", "templates")


def _is_template_path(path: str) -> bool:
    if "{{" in path:
        return True
    norm = path[2:] if path.startswith("./") else path
    norm = norm.lstrip("/")
    return any(norm == d or norm.startswith(d + "/") for d in _TEMPLATE_DENY_DIRS)


def check_extra_containers(with_map: dict[str, Any]) -> list[str]:
    """Validate the caller's extra_containers value (a JSON-array string).

    The gate workflow parses it with fromJSON and matrixes over it; context/image
    defaults are applied in build-extra, and build_args is a newline-joined
    KEY=VALUE string (consumed directly by build-extra). Absent value = no rules.
    """
    if "extra_containers" not in with_map:
        return []
    raw = with_map["extra_containers"]
    if is_expression(raw):
        return [
            "extra-containers-json: extra_containers must be a literal JSON-array "
            "string (expressions are not lintable; expand to a static JSON array "
            "or use a multiline '|' block)"
        ]
    if not isinstance(raw, str):
        return [
            "extra-containers-json: extra_containers must be a JSON-array string, "
            f"got {yaml_json_type(raw)}"
        ]
    text = raw.strip()
    if text in ("", "[]"):
        return []
    try:
        entries = json.loads(text)
    except json.JSONDecodeError as e:
        return [f"extra-containers-json: extra_containers is not valid JSON: {e}"]
    if not isinstance(entries, list):
        return [
            "extra-containers-json: extra_containers must be a JSON array, "
            f"got {yaml_json_type(entries)}"
        ]
    # Style only (stderr notice, not a violation): a single-line quoted JSON
    # array is valid but hard to review once there is more than one entry.
    # Prefer a multiline YAML '|' block — see docs/INPUTS.md.
    if entries and "\n" not in text:
        notice(
            "style",
            "extra-containers-format",
            "prefer a multiline YAML '|' block (one object per entry); "
            "single-line quoted JSON does not scale — see docs/INPUTS.md",
        )

    violations: list[str] = []
    seen: set[str] = set()
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            violations.append(f"extra-containers-json: entry {idx} is not an object")
            continue
        name = entry.get("name")
        where = f"'{name}'" if isinstance(name, str) and name else f"entry {idx}"

        unknown = set(entry) - _EXTRA_ALLOWED_KEYS
        if unknown:
            violations.append(
                f"extra-containers-json: {where}: unknown key(s) {sorted(unknown)}"
            )

        if not isinstance(name, str) or not _EXTRA_NAME_RE.match(name):
            violations.append(
                f"extra-containers-name: {where}: name must match "
                r"^[a-z0-9][a-z0-9-]{0,38}[a-z0-9]$"
            )
        elif name in seen:
            violations.append(f"extra-containers-duplicate: duplicate name '{name}'")
        else:
            seen.add(name)

        dockerfile = entry.get("dockerfile")
        if not isinstance(dockerfile, str) or not dockerfile:
            violations.append(
                f"extra-containers-dockerfile: {where}: 'dockerfile' is required"
            )

        for field in ("dockerfile", "context"):
            val = entry.get(field)
            if isinstance(val, str) and val and _is_template_path(val):
                violations.append(
                    f"extra-containers-template-path: {where}: {field} '{val}' is a "
                    "cookiecutter/scaffold path (under templates/ or "
                    "packages/templates/, or containing '{{') — not a buildable target"
                )

        stage = entry.get("target")
        if stage is not None and not isinstance(stage, str):
            violations.append(
                f"extra-containers-target: {where}: target must be a string stage name"
            )

        build_args = entry.get("build_args")
        if build_args is not None:
            if not isinstance(build_args, str):
                violations.append(
                    f"extra-containers-build-arg: {where}: build_args must be a "
                    "newline-joined KEY=VALUE string"
                )
            else:
                for line in build_args.splitlines():
                    if line.strip() and not _EXTRA_BUILD_ARG_RE.match(line):
                        violations.append(
                            f"extra-containers-build-arg: {where}: build_args line "
                            f"'{line}' must match ^[A-Za-z_][A-Za-z0-9_]*="
                        )
    return violations


_SMOKE_SECRET_ALLOWED_KEYS = {"name", "literals"}
_SMOKE_SECRET_NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
_SMOKE_LITERAL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def check_smoke_secrets(with_map: dict[str, Any]) -> list[str]:
    """Validate the caller's smoke_secrets value (a JSON-array string).

    cluster-smoke creates each entry as a Kubernetes Secret before helm install.
    literals is a newline-joined KEY=VALUE string (same shape as build_args).
    Absent / empty / [] = no rules.
    """
    if "smoke_secrets" not in with_map:
        return []
    raw = with_map["smoke_secrets"]
    if is_expression(raw):
        return [
            "smoke-secrets-json: smoke_secrets must be a literal JSON-array "
            "string (expressions are not lintable; expand to a static JSON array "
            "or use a multiline '|' block)"
        ]
    if not isinstance(raw, str):
        return [
            "smoke-secrets-json: smoke_secrets must be a JSON-array string, "
            f"got {yaml_json_type(raw)}"
        ]
    text_val = raw.strip()
    if text_val in ("", "[]"):
        return []
    try:
        entries = json.loads(text_val)
    except json.JSONDecodeError as e:
        return [f"smoke-secrets-json: smoke_secrets is not valid JSON: {e}"]
    if not isinstance(entries, list):
        return [
            "smoke-secrets-json: smoke_secrets must be a JSON array, "
            f"got {yaml_json_type(entries)}"
        ]
    if entries and "\n" not in text_val:
        notice(
            "style",
            "smoke-secrets-format",
            "prefer a multiline YAML '|' block (one object per entry); "
            "single-line quoted JSON does not scale — see docs/INPUTS.md",
        )

    violations: list[str] = []
    seen: set[str] = set()
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            violations.append(f"smoke-secrets-json: entry {idx} is not an object")
            continue
        name = entry.get("name")
        where = f"'{name}'" if isinstance(name, str) and name else f"entry {idx}"

        unknown = set(entry) - _SMOKE_SECRET_ALLOWED_KEYS
        if unknown:
            violations.append(
                f"smoke-secrets-json: {where}: unknown key(s) {sorted(unknown)}"
            )

        if not isinstance(name, str) or not _SMOKE_SECRET_NAME_RE.match(name):
            violations.append(
                f"smoke-secrets-name: {where}: name must match "
                r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$"
            )
        elif name in seen:
            violations.append(f"smoke-secrets-duplicate: duplicate name '{name}'")
        else:
            seen.add(name)

        literals = entry.get("literals")
        if not isinstance(literals, str) or not literals.strip():
            violations.append(
                f"smoke-secrets-literals: {where}: 'literals' is required "
                "(newline-joined KEY=VALUE string)"
            )
            continue
        for line in literals.splitlines():
            if line.strip() and not _SMOKE_LITERAL_RE.match(line):
                violations.append(
                    f"smoke-secrets-literals: {where}: literals line "
                    f"'{line}' must match ^[A-Za-z_][A-Za-z0-9_]*="
                )
    return violations


# --- consumer build contract (use_ci_contract) -------------------------------
# WARN-ONLY validation: the contract path is opt-in and consumer-owned, so a
# broken contract file surfaces as stderr notices (``notice: warn: ...``),
# never as lint violations. Rule ids: ci-contract-file (missing/unreadable
# contract file), ci-contract-target (a required make target is absent),
# ci-contract-manifest (ci-manifest output is not the required JSON shape).

_CI_CONTRACT_TARGETS = ("ci-manifest", "ci-build", "ci-secctx", "ci-smoke-env")
_CI_MANIFEST_REQUIRED: dict[str, tuple[str, ...]] = {
    "chart": ("path", "values", "values_local", "release", "namespace"),
    "health": ("path", "port", "workload_match"),
}


def _make_target_missing(contract_path: Path, target: str, cwd: Path) -> str | None:
    """Return a warn detail when ``make -n`` can't resolve ``target``."""
    try:
        proc = subprocess.run(
            ["make", "-n", "-f", str(contract_path), target],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"make -n {target}: {e}"
    if proc.returncode == 0:
        return None
    return f"make -n {target} failed (rc={proc.returncode}): {proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else 'no stderr'}"


def check_ci_manifest_shape(manifest: Any) -> list[str]:
    """Return warn details for missing required ci-manifest keys."""
    problems: list[str] = []
    if not isinstance(manifest, dict):
        return [f"manifest must be a JSON object, got {yaml_json_type(manifest)}"]
    images = manifest.get("images")
    if not isinstance(images, list) or not images:
        problems.append("'images' must be a non-empty array")
    else:
        for idx, entry in enumerate(images):
            if not isinstance(entry, dict):
                problems.append(f"images[{idx}] is not an object")
                continue
            if not isinstance(entry.get("name"), str) or not entry["name"]:
                problems.append(f"images[{idx}] missing 'name'")
    for section, keys in _CI_MANIFEST_REQUIRED.items():
        node = manifest.get(section)
        if not isinstance(node, dict):
            problems.append(f"'{section}' must be an object")
            continue
        missing = [k for k in keys if k not in node]
        if missing:
            problems.append(f"'{section}' missing key(s) {missing}")
    return problems


def check_ci_contract(
    with_map: dict[str, Any],
    props: dict[str, Any],
    consumer_root: Path | None,
) -> list[str]:
    """Warn-only contract-file validation; always returns no violations."""
    if contract_value(with_map, props, "use_ci_contract") is not True:
        return []
    contract_file = contract_value(with_map, props, "contract_file")
    if is_expression(contract_file):
        notice("skip", "ci-contract-file", "contract_file is an expression")
        return []
    if consumer_root is None:
        notice("skip", "ci-contract-file", "--consumer-root not given")
        return []
    contract_path = (consumer_root / str(contract_file)).resolve()
    if not contract_path.is_file():
        notice(
            "warn",
            "ci-contract-file",
            f"use_ci_contract is true but '{contract_file}' not found under "
            f"consumer root '{consumer_root}'",
        )
        return []
    notice("active", "ci-contract-file", f"checked {contract_path}")
    for target in _CI_CONTRACT_TARGETS:
        detail = _make_target_missing(contract_path, target, consumer_root)
        if detail is not None:
            notice("warn", "ci-contract-target", f"{contract_file}: {detail}")
    try:
        proc = subprocess.run(
            ["make", "-s", "-f", str(contract_path), "ci-manifest"],
            cwd=consumer_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        notice("warn", "ci-contract-manifest", f"{contract_file}: ci-manifest: {e}")
        return []
    if proc.returncode != 0:
        notice(
            "warn",
            "ci-contract-manifest",
            f"{contract_file}: ci-manifest exited {proc.returncode}",
        )
        return []
    try:
        manifest = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        notice(
            "warn",
            "ci-contract-manifest",
            f"{contract_file}: ci-manifest output is not valid JSON: {e}",
        )
        return []
    for problem in check_ci_manifest_shape(manifest):
        notice("warn", "ci-contract-manifest", f"{contract_file}: {problem}")
    return []


# --- normalized containers matrix (--emit-containers) -----------------------
# Consumed by the gate workflow: caller-lint emits this list; the matrixed
# build and image-scan jobs fromJSON() it. Entry schema:
#   {name, role: "primary"|"extra", image, dockerfile, context, target,
#    build_args, cache_scope}
# build_args excludes BUILDER_IMAGE/RUNTIME_IMAGE — the build job prepends
# those from the hardened-registry-login step per leg. The list always has
# >=1 entry (the primary), so the jobs' matrices can never be empty.

_PRIMARY_CACHE_SCOPE = "security-scan-backend"


def normalized_containers(
    scan_image: str,
    dockerfile: str,
    context: str,
    target: str,
    app_path: str,
    app_package: str,
    app_module: str,
    app_port: str,
    runtime_apks: str,
    extra_build_args: str,
    extra_containers: str,
) -> list[dict[str, str]]:
    """Return the normalized container list: primary first, then extras.

    Fails closed (SystemExit) on unparseable extra_containers — the lint
    rules have already validated caller-literal values by the time the gate
    job calls this with resolved inputs.
    """
    primary_args = "\n".join(
        [
            f"APP_PATH={app_path}",
            f"APP_PACKAGE={app_package}",
            f"APP_MODULE={app_module}",
            f"APP_PORT={app_port}",
            f"RUNTIME_APKS={runtime_apks}",
        ]
    )
    if extra_build_args.strip():
        primary_args += "\n" + extra_build_args
    containers: list[dict[str, str]] = [
        {
            "name": "primary",
            "role": "primary",
            "image": scan_image,
            "dockerfile": dockerfile,
            "context": context or ".",
            "target": target,
            "build_args": primary_args,
            "cache_scope": _PRIMARY_CACHE_SCOPE,
        }
    ]
    raw = extra_containers.strip()
    if raw in ("", "[]"):
        return containers
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"error: extra_containers is not valid JSON: {e}") from e
    if not isinstance(entries, list):
        raise SystemExit("error: extra_containers must be a JSON array")
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise SystemExit(f"error: extra_containers entry {idx} missing name")
        name = entry["name"]
        containers.append(
            {
                "name": name,
                "role": "extra",
                "image": str(entry.get("image") or f"{name}:local"),
                "dockerfile": str(entry.get("dockerfile") or ""),
                "context": str(entry.get("context") or "."),
                "target": str(entry.get("target") or ""),
                "build_args": str(entry.get("build_args") or ""),
                "cache_scope": f"security-scan-{name}",
            }
        )
    return containers


def manifest_containers(manifest_raw: str, scan_image: str) -> list[dict[str, str]]:
    """Normalized containers list from a contract ci-manifest JSON document.

    Contract path (use_ci_contract=true): the manifest is the single source
    of truth — images[0] is the primary (always tagged with the gate's
    scan_image input; a manifest ``image`` key on the primary is ignored),
    images[1:] are the extras, tagged by their optional ``image`` key or
    <name>:local when absent (the legacy extra_containers[].image
    semantics). extra_containers is ignored on this path. Entry shape
    matches normalized_containers();
    dockerfile/context/target/build_args ride along untouched (the contract
    build path does not consume them — `make ci-build` owns the build).
    Fails closed (SystemExit) on an unusable manifest.
    """
    try:
        manifest = json.loads(manifest_raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"error: ci-manifest output is not valid JSON: {e}") from e
    if not isinstance(manifest, dict):
        raise SystemExit("error: ci-manifest output must be a JSON object")
    images = manifest.get("images")
    if not isinstance(images, list) or not images:
        raise SystemExit("error: ci-manifest 'images' must be a non-empty array")
    containers: list[dict[str, str]] = []
    for idx, entry in enumerate(images):
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise SystemExit(f"error: ci-manifest images[{idx}] missing name")
        name = entry["name"]
        primary = idx == 0
        containers.append(
            {
                "name": name,
                "role": "primary" if primary else "extra",
                "image": (
                    scan_image
                    if primary
                    else str(entry.get("image") or f"{name}:local")
                ),
                "dockerfile": str(entry.get("dockerfile") or ""),
                "context": str(entry.get("context") or "."),
                "target": str(entry.get("target") or ""),
                "build_args": str(entry.get("build_args") or ""),
                "cache_scope": (
                    _PRIMARY_CACHE_SCOPE if primary else f"security-scan-{name}"
                ),
            }
        )
    return containers


def emit_containers() -> int:
    """Print the normalized containers matrix (single-line JSON) from env."""
    env = os.environ.get
    if env("GATE_USE_CI_CONTRACT", "") == "true":
        containers = manifest_containers(
            manifest_raw=env("GATE_CI_MANIFEST", ""),
            scan_image=env("GATE_SCAN_IMAGE", ""),
        )
        print(json.dumps(containers, separators=(",", ":")))
        return 0
    containers = normalized_containers(
        scan_image=env("GATE_SCAN_IMAGE", ""),
        dockerfile=env("GATE_DOCKERFILE", ""),
        context=env("GATE_CONTEXT", "."),
        target=env("GATE_TARGET", ""),
        app_path=env("GATE_APP_PATH", ""),
        app_package=env("GATE_APP_PACKAGE", ""),
        app_module=env("GATE_APP_MODULE", ""),
        app_port=env("GATE_APP_PORT", ""),
        runtime_apks=env("GATE_RUNTIME_APKS", ""),
        extra_build_args=env("GATE_EXTRA_BUILD_ARGS", ""),
        extra_containers=env("GATE_EXTRA_CONTAINERS", ""),
    )
    print(json.dumps(containers, separators=(",", ":")))
    return 0


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

    violations.extend(check_extra_containers(with_map))
    violations.extend(check_smoke_secrets(with_map))
    violations.extend(check_image_values(with_map, props, consumer_root))
    violations.extend(check_ci_contract(with_map, props, consumer_root))
    return violations


def main(argv: list[str]) -> int:
    if argv == ["--emit-containers"]:
        return emit_containers()
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
