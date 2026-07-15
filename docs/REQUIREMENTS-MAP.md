# Requirements map — gate jobs → Game Warden MVP CI spec

Every job in the reusable security gate, traced to the CI requirement it
fulfills and its current enforcement posture.

**Authoritative spec:** [Continuous Integration — Game Warden MVP](https://c3energy.atlassian.net/wiki/spaces/CCA/pages/10839163045/) (Confluence CCA `10839163045`).
**Runbook page:** [CI CD Workflow](https://c3energy.atlassian.net/wiki/spaces/CCA/pages/10910040079/) (Confluence CCA `10910040079`).

Source of truth for the job list is
`.github/workflows/reusable-security-gate.yml`. The
`test_every_job_mapped` drift guard fails if a job ships without a row here.

| Job | Spec gate / requirement | Tool(s) | Target | Current posture | Alignment |
|---|---|---|---|---|---|
| `caller-lint` | (scaffolding pre-flight — not a spec gate) | `lint_caller.py` | caller config | always fail-closed | aligned (guards the gate) |
| `phase1-build` | build hardened image + dual-registry login (CGR and/or Iron Bank) | Docker + CGR/Iron Bank | image | always blocking | aligned |
| `secrets-scan` | Secrets detection | TruffleHog | source | job blocking; finding advisory until `SECURITY_SCAN_BLOCKING=true` | aligned |
| `sast-semgrep` | SAST | Semgrep | source | warn-only (`continue-on-error`) | intentional ramp |
| `sast-sonarqube` | SAST | SonarQube | source | warn-only (`continue-on-error`) | intentional ramp |
| `helm-check` | Helm lint + restricted-PSS | helm + PSS assert | chart | blocking unless `image_only` | aligned |
| `cluster-smoke` | kind deploy + health probe | kind + kubectl | chart+image | skipped when `image_only`; else advisory until `SECURITY_SCAN_BLOCKING=true` | intentional ramp |
| `vuln-scan` | Image + SBOM vuln scan | Trivy (image+source SBOM) + Grype (image+source+image SBOM) | image + SBOM | advisory until `SECURITY_SCAN_BLOCKING=true` | aligned tooling; 1 documented exception (no Trivy-on-image-SBOM: Trivy can't match OS pkgs from a Syft SBOM) |
| `build-extra` | multi-container build (frontend+backend) | Docker matrix | extra images | blocking only when `extra_containers` set | closes spec's "frontend AND backend" |
| `vuln-scan-extra` | multi-container image scan | Trivy/Grype | extra images | blocking only when `extra_containers` set | closes spec's "frontend AND backend" |
| `security-gate` | aggregate required check | — | — | the one required check | aligned |

## Deliberate deviations & path to steady-state

These are intentional posture choices, not gaps to remediate now.

### Warn-only SAST and advisory cluster-smoke/vuln-scan are a verification ramp

Semgrep and SonarQube run warn-only, and cluster-smoke and vuln-scan stay
advisory, until the operator sets the `SECURITY_SCAN_BLOCKING=true` repo
variable. This is a deliberate ramp: it lets a consumer verify the technical
implementation — that every job runs, resolves its inputs, and produces signal —
before findings can block a merge. The spec's "all Phase 2 blocking" state is
reached by flipping `SECURITY_SCAN_BLOCKING=true` as the **final acceptance
step**, taken only after that verification. That flip is the last milestone to
steady-state, never a defect. A skipped, cancelled, or errored blocking job
still fails the gate regardless of the flag, so a broken build can never sign
off green.

### `extra_containers` fulfills the "frontend AND backend" requirement

The spec requires scanning both the frontend **and** backend images. The
primary `phase1-build`/`vuln-scan` path covers the backend; `extra_containers`
(the `build-extra` and `vuln-scan-extra` jobs) builds and image-scans every
additional container — the frontend and any sidecars — so the multi-image
scanning requirement is met. Single-image consumers leave `extra_containers`
empty and those jobs skip cleanly.

### Out of scope for the reusable gate (named, not silently missing)

Two spec items are intentionally owned elsewhere:

- **Stage-2 GHCR publish** — pushing the frontend and backend images to GHCR at
  the short SHA is a publish/release concern, not a PR gate. The reusable gate
  is deliberately push-free (fork-safe, no `packages: write`); images move
  between jobs as artifacts and never reach a registry. GHCR publish is owned by
  the consumer's release workflow.
- **`harden` clean-baseline bootstrap** — the one-time `harden` step that
  establishes a clean SAST/vuln baseline is a bootstrap action run once per repo,
  not a per-PR job. It is a prerequisite the operator runs before flipping
  `SECURITY_SCAN_BLOCKING=true`, not part of the reusable gate.

### Single documented tool exception: no Trivy-on-image-SBOM

`vuln-scan` runs Trivy on the image and the source SBOM, and Grype on the image,
source SBOM, and image SBOM — but deliberately omits Trivy-on-image-SBOM. Trivy
cannot reliably match OS packages from a third-party (Syft) SBOM; it returns
zero OS findings where the direct Trivy image scan finds them. The direct image
scan covers OS CVEs authoritatively, and Grype (same vendor as Syft) validates
the image-SBOM artifact round-trip. This is the one documented coverage
exception, not a miss.
