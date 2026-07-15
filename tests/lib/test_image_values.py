"""Unit tests for YAML-aware scan_image pinning (issue #8)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from lint_caller import values_pin_scan_image  # noqa: E402


@pytest.mark.parametrize(
    ("data", "scan_image", "expected"),
    [
        ({"backend": {"image": "app:local"}}, "app:local", True),
        (
            {"backend": {"image": {"repository": "app", "tag": "local"}}},
            "app:local",
            True,
        ),
        (
            {"image": {"repository": "app", "tag": "local", "pullPolicy": "Never"}},
            "app:local",
            True,
        ),
        ({"backend": {"image": "other:v1"}}, "app:local", False),
        (
            {"backend": {"image": {"repository": "app", "tag": "other"}}},
            "app:local",
            False,
        ),
        (None, "app:local", False),
        ("app:local", "app:local", False),  # bare string is not an image field
    ],
)
def test_values_pin_scan_image(data, scan_image, expected):
    assert values_pin_scan_image(data, scan_image) is expected


def test_comment_only_does_not_pin():
    import yaml

    text = "# scan_image: app:local\nbackend:\n  image: other:v1\n"
    data = yaml.safe_load(text)
    assert values_pin_scan_image(data, "app:local") is False


if __name__ == "__main__":
    raise SystemExit(pytest.main(["-q", __file__]))
