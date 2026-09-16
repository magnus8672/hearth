"""Client compatibility, alias routing, caller-owned tools and key isolation."""
import json
import threading
from uuid import uuid4

import pytest
from hearth import client_api
from hearth.database import scoped_session
from sqlalchemy import text

from tests.integration.test_chat import configure, csrf, promote, setup
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


def key(user, settings, **overrides):
    response = user.post('/api/v1/client-keys', headers=csrf(user, settings.user_origin), json={'name': 'Fixture client', 'capabilities': ['chat.general', 'code.implement'], 'allow_tools': True, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def prepared(bff, monkeypatch, admin, user):
    _, settings, app, migration, _ = setup(bff, monkeypatch)
    signin(admin)
    promote(admin, migration, settings)
    target = configure(admin, csrf(admin, settings.admin_origin))
    signin(user)
    owner = user.get('/api/v1/session').json()['id']
    with scoped_session(app, owner, settings.farm_id) as db:
        db.execute(text("UPDATE inference_targets SET features='[\"chat\",\"streaming\",\"tools\"]' WHERE id=:id"), {'id': target})
        db.execute(text("INSERT INTO capability_bindings(farm_id,capability_id,target_id) VALUES(:farm,'code.implement',:target)"), {'farm': settings.farm_id, 'target': target})
    return settings, app, target, owner


def test_models_are_authorized_aliases_and_streams_preserve_local_tool_roundtrip(bff, monkeypatch):
    factory, settings, app, migration, subject = bff
    with factory('admin') as admin, factory() as user:
        settings, app, target, owner = prepared(bff, monkeypatch, admin, user)
        saved = key(user, settings)
        auth = {'Authorization': 'Bearer '+saved['key']}
        assert user.get('/v1/models').status_code == 401  # browser cookie is not a client credential
        assert [row['id'] for row in user.get('/v1/models', headers=auth).json()['data']] == ['auto', 'chat.general', 'code.implement']
        assert admin.get('/v1/models', headers=auth).status_code == 404
        assert user.get('/v1/models', headers=auth | {'Origin': 'https://evil.invalid'}).status_code == 403
        calls = []
        function = {'type': 'function', 'function': {'name': 'read_local_file', 'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']}}}
        requested = {'id': 'call_1', 'type': 'function', 'function': {'name': 'read_local_file', 'arguments': '{"path":"example.py"}'}}
        def stream(base, credential, model, messages, config, **kwargs):
            calls.append((messages, kwargs, credential))
            if messages[-1]['role'] == 'tool':
                yield 'text', 'The supplied file contains a function.'
                yield 'done', 'stop'
            else:
                yield 'reasoning', 'I need the requested source.'
                yield 'tool_calls', [requested]
                yield 'usage', {'prompt_tokens': 10, 'completion_tokens': 12, 'total_tokens': 22}
                yield 'done', 'tool_calls'
        monkeypatch.setattr(client_api, 'chat_stream', stream)
        payload = {'model': 'auto', 'messages': [{'role': 'system', 'content': 'Use local tools when necessary.'}, {'role': 'user', 'content': 'Write a python script for my project.'}], 'tools': [function], 'stream': True, 'stream_options': {'include_usage': True}, 'reasoning_effort': 'medium'}
        response = user.post('/v1/chat/completions', json=payload, headers=auth)
        assert response.status_code == 200, response.text
        assert response.headers['x-hearth-capability'] == 'code.implement'
        assert response.headers['x-hearth-model'] == 'fixture'
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: {')]
        assert events[-2]['choices'][0]['finish_reason'] == 'tool_calls'
        assert events[-1]['usage']['total_tokens'] == 22
        assert response.text.endswith('data: [DONE]\n\n')
        assert calls[0][1]['tools'] == [function] and calls[0][2] != saved['key']
        assert calls[0][1]['parameters']['reasoning_effort'] == 'medium'
        assert calls[0][1]['caller_owned_tools'] is True
        with scoped_session(app, owner, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM tool_invocations')).scalar_one() == 0
            assert db.execute(text('SELECT count(*) FROM messages')).scalar_one() == 0
        payload['stream'] = False
        payload['messages'] += [{'role': 'assistant', 'content': None, 'tool_calls': [requested]}, {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'def example(): pass'}]
        followup = user.post('/v1/chat/completions', json=payload, headers=auth)
        assert followup.status_code == 200 and followup.json()['choices'][0]['message']['content'].startswith('The supplied file')
        assert followup.json()['model'] == 'auto'
        assert user.post('/v1/chat/completions', headers=auth, json=payload | {'model': 'fixture'}).status_code == 422
        user.delete('/api/v1/client-keys/'+saved['id'], headers=csrf(user, settings.user_origin))
        assert user.get('/v1/models', headers=auth).status_code == 401
        assert 'key' not in user.get('/api/v1/client-keys').json()['items'][0]


def test_scopes_unverified_tools_busy_pool_and_malformed_tool_history(bff, monkeypatch):
    factory, settings, app, migration, subject = bff
    with factory('admin') as admin, factory() as user:
        settings, app, target, owner = prepared(bff, monkeypatch, admin, user)
        saved = key(user, settings, capabilities=['chat.general'], allow_tools=False)
        auth = {'Authorization': 'Bearer '+saved['key']}
        payload = {'model': 'code.implement', 'messages': [{'role': 'user', 'content': 'hello'}]}
        assert user.post('/v1/chat/completions', json=payload, headers=auth).status_code == 403
        payload['model'] = 'chat.general'
        tools = [{'type': 'function', 'function': {'name': 'test', 'parameters': {'type': 'object'}}}]
        assert user.post('/v1/chat/completions', json=payload | {'tools': tools}, headers=auth).status_code == 403
        other = key(user, settings)
        auth = {'Authorization': 'Bearer '+other['key']}
        with scoped_session(app, owner, settings.farm_id) as db:
            db.execute(text("UPDATE inference_targets SET features='[\"chat\",\"streaming\"]' WHERE id=:id"), {'id': target})
        assert user.post('/v1/chat/completions', json=payload | {'tools': tools}, headers=auth).status_code == 503
        assert user.post('/v1/chat/completions', json=payload | {'messages': payload['messages']+[{'role': 'tool', 'tool_call_id': 'orphan', 'content': 'fake'}]}, headers=auth).status_code == 422
        assert user.post('/v1/chat/completions', json=payload | {'tools': [{'type': 'function', 'function': {'name': 'test', 'parameters': {'type': 'object', '$ref': 'https://evil.invalid/schema'}}}]}, headers=auth).status_code == 422
        with scoped_session(app, owner, settings.farm_id) as db:
            db.execute(text("UPDATE provider_pools SET active_run_id=:id,execution_state='running'"), {'id': uuid4()})
        assert user.post('/v1/chat/completions', json=payload, headers=auth).status_code == 503


def test_revoke_during_client_generation_drains_without_publishing_or_replaying(bff, monkeypatch):
    factory, settings, app, migration, subject = bff
    started, resume = threading.Event(), threading.Event()
    with factory('admin') as admin, factory() as user:
        settings, app, target, owner = prepared(bff, monkeypatch, admin, user)
        saved = key(user, settings)
        def stream(*args, **kwargs):
            started.set()
            assert resume.wait(5)
            yield 'text', 'secret after revocation'
            yield 'done', 'stop'
        monkeypatch.setattr(client_api, 'chat_stream', stream)
        response = []
        thread = threading.Thread(target=lambda: response.append(user.post('/v1/chat/completions', headers={'Authorization': 'Bearer '+saved['key']}, json={'model': 'chat.general', 'messages': [{'role': 'user', 'content': 'hello'}]})))
        thread.start()
        assert started.wait(5)
        with scoped_session(app, owner, settings.farm_id) as db:
            db.execute(text('UPDATE client_keys SET revoked_at=now() WHERE id=:id'), {'id': saved['id']})
        resume.set()
        thread.join(5)
        assert response and response[0].status_code == 502
        assert 'secret after revocation' not in response[0].text
        with scoped_session(app, owner, settings.farm_id) as db:
            assert db.execute(text('SELECT active_run_id FROM provider_pools')).scalar_one() is None


@pytest.mark.parametrize('streaming', [False, True])
def test_failed_completion_receipt_terminates_with_an_error(bff, monkeypatch, streaming):
    factory, settings, app, migration, subject = bff
    with factory('admin') as admin, factory() as user:
        settings, app, target, owner = prepared(bff, monkeypatch, admin, user)
        saved = key(user, settings)
        monkeypatch.setattr(client_api, 'chat_stream', lambda *a, **kw: iter([('text', 'answer'), ('done', 'stop')]))
        def unavailable(*args):
            raise RuntimeError('fixture database failure')
        monkeypatch.setattr(client_api, 'record_failure', unavailable)
        response = user.post('/v1/chat/completions', headers={'Authorization': 'Bearer '+saved['key']}, json={'model': 'chat.general', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': streaming})
        assert response.status_code == (200 if streaming else 502)
        assert 'receipt could not be saved' in response.text
        assert '[DONE]' not in response.text


@pytest.mark.parametrize('streaming', [False, True])
def test_context_rejection_releases_pool_and_preserves_qualification(bff, monkeypatch, streaming):
    factory, settings, app, migration, subject = bff
    with factory('admin') as admin, factory() as user:
        settings, app, target, owner = prepared(bff, monkeypatch, admin, user)
        saved = key(user, settings)
        def too_large(*args, **kwargs):
            raise client_api.ContextLimitError(28074, 8192)
        monkeypatch.setattr(client_api, 'chat_stream', too_large)
        response = user.post('/v1/chat/completions', headers={'Authorization': 'Bearer '+saved['key']}, json={'model': 'chat.general', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': streaming})
        assert response.status_code == (200 if streaming else 400)
        assert 'context_length_exceeded' in response.text and '28,074' in response.text
        assert '[DONE]' not in response.text
        with scoped_session(app, owner, settings.farm_id) as db:
            assert db.execute(text('SELECT state FROM inference_targets')).scalar_one() == 'ready'
            assert db.execute(text('SELECT active_run_id FROM provider_pools')).scalar_one() is None
