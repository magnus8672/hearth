"""Build a fresh-farm Linux ZIP from explicit deployment inputs, without local state."""

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    '.dockerignore', 'pyproject.toml', 'uv.lock', 'alembic.ini',
    'services/api/Dockerfile',
    'deploy/compose/development.yaml', 'deploy/compose/head.yaml',
    'deploy/compose/Caddyfile.development', 'deploy/compose/Caddyfile.head',
    'deploy/compose/init-databases.sh', 'deploy/compose/init-ca.sh',
    'deploy/compose/images.lock.json',
    'scripts/head.py', 'scripts/head_console.py', 'scripts/configure_identity.py',
    'scripts/setup_audio_vm.py', 'scripts/qualify_audio_vm.py',
    'runtimes/speech/hearth_speech.py', 'runtimes/speech/model-manifest.json',
    'runtimes/speech/pyproject.toml', 'runtimes/speech/uv.lock',
    'runtimes/transcription/hearth_transcription.py', 'runtimes/transcription/model-manifest.json',
    'runtimes/transcription/pyproject.toml', 'runtimes/transcription/uv.lock',
    'docs/operations/VM_PACKAGE.md',
)
TREES = {
    'deploy/setup': {'.html', '.js', '.css', '.svg'},
    'services/api/src': {'.py', '.wav'},
    'services/api/migrations': {'.py', '.json'},
    'deploy/identity/themes/hearth': {'.properties', '.ftl', '.css', '.svg', '.ico'},
    'apps/admin-web/dist': {'.html', '.js', '.css', '.svg', '.woff2', '.woff', '.png', '.ico'},
    'apps/user-web/dist': {'.html', '.js', '.css', '.svg', '.woff2', '.woff', '.png', '.ico'},
}
EXCLUDED_DIRS = {'.hearth', '.venv', '.git', '__pycache__', 'node_modules', '.pytest_cache'}


def checked_file(root, path):
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Missing or unsafe deployment input: {path.relative_to(root)}')
    for parent in (path, *path.parents):
        if parent == root:
            break
        is_link = parent.is_symlink() or bool(getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400)
        if is_link:
            raise ValueError(f'Linked deployment input: {path.relative_to(root)}')
    return path


def deployment_files(root):
    paths = {checked_file(root, root / name) for name in FILES}
    for name, extensions in TREES.items():
        folder = root / name
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError(f'Missing deployment directory: {name}')
        for directory, children, filenames in os.walk(folder, followlinks=False):
            children[:] = [child for child in children if child not in EXCLUDED_DIRS]
            for filename in filenames:
                path = Path(directory) / filename
                if path.suffix.lower() in extensions and not filename.startswith('.'):
                    paths.add(checked_file(root, path))
    for app in ('admin', 'user'):
        if root / f'apps/{app}-web/dist/index.html' not in paths:
            raise ValueError('Build both browser bundles with pnpm build first.')
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def build(output, root=ROOT):
    paths = deployment_files(root)
    output = output.resolve()
    if output in (path.resolve() for path in paths):
        raise ValueError('The ZIP cannot overwrite a deployment input.')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.partial')
    manifest = {'format': 1, 'product': 'hearth', 'profile': 'fresh-farm-linux-amd64',
                'requires_network_on_first_start': True, 'contains_farm_data': False, 'files': []}

    def write(archive, name, content):
        info = ZipInfo('hearth/' + name, date_time=(2026, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | (0o755 if name.endswith('.sh') else 0o644)) << 16
        info.compress_type = ZIP_DEFLATED
        archive.writestr(info, content, compresslevel=9)

    with ZipFile(temporary, 'w') as archive:
        for path in paths:
            name = path.relative_to(root).as_posix()
            content = path.read_bytes()
            # Bash bind mounts must retain Unix line endings after a Windows checkout.
            if path.suffix == '.sh':
                content = content.replace(b'\r\n', b'\n')
            write(archive, name, content)
            manifest['files'].append({'path': name, 'bytes': len(content),
                                      'sha256': hashlib.sha256(content).hexdigest()})
        readme = b'# hearth VM package\n\nStart with [the fresh VM setup guide](docs/operations/VM_PACKAGE.md).\n'
        write(archive, 'README.md', readme)
        manifest['files'].append({'path': 'README.md', 'bytes': len(readme),
                                  'sha256': hashlib.sha256(readme).hexdigest()})
        write(archive, 'package-manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())
    with ZipFile(temporary) as archive:
        if archive.testzip() is not None:
            raise ValueError('Archive integrity check failed.')
        for item in manifest['files']:
            if hashlib.sha256(archive.read('hearth/' + item['path'])).hexdigest() != item['sha256']:
                raise ValueError('Archive manifest check failed.')
    temporary.replace(output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + '.sha256').write_text(f'{digest}  {output.name}\n', encoding='ascii')
    return {'zip': str(output), 'bytes': output.stat().st_size, 'sha256': digest,
            'files': len(manifest['files']) + 1,
            'uncompressed_bytes': sum(item['bytes'] for item in manifest['files'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/hearth-vm.zip')
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))


if __name__ == '__main__':
    main()
