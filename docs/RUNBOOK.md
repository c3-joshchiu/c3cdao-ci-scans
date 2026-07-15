# Onboarding runbook

Copy-and-own onboarding for the c3cdao-ci-scans security gate: copy the caller,
edit `with:`, set the four secrets, create and enable the ruleset, pilot on a
scratch branch, then promote to trunk. Every step is version-pinned and
copy-paste-able.

For the requirement-by-requirement traceability, see
[REQUIREMENTS-MAP.md](REQUIREMENTS-MAP.md). For the field reference, see the
Inputs table in the [README](../README.md).

## 1. Prerequisites

The gate assumes this app shape:

- the app serves `GET /health` (cluster-smoke probes it after the helm install)
- a single-image helm deploy — one backend image built, scanned, kind-loaded,
  and installed (add `extra_containers` for frontend/sidecar images)
- an ASGI backend describable by the `app_*` inputs (`app_path`, `app_package`,
  `app_module`, `app_port`)

Tooling: `gh` (authenticated), `uv`, and **admin** on the consumer repo (secrets
and rulesets).

## 2. Copy the caller template (commit 1)

```bash
cd <consumer-repo>
mkdir -p .github/workflows
cp <ci-scans-clone>/templates/callers/security-gate.yml .github/workflows/security-gate.yml
```

You own this file from here — no tooling ever rewrites it.

## 3. Edit `with:` (commit 2)

Every `with:` line in the template carries an inline provenance comment naming
where its value must come from in your repo (Dockerfile ARG, helm values file,
package metadata, or operator choice). Edit each to match, and set your trigger
branches under `on.pull_request.branches`.

Two invariants the caller lint enforces — do not break them:

- Keep the job id `security-scan`. It is half of the required check context
  `security-scan / Security Gate`; renaming it silently un-gates merges.
- Pass secrets **explicitly** (`CGR_PULL_TOKEN: ${{ secrets.CGR_PULL_TOKEN }}`),
  never the `inherit` form. `inherit` works only when caller and callee share an
  org/enterprise; across owners it silently passes nothing and SonarQube dies at
  setup with `Unexpected value ''`.

### Version pin

The template ships with `@main` for the pilot window. In production, pin a
release tag:

```yaml
uses: c3-joshchiu/c3cdao-ci-scans/.github/workflows/reusable-security-gate.yml@v0.1.0
```

`@main` is acceptable only during the pilot migration window.

## 4. Set the four secrets (one-time)

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
| `CGR_PULL_TOKEN`, `CGR_PULL_USERNAME` | Phase 1 build — Chainguard (`cgr.dev`) login |
| `IRONBANK_TOKEN`, `IRONBANK_USERNAME` | SonarQube ephemeral + Phase 1 / build-extra Iron Bank (`registry1.dso.mil`) login — can run **alongside** Chainguard when both are set |

## 5. Create and enable the ruleset

From the ci-scans clone. `configs/local/` is gitignored — real ops configs (org
names, local paths) live there.

```bash
cp configs/examples/example-monorepo.yaml configs/local/<repo>.yaml
# edit target.* / ci_scans.* / ruleset.*

./scripts/setup-ruleset.sh --config configs/local/<repo>.yaml            # create, disabled
./scripts/setup-ruleset.sh --config configs/local/<repo>.yaml --enable   # enforce
```

`setup-ruleset.sh` creates the `security-scan-gates` ruleset **disabled** by
default (safe rollout); `--enable` sets it to active so
`security-scan / Security Gate` becomes a required check. Private repos need a
paid org/enterprise plan to enforce. Add `--dry-run` to preview the API payload
without writing.

The ops YAML is schema-validated at load (typos fail with pathed errors; see
`config/schema.json`) and carries **operations-only** fields: `target`,
`ci_scans`, `ruleset`, plus optional `workflows` and `secrets`. Gate values live
in your caller's `with:`, not here — a leftover `security_gate:` block is
deprecated and ignored with a warning.

## 6. Open a PR — the observable outcome

The check context **`security-scan / Security Gate`** appears on the PR and goes
green. The gate's `caller-lint` job runs first and names any scaffold violation
in your copied caller before anything scans.

List the live check names on a PR head (e.g. to verify a ruleset paste by eye):

```bash
gh api repos/<owner>/<repo>/commits/<sha>/check-runs --jq '.check_runs[].name'
```

Run the caller lint locally before you push:

```bash
uv run scripts/lib/lint_caller.py <caller.yml> \
  --contract contract/security-gate.schema.json \
  [--consumer-root <consumer-checkout>]
```

## 7. Pilot on a scratch branch, then promote to trunk

To pilot on a shared repo without touching its real trunk, cut a scratch branch
and scope both the trigger and the ruleset to it:

