"""Start the optional, explicitly installed local SDXL development provider."""
import argparse
import json
import os
import secrets
import subprocess
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.hearth/image-provider'


def status():
    token_file = STATE / 'controller.key'
    if not token_file.exists():
        return None
    try:
        response = httpx.get('http://127.0.0.1:1235/v1/image-provider', headers={'Authorization': 'Bearer ' + token_file.read_text(encoding='utf-8').strip()}, timeout=3, trust_env=False)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError:
        return None


def start():
    STATE.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        subprocess.run(['icacls', str(STATE), '/inheritance:r', '/grant:r', f"{os.environ['USERNAME']}:(OI)(CI)F"], stdout=subprocess.DEVNULL, check=True)
    else:
        STATE.chmod(0o700)
    existing = status()
    if existing:
        print('The local hearth image provider is already running.')
        return
    python = ROOT / '.hearth/toolchains/image-runtime' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    model = ROOT / '.hearth/models/sdxl-base-1.0'
    if not python.exists() or not (model / 'hearth-manifest.json').exists():
        raise SystemExit('Install the image environment and verified SDXL model closure first. See docs/runtimes/IMAGE_PROVIDER.md.')
    token_file = STATE / 'controller.key'
    if not token_file.exists():
        token_file.write_text(secrets.token_urlsafe(48), encoding='utf-8')
    config = STATE / 'config.json'
    config.write_text(json.dumps({'jobs': str(STATE / 'jobs'), 'model': str(model), 'token_file': str(token_file)}), encoding='utf-8')
    env = os.environ | {'PYTHONPATH': str(ROOT / 'services/api/src'), 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1'}
    with (STATE / 'runtime.log').open('ab') as log:
        process = subprocess.Popen([str(python), str(ROOT / 'runtimes/image/hearth_image.py'), '--config', str(config)],
            cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, start_new_session=os.name != 'nt')
    (STATE / 'process.json').write_text(json.dumps({'pid': process.pid, 'executable': str(python)}), encoding='utf-8')
    print('Starting the loopback image provider. Model files are verified before it accepts requests.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'status'])
    args = parser.parse_args()
    if args.action == 'start':
        start()
    else:
        result = status()
        print(json.dumps(result, indent=2) if result else 'The local image provider is not reachable.')


if __name__ == '__main__':
    main()
