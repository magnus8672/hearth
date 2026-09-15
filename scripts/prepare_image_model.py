"""Explicit model download for the experimental image provider, pinned by digest."""
import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'runtimes/image/model-manifest.json'
DESTINATION = ROOT / '.hearth/models/sdxl-base-1.0'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true', help='Download the 6.94 GB pinned SDXL closure from its official model repository.')
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if not args.download:
        print('This optional provider uses 6.94 GB of model files. Review runtimes/image/model-manifest.json and docs/runtimes/IMAGE_PROVIDER.md, then pass --download to install them.')
        return
    DESTINATION.mkdir(parents=True, exist_ok=True)

    def download(item):
        path = (DESTINATION / item['path']).resolve()
        if not path.is_relative_to(DESTINATION.resolve()):
            raise RuntimeError('Invalid recipe path.')
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size == item['bytes']:
            with path.open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() == item['sha256']:
                    return
        part = path.with_suffix(path.suffix + '.part')
        digest, size = hashlib.sha256(), 0
        url = f"{manifest['source']}/resolve/{manifest['revision']}/{item['path']}"
        with httpx.stream('GET', url, follow_redirects=True, timeout=120, trust_env=False) as response:
            response.raise_for_status()
            with part.open('wb') as output:
                for block in response.iter_bytes(1024 * 1024):
                    size += len(block)
                    if size > item['bytes']:
                        raise RuntimeError('Unexpected model file size.')
                    output.write(block)
                    digest.update(block)
        if size != item['bytes'] or digest.hexdigest() != item['sha256']:
            raise RuntimeError('Model file integrity verification failed.')
        part.replace(path)
        print('Verified', item['path'], flush=True)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(download, manifest['files']))
    (DESTINATION / 'hearth-manifest.json').write_bytes(MANIFEST.read_bytes())
    print('The complete SDXL model closure is installed and verified.')


if __name__ == '__main__':
    main()
