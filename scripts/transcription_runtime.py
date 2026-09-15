"""Start the explicitly prepared local CPU transcription provider with existing model files."""
import argparse
import json
import os
import secrets
import subprocess
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT/'.hearth/transcription-provider'


def status():
    token_file = STATE/'controller.key'
    if not token_file.exists():
        return None
    try:
        result = httpx.get('http://127.0.0.1:1237/v1/transcription-provider', headers={'Authorization': 'Bearer '+token_file.read_text(encoding='utf-8').strip()}, timeout=3, trust_env=False)
        result.raise_for_status()
        return result.json()
    except httpx.HTTPError:
        return None


def start(model=None):
    STATE.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        subprocess.run(['icacls', str(STATE), '/inheritance:r', '/grant:r', f"{os.environ['USERNAME']}:(OI)(CI)F"], stdout=subprocess.DEVNULL, check=True)
    else:
        STATE.chmod(0o700)
    if status():
        print('The local transcription provider is already running.')
        return
    config = STATE/'config.json'
    values = json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
    if model is not None:
        values['model'] = str(model.resolve(strict=True))
    if not all(key in values for key in ['model']):
        raise SystemExit('Supply --model directory on first startup. No files are downloaded automatically.')
    python = ROOT/'runtimes/transcription/.venv'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        raise SystemExit('Run uv sync --locked --project runtimes/transcription first.')
    token_file = STATE/'controller.key'
    if not token_file.exists():
        token_file.write_text(secrets.token_urlsafe(48), encoding='utf-8')
    values.update({'jobs': str(STATE/'jobs'), 'token_file': str(token_file)})
    config.write_text(json.dumps(values, indent=2), encoding='utf-8')
    with (STATE/'runtime.log').open('ab') as log:
        process = subprocess.Popen([str(python), str(ROOT/'runtimes/transcription/hearth_transcription.py'), '--config', str(config)],
            cwd=ROOT, env=os.environ | {'PYTHONPATH': str(ROOT/'services/api/src')}, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, start_new_session=os.name != 'nt')
    (STATE/'process.json').write_text(json.dumps({'pid': process.pid, 'executable': str(python)}), encoding='utf-8')
    print('Starting the CPU transcription provider. Existing model files are verified and loaded before serving requests.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'status'])
    parser.add_argument('--model', type=Path)
    args = parser.parse_args()
    if args.action == 'start':
        start(args.model)
    else:
        print(json.dumps(status(), indent=2))


if __name__ == '__main__':
    main()
