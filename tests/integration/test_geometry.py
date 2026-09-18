import base64
import hashlib
import io
import time
from uuid import UUID, uuid4

from hearth import geometry_transport, identity, image_queue
from hearth.contracts import GeometryProviderInfo, GeometryReceipt
from hearth.database import scoped_session
from hearth.geometry_probe import reference
from PIL import Image
from sqlalchemy import text

from tests.integration.test_chat import csrf, promote, setup
from tests.integration.test_identity import approve_fixture_member, signin
from tests.integration.test_identity import bff as bff
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
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Geometry fixture', 'base_url': 'http://127.0.0.1:1236', 'model_id': INFO.model, 'api_key': 'fixture', 'protocol': INFO.protocol, 'local_only': True}).json()['id']
        probe = admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 1})
        assert probe.json()['features'] == ['geometry.image_to_3d', 'geometry.jobs'], probe.text
        signin(user)
        uh = csrf(user, settings.user_origin)
        # A valid 1.7 MiB PNG exercises the base64 envelope beyond the ordinary
        # 1 MiB request limit
        # Tiny probe images did not cover real uploads.
        buffer = io.BytesIO()
        Image.new('RGB', (960, 600), '#e99044').save(buffer, format='PNG', compress_level=0)
        image = buffer.getvalue()
        assert 1_700_000 < len(image) < 1_800_000
        data = {'name': 'Fixture model', 'target_id': target, 'request': {'id': str(uuid4()), 'model': INFO.model, 'image_sha256': hashlib.sha256(image).hexdigest()}, 'image': base64.b64encode(image).decode()}
        assert user.post('/api/v1/geometry', json=data).status_code == 403
        assert user.post('/api/v1/geometry', headers=uh, json=data).status_code == 202
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = user.get('/api/v1/geometry').json()['items'][0]
            if job['status'] == 'completed':
                break
            time.sleep(.03)
        assert job['status'] == 'completed', job
        assert job['metadata']['triangles'] == 1
        assert job['name'] == 'Fixture model' and job['has_thumbnail']
        with scoped_session(engine, UUID(user.get('/api/v1/session').json()['id']), settings.farm_id) as db:
            assert db.execute(text('SELECT source_image FROM geometry_jobs WHERE id=:id'), {'id': job['id']}).scalar_one() is None
        assert user.post('/api/v1/geometry', headers=uh, json=data).status_code == 202
        assert len(calls) == 2
        path = f"/api/v1/geometry/{job['id']}"
        assert user.get(path+'/model').content == model
        preview = user.get(path+'/thumbnail')
        assert preview.status_code == 200 and preview.headers['content-type'] == 'image/png'
        assert preview.headers['cache-control'] == 'no-store'
        assert preview.headers['x-content-type-options'] == 'nosniff'
        with Image.open(io.BytesIO(preview.content)) as thumbnail:
            assert thumbnail.size == (320, 200)
        assert len(preview.content) <= 524288
        assert user.patch(path, json={'name': 'Renamed ship'}).status_code == 403
        assert user.patch(path, headers=uh, json={'name': '  Renamed ship  '}).json()['name'] == 'Renamed ship'
        assert user.post('/api/v1/geometry', headers=uh, json=data).status_code == 202
        assert user.get('/api/v1/geometry').json()['items'][0]['name'] == 'Renamed ship'
        assert admin.get(path+'/thumbnail').status_code == 403
        assert admin.patch(path, headers=ah, json={'name': 'Not mine'}).status_code == 403
        assert admin.get(path+'/model').status_code == 403
        with migration.connect() as db:
            other = db.execute(text('SELECT id FROM users WHERE farm_id=:farm AND subject<>:subject'), {'farm': settings.farm_id, 'subject': subject}).scalar_one()
        with scoped_session(engine, other, settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM geometry_jobs')).scalar_one() == 0
        assert user.delete(path, headers=uh).status_code == 200
        assert user.get(path+'/model').status_code == 404
        assert user.get(path+'/thumbnail').status_code == 404
        assert user.patch(path, headers=uh, json={'name': 'Deleted'}).status_code == 404
        with scoped_session(engine, UUID(user.get('/api/v1/session').json()['id']), settings.farm_id) as db:
            assert db.execute(text('SELECT thumbnail FROM geometry_jobs WHERE id=:id'), {'id': job['id']}).scalar_one() is None
        assert user.post('/api/v1/geometry', headers=uh, json=data).status_code == 410


def test_geometry_waiting_cancel_and_model_validation(bff, monkeypatch):
    monkeypatch.setattr(image_queue.ImageQueue, 'run', lambda self: self.stop.wait())
    factory, settings, engine, migration, _ = setup(bff, monkeypatch)
    monkeypatch.setattr(geometry_transport, 'information', lambda *args: INFO)
    monkeypatch.setattr(geometry_transport, 'render', lambda url, key, settings, data, image, observe=lambda value: False: (GeometryReceipt(**data.model_dump(), state='completed', progress=100, manifest_sha256='a'*64, execution_released=True, cancel_requested=False), triangle()))
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Geometry fixture', 'base_url': 'http://127.0.0.1:1236', 'model_id': INFO.model, 'protocol': INFO.protocol, 'local_only': True}).json()['id']
        assert admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 1}).json()['state'] == 'ready'
        signin(user)
        uh = csrf(user, settings.user_origin)
        image = reference()
        data = {'name': 'Fixture model', 'target_id': target, 'request': {'id': str(uuid4()), 'model': INFO.model, 'image_sha256': hashlib.sha256(image).hexdigest()}, 'image': base64.b64encode(image).decode()}
        missing_name = {key: value for key, value in data.items() if key != 'name'}
        assert user.post('/api/v1/geometry', headers=uh, json=missing_name).status_code == 422
        for bad_name in ['', '   ', '\t\n', 'x' * 121]:
            assert user.post('/api/v1/geometry', headers=uh, json=data | {'name': bad_name}).status_code == 422
        assert user.get('/api/v1/geometry').json()['items'] == []
        assert user.post('/api/v1/geometry', headers=uh, json=data | {'request': data['request'] | {'resolution': 1024}}).status_code == 409
        assert user.post('/api/v1/geometry', headers=uh, json=data).status_code == 202
        path = f"/api/v1/geometry/{data['request']['id']}"
        assert user.delete(path, headers=uh).status_code == 409
        assert user.post(path+'/cancel', headers=uh).status_code == 200
        assert user.get('/api/v1/geometry').json()['items'][0]['status'] == 'cancelled'
        saved_preview = user.get(path+'/thumbnail').content
        for bad_name in ['', '   ', '\t\n', 'x' * 121]:
            assert user.patch(path, headers=uh, json={'name': bad_name}).status_code == 422
        owner = UUID(user.get('/api/v1/session').json()['id'])
        # Legacy completed rows have neither catalog column populated.
        with scoped_session(engine, owner, settings.farm_id) as db:
            db.execute(text('UPDATE geometry_jobs SET name=NULL,thumbnail=NULL WHERE id=:id'), {'id': data['request']['id']})
        legacy = user.get('/api/v1/geometry').json()['items'][0]
        assert legacy['name'] == 'Model ' + data['request']['id'][:8] and not legacy['has_thumbnail']
        assert user.get(path+'/thumbnail').status_code == 404
        assert user.patch(path, headers=uh, json={'name': 'Old ship'}).status_code == 200
        assert user.get('/api/v1/geometry').json()['items'][0]['name'] == 'Old ship'
        with scoped_session(engine, owner, settings.farm_id) as db:
            db.execute(text('UPDATE geometry_jobs SET thumbnail=:thumbnail WHERE id=:id'), {'id': data['request']['id'], 'thumbnail': saved_preview})
        assert user.get(path+'/thumbnail').status_code == 200
        other_subject = str(uuid4())
        monkeypatch.setattr(identity, 'token_request', lambda config, endpoint, values: {'active': True, 'sub': other_subject, 'iss': config.issuer} if endpoint == 'token/introspect' else {'id_token': 'FIXTURE', 'access_token': 'FIXTURE', 'refresh_token': 'FIXTURE', 'expires_in': 300})
        monkeypatch.setattr(identity, 'verify_id_token', lambda *args: {'sub': other_subject, 'name': 'Other member'})
        with factory() as other:
            signin(other)
            approve_fixture_member(other, migration, settings)
            oh = csrf(other, settings.user_origin)
            assert other.get('/api/v1/geometry').json()['items'] == []
            assert other.get(path+'/thumbnail').status_code == 404
            assert other.patch(path, headers=oh, json={'name': 'Stolen title'}).status_code == 404
        # Farm scope is enforced even if the principal ID is known.
        with scoped_session(engine, owner, uuid4()) as db:
            assert db.execute(text('SELECT count(*) FROM geometry_jobs')).scalar_one() == 0


