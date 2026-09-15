"""Real PostgreSQL/API and loopback HTTP specialists; no real model inference."""
import json
import os
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from hearth import chat, inference, providers
from hearth.database import scoped_session
from sqlalchemy import text

from tests.integration.test_capability_routes import assign
from tests.integration.test_chat import csrf, promote, setup, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


@contextmanager
def specialist(host, model):
    state = {'loaded': True, 'calls': [], 'entered': threading.Event(), 'release': threading.Event()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state['calls'].append(('GET', self.path))
            data = {'data': [{'id': model}]} if self.path == '/v1/models' else {
                'models': [{'type': 'llm', 'key': model, 'loaded_instances': [{'id': model}] if state['loaded'] else []}]}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state['calls'].append(('POST', self.path, payload['model']))
            assert self.path == '/v1/chat/completions' and payload['model'] == model
            assert state['loaded'], 'Unloaded models must never receive inference'
            if payload['messages'][-1]['content'] == 'Parallel request':
                state['entered'].set()
                assert state['release'].wait(15), 'Independent servers were serialized'
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for delta, finish in [({'content': f'Answer from {host}'}, None), ({}, 'stop')]:
                self.wfile.write(('data: ' + json.dumps({'model': model, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}) + '\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n')

    server = ThreadingHTTPServer((host, 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://{host}:{server.server_port}', state
    finally:
        state['release'].set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_four_servers_persist_and_dispatch_concurrently_without_model_loading(bff, monkeypatch):
    from contextlib import ExitStack
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    monkeypatch.setattr(providers, 'list_models', inference.list_models)
    monkeypatch.setattr(providers, 'chat_stream', inference.chat_stream)
    with ExitStack() as stack, factory('admin') as admin, factory() as user:
        services = [stack.enter_context(specialist(f'127.0.0.{n+1}', model)) for n, model in enumerate(['fixture', 'coder', 'planner', 'fixture'])]
        signin(admin)
        promote(admin, migration, settings)
        headers = csrf(admin, settings.admin_origin)
        targets = []
        for n, (url, _) in enumerate(services):
            payload = {'name': f'Machine {n}', 'base_url': url, 'model_id': ['fixture', 'coder', 'planner', 'fixture'][n], 'resource_pool': f'Simulated machine {n} GPU', 'local_only': True, 'residency_policy': 'lmstudio_loaded'}
            created = admin.post('/api/v1/providers', headers=headers, json=payload)
            assert created.status_code == 201, created.text
            target = created.json()['id']
            targets.append(target)
            assert admin.post(f'/api/v1/providers/{target}/probe', headers=headers, json={'revision': 1}).json()['state'] == 'ready'
            assert admin.post('/api/v1/providers', headers=headers, json=payload).status_code == 409
        rows = admin.get('/api/v1/providers').json()['items']
        assert len(rows) == len({r['connection_id'] for r in rows}) == len({r['resource_pool_id'] for r in rows}) == 4
        assert all(r['residency_policy'] == 'lmstudio_loaded' for r in rows)
        with factory('admin') as reopened:
            signin(reopened)
            assert {r['id'] for r in reopened.get('/api/v1/providers').json()['items']} == set(targets)
        capabilities = ['chat.general', 'code.implement', 'reason.plan', 'write.compose']
        for cap, target in zip(capabilities, targets, strict=True):
            assert assign(admin, headers, cap, [target]).status_code == 200
        # Many capabilities may bind one resident model, and one capability may
        # select among several resident instances without merging identities.
        assert assign(admin, headers, 'text.summarize', [targets[0], targets[3]]).status_code == 200
        signin(user)
        uh = csrf(user, settings.user_origin)
        paths = []
        try:
            for cap in capabilities:
                path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=uh, json={}).json()['id']
                paths.append(path)
                response = user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Parallel request', 'capability': cap})
                assert response.status_code == 202, response.text
            assert all(state['entered'].wait(8) for _, state in services)
            with scoped_session(app, admin.get('/api/v1/session').json()['id'], settings.farm_id) as db:
                assert db.execute(text("SELECT count(*) FROM provider_pools WHERE execution_state='running'")).scalar_one() == 4
            # An occupied shared group refuses extra work, despite other pools.
            another = '/api/v1/chats/' + user.post('/api/v1/chats', headers=uh, json={}).json()['id']
            assert user.post(another+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Hi', 'capability': 'chat.general'}).status_code == 409
        finally:
            for _, state in services:
                state['release'].set()
        for path, target in zip(paths, targets, strict=True):
            result = wait_finished(user, path)
            assert result['runs'][-1]['status'] == 'completed'
            # Durable admission identity includes host connection and pool.
            with scoped_session(app, user.get('/api/v1/session').json()['id'], settings.farm_id) as db:
                receipt = db.execute(text('SELECT route_receipt FROM chat_runs WHERE target_id=:target'), {'target': target}).scalar_one()
                assert receipt['target_id'] == target and receipt['connection_id'] and receipt['resource_pool_id']
        # Losing residency between qualification and invocation fails before POST.
        state = services[0][1]
        state['loaded'] = False
        posts = len([c for c in state['calls'] if c[0] == 'POST'])
        response = user.post(paths[0]+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 2, 'content': 'Hello', 'capability': 'chat.general'})
        assert response.status_code == 202
        assert wait_finished(user, paths[0])['runs'][-1]['status'] == 'failed'
        assert len([c for c in state['calls'] if c[0] == 'POST']) == posts
        for _, service in services:
            assert all(call[1] in {'/v1/models', '/api/v1/models', '/v1/chat/completions'} for call in service['calls'])


def test_same_host_defaults_share_capacity_and_image_instances_are_independent(bff, monkeypatch):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    with factory('admin') as admin:
        signin(admin)
        promote(admin, migration, settings)
        headers = csrf(admin, settings.admin_origin)
        for address in ['https://192.168.1.40:1240', 'https://192.168.1.40:1241', 'https://192.168.1.41:1240', 'http://localhost:1234', 'http://127.0.0.1:1235']:
            response = admin.post('/api/v1/providers', headers=headers, json={'name': address, 'base_url': address, 'model_id': 'same-image-model', 'protocol': 'hearth.image.v1', 'local_only': True})
            assert response.status_code == 201
        rows = admin.get('/api/v1/providers').json()['items']
        assert len({r['connection_id'] for r in rows}) == 5
        assert rows[0]['resource_pool_id'] == rows[1]['resource_pool_id'] != rows[2]['resource_pool_id']
        assert rows[3]['resource_pool_id'] == rows[4]['resource_pool_id'] != rows[2]['resource_pool_id']
        assert all(r['state'] == 'configured' for r in rows)


@pytest.mark.skipif(not os.environ.get('HEARTH_LIVE_RESIDENCY_MODEL'), reason='Explicit live local model selection required.')
def test_live_loaded_model_probe_and_routed_reply(bff, monkeypatch):
    factory, settings, _, migration, _ = bff
    model = os.environ['HEARTH_LIVE_RESIDENCY_MODEL']
    url = os.environ.get('HEARTH_LIVE_RESIDENCY_URL', 'http://127.0.0.1:1234').rstrip('/')

    def loaded():
        data = httpx.get(url+'/api/v1/models', trust_env=False, timeout=10).raise_for_status().json()
        return sorted(i['id'] for m in data['models'] for i in m['loaded_instances'])

    before = loaded()
    assert model in before, 'Load the selected model explicitly before running this test.'
    times = {}

    def observed(*args, **kwargs):
        for kind, value in inference.chat_stream(*args, **kwargs):
            if kind == 'text' and value:
                times.setdefault('first_output', time.monotonic())
            yield kind, value

    monkeypatch.setattr(chat, 'chat_stream', observed)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        response = admin.post('/api/v1/providers', headers=ah, json={'name': 'Live residency qualification', 'base_url': url, 'model_id': model, 'local_only': True, 'resource_pool': 'Explicit live test GPU', 'residency_policy': 'lmstudio_loaded'})
        assert response.status_code == 201, response.text
        target = response.json()['id']
        verified = admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 1})
        assert verified.json()['state'] == 'ready', verified.text
        assert loaded() == before
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        started = time.monotonic()
        sent = user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Reply with a short greeting for the hearth connection test.'})
        admitted = time.monotonic()
        assert sent.status_code == 202, sent.text
        result = wait_finished(user, path, timeout=120)
        assert result['runs'][-1]['status'] == 'completed', result['runs']
        after = loaded()
        assert after == before
        out = Path('evidence/multi-provider/2026-09-13/live-residency.json')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({'scope': 'Real local LM Studio, HTTP/SSE and PostgreSQL through BFF APIs. Disposable farm and explicit OIDC fixtures. One physical GPU only.',
            'model': model, 'loaded_instances_before': before, 'loaded_instances_after': after,
            'probe_completed': True, 'routed_reply_completed': True,
            'request_admission_seconds': round(admitted-started, 3), 'time_to_first_output_seconds': round(times['first_output']-started, 3),
            'automatic_loading_configuration': 'not changed or verified by this test; loaded-instance preflight only',
            'no_observed_load_or_eviction': True, 'paid_inference': False}, indent=2), encoding='utf-8')
