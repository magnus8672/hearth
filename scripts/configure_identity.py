"""Console-only identity provisioning for development and standalone heads."""
import argparse
import json
import re
import sys
from contextlib import contextmanager
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from hearth.database import make_engine
from sqlalchemy import text

IDENTITY = 'http://127.0.0.1:18085'
REALM = 'hearth'
ISSUER = 'https://localhost:8445/realms/hearth'


def configuration():
    # Only the developer entry points need the QEMU appliance helpers. The VM
    # package supplies explicit values and must import without those helpers.
    from development_stack import configuration as development_configuration
    return development_configuration()


@contextmanager
def admin_client(values):
    # The standalone console reaches the private identity service directly. Its
    # headers describe the same HTTPS edge as the public login flow.
    headers = {}
    if values.get('HEARTH_IDENTITY_INTERNAL_ORIGIN'):
        public = urlsplit(values['HEARTH_IDENTITY_ORIGIN'])
        headers = {'X-Forwarded-Proto': public.scheme, 'X-Forwarded-Host': public.netloc,
                   'X-Forwarded-Port': str(public.port or 443)}
    client = httpx.Client(base_url=values.get('HEARTH_IDENTITY_INTERNAL_ORIGIN', IDENTITY),
                         headers=headers, timeout=20, trust_env=False)
    response = client.post('/realms/master/protocol/openid-connect/token', data={
        'grant_type': 'password', 'client_id': 'admin-cli', 'username': 'bootstrap',
        'password': values['HEARTH_IDENTITY_BOOTSTRAP_PASSWORD']})
    response.raise_for_status()
    client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
    try:
        yield client
    finally:
        client.close()


def configure(values=None):
    values = configuration() if values is None else values
    with admin_client(values) as client:
        realm_path = f'/admin/realms/{REALM}'
        current = client.get(realm_path)
        if current.status_code == 404:
            client.post('/admin/realms', json={'realm': REALM, 'enabled': True, 'displayName': 'hearth',
                'registrationAllowed': False}).raise_for_status()
        else:
            current.raise_for_status()
        client.put(realm_path, json={'displayName': 'hearth', 'loginTheme': 'hearth', 'bruteForceProtected': True,
            'failureFactor': 5, 'waitIncrementSeconds': 60, 'maxFailureWaitSeconds': 900,
            'permanentLockout': False, 'registrationEmailAsUsername': False, 'loginWithEmailAllowed': False,
            'duplicateEmailsAllowed': True, 'verifyEmail': False, 'resetPasswordAllowed': False,
            'rememberMe': False, 'passwordPolicy': 'length(14) and notUsername(undefined)',
            'accessTokenLifespan': 300, 'ssoSessionIdleTimeout': 1800, 'ssoSessionMaxLifespan': 28800,
            'revokeRefreshToken': True, 'refreshTokenMaxReuse': 0,
            'otpPolicyType': 'totp', 'otpPolicyAlgorithm': 'HmacSHA1', 'otpPolicyDigits': 6,
            'otpPolicyPeriod': 30, 'eventsEnabled': True, 'eventsExpiration': 604800}).raise_for_status()
        profile = client.get(realm_path + '/users/profile')
        profile.raise_for_status()
        profile_data = profile.json()
        for attribute in profile_data['attributes']:
            if attribute['name'] in {'email', 'firstName', 'lastName'}:
                attribute.pop('required', None)
        client.put(realm_path + '/users/profile', json=profile_data).raise_for_status()
        actions = client.get(realm_path + '/authentication/required-actions').json()
        for action in actions:
            if action['alias'] in {'CONFIGURE_TOTP', 'CONFIGURE_RECOVERY_AUTHN_CODES'}:
                action.update(enabled=True, defaultAction=True)
                client.put(realm_path + '/authentication/required-actions/' + action['alias'], json=action).raise_for_status()
        configure_mfa_flow(client, realm_path)
        for audience, port in [('admin', 8443), ('user', 8444)]:
            client_id = f'hearth-{audience}'
            origin = values.get(f'HEARTH_{audience.upper()}_ORIGIN', f'https://localhost:{port}')
            body = {'clientId': client_id, 'name': 'hearth Administration' if audience == 'admin' else 'Your hearth workspace', 'enabled': True,
                'protocol': 'openid-connect', 'publicClient': False, 'clientAuthenticatorType': 'client-secret',
                'secret': values[f'HEARTH_{audience.upper()}_CLIENT_SECRET'], 'standardFlowEnabled': True,
                'implicitFlowEnabled': False, 'directAccessGrantsEnabled': False, 'serviceAccountsEnabled': False,
                'rootUrl': origin, 'baseUrl': origin + '/',
                'redirectUris': [origin + '/auth/callback'], 'webOrigins': [], 'fullScopeAllowed': False,
                'attributes': {'pkce.code.challenge.method': 'S256', 'post.logout.redirect.uris': origin + '/*'},
                'defaultClientScopes': ['basic', 'profile', 'acr'], 'optionalClientScopes': [],
                'protocolMappers': [{'name': 'Authentication methods', 'protocol': 'openid-connect',
                    'protocolMapper': 'oidc-amr-mapper', 'config': {'id.token.claim': 'true', 'access.token.claim': 'true'}},
                    {'name': 'BFF token audience', 'protocol': 'openid-connect', 'protocolMapper': 'oidc-audience-mapper',
                     'config': {'included.client.audience': client_id, 'id.token.claim': 'false', 'access.token.claim': 'true', 'introspection.token.claim': 'true'}}]}
            clients = client.get(realm_path + '/clients', params={'clientId': client_id}).json()
            if clients:
                client.put(realm_path + '/clients/' + clients[0]['id'], json=body).raise_for_status()
            else:
                client.post(realm_path + '/clients', json=body).raise_for_status()
            # Client-scope links have their own REST resources. Updating the client
            # representation does not reliably change existing links.
            client_uuid = client.get(realm_path + '/clients', params={'clientId': client_id}).json()[0]['id']
            scope_path = realm_path + '/clients/' + client_uuid + '/default-client-scopes'
            for scope in client.get(realm_path + '/client-scopes').json():
                if scope['name'] in body['defaultClientScopes']:
                    client.put(scope_path + '/' + scope['id']).raise_for_status()
            for scope in client.get(scope_path).json():
                if scope['name'] not in body['defaultClientScopes']:
                    client.delete(scope_path + '/' + scope['id']).raise_for_status()
        client.put(realm_path, json={'registrationAllowed': owner_created(values)}).raise_for_status()
    print('hearth identity clients configured. Passwords and MFA remain in Keycloak.')


