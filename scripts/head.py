"""Prepare and operate a standalone Linux LAN head, without the QEMU appliance."""

import argparse
import getpass
import hashlib
import html
import io
import ipaddress
import json
import os
import re
import secrets
import ssl
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.hearth/head'
SECRET_NAMES = (
    'POSTGRES_PASSWORD', 'HEARTH_APP_PASSWORD', 'HEARTH_MIGRATION_PASSWORD',
    'HEARTH_IDENTITY_PASSWORD', 'HEARTH_IDENTITY_BOOTSTRAP_PASSWORD',
    'HEARTH_SESSION_ENCRYPTION_KEY', 'HEARTH_CA_PASSWORD',
    'HEARTH_ADMIN_CLIENT_SECRET', 'HEARTH_USER_CLIENT_SECRET',
)


def public_host(value):
    """The advertised IPv4/DNS address is distinct from the wildcard listener."""
    value = value.strip().lower()
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        labels = value.split('.')
        if (len(value) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                                        for label in labels)
                or labels[-1].isdigit() or value == 'localhost' or value.endswith('.localhost')):
            raise ValueError('Use the VM IPv4 address or DNS name, without a scheme, port or path.') from None
        return value
    if address.version != 4 or address.is_unspecified or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved:
        raise ValueError('Use a reachable VM IPv4 address. 0.0.0.0 is the listener, not its public address.')
    return str(address)


def endpoints(host, ports):
    host = public_host(host)
    if len(ports) != 3 or len(set(ports)) != 3 or any(type(port) is not int or not 1 <= port <= 65535 for port in ports):
        raise ValueError('Choose three distinct ports between 1 and 65535.')
    values = {'HEARTH_PUBLIC_HOST': host, 'HEARTH_TRUSTED_HOSTS': json.dumps([host])}
    for audience, port in zip(('ADMIN', 'USER', 'IDENTITY'), ports, strict=True):
        values[f'HEARTH_{audience}_PORT'] = str(port)
        values[f'HEARTH_{audience}_ORIGIN'] = f'https://{host}' + (f':{port}' if port != 443 else '')
    values['HEARTH_IDENTITY_AUTHORITY'] = urlsplit(values['HEARTH_IDENTITY_ORIGIN']).netloc
    return values


def base_url_endpoints(value, ports=None):
    """An HTTPS workspace origin determines the certificate name and user port."""
    value = value.strip(' ')
    error = 'Use an HTTPS workspace base URL, for example https://hearth.home.arpa:8444, without credentials, /v1, another path, query or fragment.'
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value) or '?' in value or '#' in value:
        raise ValueError(error)
    try:
        parsed = urlsplit(value)
        port = parsed.port if parsed.port is not None else 443
    except ValueError:
        raise ValueError(error) from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.path not in ('', '/') or parsed.netloc.endswith(':')):
        raise ValueError(error)
    chosen_ports = (8443, port, 8445) if ports is None else ports
    public = endpoints(parsed.hostname, chosen_ports)
    if chosen_ports[1] != port:
        raise ValueError('The workspace port in --ports must match the base URL port (443 when omitted).')
    return public


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    # Replace an incomplete write atomically, never truncate authoritative credentials.
    descriptor, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content.encode('utf-8') if isinstance(content, str) else content)
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def configure(state, host=None, ports=None, project='hearth-head', *, base_url=None):
    state = state.resolve()
    if not re.fullmatch(r'hearth-[a-z0-9-]{1,40}', project) or project == 'hearth-development':
        raise ValueError('Choose a separate hearth-* Compose project, not hearth-development.')
    if (host is None) == (base_url is None):
        raise ValueError('Supply one base URL or one host, not both.')
    public = base_url_endpoints(base_url, ports) if base_url is not None else endpoints(host, ports or (8443, 8444, 8445))
    path = state / 'config.json'
    if path.exists():
        values = load(state)
        if any(values.get(key) != value for key, value in public.items()) or values['HEARTH_COMPOSE_PROJECT'] != project:
            raise ValueError('This head already has a fixed address/project. Address changes require an identity migration; existing credentials were preserved.')
        return values
    values = public | {name: secrets.token_urlsafe(32) for name in SECRET_NAMES}
    values.update(HEARTH_FARM_ID=str(uuid4()), HEARTH_COMPOSE_PROJECT=project)
    private_write(path, json.dumps(values, indent=2) + '\n')
    return values


