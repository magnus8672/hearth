import io
import json
import os
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest
from hearth import chat, identity, vision
from hearth.database import scoped_session
from PIL import Image, ImageDraw
from sqlalchemy import text

from tests.integration.test_capability_routes import assign
from tests.integration.test_chat import configure, csrf, promote, setup, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases
from tests.live_targets import configured_provider


def picture():
    image = Image.new('RGB', (480, 300), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 50, 190, 230), fill='red')
    draw.ellipse((280, 60, 430, 220), fill='blue')
    output = io.BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()


def test_private_uploads_vision_routes_followups_and_cross_account_isolation(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    monkeypatch.setattr(vision, 'probe', lambda *a: {'vision_probe': 'explicit-fixture'})
    calls = []

    def stream(*args, **kwargs):
        calls.append((args[2], args[3]))
        yield 'text', 'A red rectangle and a blue circle.'
        yield 'done', 'stop'

    monkeypatch.setattr(chat, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user, factory() as other:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = configure(admin, ah)
        assert assign(admin, ah, 'vision.describe', [target]).status_code == 200
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        assert user.post(path+'/attachments', content=picture()).status_code == 403
        upload = user.post(path+'/attachments', headers=uh, content=picture())
        assert upload.status_code == 201, upload.text
        attachment = upload.json()
        image_url = path+'/attachments/'+attachment['id']
        assert user.get(image_url).headers['content-type'] == 'image/jpeg'
        assert user.get(path).json()['unused_attachments'] == [attachment]
        body = {'request_id': str(uuid4()), 'revision': 1, 'content': 'What shapes do you see?', 'attachment_ids': [attachment['id']]}
        assert user.post(path+'/turns', headers=uh, json=body).status_code == 409  # Text probe alone cannot qualify vision.
        assert not calls
        assert admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 2, 'vision': True}).json()['features'] == ['chat', 'streaming', 'vision']
        assert user.post(path+'/turns', headers=uh, json=body | {'attachment_ids': [str(uuid4())]}).status_code == 404
        assert user.post(path+'/turns', headers=uh, json=body | {'attachment_ids': [attachment['id']]*2}).status_code == 422
        assert user.post(path+'/turns', headers=uh, json=body | {'capability': 'code.implement'}).status_code == 409
        assert user.post(path+'/turns', headers=uh, json=body).status_code == 202
        done = wait_finished(user, path)
        assert done['runs'][-1]['capability_id'] == 'vision.describe'
        assert done['messages'][0]['attachments'] == [attachment]
        assert done['unused_attachments'] == []
        assert isinstance(calls[0][1][-1]['content'], list)
        assert calls[0][1][-1]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,')
        assert user.post(path+'/turns', headers=uh, json=body).status_code == 202
        assert len(calls) == 1
        assert user.post(path+'/turns', headers=uh, json=body | {'attachment_ids': []}).status_code == 409
        assert user.delete(image_url, headers=uh).status_code == 409
        assert user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': done['revision'], 'content': 'Which shape is blue?'}).status_code == 202
        followed = wait_finished(user, path)
        assert followed['runs'][-1]['capability_id'] == 'vision.describe'
        assert any(isinstance(m['content'], list) for m in calls[-1][1])
        other_path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        assert user.get(other_path+'/attachments/'+attachment['id']).status_code == 404
        assert user.post(other_path+'/turns', headers=uh, json=body | {'request_id': str(uuid4())}).status_code == 404
        with factory() as fresh:
            signin(fresh)
            assert fresh.get(path).json()['messages'] == followed['messages']
        other_subject = str(uuid4())
        monkeypatch.setattr(identity, 'verify_id_token', lambda *a: {'sub': other_subject, 'name': 'Other member'})
        monkeypatch.setattr(identity, 'token_request', lambda config, endpoint, data:
            {'active': True, 'sub': other_subject, 'iss': config.issuer} if endpoint == 'token/introspect' else
            {'id_token': 'OTHER FIXTURE', 'access_token': 'OTHER FIXTURE', 'refresh_token': 'OTHER FIXTURE', 'expires_in': 300})
        signin(other)
        from tests.integration.test_identity import approve_fixture_member
        approve_fixture_member(other, migration, settings)
        oh = csrf(other, settings.user_origin)
        assert other.get(image_url).status_code == 404
        assert other.post(path+'/attachments', headers=oh, content=picture()).status_code == 404
        with scoped_session(app, other.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM chat_attachments')).scalar_one() == 0


@pytest.mark.parametrize('cancel', [False, True], ids=['dispatch', 'cancel'])
def test_picture_steering_waits_for_drain_or_restores_unused_upload(bff, monkeypatch, cancel):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    monkeypatch.setattr(vision, 'probe', lambda *a: {'vision_probe': 'explicit-fixture'})
    entered, finish = threading.Event(), threading.Event()
    contexts = []

    def stream(*args, **kwargs):
        contexts.append(args[3])
        if len(contexts) == 1:
            entered.set()
            assert finish.wait(10)
        yield 'text', 'A red rectangle and a blue circle.'
        yield 'done', 'stop'

    monkeypatch.setattr(chat, 'chat_stream', stream)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = configure(admin, ah)
        assert admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 2, 'vision': True}).json()['state'] == 'ready'
        assert assign(admin, ah, 'vision.describe', [target]).status_code == 200
        signin(user)
        uh = csrf(user, settings.user_origin)
        owner = user.get('/api/v1/session').json()['id']
        path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        first = {'request_id': str(uuid4()), 'revision': 1, 'content': 'Tell me a story'}
        try:
            assert user.post(path+'/turns', headers=uh, json=first).status_code == 202
            assert entered.wait(5)
            upload = user.post(path+'/attachments', headers=uh, content=picture()).json()
            current = user.get(path).json()
            steering = {'request_id': str(uuid4()), 'revision': current['revision'], 'content': 'Describe this instead.', 'attachment_ids': [upload['id']], 'interrupt_run_id': first['request_id']}
            assert user.post(path+'/turns', headers=uh, json=steering).json()['status'] == 'queued'
            assert user.post(path+'/turns', headers=uh, json=steering | {'attachment_ids': []}).status_code == 409
            assert user.get(path).json()['unused_attachments'] == []
            assert user.delete(path+'/attachments/'+upload['id'], headers=uh).status_code == 409
            if cancel:
                assert user.post(path+'/pending/'+steering['request_id']+'/cancel', headers=uh).status_code == 200
                assert user.get(path).json()['unused_attachments'] == [upload]
        finally:
            finish.set()
        for _ in range(100):
            result = user.get(path).json()
            if not result['pending'] and all(run['status'] != 'running' for run in result['runs']):
                break
            time.sleep(.03)
        assert result['runs'][0]['status'] == 'cancelled'
        if cancel:
            assert len(contexts) == 1
            assert user.delete(path, headers=uh).status_code == 200
            with scoped_session(app, owner, settings.farm_id) as db:
                assert db.execute(text('SELECT count(*) FROM chat_attachments')).scalar_one() == 0
        else:
            assert len(contexts) == 2
            assert result['runs'][-1]['capability_id'] == 'vision.describe'
            assert result['messages'][-2]['attachments'] == [upload]
            assert contexts[-1][-1]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,')


