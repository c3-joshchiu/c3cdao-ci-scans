# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Evaluate Security Gate blocking membership from needs JSON.

Exit 0 when all blocking jobs succeeded (and cluster-smoke smoke_ok when
applicable). Exit 1 otherwise.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def blocking_jobs(image_only: bool, extra_containers: str) -> list[str]:
    blocking = ["caller-lint", "phase1-build", "secrets-scan", "vuln-scan"]
    if not image_only:
        blocking[3:3] = ["helm-check", "cluster-smoke"]
    extra = extra_containers or ""
    if extra not in ("", "[]"):
        blocking += ["build-extra", "vuln-scan-extra"]
    return blocking


def evaluate(needs: dict[str, Any], image_only: bool, extra_containers: str) -> int:
    blocking = blocking_jobs(image_only, extra_containers)
    bad = {
        k: needs.get(k, {}).get("result")
        for k in blocking
        if needs.get(k, {}).get("result") != "success"
    }
    if bad:
        print("Blocking jobs not successful:", bad)
        return 1
    if "cluster-smoke" in blocking:
        smoke = needs.get("cluster-smoke") or {}
        smoke_ok = (smoke.get("outputs") or {}).get("smoke_ok")
        if smoke_ok != "true":
            print(
                "Blocking cluster-smoke step failed "
                f"(smoke_ok={smoke_ok!r}, result={smoke.get('result')!r})"
            )
            return 1
    print("All blocking security scans passed.")
    return 0


def main() -> None:
    needs = json.loads(os.environ["NEEDS_JSON"])
    image_only = (os.environ.get("IMAGE_ONLY") or "").lower() == "true"
    extra = os.environ.get("EXTRA_CONTAINERS") or ""
    raise SystemExit(evaluate(needs, image_only, extra))


if __name__ == "__main__":
    main()
