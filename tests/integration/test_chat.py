import json
import os
import threading
import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hearth import chat, providers
from hearth.database import scoped_session
from hearth.inference import ProviderError
from sqlalchemy import text

from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


def setup(bff, monkeypatch):
    factory, settings, app, migration, subject = bff
    monkeypatch.setattr(providers, 'list_models', lambda *a: ['fixture', 'other'])
    monkeypatch.setattr(providers, 'chat_stream', lambda *a, **kw: iter([('text', 'probe'), ('done', 'stop')]))
    return factory, settings, app, migration, subject


def csrf(browser, origin):
    return {'Origin': origin, 'X-Hearth-CSRF': browser.get('/api/v1/session').json()['csrf_token']}


def promote(browser, migration, settings):
    user = browser.get('/api/v1/session').json()['id']
    with migration.begin() as db:
        db.execute(text("INSERT INTO role_grants(id,user_id,farm_id,role) VALUES(gen_random_uuid(),:id,:farm,'Owner') ON CONFLICT DO NOTHING"), {'id': user, 'farm': settings.farm_id})


def configure(admin, headers, model='fixture'):
    created = admin.post('/api/v1/providers', headers=headers, json={'name': 'Fixture server', 'base_url': 'http://127.0.0.1:1234', 'model_id': model, 'local_only': True})
    assert created.status_code == 201, created.text
    target = created.json()
    result = admin.post(f"/api/v1/providers/{target['id']}/probe", headers=headers, json={'revision': target['revision']})
    assert result.status_code == 200, result.text
    assert result.json()['features'] == ['chat', 'streaming']
    assert result.json()['admin_agent_ready'] is False
    return target['id']


