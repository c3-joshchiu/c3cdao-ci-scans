# Project Standards — c3cdao-ci-scans

Local copy of `~/.skills/STANDARDS.md` patterns, plus repo-specific decisions.
This file is authoritative for this repo; global standards cover cross-project patterns.

## Stack

- Python 3.11+ scripts under `scripts/lib/` (PEP 723 `uv` single-file deps: pyyaml, jsonschema, python-dotenv)
- Bash orchestrators under `scripts/`
- GitHub Actions reusable workflow is the scan runtime; callers are thin stubs

## Architecture (resolved)

- Reusable workflow (`workflow_call`) = published API; caller `with:` = request args
- Operator YAML (`configs/local/`) = fleet-ops only (target, secrets paths, ruleset, ci-scans ref) — not gate field storage long-term (wrapper-as-SoT redesign in flight)
- Explicit `secrets:` mapping in callers — never `secrets: inherit` across owners
- Schema defaults in `config/schema.json` are the fallback source for gate values today via `gate_value()`

## Static analysis

- Commits must be blocked by pre-commit hooks running `ruff` (format + lint) and `mypy` on `scripts/lib/`.
- Run everything: `uv run pre-commit run -a` (after hooks are installed).

## Planning-system IDs

Identifiers (`ADR-*`, `T-NNN`, `Constitution P\d+`, `Slice N`, gate slugs, `AP-*`) belong in commit messages and PR threads, not in committed source/docstrings/config filenames.
