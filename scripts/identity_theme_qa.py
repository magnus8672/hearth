"""Validate appearance in a disposable IdP realm; never provision the user's farm."""
import hashlib
import json
import secrets

from browser_appliance import BROWSER_HOME, NODE, QA, ssh
from configure_identity import admin_client, configure_mfa_flow
from development_stack import ROOT, configuration

RECORD = ROOT / '.hearth/identity-theme-qa.json'


def identity_snapshot(client):
    users = client.get('/admin/realms/hearth/users').json()
    result = []
    for user in users:
        credentials = client.get('/admin/realms/hearth/users/' + user['id'] + '/credentials').json()
        result.append({'id': user['id'], 'credentials': sorted(c['id'] for c in credentials)})
    return hashlib.sha256(json.dumps(sorted(result, key=lambda x: x['id'])).encode()).hexdigest()


def run():
    if RECORD.exists():
        raise SystemExit('An earlier theme QA record exists. Inspect it before starting another run.')
    data = {'realm': 'hearth-theme-qa-' + secrets.token_hex(6), 'marker': secrets.token_urlsafe(32),
            'username': 'theme-reviewer', 'password': secrets.token_urlsafe(24),
            'client_secret': secrets.token_urlsafe(32)}
    RECORD.write_text(json.dumps(data))
    values = configuration()
    with admin_client(values) as client:
        before = identity_snapshot(client)
        path = '/admin/realms/' + data['realm']
        try:
            client.post('/admin/realms', json={'realm': data['realm'], 'enabled': True, 'loginTheme': 'hearth',
                'displayName': 'Hearth', 'registrationAllowed': True, 'sslRequired': 'none',
                'attributes': {'frontendUrl': 'http://localhost:8085', 'hearthThemeQa': data['marker']}}).raise_for_status()
            configure_mfa_flow(client, path)
            client.post(path + '/clients', json={'clientId': 'hearth-admin', 'name': 'Hearth Administration',
                'enabled': True, 'protocol': 'openid-connect', 'publicClient': False,
                'secret': data['client_secret'], 'standardFlowEnabled': True,
                'directAccessGrantsEnabled': False, 'redirectUris': ['http://localhost:8085/qa-complete'],
                'attributes': {'pkce.code.challenge.method': 'S256'}}).raise_for_status()
            client.post(path + '/users', json={'username': data['username'], 'enabled': True,
                'firstName': 'Theme', 'lastName': 'Reviewer', 'email': 'theme-reviewer@example.invalid',
                'requiredActions': ['CONFIGURE_TOTP', 'CONFIGURE_RECOVERY_AUTHN_CODES'],
                'credentials': [{'type': 'password', 'value': data['password'], 'temporary': False}]}).raise_for_status()
            for source, target in [(RECORD, QA + '/identity-theme-qa.json'),
                                   (ROOT / 'tests/browser/identity-theme-live.mjs', QA + '/identity-theme-live.mjs')]:
                with source.open('rb') as stream:
                    ssh(f'umask 077; cat > {target}', stdin=stream)
            ssh(f'cd {QA} && HOME={BROWSER_HOME} {NODE} identity-theme-live.mjs')
            output = ROOT / 'evidence/identity-theme/2026-09-13'
            output.mkdir(parents=True, exist_ok=True)
            for name in ['admin-login.png', 'login-firelight.png', 'login-mobile.png', 'registration.png',
                         'authenticator.png', 'recovery.png', 'theme-browser.json']:
                (output / name).write_bytes(ssh(f'cat {QA}/{name}', capture_output=True).stdout)
        finally:
            current = client.get(path)
            if current.status_code == 200:
                if current.json().get('attributes', {}).get('hearthThemeQa') != data['marker']:
                    raise RuntimeError('QA realm ownership marker mismatch; cleanup stopped.')
                client.delete(path).raise_for_status()
            assert before == identity_snapshot(client), 'Existing account/credential identity changed during QA'
            ssh(f'rm -f {QA}/identity-theme-qa.json')
            RECORD.unlink()
    print('Theme QA complete; disposable realm removed and existing account/credential identities preserved.')


if __name__ == '__main__':
    run()
