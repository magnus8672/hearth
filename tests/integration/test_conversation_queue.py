"""Conversation requests use the same durable, authorized GPU queue as galleries."""
import base64
import hashlib
import json
import threading
import time
from uuid import uuid4

import pytest
from hearth import geometry_transport, identity, image_planning, image_queue, provider_health, workers
from hearth.contracts import GeometryReceipt
from hearth.database import scoped_session
from hearth.geometry_probe import reference
from sqlalchemy import text

from tests.integration.test_chat import csrf, promote, setup
from tests.integration.test_conversation_images import fixture_images
from tests.integration.test_geometry import INFO as GEOMETRY_INFO
from tests.integration.test_identity import approve_fixture_member, signin
from tests.integration.test_identity import bff as bff
from tests.integration.test_images import image_target
from tests.integration.test_postgres import databases as databases
from tests.integration.test_worker_queue import adopt, report, request
from tests.security.test_geometry import triangle


def send(user, headers, scope, content='Make us an image of a fox'):
    run_id = str(uuid4())
    if scope == 'private':
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=headers, json={}).json()['id']
        data = {'request_id': run_id, 'revision': 1, 'content': content}
        response = user.post(path + '/turns', headers=headers, json=data)
        assert response.status_code == 202, response.text
    else:
        path = '/api/v1/channels/' + user.post('/api/v1/channels', headers=headers, json={'name': 'Queued images'}).json()['id']
        data = {'request_id': run_id, 'content': '@hearth ' + content}
        response = user.post(path + '/messages', headers=headers, json=data)
        assert response.status_code == 201, response.text
    return path, run_id, data


def await_pictures(user, path):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = user.get(path).json()
        if result['messages'][-1].get('images'):
            return result['messages'][-1]['images']
        time.sleep(.02)
    pytest.fail('Planning did not hand off to the queue')


