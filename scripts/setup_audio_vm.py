"""Install independent CPU speech services on an Ubuntu 24.04 x86-64 VM.

Explicit model preparation is separate from normal service startup. This helper
does not migrate a farm, alter routing, or use the developer QEMU host aliases.
"""
import argparse
import hashlib
import ipaddress
import json
import os
import platform
import re
import secrets
import shutil
import ssl
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = Path('/var/lib/hearth-audio')
PRIVATE = Path('/etc/hearth-audio')
UNITS = Path('/etc/systemd/system')
RECIPES = {
    'speech': {'port': 1236, 'model': 'kokoro-82m-v1.0-onnx', 'path': '/v1/speech-provider', 'script': 'hearth_speech.py'},
    'transcription': {'port': 1237, 'model': 'faster-whisper-small.en', 'path': '/v1/transcription-provider', 'script': 'hearth_transcription.py'},
}


def run(*args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def address_value(value):
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        # Certificate/Host configuration is code-adjacent, never permit shell,
        # OpenSSL extension or systemd syntax in this value.
        if not re.fullmatch(r'(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', value):
            raise argparse.ArgumentTypeError('Use a plain VM hostname or private IPv4 address.') from None
        if any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-') for label in value.split('.')):
            raise argparse.ArgumentTypeError('Use a valid hostname.') from None
        return value.lower()
    if ip.version != 4 or not (ip.is_loopback or any(ip in ipaddress.ip_network(net) for net in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'])):
        raise argparse.ArgumentTypeError('Use a private LAN or loopback IPv4 address.')
    return str(ip)


def quoted(value):
    return '"'+str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$')+'"'


def write(path, value, mode=0o600):
    temporary = path.with_name(path.name+'.new')
    with temporary.open('w', encoding='utf-8') as stream:
        stream.write(value)
    temporary.chmod(mode)
    temporary.replace(path)


def fetch_models(folder):
    """Only installer runs have network access; every byte is digest-bound."""
    specs = []
    speech = json.loads((ROOT/'runtimes/speech/model-manifest.json').read_text())
    for key, name in [('model', 'kokoro-v1.0.onnx'), ('voices', 'voices-v1.0.bin')]:
        specs.append((folder/'kokoro'/name, speech['files'][key], 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/'+name))
    transcription = json.loads((ROOT/'runtimes/transcription/model-manifest.json').read_text())
    for name, item in transcription['files'].items():
        if Path(name).name != name:
            raise RuntimeError('Manifest files must be plain names.')
        specs.append((folder/'faster-whisper-small.en'/name, item, f"https://huggingface.co/{transcription['repository']}/resolve/{transcription['revision']}/{name}"))
    def valid(path, spec):
        if not path.is_file() or path.stat().st_size != spec['bytes']:
            return False
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest() == spec['sha256']
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for path, spec, url in specs:
        if valid(path, spec):
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name+'.part')
        with opener.open(url, timeout=120) as response, temporary.open('wb') as stream:
            size = 0
            while block := response.read(1024*1024):
                size += len(block)
                if size > spec['bytes']:
                    raise RuntimeError('Model download exceeded its declared size.')
                stream.write(block)
        if not valid(temporary, spec):
            raise RuntimeError('Model digest verification failed; no new file was activated.')
        temporary.replace(path)


def certificates(address):
    tls = STATE/'tls'
    tls.mkdir(mode=0o750, exist_ok=True)
    tls.chmod(0o750)
    shutil.chown(tls, user='root', group='hearth-audio')
    ca_key, ca = PRIVATE/'ca.key', PRIVATE/'ca.crt'
    if ca_key.exists() != ca.exists():
        raise RuntimeError('The provider CA is incomplete. Restore its matching key and certificate.')
    if not ca.exists():
        run('openssl', 'req', '-x509', '-newkey', 'rsa:3072', '-nodes', '-keyout', ca_key, '-out', ca,
            '-days', '3650', '-subj', '/CN=hearth audio provider CA', '-addext', 'basicConstraints=critical,CA:TRUE',
            '-addext', 'keyUsage=critical,keyCertSign,cRLSign', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ca_key.chmod(0o600)
    cert, key = tls/'server.crt', tls/'server.key'
    if cert.exists() and key.exists() and subprocess.run(['openssl', 'x509', '-checkend', '2592000', '-noout', '-in', str(cert)], stdout=subprocess.DEVNULL).returncode == 0:
        return False
    try:
        ipaddress.ip_address(address)
        san = 'IP:'+address
    except ValueError:
        san = 'DNS:'+address
    extensions = PRIVATE/'server.ext'
    write(extensions, 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName='+san+',DNS:localhost,IP:127.0.0.1\n')
    run('openssl', 'req', '-new', '-newkey', 'rsa:3072', '-nodes', '-keyout', str(key)+'.new', '-out', PRIVATE/'server.csr', '-subj', '/CN=hearth audio provider', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run('openssl', 'x509', '-req', '-in', PRIVATE/'server.csr', '-CA', ca, '-CAkey', ca_key, '-set_serial', str(secrets.randbits(128)),
        '-out', str(cert)+'.new', '-days', '397', '-sha256', '-extfile', extensions, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for path in [key, cert]:
        temporary = path.with_name(path.name+'.new')
        temporary.chmod(0o600)
        shutil.chown(temporary, user='hearth-audio', group='hearth-audio')
        temporary.replace(path)
    write(STATE/'provider-ca.crt', ca.read_text(), 0o644)
    return True


def service(kind):
    runtime = ROOT/'runtimes'/kind
    return '\n'.join([
        '[Unit]', f'Description=hearth CPU {kind} provider', 'After=network.target', '', '[Service]',
        'Type=exec', 'User=hearth-audio', 'Group=hearth-audio', 'UMask=0077',
        'WorkingDirectory='+str(runtime).replace('%', '%%'), 'Environment='+quoted('PYTHONPATH='+str(ROOT/'services/api/src')),
        'Environment=OMP_NUM_THREADS=4', 'Environment=PYTHONDONTWRITEBYTECODE=1', 'Environment=HF_HUB_OFFLINE=1',
        'ExecStart='+ ' '.join(quoted(p) for p in [runtime/'.venv/bin/python', runtime/RECIPES[kind]['script'], '--config', STATE/kind/'config.json']),
        'Restart=on-failure', 'RestartSec=5', 'TimeoutStopSec=180', 'NoNewPrivileges=true',
        'PrivateTmp=true', 'ProtectSystem=strict', 'ProtectHome=true', 'RestrictSUIDSGID=true',
        'ReadWritePaths='+quoted(STATE/kind), 'RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX',
        '', '[Install]', 'WantedBy=multi-user.target', '',
    ])


def status(address):
    trust = ssl.create_default_context(cafile=str(STATE/'provider-ca.crt'))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=trust))
    results = []
    for kind, recipe in RECIPES.items():
        token = (STATE/kind/'controller.key').read_text().strip()
        url = f"https://{address}:{recipe['port']}"
        request = urllib.request.Request(url+recipe['path'], headers={'Authorization': 'Bearer '+token})
        with opener.open(request, timeout=10) as response:
            info = json.load(response)
        if info['model'] != recipe['model'] or not info['offline']:
            raise RuntimeError('The provider returned an unexpected model.')
        results.append({'kind': kind, 'url': url, 'model': info['model'], 'protocol': info['protocol'],
                        'credential_file': str(STATE/kind/'controller.key'), 'ca_file': str(STATE/'provider-ca.crt')})
    return results


def install(args):
    if platform.machine() not in {'x86_64', 'AMD64'} or platform.freedesktop_os_release().get('ID') != 'ubuntu' or platform.freedesktop_os_release().get('VERSION_ID') != '24.04':
        raise SystemExit('This first VM recipe targets Ubuntu 24.04 x86-64 with Python 3.12.')
    if ROOT.is_relative_to('/home') or ROOT.is_relative_to('/root'):
        raise SystemExit('Put the checkout in /opt/hearth. Service home-directory isolation is enabled.')
    # The VM guest supplies Python. Never link services to a root-home uv runtime.
    interpreter = Path(shutil.which(args.python) or args.python).resolve(strict=True)
    if run(interpreter, '-c', 'import sys; assert sys.version_info[:2] == (3,12)', capture_output=True).returncode:
        raise SystemExit('Python 3.12 is required.')
    uv = Path(shutil.which(args.uv) or args.uv).resolve(strict=True)
    if subprocess.run(['id', '-u', 'hearth-audio'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        run('useradd', '--system', '--home-dir', str(STATE), '--shell', '/usr/sbin/nologin', 'hearth-audio')
    PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    PRIVATE.chmod(0o700)
    STATE.mkdir(mode=0o750, parents=True, exist_ok=True)
    STATE.chmod(0o750)
    shutil.chown(STATE, user='root', group='hearth-audio')
    previous = PRIVATE/'installation.json'
    if previous.exists() and json.loads(previous.read_text())['address'] != args.address:
        raise SystemExit('The saved VM address differs. Keep its stable DNS name or plan a certificate/provider address change.')
    old_mask = os.umask(0o022)
    try:
        for kind in RECIPES:
            run(uv, 'sync', '--locked', '--project', ROOT/'runtimes'/kind, '--python', interpreter, '--no-python-downloads')
    finally:
        os.umask(old_mask)
    fetch_models(STATE/'models')
    for path in [STATE/'models', *(STATE/'models').rglob('*')]:
        path.chmod(0o750 if path.is_dir() else 0o640)
        shutil.chown(path, user='root', group='hearth-audio')
    certificates(args.address)
    for kind, recipe in RECIPES.items():
        folder = STATE/kind
        folder.mkdir(mode=0o700, exist_ok=True)
        shutil.chown(folder, user='hearth-audio', group='hearth-audio')
        token = folder/'controller.key'
        if not token.exists():
            write(token, secrets.token_urlsafe(48))
        config = {'bind': '0.0.0.0', 'port': recipe['port'], 'hosts': [args.address, 'localhost', '127.0.0.1'],
                  'jobs': str(folder/'jobs'), 'token_file': str(token),
                  'tls_key': str(STATE/'tls/server.key'), 'tls_cert': str(STATE/'tls/server.crt')}
        if kind == 'speech':
            config.update(model=str(STATE/'models/kokoro/kokoro-v1.0.onnx'), voices=str(STATE/'models/kokoro/voices-v1.0.bin'))
        else:
            config['model'] = str(STATE/'models/faster-whisper-small.en')
        write(folder/'config.json', json.dumps(config, indent=2))
        for path in [token, folder/'config.json']:
            path.chmod(0o600)
            shutil.chown(path, user='hearth-audio', group='hearth-audio')
        write(UNITS/f'hearth-{kind}.service', service(kind), 0o644)
    write(previous, json.dumps({'address': args.address, 'source': str(ROOT)}, indent=2))
    # The root timer executes a root-owned copy, never a writable checkout.
    write(PRIVATE/'renew.py', Path(__file__).read_text())
    write(UNITS/'hearth-audio-certificates.service', '[Unit]\nDescription=Renew hearth audio provider certificates\n\n[Service]\nType=oneshot\nExecStart='+quoted(interpreter)+' '+quoted(PRIVATE/'renew.py')+' renew-certificates\n', 0o644)
    write(UNITS/'hearth-audio-certificates.timer', '[Unit]\nDescription=Check hearth audio TLS certificates daily\n\n[Timer]\nOnCalendar=daily\nPersistent=true\nRandomizedDelaySec=1h\n\n[Install]\nWantedBy=timers.target\n', 0o644)
    run('systemd-analyze', 'verify', UNITS/'hearth-speech.service', UNITS/'hearth-transcription.service', UNITS/'hearth-audio-certificates.service', UNITS/'hearth-audio-certificates.timer')
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', '--now', 'hearth-speech.service', 'hearth-transcription.service', 'hearth-audio-certificates.timer')
    # Re-running install preserves credentials/jobs and doesn't restart active
    # models. Explicit service restart is required after changing runtime code.
    for _attempt in range(90):
        try:
            report = status(args.address)
            write(STATE/'registration.json', json.dumps(report, indent=2), 0o644)
            print(json.dumps(report, indent=2))
            return
        except (OSError, ValueError):
            time.sleep(2)
    raise SystemExit('Services were installed but are not ready. Inspect systemctl status and the service journal; credentials were preserved.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'status', 'renew-certificates'])
    parser.add_argument('--address', type=address_value)
    parser.add_argument('--python', default='python3.12')
    parser.add_argument('--uv', default='uv')
    args = parser.parse_args()
    if os.name != 'posix' or os.geteuid() != 0:
        raise SystemExit('Run this VM installer with sudo inside the Linux VM.')
    os.umask(0o077)
    if args.action == 'install':
        if not args.address:
            parser.error('install requires --address with the stable VM hostname or private IPv4 address.')
        install(args)
    else:
        config = json.loads((PRIVATE/'installation.json').read_text())
        if args.action == 'status':
            print(json.dumps(status(config['address']), indent=2))
        elif certificates(config['address']):
            # Certificate renewal restarts these independent CPU providers.
            # Existing jobs retain receipts; they are never replayed.
            run('systemctl', 'restart', 'hearth-speech.service', 'hearth-transcription.service')


if __name__ == '__main__':
    main()
