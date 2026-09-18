"""Batch lifetime, isolation and receipt fencing against real restricted PostgreSQL."""
import hashlib
import json
import os
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest
from hearth import chat, conversation_media, image_planning, image_transport
from hearth.database import scoped_session
from hearth.inference import ProviderError
from sqlalchemy import text

from tests.integration.test_chat import configure, csrf, promote, setup, wait_finished
from tests.integration.test_conversation_images import channel_finished, fixture_images
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_image_planning import turn
from tests.integration.test_images import MODEL, image_target, receipt
from tests.integration.test_postgres import databases as databases

REQUEST = 'make 4 different jeep gladiators in red grey black and army-green please'
COLORS = ['red', 'grey', 'black', 'army-green']


def batch_stream(*args, **kwargs):
    yield 'text', json.dumps({'action': 'generate', 'images': [{'prompt': f'A {color} Jeep Gladiator pickup with a visible cargo bed in daylight'} for color in COLORS]})
    yield 'done', 'stop'


@pytest.mark.parametrize('scope', ['private', 'channel'])
def test_four_images_persist_in_order_and_only_in_their_conversation_scope(bff, monkeypatch, scope):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    calls = []
    fixture_images(monkeypatch, calls)
    monkeypatch.setattr(image_planning, 'chat_stream', batch_stream)
    monkeypatch.setattr(chat, 'chat_stream', lambda *a, **kw: iter([('text', 'Four descriptions: red, grey, black and army-green Jeep Gladiators.'), ('done', 'stop')]))
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        image_target(admin, ah)
        signin(user)
        headers = csrf(user, settings.user_origin)
        if scope == 'private':
            path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=headers, json={}).json()['id']
            turn(user, headers, path, REQUEST)  # No image focus yet: discussion.
            wait_finished(user, path)
            parent = turn(user, headers, path, 'ok generate the images of each please')
            result = wait_finished(user, path)
        else:
            path = '/api/v1/channels/' + user.post('/api/v1/channels', headers=headers, json={'name': 'Four trucks'}).json()['id']
            user.post(path + '/messages', headers=headers, json={'request_id': str(uuid4()), 'content': REQUEST})
            parent = str(uuid4())
            user.post(path + '/messages', headers=headers, json={'request_id': parent, 'content': '@hearth generate the images of each please'})
            result = channel_finished(user, path)
        pictures = result['messages'][-1]['images']
        assert len(pictures) == 4, result
        assert [p['batch_index'] for p in pictures] == [1, 2, 3, 4]
        assert all(p['status'] == 'completed' and p['batch_count'] == 4 for p in pictures)
        assert len({p['request']['id'] for p in pictures}) == 4
        assert pictures[0]['request']['id'] == parent
        assert len(calls) == 5  # Probe plus four real executor calls, no text-only substitute.
        for picture in pictures:
            assert user.get('/api/v1/conversation-images/' + picture['request']['id'] + '/image').status_code == 200
        assert len(user.get('/api/v1/images').json()['items']) == (4 if scope == 'private' else 0)
        assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'idle'
        with factory() as reopened:
            signin(reopened)
            assert reopened.get(path).json()['messages'][-1]['images'] == pictures
        with migration.connect() as db:
            other = db.execute(text('SELECT id FROM users WHERE farm_id=:farm AND subject<>:subject'), {'farm': settings.farm_id, 'subject': subject}).scalar_one()
        with scoped_session(app, other, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM conversation_images')).scalar_one() == 0
            assert db.execute(text('SELECT count(*) FROM image_jobs')).scalar_one() == 0
        if scope == 'private':
            turn(user, headers, path, 'Make it blue instead')
            question = wait_finished(user, path)['messages'][-1]
            assert question['content'].startswith('Which picture') and not question['images']
            assert len(calls) == 5  # An ambiguous batch reference does not guess.
            first = pictures[0]['request']['id']
            # Existing variations may reference a removed image's identity.
            with scoped_session(app, user.get('/api/v1/session').json()['id'], settings.farm_id) as db:
                db.execute(text('UPDATE conversation_images SET source_image_id=:source WHERE id=:id'), {'source': first, 'id': pictures[1]['request']['id']})
            assert user.delete('/api/v1/images/' + first, headers=headers).status_code == 200
            assert user.get('/api/v1/images/' + first + '/image').status_code == 404
            assert user.get('/api/v1/conversation-images/' + first + '/image').status_code == 404
            updated = next(m['images'] for m in user.get(path).json()['messages'] if len(m['images']) == 4)
            assert [p['status'] for p in updated] == ['deleted', 'completed', 'completed', 'completed']
            assert user.get('/api/v1/conversation-images/' + pictures[1]['request']['id'] + '/image').status_code == 200
            with scoped_session(app, user.get('/api/v1/session').json()['id'], settings.farm_id) as db:
                assert db.execute(text('SELECT image IS NULL AND sha256 IS NULL FROM conversation_images WHERE id=:id'), {'id': first}).scalar_one()


@pytest.mark.parametrize('action', ['complete', 'stop', 'steer', 'unknown', 'expire', 'revoke', 'delete'])
def test_batch_keeps_one_pool_receipt_and_preserves_completed_images_on_interruption(bff, monkeypatch, action):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    calls = []
    artifact = fixture_images(monkeypatch, calls)
    monkeypatch.setattr(image_planning, 'chat_stream', batch_stream)
    monkeypatch.setattr(chat, 'chat_stream', lambda *a, **kw: iter([('text', 'A short text reply.'), ('done', 'stop')]))
    entered, release = threading.Event(), threading.Event()
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        image_target(admin, ah)
        signin(user)
        owner = user.get('/api/v1/session').json()['id']
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=headers, json={}).json()['id']
        turn(user, headers, path, 'Generate an image of a Jeep Gladiator')
        wait_finished(user, path)
        calls.clear()

        def render(url, key, config, data, observe=lambda value: False):
            calls.append(data)
            if len(calls) == 2:
                entered.set()
                assert release.wait(10)
                if action == 'unknown':
                    raise ProviderError('Fixture lost receipt', uncertain=True)
            result = receipt(data).model_copy(update={'sha256': hashlib.sha256(artifact).hexdigest()})
            return (receipt(data, 'cancelled'), None) if observe(result) else (result, artifact)

        monkeypatch.setattr(image_transport, 'render', render)
        parent = turn(user, headers, path, REQUEST)
        try:
            assert entered.wait(5)
            running = user.get(path).json()
            assert running['runs'][-1]['status'] == 'running'
            assert [p['status'] for p in running['messages'][-1]['images']] == ['completed', 'running', 'queued', 'queued']
            assert admin.get('/api/v1/providers').json()['items'][0]['active_run_id'] == parent
            assert all(job['status'] != 'interrupted' for job in user.get('/api/v1/images').json()['items'])
            if action == 'delete':
                assert user.delete('/api/v1/images/' + running['messages'][-1]['images'][2]['request']['id'], headers=headers).status_code == 409
                assert user.delete('/api/v1/images/' + parent, headers=headers).status_code == 200
            if action == 'stop':
                assert user.post(path + '/stop', headers=headers).status_code == 200
            if action == 'steer':
                response = user.post(path + '/turns', headers=headers, json={'request_id': str(uuid4()), 'revision': running['revision'], 'content': 'Tell me a short joke instead', 'interrupt_run_id': parent})
                assert response.json()['status'] == 'queued'
            if action == 'revoke':
                with scoped_session(app, owner, settings.farm_id) as db:
                    db.execute(text("UPDATE browser_sessions SET expires_at=now()-interval '1 second' WHERE audience='user' AND user_id=:owner"), {'owner': owner})
            if action == 'expire':
                with scoped_session(app, owner, settings.farm_id) as db:
                    db.execute(text("UPDATE provider_pools SET lease_until=now()-interval '1 second' WHERE active_run_id=:id"), {'id': parent})
                assert user.get(path).json()['runs'][-1]['status'] == 'interrupted'
        finally:
            release.set()
        if action == 'revoke':
            signin(user)
        result = wait_finished(user, path)
        if action == 'steer':
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and result['messages'][-1]['content'] != 'A short text reply.':
                time.sleep(.02)
                result = user.get(path).json()
        pictures = next(m['images'] for m in result['messages'] if len(m['images']) == 4)
        assert pictures[0]['status'] == ('deleted' if action == 'delete' else 'completed')
        assert len(calls) == (4 if action in {'complete', 'delete'} else 2)
        assert sum(p['status'] == 'completed' for p in pictures) == (4 if action == 'complete' else 3 if action == 'delete' else 1)
        if action == 'delete':
            assert user.get('/api/v1/conversation-images/' + parent + '/image').status_code == 404
            assert all(job['id'] != parent for job in user.get('/api/v1/images').json()['items'])
            # Deleting the rest of the batch leaves no automatic variation source.
            for picture in pictures[1:]:
                assert user.delete('/api/v1/images/' + picture['request']['id'], headers=headers).status_code == 200
            with scoped_session(app, owner, settings.farm_id) as db:
                assert conversation_media.recent_image(db, chat_id=path.split('/')[-1]) is None
        assert all(p['status'] not in {'queued', 'running'} for p in pictures)
        expected = 'unknown' if action in {'unknown', 'expire'} else 'idle'
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and admin.get('/api/v1/providers').json()['items'][0]['execution_state'] != expected:
            time.sleep(.02)
        assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == expected


