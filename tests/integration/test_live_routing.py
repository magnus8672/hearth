"""Opt-in inference evidence; real providers, disposable farm and synthetic OIDC."""
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from hearth.database import scoped_session
from sqlalchemy import text

from tests.integration.test_capability_routes import assign
from tests.integration.test_chat import csrf, promote, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


@pytest.mark.skipif(os.getenv('HEARTH_LIVE_PROVIDER_ROUTING') != '1', reason='explicit local inference opt-in')
def test_live_specialists_and_planning_to_image_handoff(bff):
    factory, settings, app, migration, _ = bff
    output = Path('evidence/routing/2026-09-13')
    output.mkdir(parents=True, exist_ok=True)
    recorded = []
    model = 'openai/gpt-oss-20b'
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        targets = []
        for name, address in [('General local service', 'http://127.0.0.1:1234'), ('Specialist local service', 'http://localhost:1234')]:
            response = admin.post('/api/v1/providers', headers=ah, json={'name': name, 'base_url': address, 'model_id': model, 'resource_pool': 'One physical GPU', 'local_only': True})
            assert response.status_code == 201
            item = response.json()
            assert admin.post('/api/v1/providers/'+str(item['id'])+'/probe', headers=ah, json={'revision': 1}).json()['state'] == 'ready'
            targets.append(item['id'])
        prompts = [
            ('reason.plan', 'Plan a small herb garden in three short steps.'),
            ('code.explain', 'Explain this function briefly: def twice(x): return x * 2'),
            ('code.implement', 'Write a Python function to double a number. Keep the reply short.'),
            ('write.compose', 'Draft a two sentence invitation to a neighborhood picnic.'),
            ('text.summarize', 'Summarize in one sentence: The library opens at nine. It closes at five. It is closed on Sundays.'),
            ('data.extract', 'Extract city and name as a JSON object: Sam lives in Boston.'),
        ]
        assert assign(admin, ah, 'chat.general', [targets[0]]).status_code == 200
        for capability, _ in prompts:
            assert assign(admin, ah, capability, [targets[1]]).status_code == 200
        signin(user)
        uh = csrf(user, settings.user_origin)
        for capability, prompt in prompts:
            path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=uh, json={}).json()['id']
            assert user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 1, 'content': prompt}).status_code == 202
            result = wait_finished(user, path, 180)
            run = result['runs'][-1]
            assert run['status'] == 'completed', run.get('reason')
            assert run['capability_id'] == capability and run['route_receipt']['target_id'] == targets[1]
            assert result['messages'][-1]['content'].strip()
            recorded.append({'capability': capability, 'prompt': prompt, 'response': result['messages'][-1]['content'], 'receipt': run['route_receipt']})
        image_key = Path('.hearth/image-provider/controller.key').read_text(encoding='utf-8').strip()
        response = admin.post('/api/v1/providers', headers=ah, json={'name': 'Local SDXL test', 'base_url': 'http://127.0.0.1:1235', 'model_id': 'stabilityai/stable-diffusion-xl-base-1.0', 'protocol': 'hearth.image.v1', 'resource_pool': 'One physical GPU', 'api_key': image_key, 'local_only': True})
        assert response.status_code == 201
        image_target = response.json()['id']
        assert admin.post('/api/v1/providers/'+image_target+'/probe', headers=ah, json={'revision': 1}).json()['state'] == 'ready'
        assert assign(admin, ah, 'image.generate', [image_target]).status_code == 200
        path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        assert user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Remember a small red fox beside a stone fireplace. Briefly acknowledge this.'}).status_code == 202
        assert wait_finished(user, path, 180)['runs'][-1]['status'] == 'completed'
        run_id = str(uuid4())
        assert user.post(path+'/turns', headers=uh, json={'request_id': run_id, 'revision': 2, 'content': 'Generate an image of that please.'}).status_code == 202
        result = wait_finished(user, path, 240)
        assert result['runs'][-1]['status'] == 'completed', result['runs'][-1].get('reason')
        pictures = result['messages'][-1]['images']
        assert len(pictures) == 1
        artifact = user.get('/api/v1/conversation-images/'+pictures[0]['request']['id']+'/image').content
        assert hashlib.sha256(artifact).hexdigest() == pictures[0]['sha256']
        (output/'specialist-handoff.png').write_bytes(artifact)
        with scoped_session(app, user.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            plan = db.execute(text('SELECT planning_target_id,image_target_id,status FROM image_plans WHERE id=:id'), {'id': run_id}).mappings().one()
            assert str(plan['planning_target_id']) == targets[1] and str(plan['image_target_id']) == image_target and plan['status'] == 'completed'
        assert all(item['execution_state'] == 'idle' for item in admin.get('/api/v1/providers').json()['items'])
        (output/'live-routing.json').write_text(json.dumps({'scope': 'Actual LM Studio text specialists and SDXL handoff. Distinct target records share the existing one physical GPU; synthetic OIDC, disposable farm, no second host or LAN listener.', 'text': recorded, 'image': pictures[0], 'receipt': result['runs'][-1]['route_receipt'], 'completed': True}, indent=2), encoding='utf-8')
