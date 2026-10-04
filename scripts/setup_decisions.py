"""Explicit head setup for the pinned CPU decision runtime. No farm reset or model switching."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'hearth-decision:0.1.0'


def prepare(state):
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise ValueError('Run decision setup with sudo on the Linux head.')
    directory = state / 'decisions'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    subprocess.run(['docker', 'build', '-f', str(ROOT/'runtimes/decision/Dockerfile'), '-t', IMAGE, str(ROOT)], check=True)
    checkpoint = directory/'checkpoint'
    manifest = checkpoint/'manifest.json'
    if manifest.exists():
        value = json.loads(manifest.read_text())
        if value.get('revision') != '1a793eb568e6718f15941d08f85432581df534e3':
            raise ValueError('A different checkpoint is installed. Preserve it and review migration before replacing it.')
    else:
        checkpoint.mkdir(exist_ok=True, mode=0o700)
        os.chown(checkpoint, 10001, 10001)
        subprocess.run(['docker', 'run', '--rm', '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
            '-v', str(checkpoint)+':/checkpoint', '-e', 'HF_HOME=/tmp/huggingface', IMAGE,
            'python', 'prepare.py', '/checkpoint'], check=True)
    sockets = directory/'socket'
    sockets.mkdir(exist_ok=True, mode=0o700)
    os.chown(sockets, 10001, 10001)
    sockets.chmod(0o700)
    return directory


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, default=ROOT/'.hearth/head')
    args = parser.parse_args()
    prepare(args.state.resolve())
    print('Pinned decision runtime prepared. Run head.py up to activate its private socket.')
