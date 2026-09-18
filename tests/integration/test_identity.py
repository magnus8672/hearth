"""Adversarial BFF tests with real restricted-role PostgreSQL and explicit provider fixtures."""
import secrets
from contextlib import contextmanager
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from hearth import identity
from hearth.config import Settings
from hearth.database import scoped_session
from hearth.main import create_app
from joserfc import jwt
from joserfc.errors import JoseError as SignatureError
from joserfc.jwk import RSAKey
from sqlalchemy import text

from tests.integration.test_postgres import databases as databases


@pytest.fixture
def bff(databases, monkeypatch):
    app_engine, migration = databases
    farm, owner = uuid4(), uuid4()
    settings = Settings(mode='test', database_url=app_engine.url.render_as_string(hide_password=False),
        farm_id=farm, admin_client_secret=secrets.token_urlsafe(32), user_client_secret=secrets.token_urlsafe(32),
        session_encryption_key=secrets.token_urlsafe(32))
    with migration.begin() as db:
        db.execute(text("INSERT INTO farms(id,name) VALUES(:farm,'Identity security fixture')"), {'farm': farm})
        db.execute(text("INSERT INTO users(id,farm_id,issuer,subject,display_name) VALUES(:id,:farm,:issuer,:subject,'Fixture Owner')"),
            {'id': owner, 'farm': farm, 'issuer': settings.issuer, 'subject': str(owner)})
        db.execute(text("INSERT INTO role_grants(id,user_id,farm_id,role) VALUES(gen_random_uuid(),:user,:farm,'Owner')"), {'user': owner, 'farm': farm})
    subject = str(uuid4())
    monkeypatch.setattr(identity, 'token_request', lambda config, endpoint, data:
        {'active': True, 'sub': subject, 'iss': config.issuer} if endpoint == 'token/introspect' else
        {'id_token': 'EXPLICIT PROVIDER FIXTURE', 'access_token': 'EXPLICIT PROVIDER FIXTURE', 'refresh_token': 'EXPLICIT PROVIDER FIXTURE', 'expires_in': 300})
    monkeypatch.setattr(identity, 'verify_id_token', lambda config, tokens, nonce: {'sub': subject, 'name': 'Fixture Member'})

    @contextmanager
    def client(audience='user'):
        config = settings.model_copy(update={'audience': audience})
        with TestClient(create_app(config), base_url=config.origin, follow_redirects=False) as browser:
            yield browser

    yield client, settings, app_engine, migration, subject
    with migration.connect() as db:
        users = db.execute(text('SELECT id FROM users WHERE farm_id=:farm'), {'farm': farm}).scalars().all()
    for user in users:
        with scoped_session(app_engine, user, farm) as db:
            for table in ['image_queue', 'managed_workers', 'tool_invocations', 'mcp_credentials', 'client_runs', 'client_keys']:
                db.execute(text(f'DELETE FROM {table} WHERE farm_id=:farm'), {'farm': farm})
            db.execute(text('UPDATE image_jobs SET batch_run_id=NULL WHERE batch_run_id IS NOT NULL'))
            db.execute(text('DELETE FROM image_plans'))
            db.execute(text('DELETE FROM channel_runs'))
    with scoped_session(app_engine, owner, farm) as db:
        # Join only this disposable farm's synthetic channels for RLS cleanup.
        db.execute(text('INSERT INTO channel_memberships(channel_id,farm_id,owner_id) SELECT id,farm_id,:owner FROM channels ON CONFLICT DO NOTHING'), {'owner': owner})
        db.execute(text('DELETE FROM conversation_images WHERE channel_id IS NOT NULL'))
        db.execute(text('DELETE FROM channel_messages'))
    for user in users:
        with scoped_session(app_engine, user, farm) as db:
            for table in ['transcription_jobs', 'speech_jobs', 'conversation_images', 'image_jobs', 'channel_memberships', 'side_notes', 'chat_requests', 'chat_runs', 'outbox', 'messages', 'chat_attachments', 'conversations', 'workspaces']:
                db.execute(text(f'DELETE FROM {table} WHERE farm_id=:farm'), {'farm': farm})
    with scoped_session(app_engine, owner, farm) as db:
        for table in ['mcp_servers', 'channels', 'capability_routes', 'capability_bindings', 'inference_targets', 'provider_connections', 'provider_pools']:
            db.execute(text(f'DELETE FROM {table} WHERE farm_id=:farm'), {'farm': farm})
    with migration.begin() as db:
        for table in ['browser_sessions', 'audit_events', 'role_grants', 'users']:
            db.execute(text(f'DELETE FROM {table} WHERE farm_id=:farm'), {'farm': farm})
        db.execute(text('DELETE FROM farms WHERE id=:farm'), {'farm': farm})


