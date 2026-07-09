# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
# ///
"""Render the security-gate caller workflow into the consumer repo.

Replaces the jq/sed pipeline that used to live in render-callers.sh:
- security_gate defaults come from config/schema.json (one source of truth)
- booleans render exactly (jq's `// empty` treated false as missing)
- multiline values ({{EXTRA_BUILD_ARGS}}) indent to wherever the placeholder
  sits in the template, so reindenting the template can't corrupt output
"""
import argparse
import json
import re
import sys
from pathlib import Path

from config import REPO_ROOT, gate_value, load_config

TEMPLATE = REPO_ROOT / "templates" / "callers" / "security-gate.yml.tpl"

GATE_KEYS = {
    "SCAN_IMAGE": "scan_image",
    "DOCKERFILE": "dockerfile",
    "BUILDER_IMAGE": "builder_image",
    "RUNTIME_IMAGE": "runtime_image",
    "RUNTIME_APKS": "runtime_apks",
    "HELM_CHART_PATH": "helm_chart_path",
    "HELM_VALUES_FILE": "helm_values_file",
    "HELM_VALUES_LOCAL_FILE": "helm_values_local_file",
    "HELM_RELEASE_NAME": "helm_release_name",
    "CLUSTER_NAME": "cluster_name",
    "NAMESPACE": "namespace",
    "SECCTX_MAKE_TARGET": "secctx_make_target",
    "APP_PATH": "app_path",
    "APP_PACKAGE": "app_package",
    "APP_MODULE": "app_module",
    "APP_PORT": "app_port",
    "REQUIRE_HARDENED_BASES": "require_hardened_bases",
    "IRONBANK_BUILDER_IMAGE": "ironbank_builder_image",
    "IRONBANK_RUNTIME_IMAGE": "ironbank_runtime_image",
}


def to_yaml_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def render(template: str, variables: dict[str, str]) -> str:
    out = template
    for key, value in variables.items():
        placeholder = "{{" + key + "}}"
        if "\n" in value:
            # Indent continuation lines to the placeholder's own column.
            for line in out.splitlines():
                if placeholder in line:
                    indent = " " * line.index(placeholder)
                    value = value.replace("\n", "\n" + indent)
                    break
        out = out.replace(placeholder, value)
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", out)
    if leftover:
        raise SystemExit(f"error: unrendered placeholders: {', '.join(sorted(set(leftover)))}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    ci = config["ci_scans"]

    variables = {key: to_yaml_scalar(gate_value(config, field)) for key, field in GATE_KEYS.items()}
    variables |= {
        "CI_SCANS_OWNER": ci["owner"],
        "CI_SCANS_REPO": ci["repo"],
        "CI_SCANS_REF": ci["ref"],
        "TRUNK_BRANCHES_YAML": json.dumps(
            config["target"].get("trunk_branches", ["main"]), separators=(",", ":")
        ),
        "EXTRA_BUILD_ARGS": "\n".join(gate_value(config, "extra_build_args") or []),
    }

    rendered = render(TEMPLATE.read_text(), variables)

    local_path = config["target"].get("local_path")
    if not local_path:
        raise SystemExit("error: target.local_path required")
    out_dir = (Path(local_path) if Path(local_path).is_absolute() else REPO_ROOT / local_path) / ".github" / "workflows"
    dest = out_dir / "security-gate.yml"

    if args.dry_run:
        print(f"# would write {dest}")
        print(rendered, end="")
        return

    if not out_dir.parent.parent.is_dir():
        raise SystemExit(f"error: local_path not found: {local_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    dest.write_text(rendered)
    (out_dir / ".ci-scans-onboard.json").write_text(
        json.dumps({
            "source": "c3cdao-ci-scans",
            "workflow": "security-gate",
            "ci_scans": f"{ci['owner']}/{ci['repo']}@{ci['ref']}",
        }) + "\n"
    )
    print(f"wrote {dest}")
    print("remove legacy modular scan workflows in consumer repo if migrating from mini-scans")


if __name__ == "__main__":
    sys.exit(main())
