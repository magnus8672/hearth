"""Protocol qualification on the existing Keycloak, using one disposable realm.

No farm/database/account fixtures. Run through the private head-console environment.
Only synthetic credentials are used; output contains no tokens or MFA secrets.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from html.parser import HTMLParser
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
from configure_identity import admin_client, configure_mfa_flow
from hearth.identity import token_request, verify_id_token


class Forms(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.forms, self.current = [], None
        self.feed(source)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == 'form':
            self.current = {'action': attrs.get('action'), 'inputs': {}}
            self.forms.append(self.current)
        elif tag == 'input' and self.current is not None and attrs.get('name'):
            self.current['inputs'][attrs['name']] = attrs.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form':
            self.current = None

    def containing(self, name):
        return next(form for form in self.forms if name in form['inputs'])


def totp(secret):
    raw = hmac.digest(base64.b32decode(secret), struct.pack('>Q', int(time.time()) // 30), 'sha1')
    offset = raw[-1] & 15
    return f'{(struct.unpack(">I", raw[offset:offset + 4])[0] & 0x7fffffff) % 1000000:06d}'


def snapshot(client):
    users = client.get('/admin/realms/hearth/users').json()
    records = [{'id': item['id'], 'credentials': sorted(credential['id'] for credential in
                client.get('/admin/realms/hearth/users/' + item['id'] + '/credentials').json())} for item in users]
    return hashlib.sha256(json.dumps(sorted(records, key=lambda item: item['id']), sort_keys=True).encode()).hexdigest()


def run():
    values = dict(os.environ)
    internal = values['HEARTH_IDENTITY_INTERNAL_ORIGIN']
    realm = 'hearth-sso-qa-' + secrets.token_hex(6)
    marker = secrets.token_urlsafe(24)
    realm_path = '/admin/realms/' + realm
    issuer = internal + '/realms/' + realm
    auth = issuer + '/protocol/openid-connect'
    callback = internal + '/sso-test-complete'
    client_secrets = {name: secrets.token_urlsafe(32) for name in ('hearth-user', 'hearth-admin')}
    checks = []
    with admin_client(values) as admin:
        before = snapshot(admin)
        try:
            admin.post('/admin/realms', json={'realm': realm, 'enabled': True, 'sslRequired': 'none',
                'attributes': {'frontendUrl': internal, 'hearthSsoQa': marker},
                'otpPolicyType': 'totp', 'otpPolicyAlgorithm': 'HmacSHA1', 'otpPolicyDigits': 6,
                'otpPolicyPeriod': 30, 'otpPolicyCodeReusable': False}).raise_for_status()
            configure_mfa_flow(admin, realm_path)
            # A repeated setup must preserve the same executions.
            flow_path = realm_path + '/authentication/flows/hearth-browser-sso-v1/executions'
            flow_before = admin.get(flow_path).json()
            configure_mfa_flow(admin, realm_path)
            assert flow_before == admin.get(flow_path).json()
            checks.append('flow setup is idempotent')
            for name, secret in client_secrets.items():
                admin.post(realm_path + '/clients', json={'clientId': name, 'enabled': True, 'protocol': 'openid-connect',
                    'publicClient': False, 'secret': secret, 'standardFlowEnabled': True, 'directAccessGrantsEnabled': False,
                    'redirectUris': [callback], 'attributes': {'pkce.code.challenge.method': 'S256'}}).raise_for_status()

            def account(name, with_otp=True):
                password, otp = secrets.token_urlsafe(24), base64.b32encode(secrets.token_bytes(20)).decode()
                credentials = [{'type': 'password', 'value': password, 'temporary': False}]
                if with_otp:
                    credentials.append({'type': 'otp', 'secretData': json.dumps({'value': otp}),
                        'credentialData': json.dumps({'subType': 'totp', 'digits': 6, 'period': 30, 'counter': 0,
                                                      'algorithm': 'HmacSHA1', 'secretEncoding': 'BASE32'})})
                admin.post(realm_path + '/users', json={'username': name, 'enabled': True, 'firstName': 'SSO',
                    'lastName': 'Fixture', 'email': name+'@example.invalid', 'credentials': credentials}).raise_for_status()
                return password, otp

            def authorize(client, name):
                verifier, nonce, state = (secrets.token_urlsafe(32) for _ in range(3))
                query = {'client_id': name, 'redirect_uri': callback, 'response_type': 'code', 'scope': 'openid profile',
                    'nonce': nonce, 'state': state, 'code_challenge_method': 'S256',
                    'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
                response = client.get(auth + '/auth', params=query)
                return response, verifier, nonce, state

            def exchange(client, response, name, verifier, nonce, state):
                if response.status_code != 302:
                    fields = [sorted(form['inputs']) for form in Forms(response.text).forms]
                    raise AssertionError(f'Expected code redirect; status {response.status_code}, form fields {fields}, invalid_code={"Invalid authenticator code" in response.text}')
                query = parse_qs(urlsplit(response.headers['location']).query)
                assert query['state'] == [state] and 'code' in query
                config = SimpleNamespace(oidc_internal=auth, issuer=issuer, client_id=name, client_secret=client_secrets[name])
                tokens = token_request(config, 'token', {'grant_type': 'authorization_code', 'code': query['code'][0],
                    'redirect_uri': callback, 'code_verifier': verifier})
                claims = verify_id_token(config, tokens, nonce)
                return config, tokens, claims

            for first, second in [('hearth-user', 'hearth-admin'), ('hearth-admin', 'hearth-user')]:
                username = first + '-fixture'
                password, otp = account(username)
                with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as browser:
                    response, verifier, nonce, state = authorize(browser, first)
                    form = Forms(response.text).containing('username')
                    response = browser.post(form['action'], data=form['inputs'] | {'username': username, 'password': password})
                    form = Forms(response.text).containing('otp')
                    response = browser.post(form['action'], data=form['inputs'] | {'otp': totp(otp)})
                    config1, tokens1, claims1 = exchange(browser, response, first, verifier, nonce, state)
                    start = time.monotonic()
                    response, verifier, nonce, state = authorize(browser, second)
                    config2, tokens2, claims2 = exchange(browser, response, second, verifier, nonce, state)
                    assert claims1['sub'] == claims2['sub'] and claims1['sid'] == claims2['sid']
                    assert time.monotonic() - start < 10
                    checks.append(first + ' to ' + second + ': password and OTP once; immediate SSO with signed audience-specific tokens')
                    token_request(config2, 'logout', {'refresh_token': tokens2['refresh_token']})
                    for config, tokens in ((config1, tokens1), (config2, tokens2)):
                        assert token_request(config, 'token/introspect', {'token': tokens['access_token']})['active'] is False
                    response, *_ = authorize(browser, first)
                    Forms(response.text).containing('username')
                    checks.append('logout ended both client grants and SSO; fresh credentials required')

            password, _ = account('no-second-factor', with_otp=False)
            with httpx.Client(timeout=15, trust_env=False) as browser:
                response, *_ = authorize(browser, 'hearth-user')
                form = Forms(response.text).containing('username')
                response = browser.post(form['action'], data=form['inputs'] | {'username': 'no-second-factor', 'password': password})
                for _ in range(5):
                    if response.status_code != 302:
                        break
                    location = response.headers['location']
                    assert urlsplit(location).path.startswith('/realms/' + realm + '/login-actions/')
                    response = browser.get(location)
                assert 'CONFIGURE_TOTP' in response.text and 'totp' in response.text
                checks.append('missing second factor requires enrollment; no password-only session')
        finally:
            current = admin.get(realm_path)
            if current.status_code == 200:
                assert current.json().get('attributes', {}).get('hearthSsoQa') == marker
                admin.delete(realm_path).raise_for_status()
            assert snapshot(admin) == before
    print(json.dumps({'status': 'passed', 'checks': checks, 'temporary_realm_removed': True,
                      'existing_accounts_credentials_unchanged': True, 'real_browser_test': False}))


if __name__ == '__main__':
    run()
