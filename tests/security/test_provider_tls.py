import json
import ssl
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from hearth.config import Settings
from hearth.inference import ProviderError, list_models
from hearth.providers import transport_settings, validate_ca


def test_private_ca_is_connection_scoped_and_hostname_checks_remain_enabled(tmp_path):
    now = datetime.now(UTC)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'hearth TLS test CA')])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True).sign(key, hashes.SHA256()))
    server_key = ec.generate_private_key(ec.SECP256R1())
    server_cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Local test')]))
                   .issuer_name(name).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
                   .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), critical=False)
                   .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path/'server.pem', tmp_path/'server.key'
    cert_path.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(server_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    ca_pem = ca.public_bytes(serialization.Encoding.PEM).decode()
    assert validate_ca(ca_pem) == ca.fingerprint(hashes.SHA256()).hex()
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path, self.headers.get('Host'), self.headers.get('Authorization')))
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'data': [{'id': 'tls-fixture'}]}).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        base = Settings(mode='test')
        trusted = transport_settings({'tls_ca_pem': ca_pem}, base)
        address = f'https://localhost:{server.server_port}'
        assert list_models(address, 'synthetic-key', trusted) == ['tls-fixture']
        assert calls == [('/v1/models', f'localhost:{server.server_port}', 'Bearer synthetic-key')]
        with pytest.raises(ProviderError):
            list_models(address, 'synthetic-key', base)
        with pytest.raises(ProviderError):
            list_models(f'https://127.0.0.1:{server.server_port}', 'synthetic-key', trusted)
        assert len(calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