def test_image_and_geometry_share_one_queue_and_switch_only_after_release(bff, monkeypatch):
    import json

    from hearth import workers

    from tests.integration.test_images import image_target
    from tests.integration.test_worker_queue import adopt, fixture_provider
    from tests.integration.test_worker_queue import request as image_request
    monkeypatch.setattr(image_queue.ImageQueue, 'run', lambda self: self.stop.wait())
    factory, settings, engine, migration, _ = setup(bff, monkeypatch)
    fixture_provider(monkeypatch)
    monkeypatch.setattr(geometry_transport, 'information', lambda *args: INFO)
    monkeypatch.setattr(geometry_transport, 'render', lambda url, key, settings, data, image, observe=lambda value: False: (GeometryReceipt(**data.model_dump(), state='completed', progress=100, manifest_sha256='a'*64, execution_released=True, cancel_requested=False), triangle()))
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        picture = image_target(admin, ah)
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Geometry fixture', 'base_url': 'http://127.0.0.1:1236', 'model_id': INFO.model, 'protocol': INFO.protocol, 'local_only': True}).json()['id']
        assert admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 1}).json()['state'] == 'ready'
        node, _, pool = adopt(migration, settings, picture, paused=False)
        with scoped_session(migration, workers.SYSTEM, settings.farm_id) as db:
            connection = db.execute(text('SELECT connection_id FROM inference_targets WHERE id=:id'), {'id': target}).scalar_one()
            db.execute(text("UPDATE managed_workers SET policy='shared',seen_at=now(),state='ready',observed_revision=revision,ready_service='fooocus',services=services || CAST(:service AS jsonb) WHERE id=:id"), {'id': node, 'service': json.dumps({'trellis': {'name': 'TRELLIS', 'connection_id': str(connection)}})})
        signin(user)
        uh = csrf(user, settings.user_origin)
        image = reference()
        data = {'name': 'Fixture model', 'target_id': target, 'request': {'id': str(uuid4()), 'model': INFO.model, 'image_sha256': hashlib.sha256(image).hexdigest()}, 'image': base64.b64encode(image).decode()}
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


