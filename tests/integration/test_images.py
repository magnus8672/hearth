import hashlib
import io
import json
import os
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest
from hearth import image_transport
from hearth.contracts import ImageProviderInfo, ImageReceipt
from hearth.database import scoped_session
from PIL import Image
from sqlalchemy import text

from tests.integration.test_chat import configure, csrf, promote, setup
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases

MODEL = 'stabilityai/stable-diffusion-xl-base-1.0'
INFO = ImageProviderInfo(protocol='hearth.image.v1', model=MODEL, model_revision='fixture', manifest_sha256='a' * 64, shapes=['square'], steps=[20], job_cancellation=True, offline=True)


def receipt(data, state='completed'):
    return ImageReceipt(id=data.id, model=data.model, state=state, progress=20 if state == 'completed' else 1, steps=20, seed=data.seed, shape='square', width=1024, height=1024, execution_released=state != 'running', manifest_sha256='a' * 64, cancel_requested=state == 'cancelled')


def image_target(admin, headers):
    result = admin.post('/api/v1/providers', headers=headers, json={'name': 'Image fixture', 'base_url': 'http://127.0.0.1:1235', 'model_id': MODEL, 'api_key': 'fixture-controller', 'protocol': 'hearth.image.v1', 'local_only': True})
    assert result.status_code == 201, result.text
    target = result.json()
    probe = admin.post('/api/v1/providers/' + target['id'] + '/probe', headers=headers, json={'revision': 1})
    assert probe.json()['features'] == ['image.text_to_image', 'image.jobs'], probe.text
    return target['id']


def wait_image(user, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = user.get('/api/v1/images').json()['items'][0]
        if job['status'] != 'running':
            return job
        time.sleep(.02)
    raise AssertionError('Image job did not settle')


def test_private_image_artifact_persistence_idempotency_and_target_profile(bff, monkeypatch):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    calls = []
    png = io.BytesIO()
    Image.new('RGB', (1024, 1024), 'orange').save(png, format='PNG')
    artifact = png.getvalue()

    def render(url, key, config, data, observe=lambda value: False):
        calls.append(data)
        result = receipt(data).model_copy(update={'sha256': hashlib.sha256(artifact).hexdigest()})
        observe(result)
        return result, artifact

    monkeypatch.setattr(image_transport, 'information', lambda *args: INFO)
    monkeypatch.setattr(image_transport, 'render', render)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        target = image_target(admin, csrf(admin, settings.admin_origin))
        signin(user)
        headers = csrf(user, settings.user_origin)
        assert admin.get('/api/v1/images').status_code == 403
        assert user.get('/api/v1/image-targets').json()['items'][0]['ready'] is True
        data = {'target_id': target, 'request': {'id': str(uuid4()), 'model': MODEL, 'prompt': 'Private image prompt', 'seed': 42}}
        assert user.post('/api/v1/images', json=data).status_code == 403
        assert user.post('/api/v1/images', json=data | {'request': data['request'] | {'model': 'another'}}, headers=headers).status_code == 409
        assert user.post('/api/v1/images', json=data, headers=headers).status_code == 202
        job = wait_image(user)
        assert job['status'] == 'completed'
        path = '/api/v1/images/' + job['id'] + '/image'
        assert user.get(path).content == artifact
        assert user.get(path).headers['cache-control'] == 'no-store'
        assert user.post('/api/v1/images', json=data, headers=headers).status_code == 202
        assert len(calls) == 2  # One probe, one user job.
        assert user.post('/api/v1/images', json=data | {'request': data['request'] | {'seed': 43}}, headers=headers).status_code == 409
        assert user.get('/api/v1/images/' + str(uuid4()) + '/image').status_code == 404
        with factory() as reopened:
            signin(reopened)
            assert reopened.get(path).content == artifact
        with migration.connect() as db:
            other = db.execute(text('SELECT id FROM users WHERE farm_id=:farm AND subject<>:subject'), {'farm': settings.farm_id, 'subject': subject}).scalar_one()
        with scoped_session(app, other, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM image_jobs')).scalar_one() == 0


def test_image_cancel_waits_for_receipt_and_shares_chat_resource_group(bff, monkeypatch):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    entered, finish = threading.Event(), threading.Event()

    def render(url, key, config, data, observe=lambda value: False):
        if data.prompt.startswith('A small warm'):
            return receipt(data), b'probe fixture'
        observe(receipt(data, 'running'))
        entered.set()
        assert finish.wait(10)
        assert observe(receipt(data, 'running')) is True
        return receipt(data, 'cancelled'), None

    monkeypatch.setattr(image_transport, 'information', lambda *args: INFO)
    monkeypatch.setattr(image_transport, 'render', render)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        target = image_target(admin, ah)
        signin(user)
        headers = csrf(user, settings.user_origin)
        data = {'target_id': target, 'request': {'id': str(uuid4()), 'model': MODEL, 'prompt': 'A long image render', 'seed': 9}}
        try:
            assert user.post('/api/v1/images', json=data, headers=headers).status_code == 202
            assert entered.wait(5)
            chat = user.post('/api/v1/chats', headers=headers, json={}).json()
            assert user.post('/api/v1/chats/' + chat['id'] + '/turns', headers=headers, json={'request_id': str(uuid4()), 'content': 'No overlapping GPU work', 'revision': 1}).status_code == 409
            assert user.post('/api/v1/images/' + data['request']['id'] + '/cancel', headers=headers).status_code == 200
            assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'running'
        finally:
            finish.set()
        assert wait_image(user)['status'] == 'cancelled'
        assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'idle'


@pytest.mark.skipif(not os.environ.get('HEARTH_LIVE_IMAGE_PROVIDER'), reason='Live GPU image generation is explicitly opt-in.')
def test_live_image_provider_through_private_bff_and_database(bff):
    factory, settings, _, migration, _ = bff
    key = (Path('.hearth/image-provider/controller.key')).read_text(encoding='utf-8').strip()
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Explicit live image fixture', 'base_url': 'http://127.0.0.1:1235', 'model_id': MODEL, 'api_key': key, 'protocol': 'hearth.image.v1', 'local_only': True}).json()
        probe = admin.post('/api/v1/providers/' + target['id'] + '/probe', headers=ah, json={'revision': 1})
        assert probe.json()['state'] == 'ready', probe.text
        signin(user)
        headers = csrf(user, settings.user_origin)
        payload = {'target_id': target['id'], 'request': {'id': str(uuid4()), 'model': MODEL, 'prompt': 'A little friendly robot tending a fireplace in a cozy cottage, warm amber glow, painted storybook illustration', 'seed': 672, 'steps': 20, 'shape': 'square'}}
        assert user.post('/api/v1/images', headers=headers, json=payload).status_code == 202
        job = wait_image(user, 90)
        assert job['status'] == 'completed', job
        path = '/api/v1/images/' + job['id'] + '/image'
        artifact = user.get(path).content
        assert hashlib.sha256(artifact).hexdigest() == job['metadata']['sha256']
        with factory() as reopened:
            signin(reopened)
            assert reopened.get(path).content == artifact
        out = Path('evidence/images/2026-09-13')
        out.mkdir(parents=True, exist_ok=True)
        (out / 'bff-live-image.png').write_bytes(artifact)
        (out / 'bff-live-image.json').write_text(json.dumps({'scope': 'Real SDXL GPU jobs and authenticated local HTTP through admin/user BFF APIs and restricted PostgreSQL. Explicit OIDC fixtures in a disposable farm; no real user account modified.', 'probe_features': probe.json()['features'], 'metadata': job['metadata'], 'fresh_session_restores_artifact': True}, indent=2), encoding='utf-8')