@pytest.mark.skipif(not (os.environ.get('HEARTH_LIVE_IMAGE_PROVIDER') and os.environ.get('HEARTH_LIVE_CHAT_MODEL')), reason='Explicit opt-in for four local GPU renders.')
def test_live_four_gladiators_from_conversation(bff):
    factory, settings, _, migration, _ = bff
    model = os.environ['HEARTH_LIVE_CHAT_MODEL']
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah, model)
        key = Path('.hearth/image-provider/controller.key').read_text(encoding='utf-8').strip()
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Live batch fixture', 'base_url': 'http://127.0.0.1:1235', 'model_id': MODEL, 'api_key': key, 'protocol': 'hearth.image.v1', 'local_only': True}).json()
        assert admin.post('/api/v1/providers/' + target['id'] + '/probe', headers=ah, json={'revision': 1}).json()['state'] == 'ready'
        signin(user)
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=headers, json={}).json()['id']
        turn(user, headers, path, 'Remember four Jeep Gladiator pickups with visible cargo beds, in red, grey, black and army-green. Briefly acknowledge this for now.')
        assert wait_finished(user, path, 90)['runs'][-1]['status'] == 'completed'
        turn(user, headers, path, 'ok generate the images of each please')
        result = wait_finished(user, path, 240)
        assert result['runs'][-1]['status'] == 'completed', result['runs'][-1]
        pictures = result['messages'][-1]['images']
        assert len(pictures) == 4
        output = Path('evidence/images/2026-09-13/batches')
        output.mkdir(parents=True, exist_ok=True)
        for index, picture in enumerate(pictures, 1):
            prompt = picture['request']['prompt'].lower()
            assert 'gladiator' in prompt and ('pickup' in prompt or 'cargo bed' in prompt), prompt
            artifact = user.get('/api/v1/conversation-images/' + picture['request']['id'] + '/image').content
            assert hashlib.sha256(artifact).hexdigest() == picture['sha256']
            (output / f'gladiator-{index}.png').write_bytes(artifact)
        (output / 'live-batch.json').write_text(json.dumps({'scope': 'Real local GPT-OSS planning and four SDXL renders; synthetic OIDC in a disposable farm. No personal chats modified.', 'images': pictures, 'completed': True}, indent=2), encoding='utf-8')


