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
            for table in ['outbox', 'messages', 'conversations', 'workspaces']:
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

        monkeypatch.setattr(identity, 'token_request', unavailable)
        assert browser.get('/api/v1/session').status_code == 401
        assert browser.post('/api/v1/logout', headers={'Origin': settings.user_origin, 'X-Hearth-CSRF': session['csrf_token']}).status_code == 303


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