def load(state):
    path = state / 'config.json'
    if not path.exists():
        raise ValueError('Configure the head first: python3 scripts/head.py configure --base-url https://<VM-IP-or-DNS>.')
    values = json.loads(path.read_text(encoding='utf-8'))
    if not all(isinstance(values.get(name), str) and values[name] for name in (*SECRET_NAMES, 'HEARTH_FARM_ID', 'HEARTH_COMPOSE_PROJECT')):
        raise ValueError('The private head configuration is incomplete. Restore its backup; do not regenerate farm keys.')
    return values


def compose_context(state):
    values = load(state)
    ca_path = state / 'ca-password'
    # Auxiliary files are reproducible from config.json after relocation.
    private_write(ca_path, values['HEARTH_CA_PASSWORD'])
    private_write(state / 'empty.env', '')
    command = ['docker', 'compose', '--project-name', values['HEARTH_COMPOSE_PROJECT'],
               '--env-file', str(state / 'empty.env'),
               '-f', str(ROOT / 'deploy/compose/development.yaml'),
               '-f', str(ROOT / 'deploy/compose/head.yaml')]
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(('HEARTH_', 'COMPOSE_'))}
    setup_port = setup_http_port(values)
    public_directory = state / 'public-setup'
    public_directory.mkdir(exist_ok=True, mode=0o755)
    public_directory.chmod(0o755)
    # Only the admin BFF receives this Unix socket directory, never Docker or PKI keys.
    control_directory = state / 'control'
    control_directory.mkdir(exist_ok=True, mode=0o755)
    write_aliases(state, values)
    default_sni = values['HEARTH_PUBLIC_HOST']
    # Preserve old IP bookmarks from clients that omit SNI. DNS clients send
    # their hostname and still select its newly issued certificate normally.
    try:
        ipaddress.ip_address(default_sni)
    except ValueError:
        for origins in reversed(json.loads(values.get('HEARTH_PREVIOUS_ENDPOINTS', '[]'))):
            candidate = urlsplit(origins[0]).hostname
            try:
                ipaddress.ip_address(candidate)
                default_sni = candidate
                break
            except ValueError:
                pass
    environment.update(values, HEARTH_CA_PASSWORD_FILE=str(ca_path),
                       HEARTH_CONTROL_DIR=str(control_directory),
                       HEARTH_DEFAULT_SNI=default_sni,
                       HEARTH_SETUP_HTTP_PORT=str(setup_port),
                       HEARTH_SETUP_PUBLIC_DIR=str(public_directory))
    return command, environment


def write_aliases(state, values):
    """Old bookmarks get a fresh sign-in; never forward credentials or callback codes."""
    previous = json.loads(values.get('HEARTH_PREVIOUS_ENDPOINTS', '[]'))
    blocks = []
    current = {values[f'HEARTH_{audience}_ORIGIN'] for audience in ('ADMIN', 'USER', 'IDENTITY')}
    current.add(setup_url(values))
    for origins in previous[-4:]:
        parsed = [urlsplit(origin) for origin in origins]
        if len(parsed) != 3 or len({item.hostname for item in parsed}) != 1:
            raise ValueError('Invalid previous head addresses.')
        checked = endpoints(parsed[0].hostname, [item.port or 443 for item in parsed])
        if origins != [checked[f'HEARTH_{audience}_ORIGIN'] for audience in ('ADMIN', 'USER', 'IDENTITY')]:
            raise ValueError('Invalid previous head addresses.')
        welcome = setup_url(checked)
        if welcome not in current and setup_http_port(checked) == setup_http_port(values):
            blocks.append(welcome + ' {\n @unsafe not method GET HEAD\n respond @unsafe 405\n redir ' + setup_url(values) + '/ 303\n}\n')
            current.add(welcome)
        for audience, origin in zip(('ADMIN', 'USER', 'IDENTITY'), origins, strict=True):
            if origin in current or (urlsplit(origin).port or 443) != int(values[f'HEARTH_{audience}_PORT']):
                continue
            # A safe navigation to the new root, not an open redirect or forwarded POST.
            blocks.append(origin + ' {\n tls internal\n @unsafe not method GET HEAD\n respond @unsafe 405\n redir ' + values[f'HEARTH_{audience}_ORIGIN'] + '/ 303\n}\n')
            current.add(origin)
    path = state / 'public-setup/Caddyfile.aliases'
    path.write_text('\n'.join(blocks), encoding='utf-8')
    path.chmod(0o644)