def signin(browser):
    start = browser.get('/auth/login')
    assert start.status_code == 303
    query = parse_qs(urlsplit(start.headers['location']).query)
    assert query['code_challenge_method'] == ['S256']
    callback = '/auth/callback?state=' + query['state'][0] + '&code=fixture'
    response = browser.get(callback)
    assert response.status_code == 303
    return callback


@pytest.mark.parametrize('audience', ['user', 'admin'])
def test_normal_login_allows_sso_but_keeps_pkce_and_browser_binding(bff, audience):
    factory, settings, _, _, _ = bff
    with factory(audience) as browser:
        response = browser.get('/auth/login?prompt=none&redirect_uri=https://rogue.example')
        query = parse_qs(urlsplit(response.headers['location']).query)
        assert 'prompt' not in query and 'max_age' not in query
        assert query['client_id'] == ['hearth-' + audience]
        origin = settings.admin_origin if audience == 'admin' else settings.user_origin
        assert query['redirect_uri'] == [origin + '/auth/callback']
        assert query['code_challenge_method'] == ['S256']
        assert len(query['nonce'][0]) >= 32 and len(query['state'][0]) >= 32


def test_signout_ends_companion_browser_session_without_deleting_other_devices(bff, monkeypatch):
    factory, settings, _, _, _ = bff
    with factory() as browser, factory('admin') as admin, factory() as other_device:
        signin(browser)
        signin(admin)
        signin(other_device)
        assert admin.get('/api/v1/farm').status_code == 403  # SSO does not elevate a Member.
        browser.cookies.update(admin.cookies)
        session = browser.get('/api/v1/session').json()
        calls = []
        original = identity.token_request

        def record(config, endpoint, data):
            calls.append((endpoint, data))
            return original(config, endpoint, data)

        monkeypatch.setattr(identity, 'token_request', record)
        response = browser.post('/api/v1/logout', headers={'Origin': settings.user_origin, 'X-Hearth-CSRF': session['csrf_token']})
        assert response.status_code == 303
        assert calls[0][0] == 'logout' and 'refresh_token' in calls[0][1]
        assert admin.get('/api/v1/session').status_code == 401
        assert other_device.get('/api/v1/session').status_code == 200


