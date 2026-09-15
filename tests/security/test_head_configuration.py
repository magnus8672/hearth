"""LAN configuration must preserve address, credentials and private maintenance services."""

import hashlib
import io
import json
import os
import ssl
import stat
from datetime import UTC, datetime, timedelta
from zipfile import ZipFile

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from hearth.config import Settings

from scripts import head


@pytest.mark.parametrize('host', ['0.0.0.0', '127.0.0.1', 'localhost', 'x.localhost', '::', '::1',
    '169.254.169.254', '224.0.0.1', '255.255.255.255', '10.20.30.999', 'https://10.20.30.60',
    '10.20.30.60:8444', 'hearth/home', '*.home', 'bad\nname', 'x${HOME}', '-bad.home', ''])
def test_listener_and_malformed_advertised_addresses_are_rejected(host):
    with pytest.raises(ValueError):
        head.public_host(host)


@pytest.mark.parametrize('host', ['10.20.30.60', '192.168.1.20', 'hearth.home.arpa', 'hearth-vm'])
def test_private_config_drives_all_origins_and_survives_repeated_setup(tmp_path, host):
    state = tmp_path / 'head'
    values = head.configure(state, host)
    before = (state / 'config.json').read_bytes()
    assert head.configure(state, host) == values
    assert (state / 'config.json').read_bytes() == before
    with pytest.raises(ValueError, match='migration'):
        head.configure(state, 'different.home.arpa')
    with pytest.raises(ValueError, match='migration'):
        head.configure(state, host, (18443, 18444, 18445))
    assert (state / 'config.json').read_bytes() == before
    assert len(set(values[name] for name in head.SECRET_NAMES)) == len(head.SECRET_NAMES)
    assert json.loads(values['HEARTH_TRUSTED_HOSTS']) == [host]
    config = Settings(mode='production', database_url='postgresql+psycopg://app:fixture@postgres/hearth',
        session_encryption_key=values['HEARTH_SESSION_ENCRYPTION_KEY'], trusted_hosts=[host],
        admin_origin=values['HEARTH_ADMIN_ORIGIN'], user_origin=values['HEARTH_USER_ORIGIN'],
        identity_origin=values['HEARTH_IDENTITY_ORIGIN'])
    assert config.issuer == f'https://{host}:8445/realms/hearth'
    if os.name != 'nt':
        assert stat.S_IMODE((state / 'config.json').stat().st_mode) == 0o600
        assert stat.S_IMODE(state.stat().st_mode) == 0o700


@pytest.mark.parametrize('ports', [(8443, 8443, 8445), (0, 8444, 8445), (8443, 8444, 65536), (8443, 8444)])
def test_invalid_port_sets_and_development_project_cannot_be_reused(tmp_path, ports):
    with pytest.raises(ValueError):
        head.configure(tmp_path, 'hearth.home.arpa', ports)
    with pytest.raises(ValueError):
        head.configure(tmp_path, 'hearth.home.arpa', project='hearth-development')
    assert not (tmp_path / 'config.json').exists()


def test_compose_cannot_inherit_development_secrets_or_profiles(tmp_path, monkeypatch):
    values = head.configure(tmp_path, 'HEARTH.home.arpa')
    monkeypatch.setenv('HEARTH_DEVELOPMENT_PROVIDER_ALIASES', 'untrusted fixture')
    monkeypatch.setenv('HEARTH_SESSION_ENCRYPTION_KEY', 'wrong fixture')
    monkeypatch.setenv('COMPOSE_PROFILES', 'qualification,managed-pki')
    command, environment = head.compose_context(tmp_path)
    assert 'HEARTH_DEVELOPMENT_PROVIDER_ALIASES' not in environment
    assert 'COMPOSE_PROFILES' not in environment
    assert environment['HEARTH_SESSION_ENCRYPTION_KEY'] == values['HEARTH_SESSION_ENCRYPTION_KEY']
    assert not any(values[name] in ' '.join(command) for name in head.SECRET_NAMES)
    assert command[command.index('--env-file') + 1] == str(tmp_path / 'empty.env')
    assert (tmp_path / 'empty.env').read_text() == ''
    assert environment['HEARTH_PUBLIC_HOST'] == 'hearth.home.arpa'


def test_missing_credential_never_silently_rekeys_existing_farm(tmp_path):
    values = head.configure(tmp_path, 'hearth.home.arpa')
    del values['HEARTH_SESSION_ENCRYPTION_KEY']
    (tmp_path / 'config.json').write_text(json.dumps(values))
    with pytest.raises(ValueError, match='Restore'):
        head.configure(tmp_path, 'hearth.home.arpa')


@pytest.mark.parametrize('url,origin,port', [
    ('https://hearth.home.arpa', 'https://hearth.home.arpa', 443),
    (' HTTPS://HEARTH.home.arpa:443/ ', 'https://hearth.home.arpa', 443),
    ('https://hearth.home.arpa:8444/', 'https://hearth.home.arpa:8444', 8444),
    ('https://10.20.30.50:9444', 'https://10.20.30.50:9444', 9444),
])
def test_base_url_configures_certificate_name_and_canonical_origins(tmp_path, url, origin, port):
    values = head.configure(tmp_path, base_url=url)
    assert values['HEARTH_USER_ORIGIN'] == origin
    assert values['HEARTH_USER_PORT'] == str(port)
    assert values['HEARTH_PUBLIC_HOST'] in origin
    assert values['HEARTH_ADMIN_ORIGIN'] == f"https://{values['HEARTH_PUBLIC_HOST']}:8443"
    assert values['HEARTH_IDENTITY_ORIGIN'] == f"https://{values['HEARTH_PUBLIC_HOST']}:8445"
    before = (tmp_path / 'config.json').read_bytes()
    assert head.configure(tmp_path, base_url=origin + '/') == values
    assert (tmp_path / 'config.json').read_bytes() == before


