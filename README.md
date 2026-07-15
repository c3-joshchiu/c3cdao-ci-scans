# c3cdao-ci-scans

Central **monolithic security gate** as a reusable GitHub Actions workflow. Consumers copy a small caller workflow into their repo and own it from then on — no generators, no per-repo scripting.

## Architecture

```text
c3cdao-ci-scans
├── .github/workflows/reusable-security-gate.yml   ← unified gate logic (workflow_call)
├── templates/callers/security-gate.yml            ← copy-and-own caller template
└── contract/security-gate.schema.json             ← published inputs contract (generated)

consumer repo
└── .github/workflows/security-gate.yml            ← your copy: triggers + with: + uses: ...@ref
```

**One required branch-protection check:** `security-scan / Security Gate` (the live
job-id-prefixed context; the workflow's display name is `Security Scan / Security Gate`).

## Quickstart

Six steps to a gated repo. Full commands and provenance: [docs/RUNBOOK.md](docs/RUNBOOK.md).
Field reference for every `with:` value: [docs/INPUTS.md](docs/INPUTS.md).

1. **Prerequisites.** `gh` (authenticated), `uv`, and **admin** on the consumer repo
   (secrets + rulesets). The gate's app-shape settings are defaults, all overridable:
   single backend image, `GET /health`, port 8000. Add frontend/sidecar images with
   `extra_containers`, and set `health_path`, `service_port`, `smoke_workload_match`
   to match your chart and app ([docs/INPUTS.md](docs/INPUTS.md)).
2. **Copy the caller.**
   `cp <ci-scans-clone>/templates/callers/security-gate.yml .github/workflows/security-gate.yml`.
   You own it from here — no tooling ever rewrites it.
3. **Edit `with:`.** Each line carries an inline provenance comment (Dockerfile ARG,
   helm values, package metadata, or operator choice). Keep the job id `security-scan` —
   renaming it silently un-gates merges. Pass secrets explicitly, never `inherit`.
4. **Set the four secrets.** `CGR_PULL_TOKEN`, `CGR_PULL_USERNAME`, `IRONBANK_TOKEN`,
   `IRONBANK_USERNAME` — via `gh secret set --repo <owner>/<repo>` or Settings → Secrets
   and variables → Actions → New repository secret.
5. **Create the ruleset.** This creates a GitHub **repository ruleset** that makes
   `security-scan / Security Gate` a required status check on your trunk branch:
   ```bash
   ./scripts/setup-ruleset.sh --config configs/local/<repo>.yaml           # create, disabled
   ./scripts/setup-ruleset.sh --config configs/local/<repo>.yaml --enable  # enforce
   ```
6. **Open a PR.** The `security-scan / Security Gate` context appears and goes green.
   Pilot on a scratch branch first, then promote to trunk ([docs/RUNBOOK.md](docs/RUNBOOK.md)).

## Caller lint

The gate's first job (`caller-lint`) is a **fail-closed configuration pre-flight**: it
validates your copied caller's `with:` inputs, secret mappings, and structure against the
published contract. Nothing scans until it passes — it is not a security scanner. Rule ids
and local invocation: [docs/RUNBOOK.md](docs/RUNBOOK.md).

## Pin policy

Consumers pin a release tag — `uses: …/reusable-security-gate.yml@vX.Y.Z`. `@main` is
acceptable only during the pilot migration window.

## Docs

- [docs/RUNBOOK.md](docs/RUNBOOK.md) — full onboarding, ruleset provenance, enforcement
  model, caller-lint rule ids, hardened-base login (dual registry), scan boundary /
  proxy-scan posture, and maintenance.
- [docs/INPUTS.md](docs/INPUTS.md) — every `with:` field with type, default, and provenance.
- [docs/REQUIREMENTS-MAP.md](docs/REQUIREMENTS-MAP.md) — gate jobs mapped to the CI spec.
