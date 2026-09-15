import json
import os
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest
from hearth import chat, image_planning
from hearth.database import scoped_session
from hearth.inference import ProviderError
from sqlalchemy import text

from tests.integration.test_chat import configure, csrf, promote, setup, wait_finished
from tests.integration.test_conversation_images import channel_finished, fixture_images
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_images import MODEL, image_target
from tests.integration.test_postgres import databases as databases


def turn(user, headers, path, content):
    value = user.get(path).json()
    result = user.post(path + '/turns', headers=headers, json={'request_id': str(uuid4()), 'revision': value['revision'], 'content': content})
    assert result.status_code == 202, result.text
    return result.json()['id']


def prompt_stream(prompt='A blue Jeep beside a pine forest'):
    yield 'text', json.dumps({'action': 'generate', 'prompt': prompt, 'shape': 'square'})
    yield 'done', 'stop'


def test_contextual_images_variations_and_private_planning_provenance(bff, monkeypatch):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    renders, inputs = [], []
    fixture_images(monkeypatch, renders)
    monkeypatch.setattr(chat, 'chat_stream', lambda *a, **kw: iter([('text', 'We described a red Jeep beside a pine forest.'), ('done', 'stop')]))

    def stream(*args, **kwargs):
        data = json.loads(args[3][-1]['content'])
        inputs.append(data)
        assert 'fixture-controller' not in json.dumps(data)
        yield from prompt_stream('A blue Jeep beside a pine forest' if data['reference_image'] else 'A red Jeep beside a pine forest')

    monkeypatch.setattr(image_planning, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        image_target(admin, ah)
        signin(user)
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=headers, json={}).json()['id']
        turn(user, headers, path, 'Imagine a red Jeep beside a pine forest. Just describe it.')
        wait_finished(user, path)
        first_id = turn(user, headers, path, 'Please draw what we just discussed')
        first = wait_finished(user, path)
        assert first['runs'][-1]['status'] == 'completed', first
        assert first['messages'][-1]['image']['request']['prompt'] == 'A red Jeep beside a pine forest'
        assert first['messages'][-1]['image']['planning_model'] == 'fixture'
        assert inputs[0]['reference_image'] is None
        assert 'red Jeep' in inputs[0]['conversation'][0]['content']
        turn(user, headers, path, 'Thank you')
        wait_finished(user, path)
        second_id = turn(user, headers, path, 'Make it blue instead')
        second = wait_finished(user, path)
        image = second['messages'][-1]['image']
        assert image['request']['prompt'] == 'A blue Jeep beside a pine forest'
        assert image['variation'] is True
        assert image['source_image_id'] == first_id
        assert inputs[1]['reference_image']['id'] == first_id
        assert len(renders) == 3  # Probe plus two images, no overlapping planner job.
        assert user.get('/api/v1/conversation-images/' + second_id + '/image').status_code == 200
        owner = user.get('/api/v1/session').json()['id']
        with scoped_session(app, owner, settings.farm_id) as db:
            assert db.execute(text("SELECT count(*) FROM image_plans WHERE status='completed'")).scalar_one() == 2
        with migration.connect() as db:
            other = db.execute(text('SELECT id FROM users WHERE farm_id=:farm AND subject<>:subject'), {'farm': settings.farm_id, 'subject': subject}).scalar_one()
        with scoped_session(app, other, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM image_plans')).scalar_one() == 0
        with factory() as reopened:
            signin(reopened)
            assert reopened.get(path).json()['messages'][-1]['image'] == image


@pytest.mark.parametrize('outcome', ['clarify', 'invalid', 'unknown', 'changed_target'])
def test_planning_failures_or_questions_do_not_start_an_image(bff, monkeypatch, outcome):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    renders = []
    fixture_images(monkeypatch, renders)
    image_id = None
    owner = None

    def stream(*args, **kwargs):
        if outcome == 'unknown':
            raise ProviderError('Fixture lost planner receipt', uncertain=True)
        if outcome == 'changed_target':
            with scoped_session(app, owner, settings.farm_id) as db:
                db.execute(text('UPDATE inference_targets SET revision=revision+1 WHERE id=:id'), {'id': image_id})
        value = {'action': 'clarify', 'question': 'What would you like in the picture?'} if outcome == 'clarify' else {'action': 'generate', 'prompt': 'A blue Jeep'}
        if outcome == 'invalid':
            value['url'] = 'http://model-chosen-server'
        yield 'text', json.dumps(value)
        yield 'done', 'stop'

    monkeypatch.setattr(image_planning, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        image_id = image_target(admin, ah)
        signin(user)
        owner = user.get('/api/v1/session').json()['id']
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=headers, json={}).json()['id']
        turn(user, headers, path, 'Make an image of that')
        result = wait_finished(user, path)
        assert len(renders) == 1
        assert result['runs'][-1]['status'] == ('completed' if outcome == 'clarify' else 'interrupted' if outcome == 'unknown' else 'failed')
        assert result['messages'][-1]['image'] is None
        state = admin.get('/api/v1/providers').json()['items'][0]['execution_state']
        assert state == ('unknown' if outcome == 'unknown' else 'idle')
        if outcome == 'clarify':
            assert result['messages'][-1]['content'] == 'What would you like in the picture?'
            monkeypatch.setattr(image_planning, 'chat_stream', lambda *a, **kw: prompt_stream())
            turn(user, headers, path, 'A blue Jeep')
            assert wait_finished(user, path)['messages'][-1]['image']['request']['prompt'] == 'A blue Jeep beside a pine forest'


@pytest.mark.parametrize('action', ['steer', 'stop', 'revoke'])
def test_stopping_or_steering_during_planning_drains_before_any_image(bff, monkeypatch, action):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    renders = []
    fixture_images(monkeypatch, renders)
    entered, release = threading.Event(), threading.Event()

    def stream(*args, **kwargs):
        yield 'text', '{"action":"generate",'
        entered.set()
        assert release.wait(10)
        yield 'text', '"prompt":"A hidden old image"}'
        yield 'done', 'stop'

    monkeypatch.setattr(image_planning, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        image_target(admin, ah)
        signin(user)
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=headers, json={}).json()['id']
        try:
            first_id = turn(user, headers, path, 'Draw what we discussed')
            assert entered.wait(5)
            value = user.get(path).json()
            assert value['messages'][-1]['generation_phase'] == 'image_planning'
            assert 'action' not in value['messages'][-1]['content']
            if action == 'steer':
                note = {'id': str(uuid4()), 'content': 'Make an image of a fox instead'}
                assert user.post('/api/v1/side-notes', headers=headers, json=note).status_code == 201
                accepted = user.post(path + '/turns', headers=headers, json={'request_id': str(uuid4()), 'revision': value['revision'], 'interrupt_run_id': first_id, 'content': note['content'], 'note_id': note['id'], 'note_revision': 1})
                assert accepted.json()['status'] == 'queued'
            elif action == 'stop':
                assert user.post(path + '/stop', headers=headers).status_code == 200
            else:
                assert user.post('/api/v1/logout', headers=headers).status_code == 303
            assert len(renders) == 1
            assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'running'
        finally:
            release.set()
        if action == 'revoke':
            signin(user)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            result = user.get(path).json()
            if result['runs'][-1]['status'] != 'running' and (action != 'steer' or len(result['runs']) == 2):
                break
            time.sleep(.02)
        else:
            pytest.fail(str(result))
        assert result['runs'][0]['status'] == 'cancelled'
        assert len(renders) == (2 if action == 'steer' else 1)
        if action == 'steer':
            assert result['messages'][-1]['image']['request']['prompt'] == 'a fox instead'


@pytest.mark.parametrize('ending', ['complete', 'expire', 'stop'])
def test_handoff_is_durable_and_reconciler_does_not_mistake_it_for_lost_inference(bff, monkeypatch, ending):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    renders = []
    fixture_images(monkeypatch, renders)
    monkeypatch.setattr(image_planning, 'chat_stream', lambda *a, **kw: prompt_stream())
    entered, release = threading.Event(), threading.Event()
    original = image_planning.handoff

    def handoff(*args):
        entered.set()
        assert release.wait(10)
        original(*args)

    monkeypatch.setattr(image_planning, 'handoff', handoff)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        image_target(admin, ah)
        signin(user)
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=headers, json={}).json()['id']
        try:
            turn(user, headers, path, 'Draw that')
            assert entered.wait(5)
            value = user.get(path).json()
            assert value['runs'][-1]['status'] == 'running'
            assert value['messages'][-1]['generation_phase'] == 'image_handoff'
            assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'idle'
            if ending == 'expire':
                with scoped_session(app, user.get('/api/v1/session').json()['id'], settings.farm_id) as db:
                    db.execute(text("UPDATE messages SET phase_changed_at=now()-interval '61 seconds' WHERE id=:id"), {'id': value['messages'][-1]['id']})
                assert user.get(path).json()['runs'][-1]['status'] == 'interrupted'
                assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'idle'
            if ending == 'stop':
                assert user.post(path + '/stop', headers=headers).status_code == 200
        finally:
            release.set()
        assert wait_finished(user, path)['runs'][-1]['status'] == {'complete': 'completed', 'expire': 'interrupted', 'stop': 'cancelled'}[ending]
        assert len(renders) == (2 if ending == 'complete' else 1)


