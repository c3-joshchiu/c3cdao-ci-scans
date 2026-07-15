"""Unit tests for evaluate_security_gate blocking membership."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "scripts/lib/evaluate_security_gate.py"


def _load():
    spec = importlib.util.spec_from_file_location("evaluate_security_gate", MOD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()


def _needs(results: dict[str, str], smoke_ok: str | None = None) -> dict:
    out: dict = {k: {"result": v} for k, v in results.items()}
    if smoke_ok is not None and "cluster-smoke" in out:
        out["cluster-smoke"]["outputs"] = {"smoke_ok": smoke_ok}
    return out


def test_image_only_omits_helm_and_smoke():
    needs = _needs(
        {
            "caller-lint": "success",
            "phase1-build": "success",
            "secrets-scan": "success",
            "vuln-scan": "success",
            "helm-check": "skipped",
            "cluster-smoke": "skipped",
        }
    )
    assert mod.evaluate(needs, image_only=True, extra_containers="") == 0


def test_app_mode_requires_helm_and_smoke_ok():
    needs = _needs(
        {
            "caller-lint": "success",
            "phase1-build": "success",
            "secrets-scan": "success",
            "vuln-scan": "success",
            "helm-check": "success",
            "cluster-smoke": "success",
        },
        smoke_ok="true",
    )
    assert mod.evaluate(needs, image_only=False, extra_containers="") == 0


def test_smoke_continue_on_error_false_green():
    needs = _needs(
        {
            "caller-lint": "success",
            "phase1-build": "success",
            "secrets-scan": "success",
            "vuln-scan": "success",
            "helm-check": "success",
            "cluster-smoke": "success",
        },
        smoke_ok="false",
    )
    assert mod.evaluate(needs, image_only=False, extra_containers="") == 1


def test_extras_blocking_when_declared():
    needs = _needs(
        {
            "caller-lint": "success",
            "phase1-build": "success",
            "secrets-scan": "success",
            "vuln-scan": "success",
            "helm-check": "success",
            "cluster-smoke": "success",
            "build-extra": "failure",
            "vuln-scan-extra": "success",
        },
        smoke_ok="true",
    )
    assert mod.evaluate(needs, image_only=False, extra_containers='[{"name":"x"}]') == 1


def test_empty_extras_not_blocking():
    needs = _needs(
        {
            "caller-lint": "success",
            "phase1-build": "success",
            "secrets-scan": "success",
            "vuln-scan": "success",
            "helm-check": "success",
            "cluster-smoke": "success",
            "build-extra": "skipped",
            "vuln-scan-extra": "skipped",
        },
        smoke_ok="true",
    )
    assert mod.evaluate(needs, image_only=False, extra_containers="") == 0
    assert mod.evaluate(needs, image_only=False, extra_containers="[]") == 0
