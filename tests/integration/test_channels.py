import json
import threading
import time
from uuid import uuid4

import pytest
from hearth import channels, identity
from hearth.database import scoped_session
from sqlalchemy import text

from tests.integration.test_chat import configure, csrf, promote, setup
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


@pytest.mark.parametrize('content,expected', [('hello', False), ('mail@hearth.example', False), ('@hearth.example', False), ('@hearthling', False), ('@hearth hi', True), ('Hey @HEARTH, thoughts?', True), ('Thank you @hearth.', True)])
def test_explicit_mention_boundaries(content, expected):
    assert bool(channels.MENTION.search(content)) is expected


def test_joined_channels_use_shared_context_only_on_a_new_mention(bff, monkeypatch):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    contexts = []

    def stream(*args, **kwargs):
        contexts.append(args[3])
        yield 'text', 'A shared answer'
        yield 'done', 'stop'

    monkeypatch.setattr(channels, 'chat_stream', stream)
    with factory('admin') as admin, factory() as first, factory() as second:
        signin(admin)
        promote(admin, migration, settings)
        configure(admin, csrf(admin, settings.admin_origin))
        signin(first)
        h1 = csrf(first, settings.user_origin)
        assert first.post('/api/v1/channels', json={'name': 'Kitchen'}).status_code == 403
        saved = first.post('/api/v1/channels', headers=h1, json={'name': 'Kitchen'}).json()
        path = '/api/v1/channels/' + saved['id']
        one = {'request_id': str(uuid4()), 'content': 'Let us design a little spaceship.'}
        assert first.post(path + '/messages', headers=h1, json=one).status_code == 201
        assert first.post(path + '/messages', headers=h1, json=one).status_code == 201
        assert contexts == []
        assert admin.get(path).status_code == 403
        second_subject = str(uuid4())
        monkeypatch.setattr(identity, 'verify_id_token', lambda *args: {'sub': second_subject, 'name': 'Another member'})
        monkeypatch.setattr(identity, 'token_request', lambda config, endpoint, data:
            {'active': True, 'sub': subject if data.get('token') == 'EXPLICIT PROVIDER FIXTURE' else second_subject, 'iss': config.issuer}
            if endpoint == 'token/introspect' else {'id_token': 'FIXTURE', 'access_token': 'SECOND', 'refresh_token': 'FIXTURE', 'expires_in': 300})
        signin(second)
        h2 = csrf(second, settings.user_origin)
        assert second.get('/api/v1/channels').json()['items'][0]['joined'] is False
        assert second.get(path).status_code == 404
        second_id = second.get('/api/v1/session').json()['id']
        with scoped_session(app, second_id, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM channel_messages')).scalar_one() == 0
        assert second.post(path + '/messages', headers=h2, json={'request_id': str(uuid4()), 'content': 'Cannot post yet'}).status_code == 404
        assert second.post(path + '/join', headers=h2).status_code == 200
        assert second.get(path).json()['messages'][0]['content'] == one['content']
        ask = {'request_id': str(uuid4()), 'content': '@hearth suggest a name for it.'}
        assert second.post(path + '/messages', headers=h2, json=ask).status_code == 201
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = second.get(path).json()
            if result['messages'][-1]['status'] == 'completed':
                break
            time.sleep(.02)
        assert result['messages'][-1]['content'] == 'A shared answer'
        assert result['messages'][-1]['model_id'] == 'fixture'
        assert first.get(path).json()['messages'] == result['messages']
        # Reply identity is shared output, not access to another author's run.
        with scoped_session(app, first.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM channel_runs')).scalar_one() == 0
            db.execute(text("UPDATE inference_targets SET model_id='renamed-model'"))
        assert first.get(path).json()['messages'][-1]['model_id'] == 'fixture'
        assert len(contexts) == 1
        assert [json.loads(x['content'])['message'] for x in contexts[0]] == [one['content'], ask['content']]
        assert second.post(path + '/messages', headers=h2, json=ask).status_code == 201
        assert len(contexts) == 1
        assert second.post(path + '/messages', headers=h2, json={'request_id': str(uuid4()), 'content': 'Thanks!'}).status_code == 201
        assert len(contexts) == 1  # Historical mentions never retrigger.
        assert second.get('/api/v1/chats').json()['items'] == []
        assert second.post(path + '/leave', headers=h2).status_code == 200
        assert second.get(path).status_code == 404
        with scoped_session(app, second_id, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM channel_messages')).scalar_one() == 0


def test_leaving_during_response_preserves_receipt_until_backend_finishes(bff, monkeypatch):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    entered, finish = threading.Event(), threading.Event()

    def stream(*args, **kwargs):
        yield 'text', 'Partial'
        entered.set()
        assert finish.wait(10)
        yield 'text', ' must not be published'
        yield 'done', 'stop'

    monkeypatch.setattr(channels, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        configure(admin, csrf(admin, settings.admin_origin))
        signin(user)
        headers = csrf(user, settings.user_origin)
        path = '/api/v1/channels/' + user.post('/api/v1/channels', headers=headers, json={'name': 'Workshop'}).json()['id']
        try:
            assert user.post(path + '/messages', headers=headers, json={'request_id': str(uuid4()), 'content': '@hearth hello'}).status_code == 201
            assert entered.wait(5)
            assert user.post(path + '/leave', headers=headers).status_code == 200
            assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'running'
        finally:
            finish.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'idle':
                break
            time.sleep(.02)
        assert user.post(path + '/join', headers=headers).status_code == 200
        message = user.get(path).json()['messages'][-1]
        assert message['status'] == 'cancelled'
        assert message['content'] == 'Partial'
