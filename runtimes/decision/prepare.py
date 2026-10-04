"""Explicit, pinned checkpoint preparation. Never called by a request handler."""
import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import snapshot_download

MODELS = {
    'english': ('convaiinnovations/laya', '55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851', ['en']),
    'typed': ('convaiinnovations/laya-typed-decisions', '1a793eb568e6718f15941d08f85432581df534e3', ['en']),
    'multilingual': ('convaiinnovations/laya-multilingual', 'e4e9ddf21a7b1903b7acffd8814ad4307bf63a67', ['multilingual']),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--checkpoint', choices=MODELS, default='typed')
    args = parser.parse_args()
    model, revision, languages = MODELS[args.checkpoint]
    destination = args.directory / 'model'
    snapshot_download(model, revision=revision, local_dir=destination,
        allow_patterns=['rl_agent_config.json', 'model.safetensors', 'encoder/*.json', 'tokenizer/*', 'LICENSE', 'README.md'])
    hashes = {}
    for path in destination.rglob('*'):
        if path.is_file() and '.cache' not in path.parts:
            with path.open('rb') as source:
                hashes[path.relative_to(destination).as_posix()] = hashlib.file_digest(source, 'sha256').hexdigest()
    manifest = {'model': model, 'revision': revision, 'sha256': hashes, 'languages': languages, 'maximum_tokens': 1024,
                'source_revision': '8a6e1328cce2460a0e5aa348ad465bb1b5821cd2'}
    (args.directory / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({'model': model, 'revision': revision, 'files': len(hashes)}))


if __name__ == '__main__':
    main()
