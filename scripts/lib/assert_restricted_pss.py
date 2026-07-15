# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Assert restricted-PSS securityContext rows on rendered chart YAML.

For every pod spec in the render (Deployment/StatefulSet/DaemonSet/
ReplicaSet/Job/CronJob/Pod), each container and initContainer must
have, at container or pod level:
  - runAsNonRoot: true
  - allowPrivilegeEscalation: false
  - capabilities.drop containing ALL (container level)
  - seccompProfile.type RuntimeDefault or Localhost
"""
import sys
import yaml

WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "Pod"}

def pod_specs(doc):
    kind = doc.get("kind")
    meta = doc.get("metadata", {}).get("name", "?")
    if kind == "Pod":
        yield kind, meta, doc.get("spec", {})
    elif kind in WORKLOAD_KINDS:
        yield kind, meta, doc.get("spec", {}).get("template", {}).get("spec", {})
    elif kind == "CronJob":
        yield kind, meta, (doc.get("spec", {}).get("jobTemplate", {})
                           .get("spec", {}).get("template", {}).get("spec", {}))

def check(path):
    errors = []
    with open(path) as f:
        docs = [d for d in yaml.safe_load_all(f) if isinstance(d, dict)]
    checked = 0
    for doc in docs:
        for kind, name, spec in pod_specs(doc):
            pod_sc = spec.get("securityContext") or {}
            for c in (spec.get("containers") or []) + (spec.get("initContainers") or []):
                checked += 1
                where = f"{kind}/{name} container={c.get('name', '?')}"
                sc = c.get("securityContext") or {}
                def level(key):
                    return sc.get(key, pod_sc.get(key))
                if level("runAsNonRoot") is not True:
                    errors.append(f"{where}: runAsNonRoot must be true")
                if sc.get("allowPrivilegeEscalation") is not False:
                    errors.append(f"{where}: allowPrivilegeEscalation must be false")
                drops = [str(x).upper() for x in (sc.get("capabilities") or {}).get("drop") or []]
                if "ALL" not in drops:
                    errors.append(f"{where}: capabilities.drop must include ALL")
                seccomp = (level("seccompProfile") or {}).get("type")
                if seccomp not in ("RuntimeDefault", "Localhost"):
                    errors.append(f"{where}: seccompProfile.type must be RuntimeDefault or Localhost")
    if checked == 0:
        errors.append("no pod specs found in rendered chart — nothing was asserted")
    for e in errors:
        print(f"::error::restricted-PSS: {e}")
    print(f"restricted-PSS: {checked} container(s) checked, {len(errors)} violation(s)")
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(check(sys.argv[1]))
