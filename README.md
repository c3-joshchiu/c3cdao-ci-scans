# c3cdao-ci-scans

Central **monolithic security gate** as a reusable GitHub Actions workflow, plus local onboarding scripts for consumer repos.

## Architecture

```text
c3cdao-ci-scans
└── .github/workflows/reusable-security-gate.yml   ← unified gate logic (workflow_call)

consumer repo
└── .github/workflows/security-gate.yml            ← ~45 lines: triggers + uses: ...@ref
```

**One required branch-protection check:** `security-scan / Security Gate` (the live
job-id-prefixed context; the workflow's display name is `Security Scan / Security Gate`)

## Prerequisites

- `gh`, `jq`, `uv` (config load/validate + caller render run as PEP 723 Python scripts under `scripts/lib/`)
- `gh auth` with **admin** on target repo
- Consumer allows reusable workflows from this repo's owner (`enable-reusable-access.sh` if the callee is private)

## Onboard a repo (local clone)

```bash
git clone https://github.com/<owner>/c3cdao-ci-scans
cd c3cdao-ci-scans

# configs/local/ is gitignored — real configs (org names, local paths) live there
cp configs/examples/example-monorepo.yaml configs/local/my-repo.yaml
# edit target.*, security_gate.*, secrets.env_files, local_path
# (schema-validated at load: typos fail with pathed errors, see config/schema.json)

# Full pilot flow (private consumer):
./scripts/onboard-repo.sh --config configs/local/my-repo.yaml \
  --enable-access --set-secrets --pilot-pr --skip-ruleset

# After Security Scan runs on the PR:
./scripts/discover-check-names.sh --config configs/local/my-repo.yaml --pr <N>
./scripts/smoke-test.sh --config configs/local/my-repo.yaml --pr <N>
./scripts/setup-ruleset.sh --config configs/local/my-repo.yaml        # disabled
./scripts/setup-ruleset.sh --config configs/local/my-repo.yaml --enable  # private repos need a paid org/enterprise plan for rulesets
```

To pilot on a shared repo **without touching its real trunk**, cut a scratch branch
and set `target.trunk_branches: [<scratch>]` + `ruleset.target_branch: <scratch>` —
full walkthrough in the [CI CD Workflow runbook](https://c3energy.atlassian.net/wiki/spaces/CCA/pages/10910040079/CI+CD+Workflow).

### Caller requirements (baked into template)

The generated `security-gate.yml` must grant permissions the reusable workflow needs:

- `pull-requests: write`, `actions: write` (caller is the ceiling — reusable cannot elevate)
- No duplicate `concurrency` on the caller (reusable workflow owns the group)

Live required check name: `security-scan / Security Gate` (job id prefix). Profile `unified-gate` maps this via `check_overrides`.

### Secrets from local `.env`

```bash
# config: secrets.env_files + secrets.names
./scripts/set-secrets.sh --config configs/my-repo.yaml
./scripts/set-secrets.sh --config configs/my-repo.yaml --env-file ../other/.env --dry-run
```

Uses `gh secret set` (encrypts locally). Never commit `.env` files.

| Secret | Job |
|--------|-----|
| `CGR_PULL_TOKEN`, `CGR_PULL_USERNAME` | Phase 1 build (Chainguard bases, primary tier) |
| `IRONBANK_TOKEN`, `IRONBANK_USERNAME` | SonarQube ephemeral + Phase 1 build Iron Bank failover tier |

## Config (`security_gate` inputs)

Injected into the caller stub → `with:` on the reusable workflow:

| Field | Default | Purpose |
|-------|---------|---------|
| `scan_image` | `app:local` | Must match helm values-local |
| `dockerfile` | `containers/backend/Dockerfile` | Phase 1 build |
| `builder_image` / `runtime_image` / `runtime_apks` | Chainguard `cgr.dev/chainguard/python` | Phase 1 build base images |
| `helm_chart_path` | `helm/app` | Helm + cluster smoke |
| `namespace` / `cluster_name` | `app-ci` | kind smoke |
| `app_path` / `app_package` | app backend | Docker build-args |
| `extra_build_args` | `[]` | extra `KEY=VALUE` build-args for Dockerfiles with custom base-image args |
| `require_hardened_bases` | `true` | fail phase1-build without Chainguard/Iron Bank creds; `false` = consumer accepts its own bases |
| `ironbank_builder_image` / `ironbank_runtime_image` | — | builder/runtime overrides used only when the Iron Bank failover tier engages |

### Hardened-base registry failover (phase1-build)

1. `CGR_PULL_TOKEN` set → login `cgr.dev`, Chainguard bases (primary).
2. Else `IRONBANK_TOKEN` set → login `registry1.dso.mil` (Iron Bank), optionally
   swapping to `ironbank_builder_image`/`ironbank_runtime_image`.
3. Else `require_hardened_bases: false` → warn and build on the consumer's own
   bases; otherwise fail (no silent public fallback).

Consumers without a root `Makefile`/`security-helm-secctx` target get the gate's
bundled restricted-PSS assertion in helm-check, and vuln-scan defaults empty
`.trivyignore`/`.grype.yaml` when the consumer doesn't carry them.

See `configs/examples/example-monorepo.yaml`.

## Updating the reusable workflow

`.github/workflows/reusable-security-gate.yml` is hand-maintained. When the upstream source-of-truth workflow it was derived from changes, port the relevant diff manually and re-tag:

```bash
git commit -am "update reusable-security-gate.yml"
git tag v0.x.x && git push --tags
```

Pin consumers: `@v0.x.x` instead of `@main`.

## Scripts

| Script | Purpose |
|--------|---------|
| `onboard-repo.sh` | orchestrator (access, secrets, render, pilot PR, ruleset, smoke) |
| `enable-reusable-access.sh` | set ci_scans `actions/permissions/access` so a private repo can be called cross-repo |
| `set-secrets.sh` | push gate secrets from dotenv via `gh secret set` |
| `prepare-pilot-pr.sh` | clean branch from default + render + PR |
| `render-callers.sh` | write `security-gate.yml` to consumer |
| `setup-ruleset.sh` | create/update `security-scan-gates` ruleset |
| `smoke-test.sh` | pre-enable validation |
| `discover-check-names.sh` | live PR checks vs profile |

## Migrating from modular scans

1. Add the caller via `render-callers.sh` (or use ci-scans reusable + caller only after validation)
2. Delete modular workflows: `secret-scan.yml`, `semgrep.yml`, `sca-scan.yml`, `sonarqube.yml`, `helm-validate.yml`, `pr-gate.yml` (STIG stays separate if still needed)
3. Update ruleset: only `security-scan / Security Gate` required
4. Set repo variable `SECURITY_SCAN_BLOCKING=true` when ready to enforce vuln/cluster gates

## Note on path efficiency

The reusable gate runs all scan jobs on every PR (full gate). Path-based skipping (`detect-changes`) can be added later without changing the onboarding model.
