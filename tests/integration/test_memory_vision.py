"""Recall through the actual multimodal admission path, including prior images."""
import io
import json
import os
import random
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hearth import chat, memory, vision
from hearth.database import scoped_session
from PIL import Image

from tests.integration.test_capability_routes import assign
from tests.integration.test_chat import configure, csrf, promote, setup, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases
from tests.live_targets import configured_provider


def textured_picture():
    # Enough JPEG data to exceed the old text budget, even after normalization.
    image = Image.frombytes('RGB', (400, 300), random.Random(42).randbytes(400*300*3))
    output = io.BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()


def exercise_recall(user, headers, name):
    note = user.post('/api/v1/memory/notes', headers=headers, json={'title': 'Users Name', 'body': name, 'kind': 'note'}).json()
    path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=headers, json={}).json()['id']
    attachment = user.post(path+'/attachments', headers=headers, content=textured_picture())
    assert attachment.status_code == 201, attachment.text
    results = []
    revision = 1
    for index, prompt in enumerate(['Describe this picture briefly.', 'what is my name', "it's not in your attached memory system?"]):
        turn = {'request_id': str(uuid4()), 'revision': revision, 'content': prompt}
        if index == 0:
            turn['attachment_ids'] = [attachment.json()['id']]
        response = user.post(path+'/turns', headers=headers, json=turn)
        assert response.status_code == 202, response.text
        result = wait_finished(user, path, timeout=600)
        run = result['runs'][-1]
        assert run['status'] == 'completed', run
        assert run['capability_id'] == 'vision.describe'
        receipt = run['memory_receipt']
        if index:
            assert receipt['search_status'] == 'matched'
            assert any(source['id'] == note['id'] for source in receipt['sources'])
        else:
            assert receipt['sources'] == [] and receipt['search_status'] == 'no_matches'
        results.append({'prompt': prompt, 'reply': result['messages'][-1]['content'], 'receipt': receipt})
        revision = result['revision']
    return results


def test_name_note_recalled_with_previous_image_and_memory_followup(bff, monkeypatch):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    monkeypatch.setattr(vision, 'probe', lambda *a: {'vision_probe': 'explicit-fixture'})
    contexts = []
    def stream(*args, **kwargs):
        contexts.append(args[3])
        yield 'text', 'An explicit provider fixture reply.'
        yield 'done', 'stop'
    monkeypatch.setattr(chat, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = configure(admin, ah)
        assert assign(admin, ah, 'vision.describe', [target]).status_code == 200
        assert admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 2, 'vision': True}).json()['state'] == 'ready'
        signin(user)
        exercise_recall(user, csrf(user, settings.user_origin), 'Morgan')
        for index, context in enumerate(contexts):
            assert [m['role'] for m in context].count('system') == 1
            instruction = context[0]['content']
            assert 'supplied images' in instruction and 'hearth stores private conversation history' in instruction
            assert ('Morgan' in instruction) == (index > 0)
            if index:
                assert 'Users Name' in instruction
            images = [part for item in context if isinstance(item['content'], list) for part in item['content'] if part['type'] == 'image_url']
            assert len(images) == 1 and len(images[0]['image_url']['url']) > 16000
            assert sum(len(memory.content_text(item['content']).encode()) for item in context) < 6000


def test_memory_status_budget_pause_and_followup_scope(bff):
    factory, settings, app, _, _ = bff
    with factory() as user:
        signin(user)
        headers = csrf(user, settings.user_origin)
        user.post('/api/v1/memory/notes', headers=headers, json={'title': 'Users Name', 'body': 'Morgan'})
        owner = UUID(user.get('/api/v1/session').json()['id'])
        def recalled(query, context):
            with scoped_session(app, owner, settings.farm_id) as db:
                return memory.recall_context(db, query, uuid4(), context, 0)
        question = {'role': 'user', 'content': 'what is my name'}
        context, receipt = recalled('name', [{'role': 'user', 'content': '🔥'*4000}])
        assert receipt['search_status'] == 'context_full' and receipt['sources'] == []
        assert 'Morgan' not in context[0]['content'] and 'did not fit' in context[0]['content']
        followup = "it's not in your attached memory system?"
        assert memory.recall_query(followup, [question, {'role': 'assistant', 'content': 'No memory exists'}, {'role': 'user', 'content': followup}]).endswith(question['content'])
        unrelated = 'Tell me about computer memory'
        assert memory.recall_query(unrelated, [question, {'role': 'user', 'content': unrelated}]) == unrelated
        assert user.put('/api/v1/memory/settings', headers=headers, json={'revision': 1, 'enabled': False}).status_code == 200
        context, receipt = recalled('name', [question])
        assert receipt['search_status'] == 'paused' and not receipt['sources']
        assert 'paused cross-session recall' in context[0]['content'] and 'Morgan' not in context[0]['content']


@pytest.mark.skipif(os.environ.get('HEARTH_LIVE_MEMORY_VISION') != '1', reason='Explicit resident LAN vision/memory qualification required.')
def test_live_resident_qwen_name_recall_with_prior_image(bff):
    import httpx
    factory, settings, _, migration, _ = bff
    url, model = configured_provider()
    def loaded():
        return sorted(item['id'] for row in httpx.get(url+'/api/v1/models', timeout=10, trust_env=False).raise_for_status().json()['models'] for item in row['loaded_instances'])
    before = loaded()
    assert model in before
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Memory vision qualification', 'base_url': url, 'model_id': model, 'local_only': True, 'allow_insecure_http': True, 'residency_policy': 'lmstudio_loaded'})
        assert target.status_code == 201, target.text
        target_id = target.json()['id']
        probe = admin.post(f'/api/v1/providers/{target_id}/probe', headers=ah, json={'revision': 1, 'vision': True})
        assert probe.status_code == 200 and probe.json()['state'] == 'ready', probe.text
        assert assign(admin, ah, 'vision.describe', [target_id]).status_code == 200
        signin(user)
        name = random.SystemRandom().choice(['Avery', 'Rowan', 'Quinn', 'Morgan', 'Casey'])
        replies = exercise_recall(user, csrf(user, settings.user_origin), name)
        for turn in replies[1:]:
            assert name.lower() in turn['reply'].lower(), turn['reply']
        assert loaded() == before
        output = Path('.hearth/test-results/memory/2026-09-13-vision-fix')
        output.mkdir(parents=True, exist_ok=True)
        (output/'live-recall.json').write_text(json.dumps({'scope': 'Real resident Qwen vision over LAN, restricted-role PostgreSQL and BFF in disposable farm; explicit OIDC fixtures.', 'model': model, 'ordinary_note': True, 'prior_image_retained': True, 'replies': replies, 'loaded_models_unchanged': True, 'cloud_calls': 0}, indent=2), encoding='utf-8')
