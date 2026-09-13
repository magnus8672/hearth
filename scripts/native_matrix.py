"""Compile native targets and record build evidence without claiming runtime qualification."""

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime

from dev import ROOT, go_executable

results = []
for operating_system, architecture in (("windows", "amd64"), ("linux", "amd64"), ("linux", "arm64"),
                                        ("darwin", "amd64"), ("darwin", "arm64")):
    target = f"{operating_system}-{architecture}"
    destination = ROOT / ".hearth/bin" / target / ("hearth-worker.exe" if operating_system == "windows" else "hearth-worker")
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([go_executable(), "build", "-trimpath", "-o", str(destination), "./cmd/hearth-worker"],
                   cwd=ROOT / "worker", env=os.environ | {"GOOS": operating_system, "GOARCH": architecture, "CGO_ENABLED": "0"}, check=True)
    results.append({"target": target, "build": "passed", "runtime_qualified": False,
                    "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()})
output = ROOT / "evidence/foundation/2026-09-12/native-builds.json"
output.write_text(json.dumps({"recorded_at": datetime.now(UTC).isoformat(), "targets": results}, indent=2) + "\n")
print(f"Compiled {len(results)} native entry-point targets. Runtime and installer qualification remain separate.")