def test_failed_vision_check_keeps_successfully_verified_text(bff, monkeypatch):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)

    def cannot_see(*args):
        from hearth.inference import ProviderError
        raise ProviderError('No visual input support')

    monkeypatch.setattr(vision, 'probe', cannot_see)
    with factory('admin') as admin:
        signin(admin)
        promote(admin, migration, settings)
        headers = csrf(admin, settings.admin_origin)
        target = configure(admin, headers)
        result = admin.post(f'/api/v1/providers/{target}/probe', headers=headers, json={'revision': 2, 'vision': True}).json()
        assert result['state'] == 'ready' and result['features'] == ['chat', 'streaming']
        assert 'Vision was not verified' in result['reason']


@pytest.mark.skipif(os.environ.get('HEARTH_LIVE_VISION') != '1', reason='Explicit real vision model test required.')
def test_live_qwen_understands_uploaded_pixels_and_restores(bff):
    url, model = configured_provider()
    factory, settings, _, migration, _ = bff
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Live vision fixture', 'base_url': url, 'model_id': model, 'local_only': True, 'allow_insecure_http': True, 'residency_policy': 'lmstudio_loaded'}).json()['id']
        probe = admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 1, 'vision': True}).json()
        assert probe['state'] == 'ready' and 'vision' in probe['features'], probe
        assert assign(admin, ah, 'vision.describe', [target]).status_code == 200
        signin(user)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        attachment = user.post(path+'/attachments', headers=uh, content=picture()).json()['id']
        sent = user.post(path+'/turns', headers=uh, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Briefly identify the two colored shapes and which side each is on.', 'attachment_ids': [attachment]})
        assert sent.status_code == 202, sent.text
        complete = wait_finished(user, path, 300)
        run = complete['runs'][-1]
        assert run['status'] == 'completed' and run['finish_reason'] == 'stop', json.dumps(run)
        answer = complete['messages'][-1]['content'].lower()
        assert all(word in answer for word in ['red', 'blue', 'left', 'right'])
        assert 'circle' in answer and ('rectangle' in answer or 'square' in answer)
        with factory() as fresh:
            signin(fresh)
            assert fresh.get(path).json()['messages'] == complete['messages']
            assert fresh.get(path+'/attachments/'+attachment).status_code == 200
        output = Path('.hearth/test-results/vision/2026-09-13')
        output.mkdir(parents=True, exist_ok=True)
        (output/'vision-fixture.png').write_bytes(picture())
        (output/'live-vision.json').write_text(json.dumps({'scope': 'Real remote Qwen, pixel challenge, uploaded synthetic image and restricted-role PostgreSQL/BFF APIs; explicit OIDC fixtures in disposable farm.', 'model': run['model_id'], 'capability': run['capability_id'], 'finish_reason': run['finish_reason'], 'answer': complete['messages'][-1]['content'], 'pixel_challenge_passed': True, 'restored_upload_and_reply': True}, indent=2), encoding='utf-8')
