from uuid import UUID, uuid4

from hearth import identity, image_queue, workers
from hearth.database import scoped_session
from hearth.providers import release_pool
from sqlalchemy import text

from tests.integration.test_chat import csrf, promote, setup
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_images import MODEL, image_target
from tests.integration.test_postgres import databases as databases
from tests.integration.test_worker_queue import fixture_provider, request


def test_queue_fairness_and_independent_gpu_admission(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    fixture_provider(monkeypatch)
    monkeypatch.setattr(image_queue.ImageQueue, 'run', lambda self: self.stop.wait())
    with factory('admin') as admin, factory() as first:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = image_target(admin, ah)
        other = admin.post('/api/v1/providers', headers=ah, json={'name': 'Independent GPU', 'base_url': 'http://127.0.0.1:1236', 'model_id': MODEL, 'protocol': 'hearth.image.v1', 'local_only': True, 'resource_pool': 'GPU two'}).json()['id']
        assert admin.post('/api/v1/providers/' + other + '/probe', headers=ah, json={'revision': 1}).status_code == 200
        signin(first)
        fh = csrf(first, settings.user_origin)
        jobs = [request(target), request(target), request(other)]
        for data in jobs:
            assert first.post('/api/v1/images', headers=fh, json=data).status_code == 202
        with scoped_session(app, workers.SYSTEM, settings.farm_id) as db:
            pools = dict(db.execute(text('SELECT id,resource_pool_id FROM inference_targets')).all())
        admitted = image_queue.claim(app, settings, pools[UUID(target)])
        independent = image_queue.claim(app, settings, pools[UUID(other)])
        assert admitted and independent
        assert str(admitted[2].id) == jobs[0]['request']['id']
        assert str(independent[2].id) == jobs[2]['request']['id']
        subject = str(uuid4())
        monkeypatch.setattr(identity, 'verify_id_token', lambda *args: {'sub': subject, 'name': 'Another member'})
        token_request = identity.token_request
        monkeypatch.setattr(identity, 'token_request', lambda config, endpoint, data: token_request(config, endpoint, data) | ({'sub': subject} if endpoint == 'token/introspect' else {}))
        with factory() as second:
            signin(second)
            next_job = request(target)
            assert second.post('/api/v1/images', headers=csrf(second, settings.user_origin), json=next_job).status_code == 202
            assert len(second.get('/api/v1/images').json()['items']) == 1
            with scoped_session(app, workers.SYSTEM, settings.farm_id) as db:
                release_pool(db, pools[UUID(target)], admitted[2].id)
            next_admitted = image_queue.claim(app, settings, pools[UUID(target)])
            assert next_admitted and str(next_admitted[2].id) == next_job['request']['id']