def test_channel_planning_uses_only_channel_context_and_cancels_when_requester_leaves(bff, monkeypatch):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    renders, inputs = [], []
    fixture_images(monkeypatch, renders)
    entered, release = threading.Event(), threading.Event()

    def stream(*args, **kwargs):
        inputs.append(json.loads(args[3][-1]['content']))
        if len(inputs) == 2:
            entered.set()
            assert release.wait(10)
        yield from prompt_stream('A wooden spaceship above a forest')

    monkeypatch.setattr(image_planning, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        image_target(admin, ah)
        signin(user)
        headers = csrf(user, settings.user_origin)
        assert user.post('/api/v1/side-notes', headers=headers, json={'id': str(uuid4()), 'content': 'PRIVATE CANARY NOT CHANNEL CONTEXT'}).status_code == 201
        path = '/api/v1/channels/' + user.post('/api/v1/channels', headers=headers, json={'name': 'Planning workshop'}).json()['id']
        assert user.post(path + '/messages', headers=headers, json={'request_id': str(uuid4()), 'content': 'A wooden spaceship above a forest would be nice.'}).status_code == 201
        assert user.post(path + '/messages', headers=headers, json={'request_id': str(uuid4()), 'content': '@hearth draw what we discussed'}).status_code == 201
        first = channel_finished(user, path)
        assert first['messages'][-1]['image']['planning_model'] == 'fixture'
        assert 'PRIVATE CANARY' not in json.dumps(inputs)
        assert 'wooden spaceship' in json.dumps(inputs[0])
        try:
            assert user.post(path + '/messages', headers=headers, json={'request_id': str(uuid4()), 'content': '@hearth make it blue instead'}).status_code == 201
            assert entered.wait(5)
            assert user.post(path + '/leave', headers=headers).status_code == 200
            assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'running'
        finally:
            release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and admin.get('/api/v1/providers').json()['items'][0]['execution_state'] != 'idle':
            time.sleep(.02)
        assert len(renders) == 2  # Probe and only the first authorized image.
        assert user.post(path + '/join', headers=headers).status_code == 200
        assert user.get(path).json()['messages'][-1]['status'] == 'cancelled'


@pytest.mark.skipif(not (os.environ.get('HEARTH_LIVE_IMAGE_PROVIDER') and os.environ.get('HEARTH_LIVE_CHAT_MODEL')), reason='Real text planning and image GPU work require explicit opt-in.')
def test_live_contextual_image_and_variation_with_local_models(bff):
    factory, settings, _, migration, _ = bff
    model = os.environ['HEARTH_LIVE_CHAT_MODEL']
    key = Path('.hearth/image-provider/controller.key').read_text(encoding='utf-8').strip()
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah, model)
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Live planning image fixture', 'base_url': 'http://127.0.0.1:1235', 'model_id': MODEL, 'api_key': key, 'protocol': 'hearth.image.v1', 'local_only': True}).json()
        assert admin.post('/api/v1/providers/' + target['id'] + '/probe', headers=ah, json={'revision': 1}).json()['state'] == 'ready'
        signin(user)
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=headers, json={}).json()['id']
        turn(user, headers, path, 'Remember a red Jeep parked beside a pine forest at sunset. Just briefly acknowledge this description for now.')
        initial = wait_finished(user, path, 90)
        assert initial['runs'][-1]['status'] == 'completed', initial
        records = []
        output = Path('evidence/images/2026-09-13/contextual-planning')
        output.mkdir(parents=True, exist_ok=True)
        for content, name in [('Please draw what we just discussed', 'red-jeep'), ('Make it blue instead', 'blue-jeep')]:
            job_id = turn(user, headers, path, content)
            result = wait_finished(user, path, 180)
            assert result['runs'][-1]['status'] == 'completed', result['runs'][-1]
            image = result['messages'][-1]['image']
            assert image is not None, result
            assert 'jeep' in image['request']['prompt'].lower(), image
            assert ('blue' if name == 'blue-jeep' else 'red') in image['request']['prompt'].lower(), image
            artifact = user.get('/api/v1/conversation-images/' + job_id + '/image').content
            (output / (name + '.png')).write_bytes(artifact)
            records.append({'request': content, 'image': image})
            if name == 'red-jeep':
                turn(user, headers, path, 'Thank you')
                assert wait_finished(user, path, 90)['runs'][-1]['status'] == 'completed'
        assert records[1]['image']['source_image_id'] == records[0]['image']['request']['id']
        assert records[1]['image']['variation'] is True
        with factory() as reopened:
            signin(reopened)
            assert reopened.get(path).json()['messages'][-1]['image'] == records[-1]['image']
        room = '/api/v1/channels/' + user.post('/api/v1/channels', headers=headers, json={'name': 'Live contextual images'}).json()['id']
        assert user.post(room + '/messages', headers=headers, json={'request_id': str(uuid4()), 'content': 'A tiny wooden spaceship floating above a pine forest at sunset, storybook illustration.'}).status_code == 201
        channel_job = str(uuid4())
        assert user.post(room + '/messages', headers=headers, json={'request_id': channel_job, 'content': '@hearth draw what we just discussed'}).status_code == 201
        channel = channel_finished(user, room, 180)
        channel_image = channel['messages'][-1]['image']
        assert channel_image is not None and channel_image['status'] == 'completed', channel
        assert 'spaceship' in channel_image['request']['prompt'].lower()
        assert 'jeep' not in channel_image['request']['prompt'].lower()
        (output / 'channel.png').write_bytes(user.get('/api/v1/conversation-images/' + channel_job + '/image').content)
        (output / 'live-planning.json').write_text(json.dumps({'scope': 'Real LM Studio planning and SDXL generation through private and channel BFF APIs and restricted PostgreSQL. Explicit OIDC fixtures in a disposable farm; no actual user chats modified.', 'models': [model, MODEL], 'records': records, 'channel_image': channel_image, 'acknowledgement_preserves_focus': True, 'fresh_session_restored': True, 'pixel_editing': False}, indent=2), encoding='utf-8')
