import threading

from hearth import image_queue, image_transport, provider_health

from tests.integration.test_chat import csrf, promote, setup
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_images import image_target
from tests.integration.test_postgres import databases as databases
from tests.integration.test_worker_queue import adopt, fixture_provider, report, request


def test_cancel_during_readiness_recheck_never_dispatches(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    fixture_provider(monkeypatch)
    monkeypatch.setattr(image_queue.ImageQueue, 'run', lambda self: self.stop.wait())
    entered, proceed = threading.Event(), threading.Event()

    def check(*args):
        entered.set()
        assert proceed.wait(10)

    def forbidden(*args):
        raise AssertionError('Cancelled job reached inference')

    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        target = image_target(admin, csrf(admin, settings.admin_origin))
        node, token, pool = adopt(migration, settings, target, paused=False)
        assert admin.post(f'/api/v1/worker-control/{node}/poll', headers={'Authorization': 'Bearer ' + token}, json=report()).status_code == 200
        monkeypatch.setattr(provider_health, 'check_connection', check)
        monkeypatch.setattr(image_transport, 'render', forbidden)
        signin(user)
        uh = csrf(user, settings.user_origin)
        job = request(target)
        assert user.post('/api/v1/images', headers=uh, json=job).status_code == 202
        admitted = image_queue.claim(app, settings, pool)
        assert admitted
        execution = threading.Thread(target=image_queue.execute_queued, args=(app, settings, *admitted))
        execution.start()
        try:
            assert entered.wait(5)
            assert user.post('/api/v1/images/' + job['request']['id'] + '/cancel', headers=uh).status_code == 200
        finally:
            proceed.set()
            execution.join(10)
        assert not execution.is_alive()
        assert user.get('/api/v1/images').json()['items'][0]['status'] == 'cancelled'
        assert admin.get('/api/v1/providers').json()['items'][0]['execution_state'] == 'idle'
