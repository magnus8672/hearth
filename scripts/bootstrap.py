"""Fetch hash-pinned developer tools into this checkout, without host-wide installation."""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".hearth"


def fetch(entry, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        partial = destination.with_suffix(destination.suffix + ".partial")
        print(f"Downloading pinned {destination.name}")
        with urllib.request.urlopen(entry["url"], timeout=60) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, 1 << 20)
        with partial.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != entry["sha256"]:
            raise SystemExit(f"Checksum mismatch for {destination.name}; the partial file was not activated.")
        partial.replace(destination)
    with destination.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != entry["sha256"]:
            raise SystemExit(f"Checksum mismatch for existing {destination.name}; refusing to use it.")


def main():
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise SystemExit("The development appliance bootstrap currently qualifies Windows x86-64 only.")
    locks = json.loads((ROOT / "deploy/bootstrap/toolchains.lock.json").read_text())
    downloads = STATE / "downloads"
    go_archive, qemu_archive = downloads / "go.zip", downloads / "qemu.exe"
    fetch(locks["go"], go_archive)
    if not (STATE / "toolchains/go/bin/go.exe").exists():
        with zipfile.ZipFile(go_archive) as archive:
            archive.extractall(STATE / "toolchains")
    fetch(locks["qemu_development_probe"], qemu_archive)
    if not (STATE / "toolchains/qemu/qemu-system-x86_64.exe").exists():
        extractor = shutil.which("7z") or r"C:\Program Files\7-Zip\7z.exe"
        if not Path(extractor).exists():
            raise SystemExit("7-Zip is required to extract the pinned portable QEMU package.")
        subprocess.run([extractor, "x", str(qemu_archive), "-o" + str(STATE / "toolchains/qemu"), "-y"],
                       check=True, stdout=subprocess.DEVNULL)
    image = json.loads((ROOT / "deploy/appliance/base-images.lock.json").read_text())["base_images"]["linux_amd64"]
    fetch(image, STATE / "appliance/base.img")
    print("Pinned development tools and base image verified. No production installer or OS trust changes were made.")


if __name__ == "__main__":
    main()