@pytest.mark.parametrize('scope', ['private', 'channel'])
@pytest.mark.parametrize('planned', [False, True])
def test_two_members_geometry_gallery_and_conversation_share_switching_and_fairness(bff, monkeypatch, scope, planned):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    monkeypatch.setattr(image_queue.ImageQueue, 'run', lambda self: self.stop.wait())
    calls = []
    fixture_images(monkeypatch, calls)
    monkeypatch.setattr(geometry_transport, 'information', lambda *args: GEOMETRY_INFO)
    def render_geometry(url, key, config, data, image, observe=lambda value: False):
        model = triangle()
        receipt = GeometryReceipt(**data.model_dump(), state='completed', progress=100, sha256=hashlib.sha256(model).hexdigest(), manifest_sha256='a'*64, execution_released=True, cancel_requested=False)
        observe(receipt)
        return receipt, model
    monkeypatch.setattr(geometry_transport, 'render', render_geometry)
    monkeypatch.setattr(image_planning, 'chat_stream', lambda *a, **kw: iter([('text', json.dumps({'action': 'generate', 'images': [{'prompt': 'A red fox'}, {'prompt': 'A blue fox'}]})), ('done', 'stop')]))
    with factory('admin') as admin, factory() as first:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        image = image_target(admin, ah)
        geometry = admin.post('/api/v1/providers', headers=ah, json={'name': 'Geometry fixture', 'base_url': 'http://127.0.0.1:1236', 'model_id': GEOMETRY_INFO.model, 'protocol': GEOMETRY_INFO.protocol, 'local_only': True}).json()['id']
        assert admin.post(f'/api/v1/providers/{geometry}/probe', headers=ah, json={'revision': 1}).status_code == 200
        text_target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Independent text', 'base_url': 'http://127.0.0.1:1234', 'model_id': 'fixture', 'resource_pool': 'Text GPU', 'local_only': True}).json()['id']
        assert admin.post(f'/api/v1/providers/{text_target}/probe', headers=ah, json={'revision': 1}).status_code == 200
        node, token, pool = adopt(migration, settings, image, paused=False)
        with scoped_session(migration, workers.SYSTEM, settings.farm_id) as db:
            connection = db.execute(text('SELECT connection_id FROM inference_targets WHERE id=:id'), {'id': geometry}).scalar_one()
            db.execute(text("UPDATE managed_workers SET policy='shared',desired_service='trellis',services=services || CAST(:service AS jsonb) WHERE id=:id"), {'id': node, 'service': json.dumps({'trellis': {'name': 'TRELLIS', 'connection_id': str(connection)}})})
        poll = f'/api/v1/worker-control/{node}/poll'
        heartbeat = report(ready_service='trellis')
        assert admin.post(poll, headers={'Authorization': 'Bearer ' + token}, json=heartbeat).status_code == 200
        signin(first)
        fh = csrf(first, settings.user_origin)
        reference_image = reference()
        geometry_job = {'name': 'Queued fixture model', 'target_id': geometry, 'image': base64.b64encode(reference_image).decode(), 'request': {'id': str(uuid4()), 'model': GEOMETRY_INFO.model, 'image_sha256': hashlib.sha256(reference_image).hexdigest()}}
        assert first.post('/api/v1/geometry', headers=fh, json=geometry_job).status_code == 202
        geometry_admission = image_queue.claim(app, settings, pool)
        assert geometry_admission
        gallery = request(image)
        assert first.post('/api/v1/images', headers=fh, json=gallery).status_code == 202
        second_subject = str(uuid4())
        monkeypatch.setattr(identity, 'verify_id_token', lambda *args: {'sub': second_subject, 'name': 'Second member'})
        monkeypatch.setattr(identity, 'token_request', lambda config, endpoint, data:
            {'active': True, 'sub': subject if data.get('token') == 'EXPLICIT PROVIDER FIXTURE' else second_subject, 'iss': config.issuer}
            if endpoint == 'token/introspect' else {'id_token': 'FIXTURE', 'access_token': 'SECOND', 'refresh_token': 'FIXTURE', 'expires_in': 300})
        with factory() as second:
            signin(second)
            approve_fixture_member(second, migration, settings)
            sh = csrf(second, settings.user_origin)
            path, run_id, data = send(second, sh, scope, 'Make us two images of foxes' if planned else 'Make us an image of a fox')
            pictures = await_pictures(second, path)
            assert len(pictures) == (2 if planned else 1)
            assert all(item['status'] == 'queued' for item in pictures)
            assert second.post(path + ('/turns' if scope == 'private' else '/messages'), headers=sh, json=data).status_code in {201, 202}
            # Neither gallery reads nor another joined member can misdiagnose waiting as lost execution.
            second.get('/api/v1/images')
            if scope == 'channel':
                assert first.post(path + '/join', headers=fh).status_code == 200
                assert first.get(path).json()['messages'][-1]['status'] == 'running'
                assert first.post(path + '/runs/' + run_id + '/stop', headers=fh).status_code == 404
            assert image_queue.claim(app, settings, pool) is None
            assert 'current GPU job' in await_pictures(second, path)[0]['reason']
            image_queue.execute_queued(app, settings, *geometry_admission)
            # Second owner goes next, ahead of the first owner's older gallery request.
            admitted = image_queue.claim(app, settings, pool)
            assert str(admitted[2].id) == run_id
            assert str(admitted[0].id) == second.get('/api/v1/session').json()['id']
            with scoped_session(app, workers.SYSTEM, settings.farm_id) as db:
                worker = workers.for_pool(db, pool)
                assert worker['desired_service'] == 'fooocus' and worker['revision'] == 2
            prepared = threading.Event()
            actual_check = provider_health.check_connection
            monkeypatch.setattr(provider_health, 'check_connection', lambda *args: (prepared.set(), actual_check(*args)))
            execution = threading.Thread(target=image_queue.execute_queued, args=(app, settings, *admitted))
            execution.start()
            try:
                assert not prepared.wait(.15)  # A desired service is not verified readiness.
                assert admin.post(poll, headers={'Authorization': 'Bearer ' + token}, json=heartbeat | {'sequence': 2, 'observed_revision': 2, 'ready_service': 'fooocus'}).status_code == 200
                execution.join(10)
                assert not execution.is_alive()
            finally:
                execution.join(10)
            assert prepared.is_set()
            assert all(item['status'] == 'completed' for item in await_pictures(second, path))
            assert second.get(path).json()['messages'][-1]['status'] == 'completed'
            assert len(calls) == (3 if planned else 2)  # Qualification probe plus this request only.
            assert len(second.get('/api/v1/images').json()['items']) == (len(pictures) if scope == 'private' else 0)
            if scope == 'private':
                assert first.get('/api/v1/conversation-images/' + run_id + '/image').status_code == 404
            next_admitted = image_queue.claim(app, settings, pool)
            assert str(next_admitted[2].id) == gallery['request']['id']
            image_queue.execute_queued(app, settings, *next_admitted)
            assert first.get('/api/v1/images').json()['items'][0]['status'] == 'completed'


