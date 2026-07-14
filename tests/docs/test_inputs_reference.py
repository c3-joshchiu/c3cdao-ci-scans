"""DOC-2 guards: the generated inputs reference lives in docs/INPUTS.md.

Covers the generator retarget (README -> docs/INPUTS.md), the preserved
hand-written preamble, generator idempotency, and the CI drift-guard path.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INPUTS_DOC = REPO_ROOT / "docs" / "INPUTS.md"
README = REPO_ROOT / "README.md"
SCHEMA = REPO_ROOT / "contract" / "security-gate.schema.json"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
GENERATOR = REPO_ROOT / "scripts" / "lib" / "extract_contract.py"

BEGIN_MARKER = "<!-- BEGIN GENERATED: security-gate-inputs -->"
MARKER_STEM = "GENERATED: security-gate-inputs"


def _run_generator() -> None:
    subprocess.run(
        ["uv", "run", str(GENERATOR)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )


def test_table_in_inputs_doc():
    """AC-1: the generated block's BEGIN marker is present in docs/INPUTS.md."""
    _run_generator()
    assert BEGIN_MARKER in INPUTS_DOC.read_text()


def test_no_table_in_readme():
    """AC-2: neither generated marker remains in the README."""
    assert MARKER_STEM not in README.read_text()


def test_all_inputs_documented():
    """AC-3: every contract input key appears in docs/INPUTS.md."""
    _run_generator()
    keys = set(json.loads(SCHEMA.read_text())["properties"])
    text = INPUTS_DOC.read_text()
    missing = {k for k in keys if k not in text}
    assert not missing, f"inputs absent from docs/INPUTS.md: {sorted(missing)}"
    assert keys <= set(k for k in keys if k in text)


def test_generator_idempotent():
    """AC-4: two consecutive runs leave docs/INPUTS.md byte-identical."""
    _run_generator()
    first = INPUTS_DOC.read_bytes()
    _run_generator()
    second = INPUTS_DOC.read_bytes()
    assert first == second


def test_readme_pointer():
    """AC-7: the README points readers at docs/INPUTS.md."""
    assert "docs/INPUTS.md" in README.read_text()


def test_preamble_preserved():
    """AC-8: the hand-written 'Worked examples' section survives regeneration."""
    assert "Worked examples" in INPUTS_DOC.read_text()
    _run_generator()
    assert "Worked examples" in INPUTS_DOC.read_text()


def test_ci_drift_targets_inputs_doc():
    """AC-5: the CI drift guard diffs docs/INPUTS.md, not the README."""
    text = CI_YML.read_text()
    assert "docs/INPUTS.md" in text
    assert "exit-code contract/ README.md" not in text


if __name__ == "__main__":
    sys.exit(subprocess.call(["pytest", "-q", __file__]))