@pytest.mark.parametrize('url', ['http://hearth.home.arpa', 'hearth.home.arpa', 'https://0.0.0.0',
    'https://localhost', 'https://hearth.home.arpa/v1', 'https://hearth.home.arpa/base/',
    'https://hearth.home.arpa?x=1', 'https://hearth.home.arpa#fragment', 'https://hearth.home.arpa?',
    'https://hearth.home.arpa#', 'https://user:secret@hearth.home.arpa', 'https://@hearth.home.arpa',
    'https://hearth.home.arpa:0', 'https://hearth.home.arpa:65536', 'https://hearth.home.arpa:',
    'https://hea\nrth.home.arpa', 'https://hearth.home.arpa/\t', 'https://hearth.home.arpa:-1',
    'https://hearth.home.arpa:8443', 'https://hearth.home.arpa:8445'])
def test_invalid_base_url_never_writes_config(tmp_path, url):
    with pytest.raises(ValueError):
        head.configure(tmp_path, base_url=url)
    assert not (tmp_path / 'config.json').exists()


def test_legacy_host_setup_accepts_equivalent_base_url_without_rekeying(tmp_path):
    old = head.configure(tmp_path, 'hearth.home.arpa', (18443, 18444, 18445))
    assert head.configure(tmp_path, base_url='https://hearth.home.arpa:18444/', ports=(18443, 18444, 18445)) == old
    with pytest.raises(ValueError, match='match'):
        head.configure(tmp_path, base_url='https://hearth.home.arpa:18444', ports=(18443, 18446, 18445))
    with pytest.raises(ValueError, match='not both'):
        head.configure(tmp_path, 'hearth.home.arpa', base_url='https://hearth.home.arpa')


def test_interactive_setup_prompts_for_base_url_and_noninteractive_requires_it(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(head.sys, 'platform', 'linux')
    monkeypatch.setattr(head.sys, 'argv', ['head.py', '--state', str(tmp_path), 'configure'])
    monkeypatch.setattr(head.sys.stdin, 'isatty', lambda: False)
    assert head.main() == 1
    assert not (tmp_path / 'config.json').exists()
    assert 'Non-interactive' in capsys.readouterr().err
    monkeypatch.setattr(head.sys.stdin, 'isatty', lambda: True)
    prompts = []
    def reply(prompt):
        prompts.append(prompt)
        return 'https://hearth.home.arpa'
    monkeypatch.setattr('builtins.input', reply)
    assert head.main() == 0
    assert 'base URL' in prompts[0]
    assert head.load(tmp_path)['HEARTH_USER_ORIGIN'] == 'https://hearth.home.arpa'


def test_client_certificate_package_has_matching_public_material_and_no_secrets(tmp_path):
    values = head.configure(tmp_path, base_url='https://hearth.home.arpa')
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'hearth test CA')])
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
                   .not_valid_after(datetime.now(UTC) + timedelta(days=1))
                   .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                   .sign(key, hashes.SHA256()))
    pem = certificate.public_bytes(serialization.Encoding.PEM).decode()
    package, metadata = head.certificate_package(values, pem, pem)
    with ZipFile(io.BytesIO(package)) as archive:
        assert set(archive.namelist()) == {'hearth-root.crt', 'hearth-root.cer', 'hearth-server-chain.pem', 'connection.json', 'README.txt'}
        der = archive.read('hearth-root.cer')
        assert x509.load_der_x509_certificate(der) == certificate
        assert ssl.PEM_cert_to_DER_cert(archive.read('hearth-root.crt').decode()) == der
        assert metadata == json.loads(archive.read('connection.json'))
        assert metadata['root_sha256'] == hashlib.sha256(der).hexdigest()
        assert metadata['base_url'] == 'https://hearth.home.arpa'
        assert metadata['api_base_url'] == 'https://hearth.home.arpa/v1'
        assert metadata['server_name'] == 'hearth.home.arpa'
        contents = b''.join(archive.read(name) for name in archive.namelist())
        assert b'PRIVATE KEY' not in contents
        assert all(values[name].encode() not in contents for name in head.SECRET_NAMES)
    original = (tmp_path / 'config.json').read_bytes()
    head.publish_setup(tmp_path, package, metadata)
    published = tmp_path / 'public-setup'
    assert {path.name for path in published.iterdir()} == {
        'index.html', 'connection.json', 'hearth-root.crt', 'hearth-root.cer', 'hearth-client-certificates.zip',
    }
    assert (published / 'hearth-root.cer').read_bytes() == der
    assert (published / 'hearth-client-certificates.zip').read_bytes() == package
    assert (tmp_path / 'config.json').read_bytes() == original
    public_bytes = b''.join(path.read_bytes() for path in published.iterdir())
    assert all(values[name].encode() not in public_bytes for name in head.SECRET_NAMES)
    assert b'PRIVATE KEY' not in public_bytes
    assert b'@@' not in (published / 'index.html').read_bytes()
    assert b'https://hearth.home.arpa:8443' in public_bytes
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    with pytest.raises(ValueError, match='only public'):
        head.certificate_package(values, pem, pem + private)


def test_http_setup_port_preserves_existing_https_ports(tmp_path):
    values = head.configure(tmp_path, base_url='https://hearth.home.arpa')
    assert head.setup_url(values) == 'http://hearth.home.arpa'
    for ports in [(80, 8080, 8081), (80, 8443, 8445), (443, 8443, 8445)]:
        public = head.endpoints('hearth.home.arpa', ports)
        assert head.setup_http_port(public) not in ports
    assert head.setup_http_port(head.endpoints('hearth.home.arpa', (80, 8080, 8081))) == 8082
