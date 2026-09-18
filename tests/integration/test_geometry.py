import base64
import hashlib
import time
from uuid import uuid4

from hearth import geometry_transport, image_queue
from hearth.contracts import GeometryProviderInfo, GeometryReceipt
from hearth.database import scoped_session
from hearth.geometry_probe import reference
from sqlalchemy import text

from tests.integration.test_chat import csrf, promote, setup
from tests.integration.test_identity import bff as bff, signin
from tests.integration.test_postgres import databases as databases
from tests.security.test_geometry import triangle

INFO = GeometryProviderInfo(protocol='hearth.geometry.v1', model='trellis2/fixture', model_revision='fixture', manifest_sha256='a'*64, offline=True, job_cancellation=True, resolutions=[512])


def test_geometry_private_queue_artifact_and_delete(bff, monkeypatch):
    factory, settings, engine, migration, subject = setup(bff, monkeypatch)
    model = triangle()
    calls = []
    def render(url, key, settings, data, image, observe=lambda value: False):
        calls.append(data.id)
        receipt = GeometryReceipt(**data.model_dump(), state='completed', progress=100, sha256=hashlib.sha256(model).hexdigest(), manifest_sha256='a'*64, execution_released=True, cancel_requested=False)
        observe(receipt)
        return receipt, model
    monkeypatch.setattr(geometry_transport, 'information', lambda *args: INFO)
    monkeypatch.setattr(geometry_transport, 'render', render)
    with factory('admin') as admin, factory() as user:
        signin(admin); promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Geometry fixture', 'base_url': 'http://127.0.0.1:1236', 'model_id': INFO.model, 'api_key': 'fixture', 'protocol': INFO.protocol, 'local_only': True}).json()['id']
        probe = admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 1})
        assert probe.json()['features'] == ['geometry.image_to_3d', 'geometry.jobs'], probe.text
        signin(user); uh = csrf(user, settings.user_origin)
        image = reference()
        data = {'target_id': target, 'request': {'id': str(uuid4()), 'model': INFO.model, 'image_sha256': hashlib.sha256(image).hexdigest()}, 'image': base64.b64encode(image).decode()}
        assert user.post('/api/v1/geometry', json=data).status_code == 403
        assert user.post('/api/v1/geometry', headers=uh, json=data).status_code == 202
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = user.get('/api/v1/geometry').json()['items'][0]
            if job['status'] == 'completed': break
            time.sleep(.03)
        assert job['status'] == 'completed', job
        assert job['metadata']['triangles'] == 1
        assert user.post('/api/v1/geometry', headers=uh, json=data).status_code == 202
        assert len(calls) == 2
        path = f"/api/v1/geometry/{job['id']}"
        assert user.get(path+'/model').content == model
        assert admin.get(path+'/model').status_code == 403
        with migration.connect() as db:
            other = db.execute(text('SELECT id FROM users WHERE farm_id=:farm AND subject<>:subject'), {'farm': settings.farm_id, 'subject': subject}).scalar_one()
        with scoped_session(engine, other, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM geometry_jobs')).scalar_one() == 0
        assert user.delete(path, headers=uh).status_code == 200
        assert user.get(path+'/model').status_code == 404
        assert user.post('/api/v1/geometry', headers=uh, json=data).status_code == 410


def test_geometry_waiting_cancel_and_model_validation(bff, monkeypatch):
    monkeypatch.setattr(image_queue.ImageQueue, 'run', lambda self: self.stop.wait())
    factory, settings, engine, migration, _ = setup(bff, monkeypatch)
    monkeypatch.setattr(geometry_transport, 'information', lambda *args: INFO)
    monkeypatch.setattr(geometry_transport, 'render', lambda url, key, settings, data, image, observe=lambda value: False: (GeometryReceipt(**data.model_dump(), state='completed', progress=100, manifest_sha256='a'*64, execution_released=True, cancel_requested=False), triangle()))
    with factory('admin') as admin, factory() as user:
        signin(admin); promote(admin, migration, settings); ah = csrf(admin, settings.admin_origin)
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Geometry fixture', 'base_url': 'http://127.0.0.1:1236', 'model_id': INFO.model, 'protocol': INFO.protocol, 'local_only': True}).json()['id']
        assert admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 1}).json()['state'] == 'ready'
        signin(user); uh = csrf(user, settings.user_origin); image = reference()
        data = {'target_id': target, 'request': {'id': str(uuid4()), 'model': INFO.model, 'image_sha256': hashlib.sha256(image).hexdigest()}, 'image': base64.b64encode(image).decode()}
        assert user.post('/api/v1/geometry', headers=uh, json=data | {'request': data['request'] | {'resolution': 1024}}).status_code == 409
        assert user.post('/api/v1/geometry', headers=uh, json=data).status_code == 202
        path = f"/api/v1/geometry/{data['request']['id']}"
        assert user.delete(path, headers=uh).status_code == 409
        assert user.post(path+'/cancel', headers=uh).status_code == 200
        assert user.get('/api/v1/geometry').json()['items'][0]['status'] == 'cancelled'


