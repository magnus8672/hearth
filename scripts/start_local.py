"""Prepare and open the reference Windows test build without an OS trust change."""
import subprocess
import sys
import time

import httpx
from appliance import ROOT, STATE, up
from configure_identity import configure
from dev import go_executable
from setup_helper import fetch_root


def main():
    if not (STATE / 'process.json').exists():
        up()
    print('Waiting for the local control and identity services…', flush=True)
    for _ in range(90):
        try:
            with httpx.Client(timeout=3, trust_env=False) as client:
                client.get('http://127.0.0.1:18080/health/ready').raise_for_status()
                client.get('http://127.0.0.1:18085/realms/master/.well-known/openid-configuration').raise_for_status()
            break
        except httpx.HTTPError:
            time.sleep(2)
    else:
        raise SystemExit('The appliance is not ready. Run the stack command in DEVELOPMENT.md, then try again.')
    configure()
    fetch_root()
    binary = ROOT / '.hearth/bin/hearth-setup.exe'
    binary.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([go_executable(), 'build', '-trimpath', '-o', str(binary), './cmd/hearth-setup'], cwd=ROOT / 'worker', check=True)
    subprocess.run([str(binary)], cwd=ROOT, check=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Hearth could not start setup. See DEVELOPMENT.md for the local recovery commands.', file=sys.stderr)
        sys.exit(1)
