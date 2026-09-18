"""Real PostgreSQL boundaries; model and OIDC fixtures except the opt-in GPU case."""
import hashlib
import io
import json
import os
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest
from hearth import chat, identity, image_transport
from hearth.database import scoped_session
from PIL import Image
from sqlalchemy import text

from tests.integration.test_chat import configure, csrf, promote, setup, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_images import INFO, MODEL, image_target, receipt
from tests.integration.test_postgres import databases as databases


def png_bytes():
    output = io.BytesIO()
    Image.new('RGB', (1024, 1024), 'orange').save(output, format='PNG')
    return output.getvalue()


def fixture_images(monkeypatch, calls):
    artifact = png_bytes()

    def render(url, key, config, data, observe=lambda value: False):
        calls.append(data)
        result = receipt(data).model_copy(update={'sha256': hashlib.sha256(artifact).hexdigest()})
        cancelled = observe(result)
        return (receipt(data, 'cancelled'), None) if cancelled else (result, artifact)

    monkeypatch.setattr(image_transport, 'information', lambda *args: INFO)
    monkeypatch.setattr(image_transport, 'render', render)
    return artifact


def channel_finished(browser, path, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = browser.get(path).json()
        if result['messages'][-1]['status'] != 'running':
            return result
        time.sleep(.02)
    pytest.fail('Channel image did not finish')


def test_chat_dispatches_image_without_text_model_and_restores_private_artifact(bff, monkeypatch):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    calls = []
    artifact = fixture_images(monkeypatch, calls)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        image_target(admin, csrf(admin, settings.admin_origin))
        signin(user)
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=headers, json={}).json()['id']
        data = {'request_id': str(uuid4()), 'revision': 1, 'content': 'Could you make an image of a friendly fox by a fire?'}
        accepted = user.post(path + '/turns', headers=headers, json=data)
        assert accepted.status_code == 202, accepted.text
        result = wait_finished(user, path)
        assert result['runs'][-1]['status'] == 'completed', result
        picture = result['messages'][-1]['image']
        assert picture['request']['prompt'] == 'a friendly fox by a fire?'
        assert picture['sha256'] == hashlib.sha256(artifact).hexdigest()
        source = '/api/v1/conversation-images/' + data['request_id'] + '/image'
        assert user.get(source).content == artifact
        assert user.get(source).headers['cache-control'] == 'no-store'
        assert admin.get(source).status_code == 403
        assert user.get('/api/v1/images').json()['items'][0]['id'] == data['request_id']
        assert user.post(path + '/turns', headers=headers, json=data).status_code == 202
        assert len(calls) == 2  # Probe and one conversation action.
        assert user.post(path + '/turns', headers=headers, json=data | {'content': 'Make an image of something else'}).status_code == 409
        with factory() as reopened:
            signin(reopened)
            assert reopened.get(path).json()['messages'][-1]['image'] == picture
            assert reopened.get(source).content == artifact
        with migration.connect() as db:
            other = db.execute(text('SELECT id FROM users WHERE farm_id=:farm AND subject<>:subject'), {'farm': settings.farm_id, 'subject': subject}).scalar_one()
        with scoped_session(app, other, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM conversation_images')).scalar_one() == 0
        with scoped_session(app, user.get('/api/v1/session').json()['id'], uuid4()) as db:
            assert db.execute(text('SELECT count(*) FROM conversation_images')).scalar_one() == 0
        # A subsequent text turn receives the description, never a model URL or
        # invented vision input, and does not produce another image.
        configure(admin, csrf(admin, settings.admin_origin))
        contexts = []

        def stream(*args, **kwargs):
            contexts.append(args[3])
            yield 'text', 'It was a fox by a fire.'
            yield 'done', 'stop'

        monkeypatch.setattr(chat, 'chat_stream', stream)
        assert user.post(path + '/turns', headers=headers, json={'request_id': str(uuid4()), 'revision': result['revision'], 'content': 'What did I ask for?'}).status_code == 202
        assert wait_finished(user, path)['messages'][-1]['content'] == 'It was a fox by a fire.'
        assert 'image pixels are not included' in next(item['content'] for item in contexts[0] if item['role'] == 'assistant')
        assert len(calls) == 2


@pytest.mark.parametrize('ending', ['steer', 'revoke', 'unknown'])
def test_image_turn_cancellation_and_durable_steering_fence_shared_capacity(bff, monkeypatch, ending):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    calls = []
    artifact = fixture_images(monkeypatch, calls)
    entered, release = threading.Event(), threading.Event()

    def render(url, key, config, data, observe=lambda value: False):
        if data.prompt.startswith('A small warm'):
            return receipt(data), artifact
        calls.append(data)
        if len(calls) == 1:
            observe(receipt(data, 'running'))
            entered.set()
            assert release.wait(10)
            assert observe(receipt(data, 'running')) is True
            if ending == 'unknown':
                from hearth.inference import ProviderError
                raise ProviderError('Fixture lost cancellation receipt', uncertain=True)
            return receipt(data, 'cancelled'), None
        result = receipt(data).model_copy(update={'sha256': hashlib.sha256(artifact).hexdigest()})
        observe(result)
        return result, artifact

    monkeypatch.setattr(image_transport, 'render', render)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        image_target(admin, csrf(admin, settings.admin_origin))
        signin(user)
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=headers, json={}).json()['id']
        first = {'request_id': str(uuid4()), 'revision': 1, 'content': 'Make an image of a fox'}
        try:
            assert user.post(path + '/turns', headers=headers, json=first).status_code == 202
            assert entered.wait(5)
            value = user.get(path).json()
            assert value['messages'][-1]['image']['progress'] == 1
            note = {'id': str(uuid4()), 'content': 'Make an image of a red panda instead'}
            assert user.post('/api/v1/side-notes', headers=headers, json=note).status_code == 201
            steer = {'request_id': str(uuid4()), 'revision': value['revision'], 'content': note['content'], 'note_id': note['id'], 'note_revision': 1, 'interrupt_run_id': first['request_id']}
            assert user.post(path + '/turns', headers=headers, json=steer).json()['status'] == 'queued'
            assert user.get('/api/v1/side-notes').json()['items'] == []
            assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'running'
            assert len(calls) == 1
            if ending == 'revoke':
                assert user.post('/api/v1/logout', headers=headers).status_code == 303
        finally:
            release.set()
        if ending == 'revoke':
            signin(user)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            value = user.get(path).json()
            if ending == 'steer' and len(value['runs']) == 2 and value['runs'][-1]['status'] == 'completed':
                break
            if ending != 'steer' and value['pending'] and value['pending'][0]['state'] == 'blocked':
                break
            time.sleep(.02)
        else:
            pytest.fail(str(value))
        assert value['messages'][1]['image']['status'] == ('interrupted' if ending == 'unknown' else 'cancelled')
        assert user.get('/api/v1/conversation-images/' + first['request_id'] + '/image').status_code == 404
        assert len(calls) == (2 if ending == 'steer' else 1)
        if ending == 'steer':
            assert value['messages'][-1]['image']['request']['prompt'] == 'a red panda instead'
        assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == ('unknown' if ending == 'unknown' else 'idle')