def test_three_backends_keep_fairness_and_target_identity(bff, monkeypatch):
    import json

    from hearth import workers

    from tests.integration.test_images import image_target
    from tests.integration.test_worker_queue import adopt, fixture_provider
    from tests.integration.test_worker_queue import request as image_request

    monkeypatch.setattr(image_queue.ImageQueue, 'run', lambda self: self.stop.wait())
    factory, settings, engine, migration, subject = setup(bff, monkeypatch)
    fixture_provider(monkeypatch)
    h3d = INFO.model_copy(update={'model': 'hunyuan3d/2.0', 'manifest_sha256': 'b'*64})
    monkeypatch.setattr(geometry_transport, 'information', lambda url, *args: h3d if ':1238' in url else INFO)
    executed = []
    def render(url, key, settings, data, image, observe=lambda value: False):
        expected = h3d if ':1238' in url else INFO
        assert data.model == expected.model
        executed.append(data.model)
        return GeometryReceipt(**data.model_dump(), state='completed', progress=100, manifest_sha256=expected.manifest_sha256, execution_released=True, cancel_requested=False), triangle()
    monkeypatch.setattr(geometry_transport, 'render', render)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        picture = image_target(admin, ah)
        targets = {}
        for service, info, port in [('trellis', INFO, 1236), ('hunyuan', h3d, 1238)]:
            response = admin.post('/api/v1/providers', headers=ah, json={'name': service, 'base_url': f'http://127.0.0.1:{port}', 'model_id': info.model, 'protocol': info.protocol, 'local_only': True})
            assert response.status_code == 201
            targets[service] = response.json()['id']
            assert admin.post(f"/api/v1/providers/{targets[service]}/probe", headers=ah, json={'revision': 1}).json()['state'] == 'ready'
        executed.clear()
        route = admin.put('/api/v1/capability-routes/geometry.generate', headers=ah, json={'revision': 1, 'targets': [
            {'target_id': targets['trellis'], 'priority': 1}, {'target_id': targets['hunyuan'], 'priority': 0}]})
        assert route.status_code == 200
        assert [item['target_id'] for item in route.json()['targets']] == [targets['trellis'], targets['hunyuan']]
        node, _, pool = adopt(migration, settings, picture, paused=False)
        with scoped_session(migration, workers.SYSTEM, settings.farm_id) as db:
            services = {service: {'name': service, 'connection_id': str(db.execute(text('SELECT connection_id FROM inference_targets WHERE id=:id'), {'id': target}).scalar_one())} for service, target in targets.items()}
            db.execute(text("UPDATE managed_workers SET policy='shared',seen_at=now(),state='ready',observed_revision=revision,ready_service='fooocus',services=services || CAST(:services AS jsonb) WHERE id=:id"), {'id': node, 'services': json.dumps(services)})
        signin(user)
        uh = csrf(user, settings.user_origin)
        image = reference()
        def submit(client, headers, service):
            info = h3d if service == 'hunyuan' else INFO
            data = {'name': service, 'target_id': targets[service], 'request': {'id': str(uuid4()), 'model': info.model, 'image_sha256': hashlib.sha256(image).hexdigest()}, 'image': base64.b64encode(image).decode()}
            assert client.post('/api/v1/geometry', headers=headers, json=data).status_code == 202
            return data['request']['id']
        assert user.post('/api/v1/images', headers=uh, json=image_request(picture)).status_code == 202
        trellis = submit(user, uh, 'trellis')
        other_subject = str(uuid4())
        monkeypatch.setattr(identity, 'verify_id_token', lambda *args: {'sub': other_subject, 'name': 'Second member'})
        monkeypatch.setattr(identity, 'token_request', lambda config, endpoint, data: {'active': True, 'sub': subject if data.get('token') == 'EXPLICIT PROVIDER FIXTURE' else other_subject, 'iss': config.issuer} if endpoint == 'token/introspect' else {'id_token': 'FIXTURE', 'access_token': 'SECOND', 'refresh_token': 'FIXTURE', 'expires_in': 300})
        with factory() as other:
            signin(other)
            approve_fixture_member(other, migration, settings)
            oh = csrf(other, settings.user_origin)
            hunyuan = submit(other, oh, 'hunyuan')
            first = image_queue.claim(engine, settings, pool)
            assert first[1]['protocol'] == 'hearth.image.v1'
            assert image_queue.claim(engine, settings, pool) is None
            image_queue.execute_queued(engine, settings, *first)
            # A different owner's newer Hunyuan job wins over the older TRELLIS
            # job. Fairness is decided before selecting the resident backend.
            for service, expected in [('hunyuan', hunyuan), ('trellis', trellis)]:
                claimed = image_queue.claim(engine, settings, pool)
                assert str(claimed[2].id) == expected
                with scoped_session(migration, workers.SYSTEM, settings.farm_id) as db:
                    worker = workers.for_pool(db, pool)
                    assert worker['desired_service'] == service
                    assert worker['ready_service'] != service
                    db.execute(text("UPDATE managed_workers SET ready_service=:service,state='ready',observed_revision=revision,seen_at=now() WHERE id=:id"), {'id': node, 'service': service})
                assert image_queue.claim(engine, settings, pool) is None
                image_queue.execute_queued(engine, settings, *claimed)
            assert executed == [h3d.model, INFO.model]
            assert other.get('/api/v1/geometry').json()['items'][0]['status'] == 'completed'
            assert user.get('/api/v1/geometry').json()['items'][0]['status'] == 'completed'