def setup_http_port(values):
    # Preserve existing HTTPS port choices, even an unusual HTTPS listener on 80.
    used = {int(values[f'HEARTH_{audience}_PORT']) for audience in ('ADMIN', 'USER', 'IDENTITY')}
    return next(port for port in (80, 8080, 8081, 8082) if port not in used)


def setup_url(values):
    port = setup_http_port(values)
    return 'http://' + values['HEARTH_PUBLIC_HOST'] + (f':{port}' if port != 80 else '')


def compose(state, *arguments, **options):
    command, environment = compose_context(state)
    return subprocess.run([*command, *arguments], env=environment, cwd=ROOT, check=True, **options)


def require_compose():
    result = subprocess.run(['docker', 'compose', 'version', '--short'], capture_output=True, text=True, check=True)
    match = re.search(r'(\d+)\.(\d+)\.(\d+)', result.stdout)
    if not match or tuple(map(int, match.groups())) < (2, 24, 4):
        raise ValueError('Docker Compose 2.24.4 or newer is required for the safe port overrides.')


def export_ca(state):
    result = compose(state, 'exec', '-T', 'edge', 'cat', '/data/caddy/pki/authorities/local/root.crt', capture_output=True)
    certificate = result.stdout.decode('ascii')
    if not certificate.startswith('-----BEGIN CERTIFICATE-----') or 'PRIVATE KEY' in certificate:
        raise ValueError('The edge root certificate is not ready.')
    path = state / 'hearth-root.crt'
    private_write(path, certificate)
    print(f'Public trust certificate: {path}')
    return certificate


def certificate_der(pem):
    """Accept certificate PEM blocks only, never a key or unrelated material."""
    pattern = r'-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\s]+-----END CERTIFICATE-----'
    blocks = re.findall(pattern, pem)
    if not blocks or re.sub(pattern, '', pem).strip():
        raise ValueError('The certificate export must contain only public certificates.')
    return [ssl.PEM_cert_to_DER_cert(block) for block in blocks]


def certificate_package(values, root_pem, server_pem):
    roots, chain = certificate_der(root_pem), certificate_der(server_pem)
    if len(roots) != 1:
        raise ValueError('Expected one public root certificate.')
    metadata = {
        'schema_version': 1,
        'base_url': values['HEARTH_USER_ORIGIN'],
        'admin_url': values['HEARTH_ADMIN_ORIGIN'],
        'identity_url': values['HEARTH_IDENTITY_ORIGIN'],
        'api_base_url': values['HEARTH_USER_ORIGIN'] + '/v1',
        'mcp_url': values['HEARTH_USER_ORIGIN'] + '/mcp',
        'server_name': values['HEARTH_PUBLIC_HOST'],
        'root_sha256': hashlib.sha256(roots[0]).hexdigest(),
        'server_sha256': hashlib.sha256(chain[0]).hexdigest(),
    }
    instructions = (
        'hearth client certificate package\n\n'
        f"Workspace: {metadata['base_url']}\n"
        f"Administration: {metadata['admin_url']}\n"
        f"Client API: {metadata['api_base_url']}\n"
        f"MCP: {metadata['mcp_url']}\n\n"
        f"Root certificate SHA-256: {metadata['root_sha256']}\n\n"
        'Compare this fingerprint with the VM console over your trusted access path.\n'
        'Import hearth-root.crt (PEM) or hearth-root.cer (DER) as a trusted root in your client/browser.\n'
        'Use hearth-root.crt as the CA bundle for Python clients or NODE_EXTRA_CA_CERTS for Node clients.\n'
        'Keep HTTPS certificate verification enabled. DNS must resolve the server name to your VM.\n'
        'hearth-server-chain.pem is the current public server certificate and intermediate chain.\n'
        'Caddy renews it automatically; clients should trust the root rather than pin this short-lived leaf.\n'
        'No private keys, account passwords or API keys are included. Create an API key in your workspace.\n'
    )
    output = io.BytesIO()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for name, content in {
            'hearth-root.crt': root_pem, 'hearth-root.cer': roots[0],
            'hearth-server-chain.pem': server_pem,
            'install-hearth-certificate.cmd': windows_trust_installer(roots[0]),
            'connection.json': json.dumps(metadata, indent=2) + '\n', 'README.txt': instructions,
        }.items():
            archive.writestr(name, content)
    return output.getvalue(), metadata


