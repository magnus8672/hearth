"""Build the Windows AMD64 development runner package, without identities/weights."""
import hashlib
import json
import os
import subprocess
import zipfile

from dev import ROOT, go_executable


def main():
    binaries = ROOT/'.hearth/bin/windows-runner'
    binaries.mkdir(parents=True, exist_ok=True)
    for name in ('hearth-worker', 'hearth-connector'):
        subprocess.run([go_executable(), 'build', '-trimpath', '-o', str(binaries/(name+'.exe')), './cmd/'+name],
                       cwd=ROOT/'worker', env=os.environ | {'GOOS': 'windows', 'GOARCH': 'amd64', 'CGO_ENABLED': '0'}, check=True)
    out = ROOT/'dist/runners'
    out.mkdir(parents=True, exist_ok=True)
    package = out/'hearth-runner-windows-amd64-preview.zip'
    files = [(p, 'bin/'+p.name) for p in binaries.glob('*.exe')]
    files += [(ROOT/p, p) for p in ['scripts/prepare_windows_runner.py', 'scripts/prepare_ncm.py', 'docs/operations/WINDOWS_RUNNER.md', 'docs/operations/NCM_THIRD_PARTY.md', 'LICENSE']]
    files += [(p, str(p.relative_to(ROOT)).replace('\\', '/')) for p in (ROOT/'runtimes/ncm').iterdir() if p.is_file()]
    with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for path, name in files:
            z.write(path, name)
    manifest = {'kind': 'windows-runner-development-preview', 'authenticode_signed': False,
                'file': package.name, 'sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
                'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'source_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
                'files': {name: hashlib.sha256(path.read_bytes()).hexdigest() for path, name in files}}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(str(package))


if __name__ == '__main__':
    main()
