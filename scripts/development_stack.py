"""Provision the local developer appliance stack with generated, private credentials."""

import argparse
import json
import os
import secrets
import subprocess
import tarfile
import uuid

from appliance import ROOT, STATE, ssh_args

CONFIG = ROOT / ".hearth/development.json"


def configuration():
    values = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    old_names = set(values)
    for name in (
            "POSTGRES_PASSWORD", "HEARTH_APP_PASSWORD", "HEARTH_MIGRATION_PASSWORD", "HEARTH_IDENTITY_PASSWORD",
            "HEARTH_IDENTITY_BOOTSTRAP_PASSWORD", "HEARTH_SESSION_ENCRYPTION_KEY", "HEARTH_CA_PASSWORD",
            "HEARTH_ADMIN_CLIENT_SECRET", "HEARTH_USER_CLIENT_SECRET",
        ):
        values.setdefault(name, secrets.token_urlsafe(32))
    values.setdefault('HEARTH_FARM_ID', str(uuid.uuid4()))
    if set(values) != old_names:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(values, indent=2))
        if os.name == "nt":
            subprocess.run(["icacls", str(CONFIG), "/inheritance:r", "/grant:r", f"{os.environ['USERNAME']}:(F)"],
                           stdout=subprocess.DEVNULL, check=True)
        else:
            CONFIG.chmod(0o600)
    return values


def sync():
    values = configuration()
    cpu_ready = subprocess.run([str(x) for x in ssh_args()] + ['grep -q clearcpuid=519 /proc/cmdline'], check=False)
    if cpu_ready.returncode != 0:
        with (ROOT / 'deploy/appliance/60-hearth-cpu.cfg').open('rb') as stream:
            subprocess.run([str(x) for x in ssh_args()] + ['sudo tee /etc/default/grub.d/60-hearth-cpu.cfg >/dev/null && sudo update-grub'], stdin=stream, check=True)
        raise SystemExit('Guest CPU compatibility profile prepared. Run appliance.py down, appliance.py up, then repeat this stack command.')
    archive_path = STATE / "source.tar"
    with tarfile.open(archive_path, "w") as archive:
        for name in ("pyproject.toml", "uv.lock", "alembic.ini", "services", "deploy", "scripts", "tests", "apps/admin-web/dist", "apps/user-web/dist", ".dockerignore"):
            path = ROOT / name
            if path.is_dir():
                for child in path.rglob("*"):
                    if child.is_file() and "__pycache__" not in child.parts:
                        archive.add(child, arcname=child.relative_to(ROOT), recursive=False)
            else:
                archive.add(path, arcname=name)
    with archive_path.open("rb") as stream:
        subprocess.run([str(x) for x in ssh_args()] + ["tar -xf - -C /opt/hearth"], stdin=stream, check=True)
    # Stream configuration on stdin, not through process arguments or command output.
    env_content = "\n".join(f"{name}={value}" for name, value in values.items()) + "\n"
    subprocess.run([str(x) for x in ssh_args()] + ["umask 077; cat > /opt/hearth/deploy/compose/.env"],
                   input=env_content.encode(), check=True)
    subprocess.run([str(x) for x in ssh_args()] + ["umask 077; cat > /opt/hearth/deploy/compose/.ca-password"],
                   input=values["HEARTH_CA_PASSWORD"].encode(), check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["up", "sync", "status", "qualify-linux"])
    args = parser.parse_args()
    if args.action in {"up", "sync", "qualify-linux"}:
        sync()
    command = "cd /opt/hearth/deploy/compose && docker compose -f development.yaml "
    if args.action == "up":
        subprocess.run([str(x) for x in ssh_args()] + [command + "up -d --build"], check=True)
    if args.action == "status":
        subprocess.run([str(x) for x in ssh_args()] + [command + "ps"], check=True)
    if args.action == "qualify-linux":
        from dev import go_executable
        binary = ROOT / ".hearth/bin/linux-amd64/hearth-contracts"
        binary.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([go_executable(), "build", "-trimpath", "-o", str(binary), "./cmd/hearth-contracts"],
                       cwd=ROOT / "worker", env=os.environ | {"GOOS": "linux", "GOARCH": "amd64", "CGO_ENABLED": "0"}, check=True)
        with binary.open("rb") as stream:
            subprocess.run([str(x) for x in ssh_args()] + ["mkdir -p /opt/hearth/.hearth/bin /opt/hearth/.hearth/test-results && cat > /opt/hearth/.hearth/bin/hearth-contracts && chmod 700 /opt/hearth/.hearth/bin/hearth-contracts"], stdin=stream, check=True)
        subprocess.run([str(x) for x in ssh_args()] + [command + "--profile qualification run --rm --build tests"], check=True)


if __name__ == "__main__":
    main()