def configure_branding():
    """Update presentation only, including on a farm with existing accounts."""
    with admin_client(configuration()) as client:
        path = f'/admin/realms/{REALM}'
        client.put(path, json={'displayName': 'hearth', 'loginTheme': 'hearth'}).raise_for_status()
        for audience, name in [('admin', 'hearth Administration'), ('user', 'Your hearth workspace')]:
            clients = client.get(path + '/clients', params={'clientId': f'hearth-{audience}'}).json()
            if len(clients) != 1:
                raise ValueError('Configure the hearth identity clients before applying the theme.')
            client.put(path + '/clients/' + clients[0]['id'], json={'name': name}).raise_for_status()
    print('hearth sign-in branding applied. Existing accounts and authentication settings preserved.')


def address_authority(values, data):
    """Host-side check immediately before accepting maintenance from the admin BFF."""
    engine = make_engine(values['HEARTH_MIGRATION_DATABASE_URL'])
    try:
        with engine.connect() as db:
            allowed = db.execute(text("SELECT EXISTS(SELECT 1 FROM users u JOIN role_grants g ON g.user_id=u.id AND g.farm_id=u.farm_id WHERE u.id=:actor AND u.farm_id=:farm AND u.state='active' AND g.role IN ('Owner','FarmAdmin'))"),
                                 {'actor': UUID(data['actor_id']), 'farm': UUID(values['HEARTH_FARM_ID'])}).scalar_one()
            if not allowed:
                raise ValueError('An active Owner or FarmAdmin must approve the address change.')
    finally:
        engine.dispose()


