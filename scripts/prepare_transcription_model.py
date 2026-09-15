"""Explicitly download and verify the fixed local CPU transcription model closure."""
import argparse
import hashlib
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def matches(path, item):
    if not path.is_file() or path.stat().st_size != item['bytes']:
        return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() == item['sha256']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', type=Path, default=ROOT/'.hearth/models/faster-whisper-small.en')
    folder = parser.parse_args().destination.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT/'runtimes/transcription/model-manifest.json').read_text(encoding='utf-8'))
    with httpx.Client(trust_env=False, follow_redirects=True, timeout=120) as client:
        for name, item in manifest['files'].items():
            if Path(name).name != name:
                raise RuntimeError('Manifest files must be plain names.')
            path = folder/name
            if matches(path, item):
                continue
            temporary = folder/(name+'.part')
            with client.stream('GET', f"https://huggingface.co/{manifest['repository']}/resolve/{manifest['revision']}/{name}") as response, temporary.open('wb') as stream:
                response.raise_for_status()
                size = 0
                for block in response.iter_bytes():
                    size += len(block)
                    if size > item['bytes']:
                        raise RuntimeError('The model download exceeded its declared size.')
                    stream.write(block)
            if not matches(temporary, item):
                raise RuntimeError('The model download failed digest verification.')
            temporary.replace(path)
    print('The pinned CPU transcription model is ready. No inference service was started.')


if __name__ == '__main__':
    main()
