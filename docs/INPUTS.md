# Inputs

Every field the caller passes via `with:` to the reusable security gate. The
table below is generated from `workflow_call.inputs` by
`scripts/lib/extract_contract.py` and is the published contract — never
hand-edit between the markers; CI rejects drift. Edit the preamble and worked
examples above the markers freely; the generator preserves them.

## Worked examples

### Single-image default

The common case: one backend image built from one Dockerfile. Omit anything you
keep at its default.

```yaml
jobs:
  security-scan:
    uses: c3-joshchiu/c3cdao-ci-scans/.github/workflows/reusable-security-gate.yml@v0.1.0
    with:
      scan_image: app:local
      dockerfile: containers/backend/Dockerfile
      app_path: apps/app/backend
      app_package: app-backend
      app_module: app.main:app
    secrets: inherit
```

### Multi-container (`extra_containers`)

Build and image-scan a worker or sidecar alongside the primary deployable.
`extra_containers` is a JSON array passed as a string; one object per extra
image. Only the primary deployable gets a cluster smoke test.

```yaml
jobs:
  security-scan:
    uses: c3-joshchiu/c3cdao-ci-scans/.github/workflows/reusable-security-gate.yml@v0.1.0
    with:
      scan_image: app:local
      dockerfile: containers/backend/Dockerfile
      extra_containers: |
        [
          {
            "name": "worker",
            "dockerfile": "containers/worker/Dockerfile",
            "context": ".",
            "image": "worker:local",
            "build_args": "APP_PATH=apps/app/worker\nAPP_PACKAGE=app-worker"
          }
        ]
    secrets: inherit
```

### Non-8000 `service_port` / `health_path`

When the backend listens on a non-default port and exposes a non-`/health`
liveness route, set `app_port`, `service_port`, and `health_path` to match the
consumer chart and app.

```yaml
jobs:
  security-scan:
    uses: c3-joshchiu/c3cdao-ci-scans/.github/workflows/reusable-security-gate.yml@v0.1.0
    with:
      scan_image: app:local
      dockerfile: containers/backend/Dockerfile
      app_port: "9090"
      service_port: "80"
      health_path: /api/health
    secrets: inherit
```

## Field reference

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
| `health_path` | string | `/health` | HTTP path the cluster-smoke step probes on the booted primary image (GET must return 200). Set to the app's health/liveness route, e.g. /health, /healthz, /api/health. Primary deployable only — extra_containers get no cluster smoke. |
| `service_port` | string | `8000` | Port the primary backend Kubernetes Service exposes — used as the cluster-smoke `kubectl port-forward` remote port. This is the Service's .spec.ports[].port, which need not equal app_port; defaults to 8000 (today's behavior). |
| `smoke_workload_match` | string | `backend` | Case-insensitive substring identifying the backend Deployment/Service in cluster-smoke (matched against `kubectl get deploy/svc -o name`). Default 'backend'; set to the workload token for charts whose deployment name contains no 'backend' (e.g. agent-template charts). |
| `extra_containers` | string | `""` | JSON array (as a string) of additional containers to build and image-scan beyond the primary deployable — one object per entry: name, dockerfile, context (default '.'), image (default <name>:local), build_args (newline-joined KEY=VALUE string). Default "" means no extra containers (single-image behavior). Structure is validated by the caller lint; context/image defaults are applied in the build-extra job. |
<!-- END GENERATED: security-gate-inputs -->
