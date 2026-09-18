import json
from contextlib import contextmanager
from uuid import uuid4

import httpx
from hearth import head_settings
from sqlalchemy import text

from scripts import configure_identity
from tests.integration.test_chat import csrf, promote
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


def test_address_settings_require_admin_authority_csrf_and_audit(bff, monkeypatch):
    factory, settings, _, migration, _ = bff
    calls = []
    def control(request, method, path, body=None):
        calls.append((method, path, body))
        return httpx.Response(200, json={'operation': {'state': 'queued'}})
    monkeypatch.setattr(head_settings, 'control', control)
    with factory('admin') as admin, factory() as user:
        assert admin.get('/api/v1/head/settings').status_code == 401
        signin(admin)
        assert admin.get('/api/v1/head/settings').status_code == 403
        promote(admin, migration, settings)
        signin(user)
        assert user.get('/api/v1/head/settings').status_code == 403
        assert admin.get('/api/v1/head/settings').status_code == 200
        payload = {'base_url': 'https://head.home', 'expected_revision': 'a'*64, 'operation_id': str(uuid4())}
        assert admin.post('/api/v1/head/apply', json=payload).status_code == 403
        headers = csrf(admin, settings.admin_origin)
        assert admin.post('/api/v1/head/apply', json=payload | {'shell': 'no'}, headers=headers).status_code == 422
        result = admin.post('/api/v1/head/apply', json=payload, headers=headers)
        assert result.status_code == 202
        with migration.connect() as db:
            event = db.execute(text("SELECT safe_metadata FROM audit_events WHERE farm_id=:farm AND action='head.address_requested'"), {'farm': settings.farm_id}).scalar_one()
        assert event['base_url'] == payload['base_url']
        assert calls[-1][2]['actor_id'] == admin.get('/api/v1/session').json()['id']


def test_identity_migration_preserves_ids_content_and_client_keys(bff, monkeypatch):
    factory, settings, _, migration, _ = bff
    edits = []
    class Client:
        def get(self, path, params):
            return httpx.Response(200, request=httpx.Request('GET', 'http://fixture'), json=[{'id': 'fixture', 'attributes': {'keep': 'yes'}}])
        def put(self, path, json):
            edits.append(json)
            return httpx.Response(204, request=httpx.Request('PUT', 'http://fixture'))
    @contextmanager
    def admin_client(values):
        yield Client()
    monkeypatch.setattr(configure_identity, 'admin_client', admin_client)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        signin(user)
        owner = user.get('/api/v1/session').json()['id']
        headers = csrf(user, settings.user_origin)
        draft = user.post('/api/v1/drafts', headers=headers, json={'title': 'Address fixture', 'content': 'preserved private content'}).json()
        key = user.post('/api/v1/client-keys', headers=headers, json={'name': 'Address fixture', 'capabilities': ['chat.general']}).json()
        actor = admin.get('/api/v1/session').json()['id']
        # This explicitly isolated DB uses real subject/role records, not the live farm.
        values = {'HEARTH_MIGRATION_DATABASE_URL': migration.url.render_as_string(hide_password=False),
                  'HEARTH_FARM_ID': str(settings.farm_id), 'HEARTH_ADMIN_ORIGIN': 'https://head.home:8443',
                  'HEARTH_USER_ORIGIN': 'https://head.home', 'HEARTH_IDENTITY_ORIGIN': 'https://head.home:8445'}
        with migration.connect() as db:
            before = db.execute(text('SELECT id,subject FROM users WHERE farm_id=:farm ORDER BY id'), {'farm': settings.farm_id}).all()
        data = {'actor_id': actor, 'operation_id': str(uuid4()), 'old_issuer': settings.issuer}
        configure_identity.address_authority(values, data)
        configure_identity.change_address(values, data)
        with migration.connect() as db:
            after = db.execute(text('SELECT id,subject FROM users WHERE farm_id=:farm ORDER BY id'), {'farm': settings.farm_id}).all()
            assert after == before
            assert db.execute(text('SELECT count(*) FROM browser_sessions WHERE farm_id=:farm'), {'farm': settings.farm_id}).scalar_one() == 0
            assert db.execute(text('SELECT DISTINCT issuer FROM users WHERE farm_id=:farm'), {'farm': settings.farm_id}).scalar_one() == 'https://head.home:8445/realms/hearth'
        assert edits[0]['attributes']['keep'] == 'yes'
        assert edits[0]['redirectUris'] == ['https://head.home:8443/auth/callback']
        assert 'secret' not in json.dumps(edits)
        assert user.get('/api/v1/session').status_code == 401
        settings.admin_origin = values['HEARTH_ADMIN_ORIGIN']
        settings.user_origin = values['HEARTH_USER_ORIGIN']
        settings.identity_origin = values['HEARTH_IDENTITY_ORIGIN']
        settings.trusted_hosts = ['head.home']
        with factory() as moved:
            signin(moved)
            assert moved.get('/api/v1/session').json()['id'] == owner
            assert moved.get('/api/v1/drafts/'+draft['id']).json()['content'] == 'preserved private content'
            assert moved.get('/v1/models', headers={'Authorization': 'Bearer '+key['key']}).status_code == 200
