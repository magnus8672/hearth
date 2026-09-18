"""Prepare the pinned Hunyuan3D 2.0 CUDA runtime without starting inference."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath


def fetch(entry, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        with target.open('rb') as stream:
            if target.stat().st_size == entry['bytes'] and hashlib.file_digest(stream, 'sha256').hexdigest() == entry['sha256']:
                return target
        raise RuntimeError('Installed file differs from the approved inventory: ' + str(target))
    partial = target.with_suffix(target.suffix + '.partial')
    subprocess.run(['curl', '--fail', '--location', '--retry', '4', '--continue-at', '-',
                    '--output', str(partial), entry['url']], check=True)
    with partial.open('rb') as stream:
        if partial.stat().st_size != entry['bytes'] or hashlib.file_digest(stream, 'sha256').hexdigest() != entry['sha256']:
            raise RuntimeError('Download differs from the approved inventory: ' + str(target))
    partial.replace(target)
    return target


def unpack(archive, directory):
    directory.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as package:
        for item in package.getmembers():
            parts = PurePosixPath(item.name).parts[1:]
            if not parts:
                continue
            item.name = str(PurePosixPath(*parts))
            package.extract(item, directory, filter='data')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.error('This locked runtime profile requires Python 3.12.')
    root, source = args.root.resolve(), Path(__file__).resolve().parent
    if root == Path('/') or any(c.isspace() for c in str(root)):
        parser.error('Use a dedicated absolute directory without spaces.')
    root.mkdir(parents=True, exist_ok=True)
    inventory = json.loads((source / 'inventory.json').read_text())
    downloads = root / 'downloads'
    unpack(fetch(inventory['archive'], downloads / 'source.tar.gz'), root / 'engine')
    for entry in inventory['build_tools']:
        unpack(fetch(entry, downloads / (entry['name'] + '.tar.xz')), root / 'cuda')
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda entry: fetch(entry, root / 'models' / entry['path']), inventory['files']))
    shutil.copy2(source / 'requirements.txt', root / 'requirements.txt')
    py = root / '.venv/bin/python'
    if not py.exists():
        subprocess.run(['python3', '-m', 'venv', str(root / '.venv')], check=True)
    subprocess.run([str(py), '-m', 'pip', 'install', '--require-hashes', '--extra-index-url',
                    'https://download.pytorch.org/whl/cu126', '-r', str(root / 'requirements.txt')], check=True)
    includes = sorted((root / '.venv/lib').glob('python*/site-packages/nvidia/*/include'))
    env = os.environ | {'CUDA_HOME': str(root / 'cuda'), 'CPATH': ':'.join(map(str, includes)),
                        'PATH': str(root / '.venv/bin') + ':' + str(root / 'cuda/bin') + ':' + os.environ['PATH'],
                        'MAX_JOBS': '2', 'TORCH_CUDA_ARCH_LIST': '8.9'}
    # Compile only the reviewed upstream extensions; no runtime package installation.
    for folder in ['custom_rasterizer', 'differentiable_renderer']:
        subprocess.run([str(py), 'setup.py', 'build_ext', '--inplace'],
                       cwd=root / 'engine/hy3dgen/texgen' / folder, env=env, check=True)
    # Use the in-tree rasterizer, including its locally compiled kernel, at runtime.
    closure = []
    for path in sorted((root / 'engine').rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and 'build' not in path.parts:
            with path.open('rb') as stream:
                closure.append({'path': path.relative_to(root / 'engine').as_posix(), 'bytes': path.stat().st_size,
                                'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()})
    (root / 'engine-inventory.json').write_text(json.dumps(closure, indent=2) + '\n')
    shutil.copy2(source / 'inventory.json', root / 'inventory.json')
    print('Pinned Hunyuan3D 2.0 runtime prepared; inference has not started.')


if __name__ == '__main__':
    main()
