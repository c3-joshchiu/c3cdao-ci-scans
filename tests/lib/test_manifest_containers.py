"""Unit tests for contract-path container normalization (manifest_containers).

Covers the extras tag rules exposed by the geoint canary: an extras entry's
optional ``image`` key is honored (legacy extra_containers[].image semantics),
absent it falls back to <name>:local, and the primary is always tagged with
the gate's scan_image input (a manifest ``image`` key on images[0] is ignored).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from lint_caller import manifest_containers  # noqa: E402


def _manifest(images: list[dict]) -> str:
    return json.dumps({"images": images})


def test_extra_image_key_honored():
    containers = manifest_containers(
        _manifest(
            [
                {"name": "backend"},
                {"name": "frontend", "image": "psp7-gateway-frontend:local"},
            ]
        ),
        scan_image="app:local",
    )
    assert containers[1]["role"] == "extra"
    assert containers[1]["image"] == "psp7-gateway-frontend:local"


def test_extra_image_defaults_to_name_local():
    containers = manifest_containers(
        _manifest([{"name": "backend"}, {"name": "frontend"}]),
        scan_image="app:local",
    )
    assert containers[1]["image"] == "frontend:local"


def test_primary_image_key_ignored_scan_image_wins():
    containers = manifest_containers(
        _manifest([{"name": "backend", "image": "other:tag"}]),
        scan_image="app:local",
    )
    assert containers[0]["role"] == "primary"
    assert containers[0]["image"] == "app:local"


def test_unusable_manifest_fails_closed():
    with pytest.raises(SystemExit):
        manifest_containers("not json", scan_image="app:local")
    with pytest.raises(SystemExit):
        manifest_containers(json.dumps({"images": []}), scan_image="app:local")
