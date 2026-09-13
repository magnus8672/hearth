"""Fixed operations called by the native loopback developer setup surface."""
import json
import subprocess
import sys

from appliance import ROOT, ssh_args
from configure_identity import create_owner, owner_created
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from development_stack import configuration

CERTIFICATE = ROOT / '.hearth/certificates/edge-root.crt'


def fetch_root():
    response = subprocess.run([str(arg) for arg in ssh_args()] +
        ['docker exec hearth-development-edge-1 cat /data/caddy/pki/authorities/local/root.crt'],
        check=True, capture_output=True)
    certificate = x509.load_pem_x509_certificate(response.stdout)
    if not certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise ValueError('The appliance did not return a certificate authority.')
    CERTIFICATE.parent.mkdir(parents=True, exist_ok=True)
    CERTIFICATE.write_bytes(response.stdout)
    return certificate


def trust_action(action):
    process = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(ROOT / 'scripts/trust-certificate.ps1'),
        '-Action', action, '-CertificatePath', str(CERTIFICATE)], capture_output=True, check=True)
    return json.loads(process.stdout.decode('utf-8-sig'))


def status():
    certificate = x509.load_pem_x509_certificate(CERTIFICATE.read_bytes())
    return {'owner_created': owner_created(configuration()), 'trusted': trust_action('Status')['trusted'],
            'fingerprint': certificate.fingerprint(hashes.SHA256()).hex(':').upper()}


def main():
    try:
        data = json.loads(sys.stdin.read(16384))
        if set(data) != {'action', 'payload'}:
            raise ValueError('Invalid setup request.')
        if data['action'] == 'trust':
            trust_action('Trust')  # Only invoked by the authenticated, explicit user button.
            result = status()
        elif data['action'] == 'owner':
            if not trust_action('Status')['trusted']:
                raise ValueError('Complete browser trust before creating the Owner account.')
            create_owner(data['payload'])
            result = {'owner_created': True}
        elif data['action'] == 'status':
            result = status()
        elif data['action'] == 'certificate':
            result = {'certificate': CERTIFICATE.read_text(encoding='ascii')}
        else:
            raise ValueError('Unsupported setup action.')
        print(json.dumps(result))
    except ValueError as exc:
        print(json.dumps({'error': str(exc)}))
        sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'The local setup operation failed. Check appliance status, then reopen Start-Hearth.ps1.'}))
        sys.exit(1)


if __name__ == '__main__':
    main()