def test_image_and_geometry_share_one_queue_and_switch_only_after_release(bff, monkeypatch):
    import json
    from hearth import workers
    from tests.integration.test_images import image_target
    from tests.integration.test_worker_queue import fixture_provider, adopt, request as image_request
    monkeypatch.setattr(image_queue.ImageQueue, 'run', lambda self: self.stop.wait())
    factory, settings, engine, migration, _ = setup(bff, monkeypatch)
    fixture_provider(monkeypatch)
    monkeypatch.setattr(geometry_transport, 'information', lambda *args: INFO)
    monkeypatch.setattr(geometry_transport, 'render', lambda url, key, settings, data, image, observe=lambda value: False: (GeometryReceipt(**data.model_dump(), state='completed', progress=100, manifest_sha256='a'*64, execution_released=True, cancel_requested=False), triangle()))
    with factory('admin') as admin, factory() as user:
        signin(admin); promote(admin, migration, settings); ah = csrf(admin, settings.admin_origin)
        picture = image_target(admin, ah)
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Geometry fixture', 'base_url': 'http://127.0.0.1:1236', 'model_id': INFO.model, 'protocol': INFO.protocol, 'local_only': True}).json()['id']
        assert admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 1}).json()['state'] == 'ready'
        node, _, pool = adopt(migration, settings, picture, paused=False)
        with scoped_session(migration, workers.SYSTEM, settings.farm_id) as db:
            connection = db.execute(text('SELECT connection_id FROM inference_targets WHERE id=:id'), {'id': target}).scalar_one()
            db.execute(text("UPDATE managed_workers SET policy='shared',seen_at=now(),state='ready',observed_revision=revision,ready_service='fooocus',services=services || CAST(:service AS jsonb) WHERE id=:id"), {'id': node, 'service': json.dumps({'trellis': {'name': 'TRELLIS', 'connection_id': str(connection)}})})
        signin(user); uh = csrf(user, settings.user_origin)
        image = reference()
        data = {'target_id': target, 'request': {'id': str(uuid4()), 'model': INFO.model, 'image_sha256': hashlib.sha256(image).hexdigest()}, 'image': base64.b64encode(image).decode()}
        assert user.post('/api/v1/images', headers=uh, json=image_request(picture)).status_code == 202
        assert user.post('/api/v1/geometry', headers=uh, json=data).status_code == 202
        first = image_queue.claim(engine, settings, pool)
        assert first[1]['protocol'] == 'hearth.image.v1'
        assert image_queue.claim(engine, settings, pool) is None
        image_queue.execute_queued(engine, settings, *first)
        second = image_queue.claim(engine, settings, pool)
        assert second[1]['protocol'] == 'hearth.geometry.v1'
        with scoped_session(migration, workers.SYSTEM, settings.farm_id) as db:
            worker = workers.for_pool(db, pool)
            assert worker['desired_service'] == 'trellis' and worker['revision'] == 2
            assert worker['ready_service'] == 'fooocus'
            assert not workers.ready(worker, connection)
            db.execute(text("UPDATE managed_workers SET ready_service='trellis',state='ready',observed_revision=revision,seen_at=now() WHERE id=:id"), {'id': node})
        image_queue.execute_queued(engine, settings, *second)
        assert user.get('/api/v1/geometry').json()['items'][0]['status'] == 'completed'
        with scoped_session(engine, workers.SYSTEM, settings.farm_id) as db:
            assert db.execute(text('SELECT active_run_id FROM provider_pools WHERE id=:id'), {'id': pool}).scalar_one() is None
