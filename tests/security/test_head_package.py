"""Fresh-farm packaging must omit private state and the developer appliance."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

from scripts import package_head


def test_fresh_package_excludes_state_and_checks_every_payload(tmp_path):
    root = tmp_path / 'source'
    for name in package_head.FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'public source\r\n')
    for name in package_head.TREES:
        (root / name).mkdir(parents=True, exist_ok=True)
    for app in ('admin', 'user'):
        (root / f'apps/{app}-web/dist/index.html').write_text('<html></html>')
    private_paths = (
        '.hearth/head/config.json', '.env', '.venv/private.py',
        'runtimes/speech/.venv/private.py', 'runtimes/speech/credentials.json',
        'services/api/src/.hearth/config.json', 'services/api/src/__pycache__/secret.py',
        'apps/admin-web/dist/.env.json', 'apps/admin-web/dist/assets/private.key',
    )
    for name in private_paths:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'private-data-must-not-ship')
    output = tmp_path / 'head.zip'
    result = package_head.build(output, root=root)
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read('hearth/package-manifest.json'))
        assert manifest['contains_farm_data'] is False
        assert manifest['requires_network_on_first_start'] is True
        assert set(archive.namelist()) == {'hearth/package-manifest.json'} | {
            'hearth/' + item['path'] for item in manifest['files']
        }
        for item in manifest['files']:
            content = archive.read('hearth/' + item['path'])
            assert b'private-data-must-not-ship' not in content
            assert len(content) == item['bytes']
            assert hashlib.sha256(content).hexdigest() == item['sha256']
        assert b'\r\n' not in archive.read('hearth/deploy/compose/init-databases.sh')
    assert output.with_suffix('.zip.sha256').read_text().startswith(result['sha256'])


def test_standalone_identity_console_imports_without_appliance(tmp_path):
    root = Path(__file__).resolve().parents[2]
    for name in ('configure_identity.py', 'head_console.py'):
        shutil.copyfile(root / 'scripts' / name, tmp_path / name)
    program = (
        'import sys; sys.path.insert(0, sys.argv[1]); '
        'import head_console; '
        'assert "development_stack" not in sys.modules; '
        'assert "appliance" not in sys.modules'
    )
    subprocess.run([sys.executable, '-I', '-B', '-c', program, str(tmp_path)],
                   cwd=tmp_path, capture_output=True, text=True, check=True)