def windows_trust_installer(der):
    """One public-root installer, no download/elevation or execution of remote code."""
    import base64
    encoded = base64.b64encode(der).decode('ascii')
    fingerprint = hashlib.sha256(der).hexdigest().upper()
    script = (
        "$ErrorActionPreference='Stop'; "
        f"$bytes=[Convert]::FromBase64String('{encoded}'); "
        "$sha=[Security.Cryptography.SHA256]::Create(); "
        "$actual=([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-',''); "
        f"if($actual -ne '{fingerprint}'){{throw 'Certificate integrity check failed'}}; "
        "Write-Host 'Trust this hearth for your Windows account?'; "
        "Write-Host ('Root SHA-256: '+$actual); "
        "Write-Host 'Compare this fingerprint with your farm administrator before continuing.'; "
        "if((Read-Host 'Type YES to install this root certificate') -cne 'YES'){exit 1}; "
        "$cert=[Security.Cryptography.X509Certificates.X509Certificate2]::new($bytes); "
        "$store=[Security.Cryptography.X509Certificates.X509Store]::new('Root','CurrentUser'); "
        "$store.Open('ReadWrite'); try{$store.Add($cert)}finally{$store.Close()}; "
        "Write-Host 'Installed for your Windows account. Return to the welcome page and check connections.'; "
        "Write-Host 'Zen or Firefox may also require import in their certificate Authorities settings.'"
    )
    return ('@echo off\r\nrem hearth public root installer; no administrator privileges required.\r\n'
            'powershell.exe -NoProfile -Command "'+script+'"\r\n'
            'if errorlevel 1 echo Certificate installation did not complete.\r\npause\r\n')


def export_certificates(state):
    values = load(state)
    root_pem = export_ca(state)
    host = public_host(values['HEARTH_PUBLIC_HOST'])
    result = compose(state, 'exec', '-T', 'edge', 'cat',
                     f'/data/caddy/certificates/local/{host}/{host}.crt', capture_output=True)
    package, metadata = certificate_package(values, root_pem, result.stdout.decode('ascii'))
    path = state / 'hearth-client-certificates.zip'
    private_write(path, package)
    publish_setup(state, package, metadata)
    print(f'Client certificate package: {path}')
    print('Root certificate SHA-256: ' + metadata['root_sha256'])


def publish_setup(state, package, metadata):
    """Publish public certificates only; never mount the farm's private state."""
    folder = state / 'public-setup'
    folder.mkdir(parents=True, exist_ok=True, mode=0o755)
    folder.chmod(0o755)
    replacements = {
        'ADMIN_URL': metadata['admin_url'], 'WORKSPACE_URL': metadata['base_url'],
        'IDENTITY_URL': metadata['identity_url'], 'SERVER_NAME': metadata['server_name'],
        'FINGERPRINT': ':'.join(metadata['root_sha256'][i:i+2] for i in range(0, 64, 2)).upper(),
    }
    page = (ROOT / 'deploy/setup/index.html').read_text(encoding='utf-8')
    for key, value in replacements.items():
        page = page.replace('@@' + key + '@@', html.escape(value, quote=True))
    with ZipFile(io.BytesIO(package)) as archive:
        contents = {name: archive.read(name) for name in ('hearth-root.crt', 'hearth-root.cer', 'connection.json', 'install-hearth-certificate.cmd')}
    contents.update({'index.html': page.encode(), 'hearth-client-certificates.zip': package})
    for name, content in contents.items():
        descriptor, temporary = tempfile.mkstemp(prefix='.' + name, dir=folder)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(content)
            os.chmod(temporary, 0o644)
            os.replace(temporary, folder / name)
        finally:
            Path(temporary).unlink(missing_ok=True)


