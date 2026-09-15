"""Build portable development connectors. Packages contain no runtime identities."""
import hashlib
import json
import os
import subprocess
import zipfile

from dev import ROOT, go_executable


def main():
    out = ROOT / 'dist/connectors'
    out.mkdir(parents=True, exist_ok=True)
    manifest = {'kind': 'unsigned-development-connectors', 'packages': []}
    for system, architecture in [('windows', 'amd64'), ('linux', 'amd64'), ('linux', 'arm64'), ('darwin', 'arm64'), ('darwin', 'amd64')]:
        name = f'hearth-connector-{system}-{architecture}'
        binary = ROOT / '.hearth/bin' / name / ('hearth-connector.exe' if system == 'windows' else 'hearth-connector')
        binary.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([go_executable(), 'build', '-trimpath', '-o', str(binary), './cmd/hearth-connector'],
                       cwd=ROOT / 'worker', env=os.environ | {'GOOS': system, 'GOARCH': architecture, 'CGO_ENABLED': '0'}, check=True)
        package = out / (name + '.zip')
        with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(binary, binary.name)
            archive.write(ROOT / 'docs/implementation/LAN_PROVIDER_TESTING.md', 'README.md')
        manifest['packages'].append({'file': package.name, 'sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
                                     'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'bytes': package.stat().st_size})
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
