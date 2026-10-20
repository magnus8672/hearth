"""Stage pinned NCM XSum assets. Setup only: never called by an inference request."""
import argparse
import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

SOURCE = 'c70274273f489abc73832b2b98584a8483b6b203'
WEIGHTS = 'd342ce8aaea58830eef3b8ad473664673e41f692'
TOKENIZER = '607a30d783dfa663caf39e06633721c8d4cfcd7e'
DIGESTS = {'generator.pt': 'f152f390253de886e46303654f01b9e7a2586e609ba3d6b5e86d5969903b1fd4',
           'tokenizer.pt': '1f806ddaf8e023d1933e95efeabcaaf99f795576c0a05045f1a0f9389ab34fa7'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url, path, expected=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if expected and digest(path) != expected:
            raise ValueError('Existing staged file has an unexpected digest: '+path.name)
        return
    temp = path.with_name(path.name+'.partial')
    with urllib.request.urlopen(url, timeout=90) as response, temp.open('wb') as out:
        shutil.copyfileobj(response, out)
    if expected and digest(temp) != expected:
        raise ValueError('Downloaded checkpoint digest mismatch: '+path.name)
    temp.replace(path)


def prepare(root):
    root.mkdir(parents=True, exist_ok=True)
    archive = root / 'source.zip'
    download(f'https://github.com/HazyResearch/ncm/archive/{SOURCE}.zip', archive)
    source = root / 'source'
    if not source.exists():
        with zipfile.ZipFile(archive) as z:
            for item in z.infolist():
                relative = Path(*Path(item.filename).parts[1:])
                if not relative.parts or item.is_dir():
                    continue
                if '..' in relative.parts or relative.is_absolute():
                    raise ValueError('Unsafe upstream archive member.')
                # Only executable source/config and license; no evaluation data.
                if relative.parts[0] not in ('models', 'tokenization', 'utils', 'config', 'LICENSE'):
                    continue
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(z.read(item))
    for name in ('generator.pt', 'tokenizer.pt', 'config.yaml', 'README.md'):
        download(f'https://huggingface.co/hazyresearch/ncm-checkpoints/resolve/{WEIGHTS}/xsum/{name}', root/'xsum'/name, DIGESTS.get(name))
    for name in ('config.json', 'tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'merges.txt'):
        download(f'https://huggingface.co/openai-community/gpt2/resolve/{TOKENIZER}/{name}', root/'gpt2'/name)
    if (root/'xsum/config.yaml').read_bytes() != (source/'config/eval/xsum.yaml').read_bytes():
        raise ValueError('Checkpoint configuration differs from the reviewed source.')
    files = {str(p.relative_to(root)).replace('\\', '/'): digest(p) for p in root.rglob('*')
             if p.is_file() and p.name not in ('source.zip', 'inventory.json') and '__pycache__' not in p.parts}
    (root/'inventory.json').write_text(json.dumps({'source_revision': SOURCE, 'weights_revision': WEIGHTS,
                                                  'tokenizer_revision': TOKENIZER, 'files': files}, indent=2)+'\n')
    print('Pinned NCM XSum assets staged; no service started.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    prepare(parser.parse_args().output.resolve())
