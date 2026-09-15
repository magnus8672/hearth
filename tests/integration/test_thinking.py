import io
import json
import os
import threading
import time
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from hearth import chat, memory
from hearth.database import scoped_session
from sqlalchemy import text

from tests.integration.test_chat import configure, csrf, promote, setup, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


@pytest.mark.parametrize('ending', ['complete', 'steer', 'stop', 'revoke'])
def test_live_preview_separate_from_answer_recall_and_steering(bff, monkeypatch, ending):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    entered, finish = threading.Event(), threading.Event()
    contexts = []
    marker = 'ThinkingOnlyCanary'
    def stream(*args, **kwargs):
        assert kwargs['include_reasoning'] is True
        contexts.append(args[3])
        if len(contexts) == 1:
            yield 'reasoning', marker+' <script>plain text</script>'
            entered.set()
            assert finish.wait(15)
            yield 'reasoning', ' later reasoning'
            yield 'text', 'Visible answer.'
        else:
            yield 'reasoning', 'Second turn thinking.'
            yield 'text', 'New direction.'
        yield 'done', 'stop'
    monkeypatch.setattr(chat, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        configure(admin, csrf(admin, settings.admin_origin))
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        request_id = str(uuid4())
        try:
            assert user.post(path+'/turns', headers=uh, json={'request_id': request_id, 'revision': 1, 'content': 'Help me think about a weekend project.'}).status_code == 202
            assert entered.wait(5)
            active = user.get(path).json()
            assert active['messages'][-1]['content'] == ''
            assert active['runs'][0]['reasoning_text'].startswith(marker)
            assert active['runs'][0]['stream_phase'] == 'reasoning'
            assert admin.get(path).status_code == 403
            with migration.connect() as db:
                other = db.execute(text('SELECT id FROM users WHERE farm_id=:farm AND subject<>:subject'), {'farm': settings.farm_id, 'subject': subject}).scalar_one()
            with scoped_session(app, other, settings.farm_id) as db:
                assert db.execute(text('SELECT reasoning_text FROM chat_runs')).all() == []
            if ending == 'steer':
                note = user.post('/api/v1/side-notes', headers=uh, json={'id': str(uuid4()), 'content': 'Make it a garden project.'}).json()
                steered = user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': active['revision'], 'content': note['content'], 'note_id': note['id'], 'note_revision': 1, 'interrupt_run_id': request_id})
                assert steered.status_code == 202 and steered.json()['status'] == 'queued', steered.text
            elif ending == 'stop':
                assert user.post(path+'/stop', headers=uh).status_code == 200
            elif ending == 'revoke':
                with migration.begin() as db:
                    db.execute(text("DELETE FROM browser_sessions WHERE farm_id=:farm AND audience='user'"), {'farm': settings.farm_id})
        finally:
            finish.set()
        if ending == 'revoke':
            signin(user)
            uh = csrf(user, settings.user_origin)
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            done = user.get(path).json()
            if done['runs'][-1]['status'] != 'running' and (ending != 'steer' or len(done['runs']) == 2):
                break
            time.sleep(.02)
        else:
            pytest.fail('Thinking run did not settle')
        first = done['runs'][0]
        assert first['status'] == ('completed' if ending == 'complete' else 'cancelled')
        assert ('later reasoning' in first['reasoning_text']) == (ending == 'complete')
        assert marker not in done['messages'][1]['content']
        with factory() as reopened:
            signin(reopened)
            assert reopened.get(path).json()['runs'] == done['runs']
        with scoped_session(app, user.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            assert memory.search(db, marker) == []
        exported = user.get('/api/v1/memory/vault.zip')
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as vault:
            assert all(marker.encode() not in vault.read(name) for name in vault.namelist())
        if ending == 'steer':
            assert done['runs'][1]['reasoning_text'] == 'Second turn thinking.'
            assert done['messages'][-1]['content'] == 'New direction.'
        else:
            assert user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': done['revision'], 'content': 'Continue with the project.'}).status_code == 202
            assert wait_finished(user, path)['runs'][-1]['status'] == 'completed'
        assert marker not in json.dumps(contexts[-1])


def test_thinking_preview_has_utf8_cap_without_cutting_off_answer(bff, monkeypatch):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    def stream(*args, **kwargs):
        yield 'reasoning', 'A'+'🔥'*20000
        yield 'reasoning', 'This must not fill a partial UTF-8 gap.'
        yield 'text', 'The full answer still arrives.'
        yield 'done', 'stop'
    monkeypatch.setattr(chat, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        configure(admin, csrf(admin, settings.admin_origin))
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        assert user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Think about a problem.'}).status_code == 202
        done = wait_finished(user, path)
        assert done['runs'][-1]['status'] == 'completed'
        assert done['runs'][-1]['reasoning_truncated'] is True
        assert done['runs'][-1]['reasoning_text'] == 'A'+'🔥'*16383
        assert done['runs'][-1]['stream_phase'] == 'answer'
        assert done['messages'][-1]['content'] == 'The full answer still arrives.'


@pytest.mark.skipif(os.environ.get('HEARTH_LIVE_THINKING') != '1', reason='Explicit resident provider thinking preview qualification required.')
def test_live_resident_qwen_thinking_before_answer_and_restore(bff):
    import httpx
    factory, settings, _, migration, _ = bff
    url, model = 'http://10.20.30.40:1234', 'qwen/qwen3.8-27b'
    def loaded():
        return sorted(item['id'] for row in httpx.get(url+'/api/v1/models', trust_env=False, timeout=10).raise_for_status().json()['models'] for item in row['loaded_instances'])
    before = loaded()
    assert model in before
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        created = admin.post('/api/v1/providers', headers=ah, json={'name': 'Thinking preview qualification', 'base_url': url, 'model_id': model, 'local_only': True, 'allow_insecure_http': True, 'residency_policy': 'lmstudio_loaded'})
        assert created.status_code == 201, created.text
        verified = admin.post('/api/v1/providers/'+created.json()['id']+'/probe', headers=ah, json={'revision': 1})
        assert verified.json()['state'] == 'ready', verified.text
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        accepted = user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'A garden is 17 metres by 23 metres. A one metre wide path goes inside its perimeter. How much area remains for planting? Give a short answer.', 'capability': 'chat.general'})
        assert accepted.status_code == 202, accepted.text
        observed, sizes = False, set()
        deadline = time.monotonic()+600
        while time.monotonic() < deadline:
            result = user.get(path).json()
            run = result['runs'][-1]
            if run['reasoning_text']:
                sizes.add(len(run['reasoning_text']))
                if run['status'] == 'running' and not result['messages'][-1]['content']:
                    observed = True
            if run['status'] != 'running':
                break
            time.sleep(.05)
        assert run['status'] == 'completed' and run['finish_reason'] == 'stop', run['status']
        assert observed and len(sizes) > 1, 'Expected persisted thinking updates before visible answer'
        assert '315' in result['messages'][-1]['content']
        with factory() as fresh:
            signin(fresh)
            assert fresh.get(path).json()['runs'] == result['runs']
        assert loaded() == before
        output = Path('evidence/thinking/2026-09-13')
        output.mkdir(parents=True, exist_ok=True)
        (output/'live-qwen.json').write_text(json.dumps({'scope': 'Real resident LAN Qwen and restricted-role PostgreSQL/BFF, disposable farm, explicit OIDC fixtures. Synthetic garden arithmetic only.', 'model': model, 'reasoning_visible_before_answer': observed, 'distinct_preview_lengths': sorted(sizes), 'reasoning_characters': len(run['reasoning_text']), 'reasoning_text_recorded_in_evidence': False, 'answer': result['messages'][-1]['content'], 'saved_preview_restored': True, 'loaded_models_unchanged': True, 'cloud_calls': 0}, indent=2), encoding='utf-8')