def change_address(values, data):
    """Change URL bindings only, retaining accounts, subject IDs, roles and client secrets."""
    old_issuer = data['old_issuer']
    parsed = urlsplit(old_issuer)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.path != '/realms/hearth' or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('Invalid previous identity address.')
    with admin_client(values) as client:
        for audience in ('ADMIN', 'USER'):
            client_id = 'hearth-' + audience.lower()
            clients = client.get('/admin/realms/hearth/clients', params={'clientId': client_id})
            clients.raise_for_status()
            if len(clients.json()) != 1:
                raise ValueError('The existing identity clients must be configured before changing address.')
            item = clients.json()[0]
            origin = values[f'HEARTH_{audience}_ORIGIN']
            attributes = item.get('attributes', {}) | {'post.logout.redirect.uris': origin+'/*'}
            client.put('/admin/realms/hearth/clients/'+item['id'], json={
                'rootUrl': origin, 'baseUrl': origin+'/', 'redirectUris': [origin+'/auth/callback'],
                'webOrigins': [], 'attributes': attributes}).raise_for_status()
    engine = make_engine(values['HEARTH_MIGRATION_DATABASE_URL'])
    try:
        with engine.begin() as db:
            db.execute(text('UPDATE users SET issuer=:new WHERE farm_id=:farm AND issuer=:old'),
                       {'new': values['HEARTH_IDENTITY_ORIGIN']+'/realms/hearth', 'old': old_issuer, 'farm': UUID(values['HEARTH_FARM_ID'])})
            db.execute(text('DELETE FROM browser_sessions WHERE farm_id=:farm'), {'farm': UUID(values['HEARTH_FARM_ID'])})
            db.execute(text('DELETE FROM login_attempts'))
            db.execute(text("INSERT INTO audit_events(id,farm_id,actor_id,action,safe_metadata) VALUES(gen_random_uuid(),:farm,:actor,'head.address_identity_updated',CAST(:metadata AS jsonb))"),
                       {'farm': UUID(values['HEARTH_FARM_ID']), 'actor': UUID(data['actor_id']),
                        'metadata': json.dumps({'operation_id': str(UUID(data['operation_id'])), 'previous_issuer': old_issuer, 'issuer': values['HEARTH_IDENTITY_ORIGIN']+'/realms/hearth'})})
    finally:
        engine.dispose()
    print('Existing account bindings and sign-in addresses updated; browser sessions ended.')


def configure_mfa_flow(client, realm_path):
    """Password plus OTP/recovery; missing second factors force OTP enrollment.

    Uses Keycloak's documented conditional-2FA-with-OTP-default pattern. A user
    cannot get a password-only login by removing their last second factor.
    """
    path = realm_path + '/authentication'
    alias = 'hearth-browser'
    flows = client.get(path + '/flows').json()
    if not any(flow['alias'] == alias for flow in flows):
        client.post(path + '/flows', json={'alias': alias, 'providerId': 'basic-flow', 'topLevel': True, 'builtIn': False}).raise_for_status()

    def executions(flow):
        return client.get(path + '/flows/' + flow + '/executions').json()

    def requirement(flow, item, required):
        if item['requirement'] != required:
            client.put(path + '/flows/' + flow + '/executions', json={'id': item['id'], 'requirement': required}).raise_for_status()

    def execution(flow, provider, required):
        item = next((x for x in executions(flow) if x.get('providerId') == provider and x['level'] == 0), None)
        if item is None:
            client.post(path + '/flows/' + flow + '/executions/execution', json={'provider': provider}).raise_for_status()
            item = next(x for x in executions(flow) if x.get('providerId') == provider and x['level'] == 0)
        requirement(flow, item, required)
        return item

    def subflow(name):
        item = next((x for x in executions(alias) if x['displayName'] == name), None)
        if item is None:
            client.post(path + '/flows/' + alias + '/executions/flow', json={'alias': name, 'type': 'basic-flow', 'provider': 'basic-flow'}).raise_for_status()
            item = next(x for x in executions(alias) if x['displayName'] == name)
        requirement(alias, item, 'CONDITIONAL')

    execution(alias, 'auth-username-password-form', 'REQUIRED')
    subflow('hearth-second-factor')
    execution('hearth-second-factor', 'conditional-user-configured', 'REQUIRED')
    execution('hearth-second-factor', 'auth-otp-form', 'ALTERNATIVE')
    execution('hearth-second-factor', 'auth-recovery-authn-code-form', 'ALTERNATIVE')
    subflow('hearth-enroll-second-factor')
    condition = execution('hearth-enroll-second-factor', 'conditional-sub-flow-executed', 'REQUIRED')
    config = {'alias': 'hearth-require-second-factor', 'config': {'flow_to_check': 'hearth-second-factor', 'check_result': 'not-executed'}}
    if condition.get('authenticationConfig'):
        client.put(path + '/config/' + condition['authenticationConfig'], json=config).raise_for_status()
    else:
        client.post(path + '/executions/' + condition['id'] + '/config', json=config).raise_for_status()
    execution('hearth-enroll-second-factor', 'auth-otp-form', 'REQUIRED')
    client.put(realm_path, json={'browserFlow': alias}).raise_for_status()


