"""Private artifact erasure against restricted PostgreSQL, with synthetic providers."""
from uuid import uuid4

import pytest
from hearth import identity, image_transport
from hearth.database import scoped_session
from sqlalchemy import text

from tests.integration.test_chat import csrf, promote, setup
from tests.integration.test_conversation_images import fixture_images
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_images import MODEL, image_target, receipt, wait_image
from tests.integration.test_postgres import databases as databases


@pytest.mark.parametrize('state', ['completed', 'failed', 'cancelled'])
def test_delete_private_image_is_scoped_durable_and_cannot_replay(bff, monkeypatch, state):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    calls = []
    artifact = fixture_images(monkeypatch, calls)
    with factory('admin') as admin, factory() as user, factory() as outsider, factory() as anonymous:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = image_target(admin, ah)
        signin(user)
        headers = csrf(user, settings.user_origin)
        owner = user.get('/api/v1/session').json()['id']
        if state != 'completed':
            monkeypatch.setattr(image_transport, 'render', lambda url, key, config, data, observe: (receipt(data, state), None))
        data = {'target_id': target, 'request': {'id': str(uuid4()), 'model': MODEL, 'prompt': 'A synthetic orange square', 'seed': 42}}
        assert user.post('/api/v1/images', json=data, headers=headers).status_code == 202
        assert wait_image(user)['status'] == state
        path = '/api/v1/images/' + data['request']['id']
        assert anonymous.delete(path, headers=headers).status_code == 401
        assert user.delete(path).status_code == 403
        assert user.delete(path, headers=headers | {'Origin': 'https://rogue.example'}).status_code == 403
        assert admin.delete(path, headers=ah).status_code == 403
        # Authenticate a separate member; possession of an image ID grants no access.
        with monkeypatch.context() as auth:
            other_subject = str(uuid4())
            auth.setattr(identity, 'verify_id_token', lambda *args: {'sub': other_subject, 'name': 'Other member'})
            auth.setattr(identity, 'token_request', lambda config, endpoint, data:
                {'active': True, 'sub': subject if data.get('token') == 'EXPLICIT PROVIDER FIXTURE' else other_subject, 'iss': config.issuer}
                if endpoint == 'token/introspect' else {'id_token': 'FIXTURE', 'access_token': 'OTHER', 'refresh_token': 'FIXTURE', 'expires_in': 300})
            signin(outsider)
            assert outsider.delete(path, headers=csrf(outsider, settings.user_origin)).status_code == 404
            assert outsider.get(path + '/image').status_code == 404
        if state == 'completed':
            assert user.get(path + '/image').content == artifact
        assert user.delete(path, headers=headers).status_code == 200
        assert user.delete(path, headers=headers).json() == {'deleted': True}
        assert user.get('/api/v1/images').json()['items'] == []
        assert user.get(path + '/image').status_code == 404
        assert user.post('/api/v1/images', json=data, headers=headers).status_code == 410
        assert user.delete('/api/v1/images/' + str(uuid4()), headers=headers).status_code == 404
        with scoped_session(app, owner, settings.farm_id) as db:
            row = db.execute(text('SELECT image,metadata,deleted_at FROM image_jobs WHERE id=:id'), {'id': data['request']['id']}).mappings().one()
            assert row['image'] is None and row['metadata'] is None and row['deleted_at'] is not None
        with factory() as reopened:
            signin(reopened)
            assert reopened.get('/api/v1/images').json()['items'] == []
            assert reopened.get(path + '/image').status_code == 404


def test_deletion_releases_saved_image_quota(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    fixture_images(monkeypatch, [])
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        target = image_target(admin, csrf(admin, settings.admin_origin))
        signin(user)
        headers = csrf(user, settings.user_origin)
        owner = user.get('/api/v1/session').json()['id']
        data = {'target_id': target, 'request': {'id': str(uuid4()), 'model': MODEL, 'prompt': 'A synthetic orange square', 'seed': 42}}
        assert user.post('/api/v1/images', json=data, headers=headers).status_code == 202
        assert wait_image(user)['status'] == 'completed'
        with scoped_session(app, owner, settings.farm_id) as db:
            db.execute(text("INSERT INTO image_jobs(id,farm_id,owner_id,workspace_id,target_id,request,status,session_hash,authorization_version) SELECT gen_random_uuid(),farm_id,owner_id,workspace_id,target_id,request,'cancelled',session_hash,authorization_version FROM image_jobs CROSS JOIN generate_series(1,99) WHERE id=:id"), {'id': data['request']['id']})
        next_job = data | {'request': data['request'] | {'id': str(uuid4())}}
        assert user.post('/api/v1/images', json=next_job, headers=headers).status_code == 409
        assert user.delete('/api/v1/images/' + data['request']['id'], headers=headers).status_code == 200
        assert user.post('/api/v1/images', json=next_job, headers=headers).status_code == 202
        assert wait_image(user)['status'] == 'completed'