- caller: `on.pull_request.branches: [<scratch>]`
- ops YAML: `target.trunk_branches: [<scratch>]` and
  `ruleset.target_branch: <scratch>` (the ruleset then targets that literal ref,
  independent of the repo's default branch)

Full scratch-branch walkthrough:
[CI CD Workflow runbook](https://c3energy.atlassian.net/wiki/spaces/CCA/pages/10910040079/).

When the pilot is green, **promote** it to the repo's default branch:

1. In the caller, point the trigger branches at the trunk
   (`on.pull_request.branches: [main]`).
2. Re-target the ruleset: drop `ruleset.target_branch` from the ops YAML (or set
   it to the default branch) and re-run
   `./scripts/setup-ruleset.sh --config configs/local/<repo>.yaml --enable`.
3. Pin the caller's `uses:` to a release tag if it was still on `@main`.

## 8. Enforcement model (two knobs)

- **Ruleset enable** (per-consumer): `setup-ruleset.sh --enable` makes
  `security-scan / Security Gate` a required check on the target branch.
- **`SECURITY_SCAN_BLOCKING` repo variable** (gate-internal): hard-fail posture
  for cluster-smoke and vuln-scan. Until it is `true` they warn instead of
  failing; a skipped/cancelled/errored blocking job still fails the gate.
  Flipping it to `true` is the **final** acceptance step — see
  [REQUIREMENTS-MAP.md](REQUIREMENTS-MAP.md).

```bash
gh variable set SECURITY_SCAN_BLOCKING --body true --repo <owner>/<repo>
```

## Caller requirements and lint

Your `security-gate.yml` caller must grant the permissions the reusable workflow
needs:

- `pull-requests: write`, `actions: write` — the caller is the ceiling; the
  reusable workflow cannot elevate.
- No `concurrency:` on the caller — the reusable workflow owns the group.
- Secrets passed **explicitly**, never the `inherit` form (see §3).

`caller-lint` is a fail-closed configuration pre-flight: it resolves your caller
and lints it against the published contract before anything scans. Rule ids:
`no-secrets-inherit`, `no-caller-concurrency`, `unknown-input`, `type-mismatch`,
`missing-secret-map`, `image-values-mismatch`, `unreadable-caller`, plus the
`extra_containers` entry validators `extra-containers-json`,
`extra-containers-name`, `extra-containers-duplicate`,
`extra-containers-dockerfile`, `extra-containers-template-path`,
`extra-containers-target`, `extra-containers-build-arg`. A non-failing style notice
`extra-containers-format` fires when the array is packed onto one quoted line —
prefer a multiline YAML `|` block (see [INPUTS.md](INPUTS.md)). Rules skipped
for a stated reason announce on stderr (`notice: skip: image-values-mismatch:
--consumer-root not given`); with a consumer checkout supplied, the values-file
rule announces `notice: active: image-values-mismatch: checked <path>`. The
check parses values-local as YAML: a string `image` equal to `scan_image`, or
`repository` + `tag` that join to it, both pass; a comment-only mention does not.
Run it
locally:

```bash
uv run scripts/lib/lint_caller.py <caller.yml> \
  --contract contract/security-gate.schema.json \
  [--consumer-root <consumer-checkout>]
```

## Hardened-base registry login (phase1-build + build-extra)

Logins are **independent** (docker stores credentials per registry host). Setting
both `CGR_PULL_*` and `IRONBANK_*` authenticates **both** in one run — required
for mixed-base repos (e.g. Chainguard primary + Iron Bank `extra_containers`).

1. `CGR_PULL_TOKEN` set → login `cgr.dev`.
2. `IRONBANK_TOKEN` set → login `registry1.dso.mil` (does **not** require CGR to
   be absent).
3. **Primary-base image swap** (separate from login): only when Chainguard is
   *absent* and Iron Bank is *present*, the primary builder/runtime may swap to
   `ironbank_builder_image` / `ironbank_runtime_image`. With both creds set, the
   primary keeps its Chainguard bases; extras pull Iron Bank bases via the
   second login.
4. Neither credential → `require_hardened_bases: false` warns and builds on the
   consumer's own bases; otherwise fail (no silent public fallback).

Consumers without a root `Makefile`/`security-helm-secctx` target get the gate's
bundled restricted-PSS assertion in helm-check, and vuln-scan defaults empty
`.trivyignore`/`.grype.yaml` when the consumer doesn't carry them.

## Updating the reusable workflow

`.github/workflows/reusable-security-gate.yml` is hand-maintained. When the
upstream source-of-truth workflow it was derived from changes, port the relevant
diff manually and re-tag:

```bash
git commit -am "update reusable-security-gate.yml"
git tag v0.x.x && git push --tags
```

Pin consumers at `@v0.x.x` instead of `@main`.

The `contract-extract` pre-commit hook regenerates
`contract/security-gate.schema.json` and `docs/INPUTS.md` whenever the reusable
workflow changes, and CI fails on drift even when the hook is skipped — the
contract is derived output, never hand-edited.

ci-scans is public; if it ever goes private, this repo (the callee) must allow
cross-repo reusable-workflow access (Settings → Actions → Access) before
consumers can call it.

## Scripts

| Script | Purpose |
|--------|---------|
| `setup-ruleset.sh` | create/update the `security-scan-gates` ruleset (disabled by default; `--enable` to enforce) |

`scripts/lib/` holds the internals: config load/validate and the dotenv reader
(PEP 723 Python run via `uv`), the contract extractor (`extract_contract.py`),
and the caller linter (`lint_caller.py`, also run in-gate as `caller-lint`).

## Migrating from modular scans

1. Add the caller: copy `templates/callers/security-gate.yml` and edit `with:`
   (steps 2–3 above).
2. Delete modular workflows: `secret-scan.yml`, `semgrep.yml`, `sca-scan.yml`,
   `sonarqube.yml`, `helm-validate.yml`, `pr-gate.yml` (STIG stays separate if
   still needed).
3. Update the ruleset: only `security-scan / Security Gate` required.
4. Set repo variable `SECURITY_SCAN_BLOCKING=true` when ready to enforce
   vuln/cluster gates (see §8).

## Note on path efficiency

The reusable gate runs all scan jobs on every PR (full gate). Path-based skipping
(`detect-changes`) can be added later without changing the onboarding model.
