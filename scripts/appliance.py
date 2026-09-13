"""Local development appliance supervisor. No host-wide installation or emulation fallback.

uv run --group appliance python scripts/appliance.py up|status|down|ssh [command...]
The loopback SSH channel is for this developer appliance only, not member configuration.
"""

import argparse
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".hearth/appliance"
TOOLS = ROOT / ".hearth/toolchains/qemu"
CPU_PROFILE = "qemu64,+ssse3,+sse4.1,+sse4.2,+popcnt,+cx16,+lahf-lm"


def run(args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def ssh_args():
    return ["ssh", "-i", STATE / "client_key", "-p", "22220", "-o", "BatchMode=yes", "-o",
            "ConnectTimeout=5", "-o", "StrictHostKeyChecking=yes", "-o",
            f"UserKnownHostsFile={STATE / 'known_hosts'}", "hearth@127.0.0.1"]


def prepare_seed():
    import pycdlib
    import yaml
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    STATE.mkdir(parents=True, exist_ok=True)
    public_keys = {}
    for name in ("client_key", "host_key"):
        path = STATE / name
        if not path.exists():
            key = Ed25519PrivateKey.generate()
            path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                               serialization.NoEncryption()))
            if os.name == "nt":
                run(["icacls", path, "/inheritance:r", "/grant:r", f"{os.environ['USERNAME']}:(F)"],
                    stdout=subprocess.DEVNULL)
            else:
                path.chmod(0o600)
        key = serialization.load_ssh_private_key(path.read_bytes(), password=None)
        public_keys[name] = key.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                                        serialization.PublicFormat.OpenSSH).decode()
    (STATE / "known_hosts").write_text(f"[127.0.0.1]:22220 {public_keys['host_key']}\n")
    user_data = {
        "hostname": "hearth-development", "manage_etc_hosts": True, "ssh_pwauth": False,
        "disable_root": True, "ssh_deletekeys": False,
        "ssh_keys": {"ed25519_private": (STATE / "host_key").read_text(), "ed25519_public": public_keys["host_key"]},
        "users": [{"name": "hearth", "shell": "/bin/bash", "groups": ["sudo"],
                   "sudo": "ALL=(ALL) NOPASSWD:ALL", "lock_passwd": True,
                   "ssh_authorized_keys": [public_keys["client_key"]]}],
        "package_update": True, "package_upgrade": False,
        "packages": ["docker.io", "docker-compose-v2", "qemu-guest-agent"],
        "runcmd": [["systemctl", "enable", "--now", "docker"],
                   ["usermod", "-aG", "docker", "hearth"],
                   ["sh", "-c", "mkdir -p /opt/hearth && chown hearth:hearth /opt/hearth"],
                   ["sh", "-c", "printf appliance-base-ready > /var/lib/hearth-base-ready"]],
        "final_message": "Hearth development appliance base provisioned",
    }
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, rock_ridge="1.09", vol_ident="cidata")
    files = {
        "user-data": "#cloud-config\n" + yaml.safe_dump(user_data),
        "meta-data": yaml.safe_dump({"instance-id": "hearth-p0-" + str(uuid.uuid4()), "local-hostname": "hearth-development"}),
    }
    for index, (name, content) in enumerate(files.items()):
        blob = content.encode()
        iso.add_fp(io.BytesIO(blob), len(blob), iso_path=f"/FILE{index}.;1", rr_name=name,
                   joliet_path="/" + name)
    iso.write(str(STATE / "seed.iso"))
    iso.close()