def test_one_use_callback_requires_original_browser_and_personal_provision_is_atomic(bff):
    factory, settings, app, migration, subject = bff
    with factory() as browser, factory() as other:
        start = browser.get('/auth/login')
        state = parse_qs(urlsplit(start.headers['location']).query)['state'][0]
        callback = '/auth/callback?state=' + state + '&code=fixture'
        assert other.get(callback).status_code == 400
        assert browser.get(callback).status_code == 303
        assert browser.get(callback).status_code == 400
        signin(browser)
        response = browser.get('/api/v1/session').json()
        assert response['roles'] == ['Member']
        assert 'farm.inspect' not in response['permissions']
        assert len(browser.get('/api/v1/workspace').json()['drafts']) == 0
        with migration.connect() as db:
            user = db.execute(text('SELECT id FROM users WHERE issuer=:issuer AND subject=:subject'), {'issuer': settings.issuer, 'subject': subject}).scalar_one()
        with scoped_session(app, user, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM workspaces')).scalar_one() == 1


def test_exact_origin_csrf_cookie_audience_and_private_draft_revision(bff):
    factory, settings, _, _, _ = bff
    with factory() as browser, factory('admin') as admin:
        signin(browser)
        session = browser.get('/api/v1/session').json()
        csrf = {'Origin': settings.user_origin, 'X-Hearth-CSRF': session['csrf_token']}
        data = {'title': 'private canary', 'content': 'Never accessible to another principal.'}
        assert browser.post('/api/v1/drafts', json=data).status_code == 403
        assert browser.post('/api/v1/drafts', json=data, headers=csrf | {'Origin': settings.admin_origin}).status_code == 403
        assert browser.post('/api/v1/drafts', json=data, headers=csrf | {'X-Hearth-CSRF': 'wrong'}).status_code == 403
        saved = browser.post('/api/v1/drafts', json=data, headers=csrf)
        assert saved.status_code == 201
        draft = saved.json()
        path = '/api/v1/drafts/' + draft['id']
        assert browser.put(path, json=data | {'revision': 1}, headers=csrf).status_code == 200
        assert browser.put(path, json=data | {'revision': 1}, headers=csrf).status_code == 409
        token = browser.cookies.get('__Host-hearth_user_session')
        admin.cookies.set('__Host-hearth_admin_session', token, domain='localhost.local', path='/')
        assert admin.get('/api/v1/session').status_code == 401
        assert browser.get('/api/v1/farm').status_code == 403
        assert browser.get(path, headers={'host': '127.0.0.1:8444'}).status_code == 403


def test_authorization_change_idle_expiry_and_logout_invalidate_session(bff):
    factory, settings, _, migration, _ = bff
    with factory() as browser:
        signin(browser)
        session = browser.get('/api/v1/session').json()
        csrf = {'Origin': settings.user_origin, 'X-Hearth-CSRF': session['csrf_token']}
        token = browser.cookies.get('__Host-hearth_user_session')
        assert browser.post('/api/v1/logout', headers=csrf).status_code == 303
        browser.cookies.set('__Host-hearth_user_session', token, domain='localhost.local', path='/')
        assert browser.get('/api/v1/session').status_code == 401
        browser.cookies.clear()
        signin(browser)
        with migration.begin() as db:
            db.execute(text("UPDATE browser_sessions SET last_seen_at=now()-interval '31 minutes' WHERE farm_id=:farm"), {'farm': settings.farm_id})
        assert browser.get('/api/v1/session').status_code == 401
        signin(browser)
        with migration.begin() as db:
            db.execute(text('UPDATE users SET authorization_version=authorization_version+1 WHERE id=:id'), {'id': session['id']})
        assert browser.get('/api/v1/session').status_code == 401


def test_logout_remains_available_during_identity_outage(bff, monkeypatch):
    factory, settings, _, _, _ = bff
    with factory() as browser:
        signin(browser)
        session = browser.get('/api/v1/session').json()

        def unavailable(*args):
            raise ConnectionError('Explicit identity outage fixture')

        original = identity.token_request
        monkeypatch.setattr(identity, 'token_request', unavailable)
        assert browser.get('/api/v1/session').status_code == 401
        assert browser.post('/api/v1/logout', headers={'Origin': settings.user_origin, 'X-Hearth-CSRF': session['csrf_token']}).status_code == 303
        assert browser.cookies.get(identity.REAUTHENTICATE_COOKIE) == '1'
        start = browser.get('/auth/login')
        query = parse_qs(urlsplit(start.headers['location']).query)
        assert query['prompt'] == ['login']
        monkeypatch.setattr(identity, 'token_request', original)
        assert browser.get('/auth/callback?state=' + query['state'][0] + '&code=fixture').status_code == 303
        assert not browser.cookies.get(identity.REAUTHENTICATE_COOKIE)


def test_actual_oidc_signature_issuer_audience_nonce_and_expiry(monkeypatch):
    key = RSAKey.generate_key(2048, parameters={'kid': 'fixture-signing-key'})
    settings = Settings(mode='test')
    now = int(datetime.now(UTC).timestamp())
    claims = {'iss': settings.issuer, 'aud': settings.client_id, 'sub': 'fixture', 'nonce': 'browser-bound', 'iat': now, 'exp': now + 60}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {'keys': [key.as_dict(private=False)]}

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, path):
            return Response()

    monkeypatch.setattr(identity.httpx, 'Client', Client)

    def verify(value, nonce='browser-bound', signing_key=key):
        token = jwt.encode({'alg': 'RS256', 'kid': 'fixture-signing-key'}, value, signing_key)
        return identity.verify_id_token(settings, {'id_token': token, 'access_token': 'fixture'}, nonce)

    assert verify(claims)['sub'] == 'fixture'
    for changed in [claims | {'iss': 'https://rogue.example'}, claims | {'aud': 'hearth-user'},
                    claims | {'nonce': 'other-browser'}, claims | {'exp': now - 60}]:
        with pytest.raises(SignatureError):
            verify(changed)
    with pytest.raises(SignatureError):
        verify(claims, signing_key=RSAKey.generate_key(2048))
