"""Operator installation of the pinned Linux CUDA geometry provider.

Run on the GPU machine as root. This console action downloads the approved
inventory, prepares a private TLS service, and leaves it stopped for adoption.
"""
import argparse
import ipaddress
import json
import os
import pwd
import secrets
import shutil
import subprocess
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run(list(map(str, args)), check=True)


def install(args):
    if os.geteuid() != 0:
        raise SystemExit('Run this installer as root on the Linux GPU worker.')
    account = pwd.getpwnam(args.user)
    for value in (args.host, args.controller):
        address = ipaddress.ip_address(value)
        if address.version != 4 or not address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified:
            raise ValueError('Supply the private LAN IPv4 addresses of the GPU worker and head.')
    root, state = args.root.resolve(), args.state.resolve()
    if root == Path('/') or state == Path('/') or any(c.isspace() for c in str(root) + str(state)):
        raise ValueError('Use dedicated absolute directories without spaces.')
    if (state / 'config.json').exists():
        raise SystemExit('Existing provider preserved. Drain it and review a signed recipe update before upgrading.')
    backend = args.backend
    if (root / 'inventory.json').exists():
        installed = json.loads((root / 'inventory.json').read_text())
        expected = 'hunyuan3d/2.0' if backend == 'hunyuan' else 'trellis2/q8'
        if installed.get('model') != expected:
            raise SystemExit('This directory belongs to a different model. Use a separate installation root.')
    runtime = SOURCE / ('runtimes/hunyuan' if backend == 'hunyuan' else 'runtimes/geometry')
    run('python3', runtime / 'prepare.py', '--root', root)
    (root / 'app/hearth').mkdir(parents=True, exist_ok=True)
    for name in ('contracts.py', 'geometry_validation.py'):
        shutil.copy2(SOURCE / 'services/api/src/hearth' / name, root / 'app/hearth' / name)
    (root / 'app/hearth/__init__.py').touch()
    shutil.copy2(SOURCE / 'runtimes/geometry/hearth_geometry.py', root / 'app/hearth_geometry.py')
    if backend == 'hunyuan':
        shutil.copy2(runtime / 'hunyuan_runner.py', root / 'app/hunyuan_runner.py')
    shutil.copy2(runtime / 'requirements.txt', root / 'requirements.txt')
    run('python3', '-m', 'venv', root / '.venv')
    indexes = ['--extra-index-url', 'https://download.pytorch.org/whl/cu126'] if backend == 'hunyuan' else []
    run(root / '.venv/bin/pip', 'install', '--require-hashes', *indexes, '-r', root / 'requirements.txt')
    state.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chown(state, 0, account.pw_gid)
    (state / 'jobs').mkdir(mode=0o700)
    os.chown(state / 'jobs', account.pw_uid, account.pw_gid)
    previous = os.umask(0o077)
    try:
        (state / 'controller.key').write_text(secrets.token_hex(32))
        run('openssl', 'req', '-x509', '-newkey', 'rsa:3072', '-nodes', '-days', '3650', '-keyout', state / 'ca.key', '-out', state / 'ca.pem', '-subj', '/CN=hearth geometry ' + secrets.token_hex(8), '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
        run('openssl', 'req', '-newkey', 'rsa:3072', '-nodes', '-keyout', state / 'server.key', '-out', state / 'server.csr', '-subj', '/CN=' + args.host)
        (state / 'extensions').write_text(f'subjectAltName=IP:{args.host},IP:127.0.0.1\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n')
        run('openssl', 'x509', '-req', '-in', state / 'server.csr', '-CA', state / 'ca.pem', '-CAkey', state / 'ca.key', '-CAcreateserial', '-days', '365', '-out', state / 'server.pem', '-extfile', state / 'extensions')
        config = {'installation': str(root), 'jobs': str(state / 'jobs'), 'token_file': str(state / 'controller.key'),
                  'listen': '0.0.0.0', 'port': args.port, 'health_port': args.health_port,
                  'tls_key': str(state / 'server.key'), 'tls_cert': str(state / 'server.pem'),
                  'allowed_hosts': [args.host, '127.0.0.1'], 'allowed_controllers': [args.controller, '127.0.0.1']}
        (state / 'config.json').write_text(json.dumps(config, indent=2)+'\n')
        for name in ('server.key', 'server.pem', 'controller.key', 'config.json'):
            path = state / name
            path.chmod(0o640)
            os.chown(path, 0, account.pw_gid)
    finally:
        os.umask(previous)
    unit = (SOURCE / 'runtimes/geometry/hearth-trellis.service').read_text()
    unit = unit.replace('User=operator', 'User=' + args.user).replace('Group=operator', 'Group=' + str(account.pw_gid)).replace('/opt/hearth-trellis', str(root)).replace('/var/lib/hearth-trellis', str(state))
    if backend == 'hunyuan':
        unit = unit.replace('TRELLIS', 'Hunyuan3D 2.0')
        unit = unit.replace('[Service]', '[Service]\nEnvironment=PYTHONDONTWRITEBYTECODE=1\nEnvironment=NUMBA_CACHE_DIR=' + str(state / 'jobs/cache'))
    (Path('/etc/systemd/system') / ('hearth-hunyuan.service' if backend == 'hunyuan' else 'hearth-trellis.service')).write_text(unit)
    run('systemctl', 'daemon-reload')
    print(f'Prepared https://{args.host}:{args.port}/v1, backend {backend}. Service remains stopped.')
    print(f'Public CA: {state / "ca.pem"}. Controller key stays in {state / "controller.key"}.')
    print('Review the installed files, register the provider, and sign its worker recipe before activation.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--controller', required=True)
    parser.add_argument('--backend', choices=['trellis', 'hunyuan'], default='trellis')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--port', type=int)
    parser.add_argument('--health-port', type=int)
    args = parser.parse_args()
    args.root = args.root or Path('/opt/hearth-' + args.backend)
    args.state = args.state or Path('/var/lib/hearth-' + args.backend)
    if args.port is None:
        args.port = 1238 if args.backend == 'hunyuan' else 1236
    if args.health_port is None:
        args.health_port = 1239 if args.backend == 'hunyuan' else 1237
    if args.port == args.health_port or not all(1024 <= port <= 65535 for port in (args.port, args.health_port)):
        parser.error('Choose two different unprivileged ports.')
    install(args)


if __name__ == '__main__':
    main()
