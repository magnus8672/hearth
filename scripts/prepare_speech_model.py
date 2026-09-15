"""Explicitly fetch the digest-pinned Kokoro model and stock voice pack."""
import argparse
import json
from pathlib import Path

import httpx
from prepare_transcription_model import matches

ROOT = Path(__file__).resolve().parents[1]
FILES = {'model': 'kokoro-v1.0.onnx', 'voices': 'voices-v1.0.bin'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', type=Path, default=ROOT/'.hearth/models/kokoro')
    folder = parser.parse_args().destination.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT/'runtimes/speech/model-manifest.json').read_text())
    with httpx.Client(trust_env=False, follow_redirects=True, timeout=120) as client:
        for key, name in FILES.items():
            item, path = manifest['files'][key], folder/name
            if matches(path, item):
                continue
            temporary = folder/(name+'.part')
            url = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/'+name
            with client.stream('GET', url) as response, temporary.open('wb') as stream:
                response.raise_for_status()
                size = 0
                for block in response.iter_bytes():
                    size += len(block)
                    if size > item['bytes']:
                        raise RuntimeError('The speech download exceeded its declared size.')
                    stream.write(block)
            if not matches(temporary, item):
                raise RuntimeError('The speech model download failed digest verification.')
            temporary.replace(path)
    print('The pinned CPU speech model and stock voices are ready. No service was started.')


if __name__ == '__main__':
    main()