def migration_url(values):
    return values.get('HEARTH_MIGRATION_DATABASE_URL') or f"postgresql+psycopg://hearth_migrator:{values['HEARTH_MIGRATION_PASSWORD']}@127.0.0.1:55432/hearth"


def owner_created(values):
    engine = make_engine(migration_url(values))
    try:
        with engine.connect() as db:
            return db.execute(text("SELECT EXISTS(SELECT 1 FROM role_grants WHERE farm_id=:farm AND role='Owner')"), {'farm': UUID(values['HEARTH_FARM_ID'])}).scalar_one()
    finally:
        engine.dispose()


def create_owner(data, values=None):
    if set(data) != {'username', 'password', 'name', 'farm_name'}:
        raise ValueError('Invalid setup fields.')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{2,39}', data['username']):
        raise ValueError('Use 3 to 40 letters, numbers, dots, dashes or underscores for your username.')
    if not 14 <= len(data['password']) <= 256 or not 1 <= len(data['name'].strip()) <= 100 or not 1 <= len(data['farm_name'].strip()) <= 100:
        raise ValueError('Use a password of at least 14 characters and names of 1 to 100 characters.')
    values = configuration() if values is None else values
    farm_id = UUID(values['HEARTH_FARM_ID'])
    engine = make_engine(migration_url(values))
    try:
        with engine.begin() as db, admin_client(values) as client:
            # Serializes concurrent local setup tools; public account provisioning cannot create Owner.
            db.execute(text('SELECT pg_advisory_xact_lock(762309842)'))
            if db.execute(text("SELECT EXISTS(SELECT 1 FROM role_grants WHERE farm_id=:farm AND role='Owner')"), {'farm': farm_id}).scalar_one():
                raise ValueError('Owner setup is already complete. Sign in to your existing hearth.')
            path = f'/admin/realms/{REALM}'
            response = client.post(path + '/users', json={'username': data['username'], 'firstName': data['name'].strip(),
                'enabled': True, 'requiredActions': ['CONFIGURE_TOTP', 'CONFIGURE_RECOVERY_AUTHN_CODES'],
                'credentials': [{'type': 'password', 'value': data['password'], 'temporary': False}]})
            if response.status_code == 409:
                raise ValueError('That username already exists. Choose a new Owner username.')
            response.raise_for_status()
            subject = response.headers['Location'].rstrip('/').split('/')[-1]
            user_id = uuid4()
            db.execute(text('INSERT INTO farms(id,name) VALUES(:farm,:name)'), {'farm': farm_id, 'name': data['farm_name'].strip()})
            db.execute(text('INSERT INTO users(id,farm_id,issuer,subject,display_name) VALUES(:user,:farm,:issuer,:subject,:name)'),
                {'user': user_id, 'farm': farm_id,
                 'issuer': values.get('HEARTH_IDENTITY_ORIGIN', 'https://localhost:8445') + f'/realms/{REALM}',
                 'subject': subject, 'name': data['name'].strip()})
            db.execute(text("INSERT INTO role_grants(id,user_id,farm_id,role) VALUES(gen_random_uuid(),:user,:farm,'Owner')"), {'user': user_id, 'farm': farm_id})
            db.execute(text("INSERT INTO audit_events(id,farm_id,actor_id,action,safe_metadata) VALUES(gen_random_uuid(),:farm,:user,'identity.owner_bootstrap','{\"channel\":\"local_console\"}')"), {'farm': farm_id, 'user': user_id})
        # Owner creation remains a local console action. Public signup creates Members only.
        with admin_client(values) as client:
            client.put(f'/admin/realms/{REALM}', json={'registrationAllowed': True}).raise_for_status()
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['configure', 'theme', 'owner', 'status'])
    args = parser.parse_args()
    try:
        if args.action == 'configure':
            configure()
        elif args.action == 'theme':
            configure_branding()
        elif args.action == 'status':
            print(json.dumps({'owner_created': owner_created(configuration())}))
        else:
            create_owner(json.loads(sys.stdin.read(16384)))
            print(json.dumps({'owner_created': True}))
    except ValueError as exc:
        print(json.dumps({'error': str(exc)}))
        sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'The local setup service could not complete this action. Verify that the appliance and identity service are ready.'}))
        sys.exit(1)


if __name__ == '__main__':
    main()
