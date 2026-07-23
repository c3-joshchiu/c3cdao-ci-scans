# Consumer build contract (`use_ci_contract`)

Opt-in (default **off**): set `use_ci_contract: true` on the caller and the
gate stops owning your build knowledge (dockerfile/context/target/`APP_*`
inputs, secctx make target, inline smoke scaffold). Instead it drives four
make targets in a contract makefile you own (`contract_file`, default
`Makefile.ci`, path relative to your repo root). Start from
[`templates/consumer/Makefile.ci`](../templates/consumer/Makefile.ci) — it
reproduces the gate's default behavior; edit it for your repo.

With the flag **false** (default) nothing changes: the legacy input-driven
path runs exactly as before.

## Target interface

| Target | Invocation | Env provided by the gate |
| --- | --- | --- |
| `ci-manifest` | `make -s -f <contract_file> ci-manifest` | — |
| `ci-build` | `make -f <contract_file> ci-build IMAGE=<name>` | `CI_BUILDER_BASE`, `CI_RUNTIME_BASE`, `CI_IMAGE_TAG` |
| `ci-secctx` | `make -f <contract_file> ci-secctx` | — |
| `ci-smoke-env` | `make -f <contract_file> ci-smoke-env NAMESPACE=<ns>` | — |

- **`ci-manifest`** prints a JSON document to stdout:

  ```json
  {
    "images": [{"name": "...", "dockerfile": "...", "context": "...",
                "target": "...", "build_args": "KEY=VALUE\n..."}],
    "chart":  {"path": "...", "values": "...", "values_local": "...",
               "release": "...", "namespace": "..."},
    "health": {"path": "...", "port": "...", "workload_match": "..."}
  }
  ```

  `images[0]` is the **primary** — the gate tags it with its `scan_image`
  input. `images[1:]` are the extras, tagged `<name>:local`. On the contract
  path the manifest is the single source of truth for the containers list:
  the `extra_containers` input is **ignored** (one owner, no merge rules).
- **`ci-build IMAGE=<name>`** must produce the local-daemon tag the gate
  passes as `CI_IMAGE_TAG`. `CI_BUILDER_BASE` / `CI_RUNTIME_BASE` are the
  hardened base images after the gate's registry-login failover resolution
  (Chainguard / Iron Bank) — consume them as your base-image build args.
  The gate verifies the tag exists after the target runs, then SBOMs,
  saves, and uploads the image exactly as on the legacy path.
- **`ci-secctx`** is your own pod-security assertion (what
  `secctx_make_target` invoked on the legacy path). A missing target is a
  notice, not a failure. **The gate's bundled restricted-PSS assertion
  still runs in-gate on both paths** — it is gate policy and cannot be
  edited out of a consumer contract file.
- **`ci-smoke-env NAMESPACE=<ns>`** provisions cluster-smoke prerequisites
  before `helm install`: the reference implementation deploys the pgvector
  Postgres + Service, creates the `app-database-url` secret, and installs
  the Gateway API CRDs (the scaffold the gate previously ran inline). The
  gate has already created the namespace and kind-loaded the built images;
  `smoke_secrets` are still created by the gate on both paths.

## Caller lint

When `use_ci_contract: true`, `lint_caller.py` additionally validates the
contract file **warn-only** (stderr notices, never failures):
`ci-contract-file` (file missing), `ci-contract-target` (`make -n` cannot
resolve one of the four targets), `ci-contract-manifest` (`ci-manifest`
output missing required JSON keys).
