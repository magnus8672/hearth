from uuid import uuid4

import pytest
from hearth import chat, routing
from hearth.database import scoped_session
from sqlalchemy import text

from tests.integration.test_chat import configure, csrf, promote, setup, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


def assign(admin, headers, capability, targets, revision=1):
    return admin.put('/api/v1/capability-routes/' + capability, headers=headers, json={
        'revision': revision, 'targets': [{'target_id': target, 'priority': 100-index} for index, target in enumerate(targets)]})


@pytest.mark.parametrize(('capability', 'prompt'), [
    ('reason.plan', 'Plan a weekend garden project.'),
    ('code.explain', 'Explain this function: def twice(x): return x * 2'),
    ('code.implement', 'Write a Python function to double a number.'),
    ('write.compose', 'Draft a friendly invitation.'),
    ('text.summarize', 'Summarize: The rain stopped and the sun came out.'),
    ('data.extract', 'Extract the city from: Sam lives in Boston.'),
])
def test_specialists_dispatch_through_assigned_targets_and_failure_fails_closed(bff, monkeypatch, capability, prompt):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    seen = []

    def stream(*args, **kwargs):
        seen.append((args[2], args[3]))
        yield 'text', 'Specialist fixture answer.'
        yield 'done', 'stop'
    monkeypatch.setattr(chat, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        specialist = configure(admin, ah, 'other')
        result = assign(admin, ah, capability, [specialist])
        assert result.status_code == 200, result.text
        assert result.json()['targets'][0]['ready']
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', json={}, headers=uh).json()['id']
        turn = {'request_id': str(uuid4()), 'revision': 1, 'content': prompt}
        assert user.post(path+'/turns', json=turn, headers=uh).status_code == 202
        result = wait_finished(user, path)
        assert result['runs'][0]['capability_id'] == capability
        assert seen[0][0] == 'other'
        assert seen[0][1][0]['role'] == 'system'
        assert seen[0][1][-1]['content'] == prompt
        # Changing the route of an idempotent request must never send it again.
        assert user.post(path+'/turns', json=turn | {'capability': 'chat.general'}, headers=uh).status_code == 409
        with scoped_session(app, user.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            db.execute(text("UPDATE inference_targets SET state='failed',reason='Connection failed' WHERE id=:id"), {'id': specialist})
        assert user.post(path+'/turns', json=turn | {'request_id': str(uuid4()), 'revision': 2}, headers=uh).status_code == 409
        assert len(seen) == 1


def test_route_permissions_conflicts_pending_profiles_and_explicit_disconnect(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    with factory('admin') as admin, factory() as user:
        assert admin.get('/api/v1/capability-routes').status_code == 401
        signin(admin)
        assert admin.get('/api/v1/capability-routes').status_code == 403
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = configure(admin, ah)
        assert assign(admin, {}, 'reason.plan', [target]).status_code == 403
        assert assign(admin, ah, 'reason.plan', [str(uuid4())]).status_code == 404
        assert assign(admin, ah, 'reason.plan', [target, target]).status_code == 422
        assert assign(admin, ah, 'reason.plan', [target]).status_code == 200
        assert assign(admin, ah, 'reason.plan', [], revision=1).status_code == 409
        for capability in routing.PENDING:
            result = assign(admin, ah, capability, [target])
            assert result.status_code == 200
            assert result.json()['profile']['executable'] is False
            assert result.json()['targets'][0]['ready'] is False
        signin(user)
        assert user.get('/api/v1/capability-routes').status_code == 403
        caps = {item['capability_id']: item for item in user.get('/api/v1/capabilities').json()['items']}
        assert all(caps[key]['state'] != 'ready' for key in routing.PENDING)
        for capability in ('memory.retrieve', 'memory.index'):
            assert caps[capability]['state'] == 'ready' and caps[capability]['builtin']
            assert assign(admin, ah, capability, [target]).status_code == 409
        assert caps['reason.plan']['state'] == 'ready'
        assert caps['code.implement']['output_modalities'] == ['text']
        # Explicit disconnect survives a subsequent successful provider probe.
        assert assign(admin, ah, 'chat.general', []).status_code == 200
        assert admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 2}).json()['state'] == 'ready'
        routes = admin.get('/api/v1/capability-routes').json()['items']
        assert next(item for item in routes if item['capability_id'] == 'chat.general')['targets'] == []
        # A different farm cannot observe these assignments through the app role.
        with scoped_session(app, user.get('/api/v1/session').json()['id'], uuid4()) as db:
            assert db.execute(text('SELECT count(*) FROM capability_routes')).scalar_one() == 0


def test_retarget_invalidates_evidence_preserves_bindings_and_rejects_busy_pool(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    with factory('admin') as admin:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = configure(admin, ah)
        assert assign(admin, ah, 'code.implement', [target]).status_code == 200
        payload = {'revision': 2, 'name': 'Workshop', 'base_url': 'https://192.168.1.90:1240', 'model_id': 'fixture', 'protocol': 'openai.chat.v1', 'resource_pool': 'Workshop GPU', 'local_only': True}
        with scoped_session(app, admin.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            db.execute(text("UPDATE provider_pools SET active_run_id=:id,execution_state='unknown'"), {'id': uuid4()})
        assert admin.put(f'/api/v1/providers/{target}', json=payload, headers=ah).status_code == 409
        assert assign(admin, ah, 'code.implement', [], revision=2).status_code == 409
        with scoped_session(app, admin.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            db.execute(text("UPDATE provider_pools SET active_run_id=NULL,execution_state='idle'"))
        assert admin.put(f'/api/v1/providers/{target}', json=payload | {'tls_ca_pem': 'PRIVATE KEY should never be accepted'}, headers=ah).status_code == 400
        response = admin.put(f'/api/v1/providers/{target}', json=payload, headers=ah)
        assert response.status_code == 200, response.text
        item = admin.get('/api/v1/providers').json()['items'][0]
        assert item['id'] == target and item['state'] == 'configured' and item['verified_until'] is None
        assert item['pool_name'] == 'Workshop GPU'
        assert item['base_url'] == 'https://192.168.1.90:1240/v1'
        assert admin.put(f'/api/v1/providers/{target}', json=payload, headers=ah).status_code == 409
        routes = admin.get('/api/v1/capability-routes').json()['items']
        bound = next(row for row in routes if row['capability_id'] == 'code.implement')['targets']
        assert len(bound) == 1 and bound[0]['target_id'] == target and not bound[0]['ready']


def test_ordered_routes_skip_busy_targets_but_never_retry_after_dispatch(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    from hearth.inference import ProviderError
    seen = []

    def interrupted(*args, **kwargs):
        seen.append(args[2])
        yield 'text', 'Started once'
        raise ProviderError('Test transport lost its receipt.', uncertain=True)
    monkeypatch.setattr(chat, 'chat_stream', interrupted)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        first = configure(admin, ah)
        second = configure(admin, ah, 'other')
        payload = {'revision': 2, 'name': 'Second host fixture', 'base_url': 'http://127.0.0.1:1250', 'model_id': 'other', 'resource_pool': 'Second independent GPU', 'local_only': True}
        assert admin.put(f'/api/v1/providers/{second}', headers=ah, json=payload).status_code == 200
        assert admin.post(f'/api/v1/providers/{second}/probe', headers=ah, json={'revision': 3}).json()['state'] == 'ready'
        assert assign(admin, ah, 'write.compose', [first, second]).status_code == 200
        # An admission competing with another transaction must skip its pool,
        # not deadlock while holding other candidates in a different order.
        with scoped_session(app, admin.get('/api/v1/session').json()['id'], settings.farm_id) as held:
            held.execute(text('SELECT p.id FROM provider_pools p JOIN inference_targets t ON t.resource_pool_id=p.id WHERE t.id=:id FOR UPDATE OF p'), {'id': first})
            with scoped_session(app, admin.get('/api/v1/session').json()['id'], settings.farm_id) as selecting:
                selecting.execute(text("SET LOCAL lock_timeout='1s'"))
                assert str(routing.select(selecting, 'write.compose')['id']) == second
        with scoped_session(app, admin.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            db.execute(text("UPDATE provider_pools SET active_run_id=:run,execution_state='running',lease_until=now()+interval '240 seconds' WHERE id=(SELECT resource_pool_id FROM inference_targets WHERE id=:id)"), {'run': uuid4(), 'id': first})
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', json={}, headers=uh).json()['id']
        assert user.post(path+'/turns', json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Draft an invitation.'}, headers=uh).status_code == 202
        result = wait_finished(user, path)
        assert result['runs'][0]['status'] == 'interrupted'
        assert result['runs'][0]['route_receipt']['target_id'] == second
        assert seen == ['other']
        with scoped_session(app, admin.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            assert db.execute(text("SELECT execution_state FROM provider_pools WHERE id=(SELECT resource_pool_id FROM inference_targets WHERE id=:id)"), {'id': second}).scalar_one() == 'unknown'


def test_steering_keeps_explicit_specialist_and_completed_receipt_survives_retarget(bff, monkeypatch):
    import threading
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def stream(*args, **kwargs):
        calls.append(args[2])
        yield 'text', 'A beginning'
        if len(calls) == 1:
            entered.set()
            assert release.wait(10)
        yield 'done', 'stop'
    monkeypatch.setattr(chat, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        first = configure(admin, ah)
        second = configure(admin, ah, 'other')
        assert assign(admin, ah, 'chat.general', [first]).status_code == 200
        assert assign(admin, ah, 'reason.plan', [second]).status_code == 200
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        run_id = str(uuid4())
        assert user.post(path+'/turns', headers=uh, json={'request_id': run_id, 'revision': 1, 'content': 'Hello'}).status_code == 202
        try:
            assert entered.wait(5)
            response = user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 2, 'content': 'What should I do first?', 'capability': 'reason.plan', 'interrupt_run_id': run_id})
            assert response.status_code == 202
            assert response.json()['status'] == 'queued'
        finally:
            release.set()
        import time
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            result = user.get(path).json()
            if len(result['runs']) == 2 and result['runs'][-1]['status'] == 'completed':
                break
            time.sleep(.02)
        assert calls == ['fixture', 'other']
        receipt = result['runs'][-1]['route_receipt']
        assert receipt['capability_id'] == 'reason.plan' and receipt['model_id'] == 'other'
        update = {'revision': 2, 'name': 'New host', 'base_url': 'http://127.0.0.1:1250', 'model_id': 'changed-model', 'resource_pool': 'New GPU', 'local_only': True}
        assert admin.put(f'/api/v1/providers/{second}', headers=ah, json=update).status_code == 200
        result = user.get(path).json()
        assert result['runs'][-1]['model_id'] == 'other' and result['runs'][-1]['route_receipt'] == receipt
        replies = {message['id']: message for message in result['messages'] if message['role'] == 'assistant'}
        assert [replies[run['assistant_message_id']]['role'] for run in result['runs']] == ['assistant', 'assistant']
        assert [run['model_id'] for run in result['runs']] == ['fixture', 'other']
        # Runs predating recorded provenance must not borrow a server's current
        # model name, which could have changed since the response was written.
        with scoped_session(app, user.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            db.execute(text("UPDATE chat_runs SET route_receipt='{}' WHERE id=:id"), {'id': result['runs'][0]['id']})
        assert user.get(path).json()['runs'][0]['model_id'] is None