def up():
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise SystemExit("This reference helper currently qualifies Windows x86-64 only.")
    import ctypes
    value, written = ctypes.c_uint32(), ctypes.c_uint32()
    code = ctypes.WinDLL("WinHvPlatform.dll").WHvGetCapability(0, ctypes.byref(value), 4, ctypes.byref(written))
    if code != 0 or value.value != 1:
        raise SystemExit("Windows Hypervisor Platform unavailable; no emulation fallback is permitted.")
    if (STATE / "process.json").exists():
        raise SystemExit("Appliance process record exists. Inspect status before starting another head.")
    if not (STATE / "base.img").exists():
        raise SystemExit("Verified base image missing. See deploy/appliance/base-images.lock.json.")
    if not (STATE / "system.qcow2").exists():
        prepare_seed()
        run([TOOLS / "qemu-img.exe", "create", "-f", "qcow2", "-F", "qcow2", "-b", STATE / "base.img",
             STATE / "system.qcow2", "48G"])
    if not (STATE / "uefi-vars.fd").exists():
        shutil.copy2(TOOLS / "share/edk2-i386-vars.fd", STATE / "uefi-vars.fd")
    args = [str(TOOLS / "qemu-system-x86_64.exe"), "-name", "hearth-development", "-machine", "q35",
            "-accel", "whpx", "-cpu", CPU_PROFILE, "-smp", "4", "-m", "8192", "-display", "none", "-no-reboot",
            "-drive", f"if=pflash,format=raw,unit=0,readonly=on,file={TOOLS / 'share/edk2-x86_64-code.fd'}",
            "-drive", f"if=pflash,format=raw,unit=1,file={STATE / 'uefi-vars.fd'}",
            "-drive", f"file={STATE / 'system.qcow2'},if=virtio,format=qcow2",
            "-drive", f"file={STATE / 'seed.iso'},format=raw,media=cdrom,readonly=on",
            "-netdev", "user,id=net0,hostfwd=tcp:127.0.0.1:22220-:22,hostfwd=tcp:127.0.0.1:55432-:5432,hostfwd=tcp:127.0.0.1:18080-:8080,hostfwd=tcp:127.0.0.1:18085-:8085,hostfwd=tcp:127.0.0.1:18443-:8443,hostfwd=tcp:127.0.0.1:8443-:8443,hostfwd=tcp:127.0.0.1:8444-:8444,hostfwd=tcp:127.0.0.1:8445-:8445",
            "-device", "virtio-net-pci,netdev=net0", "-serial", f"file:{STATE / 'serial.log'}"]
    with (STATE / "process.log").open("ab") as log:
        process = subprocess.Popen(args, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    (STATE / "process.json").write_text(json.dumps({"pid": process.pid, "executable": args[0], "accelerator": "whpx"}, indent=2))
    print(f"Appliance started with WHPX, PID {process.pid}. Logs remain under .hearth/appliance.")


def wait_for_recorded_exit(record):
    """Wait for our own guest process without killing a process or accepting PID reuse."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000 | 0x100000, False, record["pid"])
    if not handle:
        if ctypes.get_last_error() == 87:
            return
        raise SystemExit("Cannot inspect the recorded process. Its state record has been preserved.")
    try:
        buffer, length = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
            raise SystemExit("Cannot identify the recorded process. Its state record has been preserved.")
        expected = Path(record['executable']).resolve()
        allowed = {(TOOLS / 'qemu-system-x86_64.exe').resolve(),
                   (ROOT / '.hearth/toolchains/qemu-10.2.0/qemu-system-x86_64.exe').resolve()}
        if expected not in allowed or Path(buffer.value).resolve() != expected:
            raise SystemExit("Recorded PID belongs to another executable. No process action was taken.")
        if kernel.WaitForSingleObject(handle, 30_000) != 0:
            raise SystemExit("Guest shutdown is still in progress. The process record prevents duplicate startup.")
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["up", "status", "down", "ssh"])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "up":
        up()
    elif args.action == "ssh":
        if not args.command:
            raise SystemExit("Specify an explicit development appliance command.")
        run(ssh_args() + args.command)
    elif args.action == "status":
        record = STATE / "process.json"
        print(record.read_text() if record.exists() else "No appliance process record")
        result = subprocess.run([str(arg) for arg in ssh_args()] + ["test -f /var/lib/hearth-base-ready && docker --version && docker compose version"], check=False)
        sys.exit(result.returncode)
    elif args.action == "down":
        # Ask the authenticated guest to shut down. Never kill an unrelated reused PID.
        record = json.loads((STATE / "process.json").read_text())
        run(ssh_args() + ["sudo poweroff"])
        wait_for_recorded_exit(record)
        (STATE / "process.json").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