def wait_finished(browser, path, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = browser.get(path).json()
        if value['runs'] and value['runs'][-1]['status'] != 'running':
            return value
        time.sleep(.02)
    pytest.fail('Fixture stream did not finish')


def test_admin_boundary_private_chat_idempotency_and_draft_separation(bff, monkeypatch):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    calls = []

    def stream(*args, **kwargs):
        calls.append(args[3])
        yield 'text', 'A private answer.'
        yield 'done', 'stop'
    monkeypatch.setattr(chat, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        assert admin.get('/api/v1/providers').status_code == 403
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = configure(admin, ah)
        assert admin.post(f'/api/v1/providers/{target}/probe', json={'revision': 2}).status_code == 403
        assert admin.post(f'/api/v1/providers/{uuid4()}/probe', json={'revision': 2}, headers=ah).status_code == 404
        signin(user)
        uh = csrf(user, settings.user_origin)
        assert user.get('/api/v1/providers').status_code == 403
        response = user.post('/api/v1/chats', json={}, headers=uh)
        assert response.status_code == 201
        path = '/api/v1/chats/' + response.json()['id']
        turn = {'request_id': str(uuid4()), 'revision': 1, 'content': 'Private prompt'}
        assert user.post(path + '/turns', json=turn).status_code == 403
        assert user.post(path + '/turns', json=turn, headers=uh).status_code == 202
        result = wait_finished(user, path)
        assert result['messages'][-1]['content'] == 'A private answer.'
        assert result['runs'][-1]['status'] == 'completed'
        assert user.post(path + '/turns', json=turn, headers=uh).status_code == 202
        assert len(calls) == 1
        assert user.post(path + '/turns', json=turn | {'content': 'different'}, headers=uh).status_code == 409
        assert user.get('/api/v1/workspace').json()['drafts'] == []
        draft_path = '/api/v1/drafts/' + response.json()['id']
        assert user.get(draft_path).status_code == 404
        assert user.put(draft_path, json={'title': 'overwrite', 'content': 'bad', 'revision': 2}, headers=uh).status_code == 404
        assert user.delete(draft_path, headers=uh).status_code == 404
        # Farm Owner has no SQL access to another principal's personal content.
        other_owner = migration.connect()
        try:
            owner = other_owner.execute(text("SELECT id FROM users WHERE farm_id=:farm AND subject<>:subject"), {'farm': settings.farm_id, 'subject': subject}).scalar_one()
        finally:
            other_owner.close()
        with scoped_session(app, owner, settings.farm_id) as db:
            for table in ('conversations', 'messages', 'chat_runs'):
                assert db.execute(text(f'SELECT count(*) FROM {table}')).scalar_one() == 0
        assert user.get('/api/v1/chats/' + str(uuid4())).status_code == 404
        assert user.post(path + '/turns', json={'request_id': str(uuid4()), 'revision': 2, 'content': 'Follow up'}, headers=uh).status_code == 202
        wait_finished(user, path)
        assert [item['role'] for item in calls[-1]] == ['system', 'user', 'assistant', 'user']


@pytest.mark.parametrize('ending', ['cancel', 'failure', 'revocation'])
def test_shared_admission_cancellation_revocation_and_uncertain_execution(bff, monkeypatch, ending):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    entered, finish = threading.Event(), threading.Event()

    def stream(*args, **kwargs):
        yield 'text', 'Partial answer'
        entered.set()
        assert finish.wait(10)
        if ending == 'failure':
            raise ProviderError('Connection interrupted.', uncertain=True)
        yield 'text', ' must not appear after stop'
        yield 'done', 'stop'
    monkeypatch.setattr(chat, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        configure(admin, ah, 'other')
        signin(user)
        uh = csrf(user, settings.user_origin)
        chat_id = user.post('/api/v1/chats', json={}, headers=uh).json()['id']
        path = '/api/v1/chats/' + chat_id
        turn = {'request_id': str(uuid4()), 'revision': 1, 'content': 'Start'}
        try:
            assert user.post(path + '/turns', json=turn, headers=uh).status_code == 202
            assert entered.wait(5)
            assert user.get(path).json()['messages'][-1]['content'] == 'Partial answer'
            another = user.post('/api/v1/chats', json={}, headers=uh).json()['id']
            assert user.post('/api/v1/chats/' + another + '/turns', json=turn | {'request_id': str(uuid4())}, headers=uh).status_code == 409
            if ending == 'cancel':
                assert user.post(path + '/stop', headers=uh).status_code == 200
                assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'running'
            if ending == 'revocation':
                with migration.begin() as db:
                    db.execute(text('DELETE FROM browser_sessions WHERE farm_id=:farm AND audience=\'user\''), {'farm': settings.farm_id})
        finally:
            finish.set()
        if ending == 'revocation':
            assert user.get(path).status_code == 401
            signin(user)
        result = wait_finished(user, path)
        assert result['runs'][-1]['status'] == ('interrupted' if ending == 'failure' else 'cancelled')
        assert result['messages'][-1]['content'] == 'Partial answer'
        items = admin.get('/api/v1/providers').json()['items']
        pool = items[0]
        assert pool['execution_state'] == ('unknown' if ending == 'failure' else 'idle')
        if ending == 'failure':
            clear_path = '/api/v1/provider-pools/' + pool['resource_pool_id'] + '/clear'
            assert admin.post(clear_path, json={'expected_run_id': str(uuid4()), 'confirm_backend_idle': True}, headers=ah).status_code == 409
            assert admin.post(clear_path, json={'expected_run_id': pool['active_run_id'], 'confirm_backend_idle': False}, headers=ah).status_code == 400
            assert admin.post(clear_path, json={'expected_run_id': pool['active_run_id'], 'confirm_backend_idle': True}, headers=ah).status_code == 200


@pytest.mark.parametrize('ending', ['dispatch', 'cancel', 'revoke'])
def test_private_notes_and_durable_steering_wait_for_backend(bff, monkeypatch, ending):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    entered, finish = threading.Event(), threading.Event()
    contexts = []

    def stream(*args, **kwargs):
        contexts.append(args[3])
        if len(contexts) == 1:
            yield 'text', 'Incomplete thought'
            entered.set()
            assert finish.wait(15)
            yield 'text', ' hidden after steering'
        else:
            yield 'text', 'A new direction'
        yield 'done', 'stop'

    monkeypatch.setattr(chat, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        configure(admin, csrf(admin, settings.admin_origin))
        signin(user)
        uh = csrf(user, settings.user_origin)
        assert admin.get('/api/v1/side-notes').status_code == 403
        note = {'id': str(uuid4()), 'content': 'Make it shorter'}
        assert user.post('/api/v1/side-notes', json=note).status_code == 403
        assert user.post('/api/v1/side-notes', headers=uh, json=note).status_code == 201
        assert user.post('/api/v1/side-notes', headers=uh, json=note).status_code == 201
        assert len(user.get('/api/v1/side-notes').json()['items']) == 1
        with migration.connect() as db:
            other = db.execute(text('SELECT id FROM users WHERE farm_id=:farm AND subject<>:subject'), {'farm': settings.farm_id, 'subject': subject}).scalar_one()
        with scoped_session(app, other, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM side_notes')).scalar_one() == 0
        saved = user.post('/api/v1/chats', json={}, headers=uh).json()
        path = '/api/v1/chats/' + saved['id']
        first = {'request_id': str(uuid4()), 'revision': 1, 'content': 'Tell me a story'}
        try:
            assert user.post(path + '/turns', json=first, headers=uh).status_code == 202
            assert entered.wait(5)
            assert len(contexts) == 1 and contexts[0][0]['role'] == 'system'
            assert contexts[0][1:] == [{'role': 'user', 'content': 'Tell me a story'}]
            value = user.get(path).json()
            steer = {'request_id': str(uuid4()), 'revision': value['revision'], 'content': note['content'], 'note_id': note['id'], 'note_revision': 1, 'interrupt_run_id': first['request_id']}
            assert user.post(path + '/turns', json=steer | {'note_revision': 2}, headers=uh).status_code == 409
            assert len(user.get('/api/v1/side-notes').json()['items']) == 1
            assert user.post(path + '/turns', json=steer, headers=uh).json()['status'] == 'queued'
            assert user.post(path + '/turns', json=steer, headers=uh).json()['status'] == 'queued'
            assert user.get('/api/v1/side-notes').json()['items'] == []
            value = user.get(path).json()
            assert value['runs'][-1]['cancel_requested'] is True
            assert value['pending'][0]['content'] == note['content']
            assert len(contexts) == 1
            with scoped_session(app, other, settings.farm_id) as db:
                assert db.execute(text('SELECT count(*) FROM chat_requests')).scalar_one() == 0
            if ending == 'cancel':
                assert user.post(path + '/pending/' + steer['request_id'] + '/cancel', headers=uh).status_code == 200
            elif ending == 'revoke':
                with migration.begin() as db:
                    db.execute(text("DELETE FROM browser_sessions WHERE farm_id=:farm AND audience='user'"), {'farm': settings.farm_id})
        finally:
            finish.set()
        if ending == 'revoke':
            signin(user)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            value = user.get(path).json()
            if ending == 'dispatch' and len(value['runs']) == 2 and value['runs'][-1]['status'] == 'completed':
                break
            if ending == 'cancel' and value['runs'][0]['status'] == 'cancelled':
                break
            if ending == 'revoke' and value['pending'] and value['pending'][0]['state'] == 'blocked':
                break
            time.sleep(.02)
        else:
            pytest.fail('Queued steering did not settle')
        assert value['messages'][1]['content'] == 'Incomplete thought'
        assert value['runs'][0]['status'] == 'cancelled'
        if ending == 'dispatch':
            assert len(contexts) == 2
            assert contexts[1][0]['role'] == 'system'
            assert contexts[1][1:] == [{'role': 'user', 'content': 'Tell me a story'}, {'role': 'user', 'content': 'Make it shorter'}]
            assert [m['role'] for m in value['messages']] == ['user', 'assistant', 'user', 'assistant']
            assert value['messages'][-1]['content'] == 'A new direction'
            assert value['pending'] == []
        else:
            assert len(contexts) == 1
        if ending == 'cancel':
            assert user.post(path + '/turns', json=steer, headers=uh).json()['status'] == 'cancelled'


def test_note_dismiss_revision_and_send_failure_preserves_note(bff, monkeypatch):
    factory, settings, _, _, _ = setup(bff, monkeypatch)
    with factory() as user:
        signin(user)
        uh = csrf(user, settings.user_origin)
        note = {'id': str(uuid4()), 'content': 'A thought for later'}
        assert user.post('/api/v1/side-notes', json=note, headers=uh).status_code == 201
        path = '/api/v1/chats/' + user.post('/api/v1/chats', json={}, headers=uh).json()['id']
        # No qualified provider: admission fails without consuming the note.
        turn = {'request_id': str(uuid4()), 'revision': 1, 'content': note['content'], 'note_id': note['id'], 'note_revision': 1}
        assert user.post(path + '/turns', json=turn, headers=uh).status_code == 409
        assert len(user.get('/api/v1/side-notes').json()['items']) == 1
        dismiss = '/api/v1/side-notes/' + note['id'] + '/dismiss'
        assert user.post(dismiss, json={'revision': 2}, headers=uh).status_code == 409
        assert user.post(dismiss, json={'revision': 1}, headers=uh).status_code == 200
        assert user.post(dismiss, json={'revision': 1}, headers=uh).status_code == 200
        assert user.get('/api/v1/side-notes').json()['items'] == []


def test_late_release_cannot_clear_new_receipt(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    with factory('admin') as admin:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        pool = admin.get('/api/v1/providers').json()['items'][0]
        principal_id = UUID(admin.get('/api/v1/session').json()['id'])
        newer = uuid4()
        with scoped_session(app, principal_id, settings.farm_id) as db:
            db.execute(text("UPDATE provider_pools SET active_run_id=:run,execution_state='running',lease_until=now()+interval '1 minute' WHERE id=:pool"), {'run': newer, 'pool': pool['resource_pool_id']})
            providers.release_pool(db, pool['resource_pool_id'], uuid4())
        assert admin.get('/api/v1/providers').json()['items'][0]['active_run_id'] == str(newer)


def test_lost_execution_is_durable_unknown_and_is_never_automatically_replayed(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        signin(user)
        uh = csrf(user, settings.user_origin)
        dispatched = []
        monkeypatch.setattr(user.app.state.inference_executor, 'submit', lambda *args: dispatched.append(args))
        chat_id = user.post('/api/v1/chats', json={}, headers=uh).json()['id']
        path = '/api/v1/chats/' + chat_id
        turn = {'request_id': str(uuid4()), 'revision': 1, 'content': 'Do not replay this prompt'}
        assert user.post(path + '/turns', json=turn, headers=uh).status_code == 202
        owner = UUID(user.get('/api/v1/session').json()['id'])
        with scoped_session(app, owner, settings.farm_id) as db:
            db.execute(text("UPDATE provider_pools SET lease_until=now()-interval '1 second'"))
        value = user.get(path).json()
        assert value['runs'][0]['status'] == 'interrupted'
        assert user.post(path + '/turns', json=turn, headers=uh).json()['status'] == 'interrupted'
        assert len(dispatched) == 1
        assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'unknown'


@pytest.mark.skipif(not os.environ.get('HEARTH_LIVE_CHAT_MODEL'), reason='Explicit existing local model selection required; no inference during ordinary tests.')
def test_live_selected_model_stream_persistence_and_followup(bff, monkeypatch):
    factory, settings, _, migration, _ = bff
    model = os.environ['HEARTH_LIVE_CHAT_MODEL']
    url = os.environ.get('HEARTH_LIVE_CHAT_URL', 'http://127.0.0.1:1234')
    chunks = []
    real_stream = chat.chat_stream

    def observed_stream(*args, **kwargs):
        for kind, value in real_stream(*args, **kwargs):
            if kind == 'text':
                chunks.append(len(value))
            yield kind, value
    monkeypatch.setattr(chat, 'chat_stream', observed_stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = admin.post('/api/v1/providers', json={'name': 'Explicit live model fixture', 'base_url': url, 'model_id': model, 'local_only': True}, headers=ah)
        assert target.status_code == 201, target.text
        probe = admin.post('/api/v1/providers/' + target.json()['id'] + '/probe', json={'revision': 1}, headers=ah)
        assert probe.status_code == 200 and probe.json()['state'] == 'ready', probe.text
        signin(user)
        uh = csrf(user, settings.user_origin)
        saved = user.post('/api/v1/chats', json={}, headers=uh).json()
        path = '/api/v1/chats/' + saved['id']
        first = user.post(path + '/turns', json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Remember this code word: ember. Reply with a brief acknowledgement.'}, headers=uh)
        assert first.status_code == 202, first.text
        initial = wait_finished(user, path, 60)
        assert initial['runs'][-1]['status'] == 'completed', initial['runs']
        followup = user.post(path + '/turns', json={'request_id': str(uuid4()), 'revision': initial['revision'], 'content': 'What code word did I give you? Answer briefly.'}, headers=uh)
        assert followup.status_code == 202, followup.text
        complete = wait_finished(user, path, 60)
        assert complete['runs'][-1]['status'] == 'completed', complete['runs']
        assert 'ember' in complete['messages'][-1]['content'].lower()
        assert '<|' not in complete['messages'][-1]['content']
        # A fresh BFF application/session reads the same committed content.
        with factory() as reopened:
            signin(reopened)
            restored = reopened.get(path).json()
            assert restored['messages'] == complete['messages']
        assert len(chunks) > 1
        output = Path('evidence/inference/2026-09-13')
        output.mkdir(parents=True, exist_ok=True)
        (output / 'live-chat.json').write_text(json.dumps({
            'scope': 'Real LM Studio HTTP/SSE and PostgreSQL through both BFF APIs; explicit OIDC fixtures in a disposable farm. No real user account or personal content used.',
            'model': model, 'url': url, 'probe': probe.json()['features'], 'completed_turns': 2,
            'answer_text_chunks': len(chunks), 'followup_answer': complete['messages'][-1]['content'],
            'fresh_session_restores_messages': True, 'tools_enabled': False, 'paid_inference': False
        }, indent=2), encoding='utf-8')