@pytest.mark.parametrize('scope', ['private', 'channel'])
@pytest.mark.parametrize('ending', ['stop', 'session', 'expire', 'revoke', 'worker_failed', 'resident', 'restart'])
def test_waiting_conversation_settles_visibly_without_rendering_or_replay(bff, monkeypatch, scope, ending):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    monkeypatch.setattr(image_queue.ImageQueue, 'run', lambda self: self.stop.wait())
    calls = []
    fixture_images(monkeypatch, calls)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        target = image_target(admin, csrf(admin, settings.admin_origin))
        node, _, pool = adopt(migration, settings, target)
        signin(user)
        uh = csrf(user, settings.user_origin)
        owner = user.get('/api/v1/session').json()['id']
        path, run_id, _ = send(user, uh, scope)
        assert image_queue.claim(app, settings, pool) is None

        assert 'paused' in await_pictures(user, path)[0]['reason']
        with scoped_session(migration, owner, settings.farm_id) as db:
            if ending == 'session':
                db.execute(text("UPDATE browser_sessions SET expires_at=now()-interval '1 second' WHERE user_id=(SELECT owner_id FROM image_jobs WHERE id=:id) AND audience='user'"), {'id': run_id})
            if ending == 'expire':
                db.execute(text("UPDATE capability_queue SET expires_at=now()-interval '1 second' WHERE id=:id"), {'id': run_id})
            if ending == 'revoke':
                db.execute(text('UPDATE users SET authorization_version=authorization_version+1 WHERE id=(SELECT owner_id FROM image_jobs WHERE id=:id)'), {'id': run_id})
            if ending == 'worker_failed':
                db.execute(text("UPDATE managed_workers SET state='failed' WHERE id=:id"), {'id': node})
            if ending in {'resident', 'restart'}:
                db.execute(text("UPDATE managed_workers SET paused=false,state='ready',seen_at=now(),observed_revision=revision,desired_service=:service,ready_service=:service WHERE id=:id"), {'id': node, 'service': 'trellis' if ending == 'resident' else 'fooocus'})
        if ending == 'stop':
            assert user.post(path + ('/stop' if scope == 'private' else '/runs/' + run_id + '/stop'), headers=uh).status_code == 200
        image_queue.maintain(app, settings)
        admitted = image_queue.claim(app, settings, pool)
        if ending == 'restart':
            # Claimed-but-lost work is not re-executed after lease expiry.
            assert admitted
            with scoped_session(migration, owner, settings.farm_id) as db:
                db.execute(text("UPDATE provider_pools SET lease_until=now()-interval '1 second' WHERE id=:id"), {'id': pool})
            image_queue.maintain(app, settings)
        else:
            assert admitted is None
        with scoped_session(migration, owner, settings.farm_id) as db:
            image = db.execute(text('SELECT status,reason FROM image_jobs WHERE id=:id'), {'id': run_id}).mappings().one()
            assert image['status'] == ('interrupted' if ending == 'restart' else 'failed' if ending in {'resident', 'worker_failed'} else 'cancelled')
            assert image['reason']
            runs = 'chat_runs' if scope == 'private' else 'channel_runs'
            assert db.execute(text(f'SELECT status FROM {runs} WHERE id=:id'), {'id': run_id}).scalar_one() == image['status']
            assert db.execute(text('SELECT state FROM capability_queue WHERE id=:id'), {'id': run_id}).scalar_one() == 'finished'
        assert len(calls) == 1
        assert image_queue.claim(app, settings, pool) is None