def show_urls(values):
    print('Configured to listen on 0.0.0.0. Connect using these addresses:')
    print('Welcome & trust: ' + setup_url(values))
    print('Administration: ' + values['HEARTH_ADMIN_ORIGIN'])
    print('Workspace:      ' + values['HEARTH_USER_ORIGIN'])
    print('Client API:     ' + values['HEARTH_USER_ORIGIN'] + '/v1')
    print('MCP:            ' + values['HEARTH_USER_ORIGIN'] + '/mcp')
    print('Sign-in:        ' + values['HEARTH_IDENTITY_ORIGIN'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=STATE, help='Private configuration directory on this VM.')
    actions = parser.add_subparsers(dest='action', required=True)
    config = actions.add_parser('configure')
    address = config.add_mutually_exclusive_group()
    address.add_argument('--base-url', help='Public HTTPS workspace URL, for example https://hearth.home.arpa:8444. Prompts when omitted.')
    address.add_argument('--host', help='Compatibility option: VM IPv4/DNS name, with workspace port 8444 by default.')
    config.add_argument('--ports', nargs=3, type=int, metavar=('ADMIN', 'WORKSPACE', 'IDENTITY'))
    config.add_argument('--project', default='hearth-head')
    actions.add_parser('up')
    actions.add_parser('owner')
    actions.add_parser('status')
    actions.add_parser('export-ca')
    actions.add_parser('export-certificates')
    actions.add_parser('install-control')
    args = parser.parse_args()
    state = args.state.resolve()
    try:
        if sys.platform != 'linux':
            raise ValueError('Run this standalone head helper on the Linux VM. The Windows development launcher is unchanged.')
        if args.action == 'configure':
            if args.base_url is None and args.host is None:
                if not sys.stdin.isatty():
                    raise ValueError('Non-interactive setup needs --base-url https://<VM-IP-or-DNS>.')
                args.base_url = input('Public workspace base URL (https://name-or-IP[:port]): ')
            show_urls(configure(state, args.host, args.ports, args.project, base_url=args.base_url))
            return 0
        values = load(state)
        require_compose()
        if args.action == 'install-control':
            from head_control import install
            install(state)
            return 0
        if args.action == 'up':
            if any(not (ROOT / f'apps/{app}-web/dist/index.html').is_file() for app in ('admin', 'user')):
                raise ValueError('Build both browser bundles with pnpm build before starting the head.')
            compose(state, 'config', '--quiet')
            compose(state, 'up', '-d', '--build')
            compose(state, 'run', '--rm', '--no-deps', '-T', 'head-console', 'configure')
            # Caddy's administration endpoint is disabled; refresh bind mounts by recreation.
            compose(state, 'up', '-d', '--no-deps', '--force-recreate', 'edge')
            export_certificates(state)
            if Path('/run/systemd/system').is_dir() and os.geteuid() == 0:
                from head_control import install
                install(state)
            show_urls(values)
            print('First startup: run python3 scripts/head.py owner to create the Owner account locally.')
        elif args.action == 'owner':
            result = compose(state, 'run', '--rm', '--no-deps', '-T', 'head-console', 'status', capture_output=True, text=True)
            if json.loads(result.stdout)['owner_created']:
                raise ValueError('Owner setup is already complete. Sign in to your existing hearth.')
            data = {'username': input('Owner username: '), 'name': input('Display name: '),
                    'farm_name': input('Farm name: '), 'password': getpass.getpass('Password (14+ characters): ')}
            if data['password'] != getpass.getpass('Repeat password: '):
                raise ValueError('Passwords did not match. No account was created.')
            compose(state, 'run', '--rm', '--no-deps', '-T', 'head-console', 'owner', input=json.dumps(data).encode())
        elif args.action == 'status':
            compose(state, 'ps')
            compose(state, 'run', '--rm', '--no-deps', '-T', 'head-console', 'status')
            show_urls(values)
        elif args.action == 'export-ca':
            export_ca(state)
        else:
            export_certificates(state)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError:
        print('The head command failed. Review the service status before retrying; saved state was preserved.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
