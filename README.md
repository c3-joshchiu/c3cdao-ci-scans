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
job-id-prefixed context; the workflow's display name is `Security Scan / Security Gate`)

## Onboarding runbook

### 1. Prerequisites

Structural — the gate assumes this app shape:

- the app serves `GET /health` (cluster-smoke probes it after the helm install)
- a single-image helm deploy (one backend image is built, scanned, kind-loaded, and installed)
- an ASGI backend describable by the `app_*` inputs (`app_path`, `app_package`, `app_module`, `app_port`)

Tooling: `gh` (authenticated), `uv`, and **admin** on the consumer repo (secrets + rulesets).

### 2. Copy the caller template (commit 1)

```bash
cd <consumer-repo>
mkdir -p .github/workflows
cp <ci-scans-clone>/templates/callers/security-gate.yml .github/workflows/security-gate.yml
```

You own this file from here — no tooling ever rewrites it.

### 3. Edit `with:` (commit 2)

Every `with:` line in the template carries an inline provenance comment saying where
its value must come from in your repo (Dockerfile ARG, helm values file, package
metadata, or operator choice). Edit the values to match, and set your trigger
branches under `on.pull_request.branches`. Keep the job id `security-scan` —
renaming it silently changes the required check context and un-gates merges.
Full field reference: the [Inputs](#inputs) table below.

### 4. One-time secrets

```bash
gh secret set CGR_PULL_TOKEN     --repo <owner>/<repo>
gh secret set CGR_PULL_USERNAME  --repo <owner>/<repo>
gh secret set IRONBANK_TOKEN     --repo <owner>/<repo>
gh secret set IRONBANK_USERNAME  --repo <owner>/<repo>
```

These four names are exactly what the workflow declares (not the older
`*_IDENTITY`/`*_CLI_SECRET` spellings). UI alternative: Settings → Secrets and
variables → Actions → New repository secret.

| Secret | Job |
|--------|-----|
| `CGR_PULL_TOKEN`, `CGR_PULL_USERNAME` | Phase 1 build (Chainguard bases, primary tier) |
| `IRONBANK_TOKEN`, `IRONBANK_USERNAME` | SonarQube ephemeral + Phase 1 build Iron Bank failover tier |

### 5. Ruleset

From the ci-scans clone:

```bash
# configs/local/ is gitignored — real ops configs (org names, local paths) live there
cp configs/examples/example-monorepo.yaml configs/local/<repo>.yaml
# edit target.* / ci_scans.* / ruleset.*

./scripts/setup-ruleset.sh --config configs/local/<repo>.yaml           # create, disabled
./scripts/setup-ruleset.sh --config configs/local/<repo>.yaml --enable  # enforce (private repos need a paid org/enterprise plan)
```

The ops YAML is schema-validated at load (typos fail with pathed errors; see
`config/schema.json`) and carries **operations-only** fields: `target`, `ci_scans`,
`ruleset`, plus optional `workflows` and `secrets`. Gate values live in your
caller's `with:`, not here — a leftover `security_gate:` block is deprecated and
ignored with a warning telling you to remove it.

### 6. Open a PR — the observable outcome

The check context **`security-scan / Security Gate`** appears on the PR and goes
green. The gate's `caller-lint` job runs first and names any scaffold violation in
your copied caller before anything scans (see [Caller lint](#caller-lint)).

To list the live check names on a PR head (e.g. to verify a ruleset paste by eye):

```bash
gh api repos/<owner>/<repo>/commits/<sha>/check-runs --jq '.check_runs[].name'
```

### Promote a scratch-branch pilot to main

To pilot on a shared repo without touching its real trunk, cut a scratch branch and
set `target.trunk_branches: [<scratch>]` + `ruleset.target_branch: <scratch>` —
full walkthrough in the [CI CD Workflow runbook](https://c3energy.atlassian.net/wiki/spaces/CCA/pages/10910040079/CI+CD+Workflow).
When the pilot is done, promote it to the repo's default branch:

1. In the caller, point the trigger branches at the trunk (`on.pull_request.branches: [main]`).
2. Re-target the ruleset: drop `ruleset.target_branch` from the ops YAML (or set it
   to the default branch) and re-run `./scripts/setup-ruleset.sh --config … --enable`.

## Caller requirements (baked into the template)

Your `security-gate.yml` caller must grant the permissions the reusable workflow needs:

- `pull-requests: write`, `actions: write` (caller is the ceiling — reusable cannot elevate)
- No `concurrency:` on the caller (the reusable workflow owns the group)
- Secrets passed **explicitly**, never the inherit form — inherit only works when
  caller and callee share an org/enterprise; across owners it silently passes
  nothing (callee sees empty secrets, SonarQube dies at setup with `Unexpected value ''`)

### Caller lint

The gate's first job (`caller-lint`) resolves your caller file and lints it against
the published contract — fail closed; nothing scans until it passes. Rule ids:
`no-secrets-inherit`, `no-caller-concurrency`, `unknown-input`, `type-mismatch`,
`missing-secret-map`, `image-values-mismatch`, `unreadable-caller`. Rules skipped
for a stated reason announce themselves on stderr (`notice: skip: image-values-mismatch:
--consumer-root not given`); with a consumer checkout supplied, the values-file rule
announces `notice: active: image-values-mismatch: checked <path>`. Run it locally:

```bash
uv run scripts/lib/lint_caller.py <caller.yml> --contract contract/security-gate.schema.json \
  [--consumer-root <consumer-checkout>]
```

## Pin policy

Consumers pin a release tag — `uses: …/reusable-security-gate.yml@vX.Y.Z`.
`@main` is acceptable only during the pilot migration window.

## Two-knob enforcement model

- **Ruleset enable** (per-consumer): `setup-ruleset.sh --enable` makes
  `security-scan / Security Gate` a required check on the target branch.
- **`SECURITY_SCAN_BLOCKING` repo variable** (gate-internal): hard-fail posture for
  cluster-smoke and vuln-scan. Until it is `true` they warn instead of failing —
  but a skipped/cancelled/errored blocking job still fails the gate.

## Inputs

Passed via the caller's `with:` to the reusable workflow. This table is generated
from `workflow_call.inputs` by `scripts/lib/extract_contract.py` — never hand-edit
between the markers (CI rejects drift).

<!-- BEGIN GENERATED: security-gate-inputs -->
| Input | Type | Default | Where the value comes from |
| --- | --- | --- | --- |
| `scan_image` | string | `app:local` | Local-daemon tag the image is built and scanned under; must match the backend image tag in the consumer's helm values-local file (the pullPolicy: Never pair — cluster-smoke kind-loads this exact tag). |
| `dockerfile` | string | `containers/backend/Dockerfile` | Path to the backend Dockerfile in the consumer repo. |
| `builder_image` | string | `cgr.dev/chainguard/python:latest-dev` | Build-stage base image, passed as the Dockerfile's BUILDER_IMAGE build ARG; must match the builder base ARG in the consumer's Dockerfile. |
| `runtime_image` | string | `cgr.dev/chainguard/python:latest` | Runtime-stage base image, passed as the Dockerfile's RUNTIME_IMAGE build ARG; must match the runtime base ARG in the consumer's Dockerfile. |
| `runtime_apks` | string | `""` | Extra runtime packages, passed as the Dockerfile's RUNTIME_APKS build ARG; set only when the consumer Dockerfile's runtime stage installs apks. |
| `extra_build_args` | string | `""` | Newline-separated KEY=VALUE pairs appended to the Docker build-args — for consumer Dockerfiles whose base-image args aren't BUILDER_IMAGE/RUNTIME_IMAGE (e.g. ppubs' PYTHON_DEV/PYTHON_RUN/NODE_DEV). |
| `require_hardened_bases` | boolean | `true` | Hardened-base policy — operator posture decision, not read from a consumer file. true (default): fail phase1-build when neither Chainguard nor Iron Bank credentials are configured. false: warn and build with the consumer-specified bases (pilot escape hatch — the consumer explicitly owns that posture). |
| `ironbank_registry` | string | `registry1.dso.mil` | Iron Bank registry host, used only when the Iron Bank failover tier engages (no CGR credentials); operator decision, defaults to the DoD registry. |
| `ironbank_builder_image` | string | `""` | Optional Iron Bank replacement for builder_image, used only when the Iron Bank failover tier engages (no CGR credentials); left empty, the consumer's builder_image passes through. |
| `ironbank_runtime_image` | string | `""` | Optional Iron Bank replacement for runtime_image, used only when the Iron Bank failover tier engages (no CGR credentials); left empty, the consumer's runtime_image passes through. |
| `helm_chart_path` | string | `helm/app` | Path to the consumer's helm chart directory — the helm lint/template target and the cluster-smoke install source. |
| `helm_values_file` | string | `helm/app/values.yaml` | Path to the consumer chart's base values file, used by helm lint and template. |
| `helm_values_local_file` | string | `helm/app/values-local.yaml` | Path to the consumer chart's local-overrides values file, layered onto the cluster-smoke helm install; its backend image tag must equal scan_image with pullPolicy: Never. |
| `helm_release_name` | string | `app-ci` | Helm release name for template and the cluster-smoke install; operator choice, no consumer-file counterpart. |
| `cluster_name` | string | `app-ci` | kind cluster name cluster-smoke creates and loads the image into; operator choice, no consumer-file counterpart. |
| `namespace` | string | `app-ci` | Kubernetes namespace cluster-smoke deploys the release into; operator choice, no consumer-file counterpart. |
| `secctx_make_target` | string | `security-helm-secctx` | Name of the consumer Makefile target that asserts pod security contexts; skipped with a notice when the consumer Makefile lacks it. |
| `app_path` | string | `apps/app/backend` | Consumer repo path to the backend app directory, passed as the Dockerfile's APP_PATH build ARG. |
| `app_package` | string | `app-backend` | Backend package dist name, passed as the Dockerfile's APP_PACKAGE build ARG; must match the consumer backend's package metadata. |
| `app_module` | string | `app.main:app` | ASGI entrypoint as module:attr, passed as the Dockerfile's APP_MODULE build ARG; must match the consumer backend's app object. |
| `app_port` | string | `8000` | Container port the backend listens on, passed as the Dockerfile's APP_PORT build ARG; must match the consumer chart's backend service/probe port. |
<!-- END GENERATED: security-gate-inputs -->

### Hardened-base registry failover (phase1-build)

1. `CGR_PULL_TOKEN` set → login `cgr.dev`, Chainguard bases (primary).
2. Else `IRONBANK_TOKEN` set → login `registry1.dso.mil` (Iron Bank), optionally
   swapping to `ironbank_builder_image`/`ironbank_runtime_image`.
3. Else `require_hardened_bases: false` → warn and build on the consumer's own
   bases; otherwise fail (no silent public fallback).

Consumers without a root `Makefile`/`security-helm-secctx` target get the gate's
bundled restricted-PSS assertion in helm-check, and vuln-scan defaults empty
`.trivyignore`/`.grype.yaml` when the consumer doesn't carry them.

## Updating the reusable workflow

`.github/workflows/reusable-security-gate.yml` is hand-maintained. When the upstream source-of-truth workflow it was derived from changes, port the relevant diff manually and re-tag:

```bash
git commit -am "update reusable-security-gate.yml"
git tag v0.x.x && git push --tags
```

Pin consumers: `@v0.x.x` instead of `@main`.

The `contract-extract` pre-commit hook regenerates
`contract/security-gate.schema.json` and this README's inputs table whenever the
reusable workflow changes, and CI fails on drift even when the hook is skipped —
the contract is derived output, never hand-edited.

ci-scans is public; if it ever goes private, this repo (the callee) must allow
cross-repo reusable-workflow access (Settings → Actions → Access) before consumers
can call it.

## Scripts

| Script | Purpose |
|--------|---------|
| `setup-ruleset.sh` | create/update the `security-scan-gates` ruleset (disabled by default; `--enable` to enforce) |

`scripts/lib/` holds the internals: config load/validate and the dotenv reader
(PEP 723 Python run via `uv`), the contract extractor (`extract_contract.py`), and
the caller linter (`lint_caller.py`, also run in-gate as `caller-lint`).

## Migrating from modular scans

1. Add the caller: copy `templates/callers/security-gate.yml` and edit `with:` (runbook above)
2. Delete modular workflows: `secret-scan.yml`, `semgrep.yml`, `sca-scan.yml`, `sonarqube.yml`, `helm-validate.yml`, `pr-gate.yml` (STIG stays separate if still needed)
3. Update ruleset: only `security-scan / Security Gate` required
4. Set repo variable `SECURITY_SCAN_BLOCKING=true` when ready to enforce vuln/cluster gates

## Note on path efficiency

The reusable gate runs all scan jobs on every PR (full gate). Path-based skipping (`detect-changes`) can be added later without changing the onboarding model.
