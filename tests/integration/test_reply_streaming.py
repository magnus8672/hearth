import ast
import json
import os
import re
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from hearth import channels, chat

from tests.integration.test_capability_routes import assign
from tests.integration.test_chat import configure, csrf, promote, setup, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


def test_limited_reply_keeps_model_finish_and_context_for_explicit_continuation(bff, monkeypatch):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    contexts = []

    def stream(*args, **kwargs):
        contexts.append(args[3])
        yield 'text', 'Partial code' if len(contexts) == 1 else 'Completed code'
        yield 'done', 'length' if len(contexts) == 1 else 'stop'

    monkeypatch.setattr(chat, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = configure(admin, ah)
        assert assign(admin, ah, 'code.implement', [target]).status_code == 200
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        assert user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Write a Python Fibonacci script.'}).status_code == 202
        first = wait_finished(user, path)
        assert first['runs'][0]['finish_reason'] == 'length'
        assert first['runs'][0]['assistant_message_id'] == first['messages'][-1]['id']
        assert first['messages'][-1]['content'] == 'Partial code'
        assert len(contexts) == 1  # No automatic second generation.
        assert user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': first['revision'], 'content': 'Continue your previous reply.', 'capability': 'code.implement'}).status_code == 202
        complete = wait_finished(user, path)
        assert complete['runs'][-1]['finish_reason'] == 'stop'
        assert {'role': 'assistant', 'content': 'Partial code'} in contexts[-1]
        with factory() as fresh:
            signin(fresh)
            assert fresh.get(path).json()['runs'] == complete['runs']


def test_channel_reports_output_limit_in_saved_reply(bff, monkeypatch):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    monkeypatch.setattr(channels, 'chat_stream', lambda *a, **kw: iter([('text', 'Partial shared reply'), ('done', 'length')]))
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        configure(admin, csrf(admin, settings.admin_origin))
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/channels/' + user.post('/api/v1/channels', headers=uh, json={'name': 'Output test'}).json()['id']
        assert user.post(path+'/messages', headers=uh, json={'request_id': str(uuid4()), 'content': '@hearth hello'}).status_code == 201
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            message = user.get(path).json()['messages'][-1]
            if message['status'] != 'running':
                break
            time.sleep(.02)
        assert message['status'] == 'completed'
        assert message['model_id'] == 'fixture'
        assert 'may be incomplete' in message['reason']


@pytest.mark.skipif(not os.environ.get('HEARTH_LIVE_REPLY_URL'), reason='Explicit real coding server required; ordinary tests never run local inference.')
def test_live_qwen_fibonacci_stream_finishes_and_restores(bff, monkeypatch):
    factory, settings, _, migration, _ = bff
    url = os.environ['HEARTH_LIVE_REPLY_URL'].rstrip('/')
    model = os.environ['HEARTH_LIVE_REPLY_MODEL']

    def loaded():
        data = httpx.get(url+'/api/v1/models', timeout=10, trust_env=False).raise_for_status().json()
        return sorted(i['id'] for m in data['models'] for i in m['loaded_instances'])

    before = loaded()
    assert model in before
    chunks = []
    original = chat.chat_stream

    def observed(*args, **kwargs):
        for kind, value in original(*args, **kwargs):
            if kind == 'text':
                chunks.append(len(value))
            yield kind, value

    monkeypatch.setattr(chat, 'chat_stream', observed)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        created = admin.post('/api/v1/providers', headers=ah, json={'name': 'Explicit coding regression fixture', 'base_url': url, 'model_id': model, 'local_only': True, 'allow_insecure_http': True, 'residency_policy': 'lmstudio_loaded'})
        assert created.status_code == 201, created.text
        target = created.json()['id']
        probe = admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 1})
        assert probe.json()['state'] == 'ready', probe.text
        assert assign(admin, ah, 'code.implement', [target]).status_code == 200
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/' + user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        started = time.monotonic()
        sent = user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Can you write a python script which will calculate the fibonacci sequence out to 1000 integers?'})
        assert sent.status_code == 202, sent.text
        complete = wait_finished(user, path, timeout=900)
        run, answer = complete['runs'][-1], complete['messages'][-1]
        assert run['status'] == 'completed' and run['finish_reason'] == 'stop', run
        assert run['model_id'] == model and run['assistant_message_id'] == answer['id']
        assert len(answer['content']) > 500 and len(chunks) > 5
        blocks = re.findall(r'```(?:python|py)\s*\n(.*?)```', answer['content'], re.DOTALL)
        assert blocks, 'Expected a complete Python code fence'
        parsed = [ast.parse(block) for block in blocks]  # Parse only. Never execute model-authored code.
        assert any(isinstance(node, (ast.FunctionDef, ast.For, ast.While)) for tree in parsed for node in ast.walk(tree))
        with factory() as fresh:
            signin(fresh)
            restored = fresh.get(path).json()
            assert restored['messages'] == complete['messages']
            assert restored['runs'] == complete['runs']
        after = loaded()
        assert before == after
        output = Path('evidence/replies/2026-09-13')
        output.mkdir(parents=True, exist_ok=True)
        (output/'live-code.txt').write_text(answer['content'], encoding='utf-8')
        (output/'live-qwen.json').write_text(json.dumps({
            'scope': 'Real remote LM Studio, restricted-role PostgreSQL and both BFF APIs with explicit OIDC fixtures in a disposable farm. No user conversation modified.',
            'model': model, 'address': url, 'max_output_tokens': settings.chat_max_output_tokens,
            'elapsed_seconds': round(time.monotonic()-started, 3), 'finish_reason': run['finish_reason'],
            'answer_characters': len(answer['content']), 'answer_chunks': len(chunks),
            'complete_python_blocks_parsed': len(blocks), 'model_code_executed': False,
            'saved_message_and_model_restored': True, 'loaded_before': before, 'loaded_after': after,
        }, indent=2), encoding='utf-8')
