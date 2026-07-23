"""Unit tests for manifest container normalization + shape validation.

Covers the extras tag rules exposed by the geoint canary: an extras entry's
optional ``image`` key is honored, absent it falls back to <name>:local, and
the primary is always tagged with the gate's scan_image input (a manifest
``image`` key on images[0] is ignored). Shape enforcement lives in
check_ci_manifest_shape (blocking in caller lint, fail-closed in
--emit-manifest).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from lint_caller import check_ci_manifest_shape, manifest_containers  # noqa: E402


def _image(name: str, **extra) -> dict:
    return {"name": name, "dockerfile": f"containers/{name}/Dockerfile", "context": ".", **extra}


def _manifest(images: list[dict]) -> dict:
    return {
        "images": images,
        "chart": {
            "path": "helm/app",
            "values": "helm/app/values.yaml",
            "values_local": "helm/app/values-local.yaml",
            "release": "app-ci",
            "namespace": "app-ci",
        },
        "health": {"path": "/health", "port": "8000", "workload_match": "backend"},
    }


def test_extra_image_key_honored():
    containers = manifest_containers(
        _manifest([_image("backend"), _image("frontend", image="psp7-gateway-frontend:local")]),
        scan_image="app:local",
    )
    assert containers[1]["role"] == "extra"
    assert containers[1]["image"] == "psp7-gateway-frontend:local"


def test_extra_image_defaults_to_name_local():
    containers = manifest_containers(
        _manifest([_image("backend"), _image("frontend")]),
        scan_image="app:local",
    )
    assert containers[1]["image"] == "frontend:local"


def test_primary_image_key_ignored_scan_image_wins():
    containers = manifest_containers(
        _manifest([_image("backend", image="other:tag")]),
        scan_image="app:local",
    )
    assert containers[0]["role"] == "primary"
    assert containers[0]["image"] == "app:local"


def test_shape_clean_manifest_has_no_problems():
    assert check_ci_manifest_shape(_manifest([_image("backend")])) == []


def test_shape_rejects_non_object():
    assert check_ci_manifest_shape("not a dict")
    assert check_ci_manifest_shape(None)


def test_shape_rejects_empty_images():
    assert any(
        "'images'" in p for p in check_ci_manifest_shape(_manifest([]))
    )


def test_shape_rejects_image_missing_required_keys():
    problems = check_ci_manifest_shape(_manifest([{"name": "backend"}]))
    assert any("dockerfile" in p for p in problems)
    assert any("context" in p for p in problems)


def test_shape_rejects_missing_chart_and_health_keys():
    doc = _manifest([_image("backend")])
    del doc["chart"]["values_local"]
    del doc["health"]
    problems = check_ci_manifest_shape(doc)
    assert any("values_local" in p for p in problems)
    assert any("'health'" in p for p in problems)
