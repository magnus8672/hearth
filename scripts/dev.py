"""Repeatable developer entry point. Integration mode requires the real database."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=ROOT):
    subprocess.run([str(arg) for arg in args], cwd=cwd, check=True)


def go_executable():
    local = ROOT / ".hearth/toolchains/go/bin" / ("go.exe" if os.name == "nt" else "go")
    command = str(local) if local.exists() else shutil.which("go")
    if not command:
        raise SystemExit("Go is missing. Run scripts/bootstrap.py on the Windows reference host.")
    return command


def generate():
    run(sys.executable, "scripts/generate_contracts.py")
    run(sys.executable, "scripts/contract_fixtures.py")
    go = Path(go_executable()).parent / ("gofmt.exe" if os.name == "nt" else "gofmt")
    run(go, "-w", "worker/internal/contracts/generated.go")
    run(shutil.which("pnpm"), "exec", "openapi-typescript", "packages/contracts/openapi.json", "-o", "packages/contracts/src/api.generated.ts")


def check(integration):
    go = go_executable()
    binary = ROOT / ".hearth/bin" / ("hearth-contracts.exe" if os.name == "nt" else "hearth-contracts")
    binary.parent.mkdir(parents=True, exist_ok=True)
    run(go, "test", "./...", cwd=ROOT / "worker")
    run(go, "build", "-trimpath", "-o", binary, "./cmd/hearth-contracts", cwd=ROOT / "worker")
    os.environ["HEARTH_REQUIRE_INTEGRATIONS"] = "1" if integration else "0"
    run(sys.executable, "-m", "ruff", "check", "services/api/src", "runtimes/image", "runtimes/speech", "runtimes/transcription", "scripts", "tests")
    arguments = [] if integration else ["--ignore=tests/integration/test_postgres.py", "--ignore=tests/integration/test_identity.py", "--ignore=tests/integration/test_chat.py", "--ignore=tests/integration/test_channels.py", "--ignore=tests/integration/test_images.py"]
    run(sys.executable, "-m", "pytest", "-q", *arguments)
    for command in ("typecheck", "test", "build"):
        run(shutil.which("pnpm"), command)
    if not integration:
        print("Offline checks passed. PostgreSQL, appliance boot, browser trust and identity are NOT qualified by this command.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["generate", "check", "check-offline", "stack"])
    args = parser.parse_args()
    if args.action == "generate":
        generate()
    elif args.action.startswith("check"):
        check(args.action == "check")
    elif args.action == "stack":
        run(sys.executable, "scripts/development_stack.py", "up")


if __name__ == "__main__":
    main()
