"""Download the pinned Linux CUDA TRELLIS profile; never start inference."""
import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path


def fetch(item, destination):
    if not destination.exists():
        temporary = destination.with_suffix('.partial')
        subprocess.run(['curl', '--fail', '--location', '--retry', '5', '--continue-at', '-',
                        '--output', str(temporary), item['url']], check=True)
        temporary.rename(destination)
    with destination.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if destination.stat().st_size != item['bytes'] or digest != item['sha256']:
        raise RuntimeError(f'Inventory verification failed: {destination.name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    inventory = json.loads(Path(__file__).with_name('inventory.json').read_text())
    archive = root / 'engine.tar.gz'
    fetch(inventory['archive'], archive)
    engine = root / 'engine'
    engine.mkdir(exist_ok=True)
    with tarfile.open(archive) as bundle:
        bundle.extractall(engine, filter='data')
    closure = []
    for path in sorted(engine.rglob('*')):
        if path.is_file():
            with path.open('rb') as stream:
                closure.append({'path': str(path.relative_to(engine)), 'bytes': path.stat().st_size,
                                'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()})
    (root / 'engine-inventory.json').write_text(json.dumps(closure, indent=2)+'\n')
    models = root / 'models'
    models.mkdir(exist_ok=True)
    for item in inventory['files']:
        fetch(item, models / item['path'])
        print('Verified', item['path'], flush=True)
    (root / 'inventory.json').write_text(json.dumps(inventory, indent=2)+'\n')
    print('Pinned TRELLIS engine and weights prepared.', flush=True)


if __name__ == '__main__':
    main()