@pytest.mark.parametrize('scope,action', [('private', 'stop'), ('private', 'steer'), ('channel', 'stop'), ('channel', 'leave')])
def test_cancel_waiting_batch_behind_paused_gallery_preserves_other_work(bff, monkeypatch, scope, action):
    from hearth import chat
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    monkeypatch.setattr(image_queue.ImageQueue, 'run', lambda self: self.stop.wait())
    calls = []
    fixture_images(monkeypatch, calls)
    monkeypatch.setattr(image_planning, 'chat_stream', lambda *a, **kw: iter([('text', json.dumps({'action': 'generate', 'images': [{'prompt': 'A red fox'}, {'prompt': 'A blue fox'}]})), ('done', 'stop')]))
    monkeypatch.setattr(chat, 'chat_stream', lambda *a, **kw: iter([('text', 'Steering succeeded.'), ('done', 'stop')]))
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = image_target(admin, ah)
        planner = admin.post('/api/v1/providers', headers=ah, json={'name': 'Planner', 'base_url': 'http://127.0.0.1:1234', 'model_id': 'fixture', 'resource_pool': 'Text only', 'local_only': True}).json()['id']
        assert admin.post(f'/api/v1/providers/{planner}/probe', headers=ah, json={'revision': 1}).status_code == 200
        _, _, pool = adopt(migration, settings, target)
        signin(user)
        uh = csrf(user, settings.user_origin)
        owner = user.get('/api/v1/session').json()['id']
        earlier = request(target)
        assert user.post('/api/v1/images', headers=uh, json=earlier).status_code == 202
        path, run_id, _ = send(user, uh, scope, 'Make us two images of foxes')
        assert all(item['status'] == 'queued' for item in await_pictures(user, path))
        if action == 'leave':
            assert user.post(path + '/leave', headers=uh).status_code == 200
        elif action == 'steer':
            current = user.get(path).json()
            assert user.post(path + '/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': current['revision'], 'interrupt_run_id': run_id, 'content': 'Explain the weather'}).status_code == 202
        else:
            assert user.post(path + ('/stop' if scope == 'private' else '/runs/' + run_id + '/stop'), headers=uh).status_code == 200
        # The cancelled batch is not at the head of this paused queue.
        followups = image_queue.maintain(app, settings)
        if action == 'steer':
            assert len(followups) == 1
            # Tick schedules this after commit, even when the browser is closed.
            chat.dispatch_pending(app, settings, *followups[0])
        assert image_queue.claim(app, settings, pool) is None
        with scoped_session(app, owner, settings.farm_id) as db:
            assert db.execute(text('SELECT state FROM capability_queue WHERE id=:id'), {'id': run_id}).scalar_one() == 'finished'
            assert set(db.execute(text('SELECT status FROM image_jobs WHERE batch_run_id=:id'), {'id': run_id}).scalars()) == {'cancelled'}
            assert db.execute(text('SELECT status FROM image_jobs WHERE id=:id'), {'id': earlier['request']['id']}).scalar_one() == 'queued'
        if action == 'steer':
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                result = user.get(path).json()
                if result['messages'][-1]['content'] == 'Steering succeeded.':
                    break
                time.sleep(.02)
            assert result['messages'][-1]['content'] == 'Steering succeeded.'
        assert len(calls) == 1


@pytest.mark.parametrize('scope', ['private', 'channel'])
def test_undispatched_conversation_resumes_once_after_bff_restart(bff, monkeypatch, scope):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    monkeypatch.setattr(image_queue.ImageQueue, 'run', lambda self: self.stop.wait())
    calls = []
    fixture_images(monkeypatch, calls)
    with factory('admin') as admin:
        signin(admin)
        promote(admin, migration, settings)
        target = image_target(admin, csrf(admin, settings.admin_origin))
        with factory() as user:
            signin(user)
            path, run_id, _ = send(user, csrf(user, settings.user_origin), scope)
            assert await_pictures(user, path)[0]['status'] == 'queued'
        with factory() as reopened:
            signin(reopened)
            assert await_pictures(reopened, path)[0]['status'] == 'queued'
            with scoped_session(app, workers.SYSTEM, settings.farm_id) as db:
                pool = db.execute(text('SELECT resource_pool_id FROM inference_targets WHERE id=:id'), {'id': target}).scalar_one()
            admitted = image_queue.claim(app, settings, pool)
            assert str(admitted[2].id) == run_id
            image_queue.execute_queued(app, settings, *admitted)
            assert await_pictures(reopened, path)[0]['status'] == 'completed'
            assert image_queue.claim(app, settings, pool) is None
            assert len(calls) == 2
