"""Build a deterministic, resource-only Keycloak theme JAR. No Java providers."""
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def package():
    source = ROOT / 'deploy/identity/themes/hearth'
    target = ROOT / '.hearth/packages/hearth-identity-theme.jar'
    target.parent.mkdir(parents=True, exist_ok=True)
    files = {'META-INF/keycloak-themes.json': json.dumps({'themes': [{'name': 'hearth', 'types': ['login']}]}).encode()}
    for path in sorted(source.rglob('*')):
        if path.is_file():
            files['theme/hearth/' + path.relative_to(source).as_posix()] = path.read_bytes()
    with ZipFile(target, 'w', compression=ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = ZipInfo(name, date_time=(2026, 9, 12, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    print('Packaged .hearth/packages/hearth-identity-theme.jar')
    return target


if __name__ == '__main__':
    package()