@pytest.mark.parametrize('action', ['leave', 'stop'])
def test_channel_batch_stops_when_requester_leaves_or_stops(bff, monkeypatch, action):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    calls = []
    artifact = fixture_images(monkeypatch, calls)
    monkeypatch.setattr(image_planning, 'chat_stream', batch_stream)
    entered, release = threading.Event(), threading.Event()
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        image_target(admin, ah)
        signin(user)
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/channels/' + user.post('/api/v1/channels', headers=headers, json={'name': 'Batch lifetime'}).json()['id']
        calls.clear()

        def render(url, key, config, data, observe=lambda value: False):
            calls.append(data)
            if len(calls) == 2:
                entered.set()
                assert release.wait(10)
            result = receipt(data).model_copy(update={'sha256': hashlib.sha256(artifact).hexdigest()})
            return (receipt(data, 'cancelled'), None) if observe(result) else (result, artifact)

        monkeypatch.setattr(image_transport, 'render', render)
        parent = str(uuid4())
        assert user.post(path + '/messages', headers=headers, json={'request_id': parent, 'content': '@hearth generate 4 images of trucks'}).status_code == 201
        try:
            assert entered.wait(5)
            assert user.post(path + ('/leave' if action == 'leave' else f'/runs/{parent}/stop'), headers=headers).status_code == 200
        finally:
            release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and admin.get('/api/v1/providers').json()['items'][0]['execution_state'] != 'idle':
            time.sleep(.02)
        assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'idle'
        assert len(calls) == 2
        if action == 'leave':
            user.post(path + '/join', headers=headers)
        pictures = user.get(path).json()['messages'][-1]['images']
        assert [p['status'] for p in pictures] == ['completed', 'cancelled', 'cancelled', 'cancelled']


def test_gallery_reconciles_batch_lost_before_its_first_render_without_replay(bff, monkeypatch):
    from hearth import image_batches
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    calls = []
    fixture_images(monkeypatch, calls)
    monkeypatch.setattr(image_planning, 'chat_stream', batch_stream)
    entered, release = threading.Event(), threading.Event()
    original = image_batches.execute_batch

    def delayed(*args):
        entered.set()
        assert release.wait(10)
        original(*args)

    monkeypatch.setattr(image_batches, 'execute_batch', delayed)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        image_target(admin, ah)
        signin(user)
        headers = csrf(user, settings.user_origin)
        owner = user.get('/api/v1/session').json()['id']
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=headers, json={}).json()['id']
        parent = turn(user, headers, path, 'Generate 4 images of trucks')
        try:
            assert entered.wait(5)
            with scoped_session(app, owner, settings.farm_id) as db:
                db.execute(text("UPDATE provider_pools SET lease_until=now()-interval '1 second' WHERE active_run_id=:id"), {'id': parent})
            gallery = user.get('/api/v1/images').json()['items']
            assert len(gallery) == 4 and all(p['status'] == 'interrupted' for p in gallery)
            assert user.get(path).json()['runs'][-1]['status'] == 'interrupted'
        finally:
            release.set()
        assert len(calls) == 1  # Probe only; interrupted batch is never replayed.
        assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'unknown'