def test_channel_image_is_shared_only_with_joined_members_not_private_gallery(bff, monkeypatch):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    calls = []
    artifact = fixture_images(monkeypatch, calls)
    with factory('admin') as admin, factory() as first, factory() as second:
        signin(admin)
        promote(admin, migration, settings)
        image_target(admin, csrf(admin, settings.admin_origin))
        signin(first)
        h1 = csrf(first, settings.user_origin)
        path = '/api/v1/channels/' + first.post('/api/v1/channels', headers=h1, json={'name': 'Image workshop'}).json()['id']
        assert first.post(path + '/messages', headers=h1, json={'request_id': str(uuid4()), 'content': 'Make an image of a fox'}).status_code == 201
        assert len(calls) == 1  # No new mention, no generation.
        data = {'request_id': str(uuid4()), 'content': 'Make an image of a fox, @hearth'}
        assert first.post(path + '/messages', headers=h1, json=data).status_code == 201
        result = channel_finished(first, path)
        assert result['messages'][-1]['image']['status'] == 'completed', result
        source = '/api/v1/conversation-images/' + data['request_id'] + '/image'
        assert first.get(source).content == artifact
        assert first.post(path + '/messages', headers=h1, json=data).status_code == 201
        assert len(calls) == 2
        assert first.get('/api/v1/images').json()['items'] == []
        assert first.get('/api/v1/images/' + data['request_id'] + '/image').status_code == 404
        assert first.delete('/api/v1/images/' + data['request_id'], headers=h1).status_code == 404
        second_subject = str(uuid4())
        monkeypatch.setattr(identity, 'verify_id_token', lambda *args: {'sub': second_subject, 'name': 'Another member'})
        monkeypatch.setattr(identity, 'token_request', lambda config, endpoint, data:
            {'active': True, 'sub': subject if data.get('token') == 'EXPLICIT PROVIDER FIXTURE' else second_subject, 'iss': config.issuer}
            if endpoint == 'token/introspect' else {'id_token': 'FIXTURE', 'access_token': 'SECOND', 'refresh_token': 'FIXTURE', 'expires_in': 300})
        signin(second)
        h2 = csrf(second, settings.user_origin)
        assert second.get(source).status_code == 404
        second_id = second.get('/api/v1/session').json()['id']
        with scoped_session(app, second_id, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM conversation_images')).scalar_one() == 0
        assert second.post(path + '/join', headers=h2).status_code == 200
        assert second.get(source).content == artifact
        assert second.get(path).json()['messages'][-1]['image'] == result['messages'][-1]['image']
        assert second.post(path + '/runs/' + data['request_id'] + '/stop', headers=h2).status_code == 404
        assert second.post(path + '/leave', headers=h2).status_code == 200
        assert second.get(source).status_code == 404
        with scoped_session(app, second_id, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM conversation_images')).scalar_one() == 0


def test_leaving_during_channel_image_prevents_late_publication(bff, monkeypatch):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    entered, release = threading.Event(), threading.Event()
    artifact = fixture_images(monkeypatch, [])

    def render(url, key, config, data, observe=lambda value: False):
        if data.prompt.startswith('A small warm'):
            return receipt(data), artifact
        observe(receipt(data, 'running'))
        entered.set()
        assert release.wait(10)
        assert observe(receipt(data, 'running')) is True
        return receipt(data, 'cancelled'), None

    monkeypatch.setattr(image_transport, 'render', render)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        image_target(admin, csrf(admin, settings.admin_origin))
        signin(user)
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/channels/' + user.post('/api/v1/channels', headers=headers, json={'name': 'Stop workshop'}).json()['id']
        data = {'request_id': str(uuid4()), 'content': '@hearth draw a fox'}
        try:
            assert user.post(path + '/messages', headers=headers, json=data).status_code == 201
            assert entered.wait(5)
            assert user.post(path + '/leave', headers=headers).status_code == 200
            assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'running'
        finally:
            release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'idle':
                break
            time.sleep(.02)
        else:
            pytest.fail('Provider did not release after channel leave')
        assert user.post(path + '/join', headers=headers).status_code == 200
        assert user.get(path).json()['messages'][-1]['image']['status'] == 'cancelled'
        assert user.get('/api/v1/conversation-images/' + data['request_id'] + '/image').status_code == 404


@pytest.mark.skipif(not os.environ.get('HEARTH_LIVE_IMAGE_PROVIDER'), reason='Live GPU image generation is explicitly opt-in.')
def test_live_chat_and_channel_image_dispatch(bff):
    factory, settings, _, migration, _ = bff
    key = Path('.hearth/image-provider/controller.key').read_text(encoding='utf-8').strip()
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Live conversation image fixture', 'base_url': 'http://127.0.0.1:1235', 'model_id': MODEL, 'api_key': key, 'protocol': 'hearth.image.v1', 'local_only': True}).json()
        probe = admin.post('/api/v1/providers/' + target['id'] + '/probe', headers=ah, json={'revision': 1})
        assert probe.json()['state'] == 'ready', probe.text
        signin(user)
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=headers, json={}).json()['id']
        request_id = str(uuid4())
        prompt = 'Make an image of a little red fox asleep beside a glowing stone fireplace, warm storybook illustration'
        assert user.post(path + '/turns', headers=headers, json={'request_id': request_id, 'revision': 1, 'content': prompt}).status_code == 202
        result = wait_finished(user, path, 120)
        assert result['runs'][-1]['status'] == 'completed', result
        source = '/api/v1/conversation-images/' + request_id + '/image'
        png = user.get(source).content
        assert hashlib.sha256(png).hexdigest() == result['messages'][-1]['image']['sha256']
        with factory() as reopened:
            signin(reopened)
            assert reopened.get(source).content == png
        room = '/api/v1/channels/' + user.post('/api/v1/channels', headers=headers, json={'name': 'Live image workshop'}).json()['id']
        channel_request = str(uuid4())
        assert user.post(room + '/messages', headers=headers, json={'request_id': channel_request, 'content': '@hearth draw a tiny wooden spaceship above a pine forest, warm storybook illustration'}).status_code == 201
        channel = channel_finished(user, room, 120)
        assert channel['messages'][-1]['image']['status'] == 'completed', channel
        channel_png = user.get('/api/v1/conversation-images/' + channel_request + '/image').content
        assert hashlib.sha256(channel_png).hexdigest() == channel['messages'][-1]['image']['sha256']
        assert len(user.get('/api/v1/images').json()['items']) == 1
        output = Path('evidence/images/2026-09-13/chat-routing')
        output.mkdir(parents=True, exist_ok=True)
        (output / 'private-chat.png').write_bytes(png)
        (output / 'channel.png').write_bytes(channel_png)
        (output / 'live-dispatch.json').write_text(json.dumps({'scope': 'Real local SDXL, BFF dispatch and restricted PostgreSQL. Explicit OIDC fixtures in disposable farm; no real user records changed.', 'private_request': prompt, 'private_image': result['messages'][-1]['image'], 'channel_image': channel['messages'][-1]['image'], 'fresh_session_restores_png': True, 'channel_excluded_from_private_gallery': True, 'text_model_required': False}, indent=2), encoding='utf-8')
