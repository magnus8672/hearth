from uuid import UUID, uuid4

import pytest
from hearth import chat, provider_health, routing
from hearth.database import scoped_session
from hearth.inference import ProviderError
from sqlalchemy import text

from tests.integration.test_chat import configure, csrf, promote, setup, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


def test_qualification_survives_time_and_startup_preserves_vision_without_generation(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    calls = []
    monkeypatch.setattr(provider_health, 'list_models', lambda *args: calls.append('models') or ['fixture'])
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = UUID(configure(admin, ah))
        with scoped_session(app, provider_health.SYSTEM, settings.farm_id) as db:
            db.execute(text("UPDATE inference_targets SET verified_until=now()-interval '30 days',features='[\"chat\",\"streaming\",\"vision\"]' WHERE id=:id"), {'id': target})
            row = provider_health.target_record(db, target)
            assert routing.readiness('vision.describe', row)[0]
        assert not admin.get('/api/v1/providers').json()['items'][0]['expired']
        pending = provider_health.prepare_startup(app, settings)
        assert len(pending) == 1
        assert provider_health.check_target(app, settings, *pending[0])
        assert calls == ['models']
        item = admin.get('/api/v1/providers').json()['items'][0]
        assert item['state'] == 'ready' and item['verified_until'] is None
        assert item['revision'] == 2 and 'vision' in item['features']
        monkeypatch.setattr(chat, 'chat_stream', lambda *a, **kw: iter([('text', 'Still ready.'), ('done', 'stop')]))
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        assert user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Hello'}).status_code == 202
        assert wait_finished(user, path)['runs'][-1]['status'] == 'completed'
        assert provider_health.prepare_startup(app, settings.model_copy(update={'farm_id': uuid4()})) == []


@pytest.mark.parametrize('change', ['disable', 'revision', 'http'])
def test_startup_cannot_publish_over_a_concurrent_admin_change(bff, monkeypatch, change):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    with factory('admin') as admin:
        signin(admin)
        promote(admin, migration, settings)
        target = UUID(configure(admin, csrf(admin, settings.admin_origin)))
        pending = provider_health.prepare_startup(app, settings)
        def observe(*args):
            with scoped_session(app, provider_health.SYSTEM, settings.farm_id) as db:
                state = 'disabled' if change == 'disable' else 'configured'
                db.execute(text("UPDATE inference_targets SET revision=revision+1,state=:state,reason='Administrator changed settings',features='[]' WHERE id=:id"), {'id': target, 'state': state})
            return ['fixture']
        monkeypatch.setattr(provider_health, 'list_models', observe)
        assert provider_health.check_target(app, settings, *pending[0])
        item = admin.get('/api/v1/providers').json()['items'][0]
        assert item['state'] == ('disabled' if change == 'disable' else 'configured')
        assert item['revision'] == 3 and item['features'] == []
        with scoped_session(app, provider_health.SYSTEM, settings.farm_id) as db:
            provider_health.record_failure(db, {'id': target, 'revision': 2}, ProviderError('Stale request failed.'))
        assert admin.get('/api/v1/providers').json()['items'][0]['state'] == item['state']


def test_startup_defers_busy_and_unknown_pools_and_allows_boot_grace(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    with factory('admin') as admin:
        signin(admin)
        promote(admin, migration, settings)
        target = UUID(configure(admin, csrf(admin, settings.admin_origin)))
        run = uuid4()
        with scoped_session(app, provider_health.SYSTEM, settings.farm_id) as db:
            db.execute(text("UPDATE provider_pools SET active_run_id=:run,execution_state='unknown',lease_until=now()"), {'run': run})
        pending = provider_health.prepare_startup(app, settings)
        monkeypatch.setattr(provider_health, 'list_models', lambda *a: pytest.fail('A busy provider must not be probed.'))
        assert not provider_health.check_target(app, settings, *pending[0])
        with scoped_session(app, provider_health.SYSTEM, settings.farm_id) as db:
            row = provider_health.target_record(db, target)
            assert row['active_run_id'] == run and row['execution_state'] == 'unknown'
            db.execute(text("UPDATE provider_pools SET active_run_id=NULL,execution_state='idle',lease_until=NULL"))
        monkeypatch.setattr(provider_health, 'list_models', lambda *a: [])
        assert not provider_health.check_target(app, settings, *pending[0], final=False)
        assert admin.get('/api/v1/providers').json()['items'][0]['state'] == 'configured'
        assert provider_health.check_target(app, settings, *pending[0])
        assert admin.get('/api/v1/providers').json()['items'][0]['state'] == 'failed'
        assert provider_health.prepare_startup(app, settings) == []


@pytest.mark.parametrize('provider_fault', [True, False])
def test_real_dispatch_failure_invalidates_only_provider_errors_without_replay(bff, monkeypatch, provider_fault):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    calls = []
    def stream(*a, **kw):
        calls.append(1)
        raise ProviderError('Fixture failure', provider_fault=provider_fault)
    monkeypatch.setattr(chat, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        turn = {'request_id': str(uuid4()), 'revision': 1, 'content': 'Hello'}
        assert user.post(path+'/turns', headers=uh, json=turn).status_code == 202
        assert wait_finished(user, path)['runs'][-1]['status'] == 'failed'
        assert admin.get('/api/v1/providers').json()['items'][0]['state'] == ('failed' if provider_fault else 'ready')
        assert user.post(path+'/turns', headers=uh, json=turn).status_code == 202
        assert calls == [1]


def test_only_admin_runtime_starts_background_checks(bff, monkeypatch):
    from fastapi.testclient import TestClient
    from hearth.main import create_app
    _, settings, _, _, _ = bff
    called = []
    class Checks:
        def __init__(self, *args):
            called.append('start')
        def close(self):
            called.append('close')
    monkeypatch.setattr(provider_health, 'StartupChecks', Checks)
    for mode, audience in [('test', 'admin'), ('development', 'user'), ('development', 'admin')]:
        with TestClient(create_app(settings.model_copy(update={'mode': mode, 'audience': audience}))):
            pass
    assert called == ['start', 'close']


def test_startup_checks_independent_targets_concurrently(bff, monkeypatch):
    from threading import Barrier, Event
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    entered = Barrier(3)
    release = Event()
    def check(*args):
        entered.wait(timeout=5)
        assert release.wait(5)
    monkeypatch.setattr(provider_health, 'check_connection', check)
    with factory('admin') as admin:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        configure(admin, ah, 'other')
        checks = provider_health.StartupChecks(app, settings)
        try:
            entered.wait(timeout=5)
        finally:
            release.set()
            checks.close()
        assert all(item['state'] == 'ready' for item in admin.get('/api/v1/providers').json()['items'])
