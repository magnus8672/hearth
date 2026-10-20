"""Prepare a Windows worker's fixed LLM/NCM services; never starts a model.

The resulting private inventory must be reviewed and signed on the head with
adopt_worker.py before the worker can activate either backend.
"""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from prepare_ncm import digest, download, prepare

ROOT = Path(__file__).resolve().parents[1]
LLAMA_TAG = 'b11756'
LLAMA_SHA = '75ce69fdda503c3d6d3b3401f61369bd072194746ec65fbbc5fd7e749edd2914'


def tree_digest(root):
    h = hashlib.sha256()
    for path in sorted(root.rglob('*'), key=str):
        if path.is_symlink():
            raise ValueError('Runtime links are not permitted.')
        if not path.is_file():
            continue
        h.update((path.relative_to(root).as_posix()+'\0'+digest(path)+'\n').encode())
    return h.hexdigest()


def run(*args):
    subprocess.run([str(a) for a in args], check=True)


def stage(args):
    if os.name != 'nt' or sys.version_info[:2] != (3, 12):
        raise ValueError('Run setup on Windows with Python 3.12.')
    home = args.home.resolve()
    if home.exists():
        raise ValueError('Use a new empty destination; existing worker identities are never replaced.')
    if not args.llm_model.is_file() or args.llm_model.suffix.lower() != '.gguf':
        raise ValueError('Select an existing GGUF model.')
    home.mkdir(parents=True)
    # Windows ignores POSIX mode bits: protect setup output with a user-only DACL.
    identity = subprocess.check_output(['whoami'], text=True).strip()
    run('icacls', home, '/inheritance:r', '/grant:r', identity+':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F')
    binary_source = ROOT / 'bin' if (ROOT/'bin/hearth-worker.exe').exists() else ROOT/'.hearth/bin/windows-runner'
    for name in ('hearth-worker.exe', 'hearth-connector.exe'):
        shutil.copyfile(binary_source/name, home/name)
    archive = home/'llama.zip'
    download(f'https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/llama-{LLAMA_TAG}-bin-win-vulkan-x64.zip', archive, LLAMA_SHA)
    llama = home/'llama'
    llama.mkdir()
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            path = Path(item.filename)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsafe llama.cpp archive.')
        z.extractall(llama)
    candidates = list(llama.rglob('llama-server.exe'))
    if len(candidates) != 1:
        raise ValueError('Unexpected llama.cpp package layout.')
    server = candidates[0]
    download(f'https://raw.githubusercontent.com/ggml-org/llama.cpp/{LLAMA_TAG}/LICENSE', llama/'LICENSE')
    runtime = home/'ncm-service'
    shutil.copytree(ROOT/'runtimes/ncm', runtime, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    prepare(home/'ncm')
    run(sys.executable, '-m', 'venv', home/'python')
    python = home/'python/Scripts/python.exe'
    run(python, '-m', 'pip', 'install', '--extra-index-url', 'https://download.pytorch.org/whl/cpu', '-r', runtime/'requirements-windows-cpu.lock')
    services = {}
    for name, public_port, backend_port in [('llm', 1240, 1243), ('ncm', 1244, 1242)]:
        identity_dir = home/(name+'-identity')
        key = home/(name+'-engine.key')
        key.write_text(secrets.token_hex(32))
        connector = home/'hearth-connector.exe'
        run(connector, '--init', '--dir', identity_dir, '--public-host', args.public_host,
            '--listen', args.public_host+':'+str(public_port), '--upstream', f'http://127.0.0.1:{backend_port}', '--upstream-key-file', key)
        if name == 'llm':
            executable = server
            arguments = ['--model', str(args.llm_model.resolve()), '--alias', args.llm_id, '--host', '127.0.0.1',
                         '--port', str(backend_port), '--api-key-file', str(key), '--ctx-size', str(args.context),
                         '--parallel', '1', '--n-gpu-layers', str(args.gpu_layers), '--no-webui']
            files = {str(server): digest(server), str(args.llm_model.resolve()): digest(args.llm_model)}
            directories = {str(llama): tree_digest(llama)}
            health, field, value = '/health', 'status', 'ok'
        else:
            executable = python
            arguments = ['-I', '-B', str(runtime/'serve.py'), '--root', str(home/'ncm'), '--key-file', str(key), '--threads', '4']
            files = {str(python): digest(python)}
            # The venv launcher relies on its base interpreter as well.
            base = Path(sys.base_prefix)
            for path in base.glob('*.dll'):
                files[str(path)] = digest(path)
            files[str(base/'python.exe')] = digest(base/'python.exe')
            directories = {str(home/'python'): tree_digest(home/'python'), str(home/'ncm/source'): tree_digest(home/'ncm/source'),
                           str(home/'ncm/xsum'): tree_digest(home/'ncm/xsum'), str(home/'ncm/gpt2'): tree_digest(home/'ncm/gpt2'),
                           str(runtime): tree_digest(runtime)}
            for dependency in ('Lib', 'DLLs'):
                if (base/dependency).is_dir():
                    directories[str(base/dependency)] = tree_digest(base/dependency)
            health, field, value = '/v1/ncm-provider', 'model', 'hazyresearch/ncm-xsum'
        files.update({str(connector): digest(connector), str(identity_dir/'connector.json'): digest(identity_dir/'connector.json')})
        services[name] = {'name': 'LLM chat' if name == 'llm' else 'NCM XSum (experimental)', 'connection_id': 'REPLACE_WITH_REGISTERED_CONNECTION_UUID',
                          'unit': f'hearth-{name}.service', 'files': files, 'directories': directories,
                          'health_url': f'http://127.0.0.1:{backend_port}'+health, 'health_key_file': str(key), 'health_field': field, 'health_value': value,
                          'processes': [{'executable': str(executable), 'arguments': arguments, 'directory': str(executable.parent)},
                                        {'executable': str(connector), 'arguments': ['--dir', str(identity_dir)], 'directory': str(home)}]}
    inventory = {'platform': 'windows', 'name': 'Windows text worker', 'pool_id': 'REPLACE_WITH_SHARED_POOL_UUID',
                 'bundle_directory': str(home/'control'), 'services': services}
    (home/'inventory.json').write_text(json.dumps(inventory, indent=2)+'\n')
    print('Prepared. Register the two providers in one resource group, then review/sign inventory.json on the head. No backend was started.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', required=True, type=Path)
    parser.add_argument('--public-host', required=True)
    parser.add_argument('--llm-model', required=True, type=Path)
    parser.add_argument('--llm-id', default='hearth-local-llm')
    parser.add_argument('--context', type=int, choices=[2048, 4096, 8192, 16384, 32768], default=8192)
    parser.add_argument('--gpu-layers', type=int, choices=range(0, 1000), default=99)
    stage(parser.parse_args())
