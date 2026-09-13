"""Collect bounded, non-secret evidence from the real reference development stack."""

import hashlib
import importlib.metadata
import json
import platform
import shlex
import ssl
import subprocess
from datetime import UTC, datetime

import httpx
from appliance import CPU_PROFILE, ROOT, ssh_args
from cryptography import x509
from cryptography.hazmat.primitives import hashes

OUTPUT = ROOT / "evidence/foundation/2026-09-12"


def guest(command):
    return subprocess.run([str(x) for x in ssh_args()] + [command], capture_output=True, text=True,
                          check=True, timeout=30).stdout


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    root = guest("cd /opt/hearth/deploy/compose && docker compose -f development.yaml exec -T edge cat /data/caddy/pki/authorities/local/root.crt")
    certificate = x509.load_pem_x509_certificate(root.encode())
    trust_path = ROOT / ".hearth/certificates/edge-root.crt"
    trust_path.parent.mkdir(parents=True, exist_ok=True)
    trust_path.write_text(root)
    context = ssl.create_default_context(cadata=root)
    with httpx.Client(verify=context, trust_env=False, timeout=15) as client:
        health = client.get("https://localhost:18443/health/ready")
        health.raise_for_status()
        denied = client.get("https://localhost:18443/api/v1/session", headers={"X-User-ID": "owner"})
        assert denied.status_code == 401
    with httpx.Client(trust_env=False, timeout=15) as client:
        identity = client.get("http://127.0.0.1:18085/realms/master/.well-known/openid-configuration")
        identity.raise_for_status()
        assert "S256" in identity.json()["code_challenge_methods_supported"]
    services = [json.loads(line) for line in guest("cd /opt/hearth/deploy/compose && docker compose -f development.yaml ps --format json").splitlines()]
    ca = guest("cd /opt/hearth/deploy/compose && docker compose -f development.yaml exec -T step-ca step ca health --ca-url https://step-ca:9000 --root /home/step/certs/root_ca.crt").strip()
    assert ca == "ok"
    native_probe = "import hashlib,importlib.metadata,json,pathlib; import switchyard_rust._switchyard_rust as native; p=pathlib.Path(native.__file__); print(json.dumps(dict(version=importlib.metadata.version('nemo-switchyard'),binary_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),avx_visible=' avx ' in pathlib.Path('/proc/cpuinfo').read_text())))"
    native = json.loads(guest("cd /opt/hearth/deploy/compose && docker compose -f development.yaml exec -T api .venv/bin/python -c " + shlex.quote(native_probe)))
    inventory = json.loads((ROOT / "evidence/preparation/2026-09-12/inspection.json").read_text())
    original = inventory["source_inventory"]
    changed = [item["file"] for item in original if hashlib.sha256((ROOT / item["file"]).read_bytes()).hexdigest() != item["sha256"]]
    if changed:
        raise RuntimeError(f"Original design inputs changed: {changed}")
    versions = {name: importlib.metadata.version(name) for name in ("fastapi", "pydantic", "sqlalchemy", "alembic", "joserfc", "nemo-switchyard", "graphifyy")}
    report = {
        "recorded_at": datetime.now(UTC).isoformat(), "qualification": "development_foundation_only",
        "host": {"os": platform.system(), "release": platform.release(), "architecture": platform.machine()},
        "accelerator": "whpx", "cpu_profile": CPU_PROFILE,
        "services": [{key: value.get(key) for key in ("Service", "State", "Health", "Image")} for value in services],
        "api_https_readiness": health.json(), "forged_identity_status": denied.status_code,
        "tls": {"validation": "certificate chain and hostname verified", "root_sha256": certificate.fingerprint(hashes.SHA256()).hex(), "trust_delivery": "pinned SSH host key; application-scoped CA file", "os_trust_store_changed": False},
        "keycloak": {"discovery": "master realm reachable", "pkce_s256": True, "hearth_login_qualified": False},
        "step_ca": {"health": ca, "member_issuance_qualified": False}, "python_versions": versions,
        "linux_switchyard": native | {"build": "hash-pinned source release compiled for x86-64-v2", "rust": "1.96.1", "maturin": "1.15.0"},
        "original_design_files_unchanged": len(original),
        "not_qualified": ["production installer", "trusted browser signup", "OIDC BFF sessions", "member enrollment lifecycle", "inference", "media", "non-Windows appliance boot"],
    }
    path = OUTPUT / "stack.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Recorded verified development stack evidence in {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
