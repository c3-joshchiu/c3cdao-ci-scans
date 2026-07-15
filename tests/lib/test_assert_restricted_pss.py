"""Golden tests for assert_restricted_pss."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "scripts/lib/assert_restricted_pss.py"


def _load():
    spec = importlib.util.spec_from_file_location("assert_restricted_pss", MOD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()

PASS_YAML = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: app
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: [ALL]
"""

FAIL_YAML = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  template:
    spec:
      containers:
        - name: app
          securityContext: {}
"""


def test_pass(tmp_path):
    p = tmp_path / "ok.yaml"
    p.write_text(PASS_YAML)
    assert mod.check(str(p)) == 0


def test_fail(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(FAIL_YAML)
    assert mod.check(str(p)) == 1
