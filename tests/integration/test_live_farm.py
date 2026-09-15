import json
import os
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from hearth import chat, inference

from tests.integration.test_capability_routes import assign
from tests.integration.test_chat import csrf, promote, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


@pytest.mark.skipif(os.environ.get('HEARTH_LIVE_FARM') != '1', reason='Explicit two-machine local inference test required.')
def test_real_resident_specialists_stream_concurrently(bff, monkeypatch):
    factory, settings, _, migration, _ = bff
    servers = [('http://127.0.0.1:1234', 'openai/gpt-oss-20b', 'chat.general'),
               ('http://10.20.30.40:1234', 'qwen/qwen3.8-27b', 'code.implement')]

    def loaded():
        return {url: sorted(i['id'] for m in httpx.get(url+'/api/v1/models', timeout=10, trust_env=False).raise_for_status().json()['models'] for i in m['loaded_instances']) for url, _, _ in servers}

    before = loaded()
    assert all(model in before[url] for url, model, _ in servers)
    intervals = {}
    coding_started = threading.Event()

    def observed(*args, **kwargs):
        model = args[2]
        for kind, value in inference.chat_stream(*args, **kwargs):
            intervals.setdefault(model, {})['last_event'] = time.monotonic()
            intervals[model].setdefault('first_event', time.monotonic())
            if model == servers[1][1]:
                coding_started.set()
            yield kind, value

    monkeypatch.setattr(chat, 'chat_stream', observed)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        ids, paths = [], []
        for url, model, capability in servers:
            result = admin.post('/api/v1/providers', headers=ah, json={'name': 'Physical farm regression '+capability, 'base_url': url, 'model_id': model, 'local_only': True, 'allow_insecure_http': True, 'residency_policy': 'lmstudio_loaded'})
            assert result.status_code == 201, result.text
            target = result.json()['id']
            assert admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 1}).json()['state'] == 'ready'
            assert assign(admin, ah, capability, [target]).status_code == 200
            ids.append(target)
        rows = admin.get('/api/v1/providers').json()['items']
        assert len({r['resource_pool_id'] for r in rows}) == len({r['connection_id'] for r in rows}) == 2
        signin(user)
        uh = csrf(user, settings.user_origin)
        for _ in range(3):
            paths.append('/api/v1/chats/'+user.post('/api/v1/chats', headers=uh, json={}).json()['id'])
        assert user.post(paths[1]+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Write a Python script which calculates the first 1000 Fibonacci numbers. Include a brief explanation.'}).status_code == 202
        assert coding_started.wait(60)
        assert user.post(paths[2]+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Write a Python function to add numbers.'}).status_code == 409
        assert user.post(paths[0]+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Good afternoon. Please give me a short friendly greeting.'}).status_code == 202
        general = wait_finished(user, paths[0], 300)
        coding = wait_finished(user, paths[1], 900)
        for result, expected in [(general, servers[0][1]), (coding, servers[1][1])]:
            run = result['runs'][-1]
            assert run['status'] == 'completed' and run['finish_reason'] == 'stop', json.dumps(run)
            assert run['model_id'] == expected
        a, b = [intervals[server[1]] for server in servers]
        overlap = min(a['last_event'], b['last_event']) - max(a['first_event'], b['first_event'])
        assert overlap > 0, intervals
        assert loaded() == before
        assert all(row['execution_state'] == 'idle' for row in admin.get('/api/v1/providers').json()['items'])
        out = Path('evidence/vision/2026-09-13')
        out.mkdir(parents=True, exist_ok=True)
        (out/'physical-concurrency.json').write_text(json.dumps({'scope': 'Two real LM Studio servers and resident models through real PostgreSQL/BFF APIs in a disposable farm, with explicit OIDC fixtures.',
            'servers': servers, 'simultaneous_stream_seconds': round(overlap, 3), 'independent_pool_ids': True,
            'second_coding_request_rejected_while_busy': True, 'both_completed': True,
            'loaded_before_and_after': before, 'no_load_or_unload_in_dispatch': True,
            'setup': 'The existing local GPT-OSS was loaded explicitly before this test; no models were downloaded.',
            'remaining': 'Physical server failure/recovery and external JIT configuration are not attested.'}, indent=2), encoding='utf-8')
