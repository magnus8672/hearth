import threading
import time
from uuid import uuid4

from fastapi.testclient import TestClient

from runtimes.image.hearth_image import Cancelled, create_app

TOKEN = 'explicit-runtime-test-credential-not-a-real-secret'


class Engine:
    def __init__(self):
        self.calls = 0
        self.entered, self.finish = threading.Event(), threading.Event()
        self.released = False

    def generate(self, data, cancelled, progress, output):
        self.calls += 1
        self.entered.set()
        assert self.finish.wait(5)
        if cancelled():
            raise Cancelled()
        progress(data.steps)
        output.write_bytes(b'explicit fixture bytes')

    def release(self):
        self.released = True


def test_runtime_auth_bounded_body_idempotency_and_scoped_cancellation(tmp_path):
    engine = Engine()
    app = create_app(tmp_path, tmp_path, TOKEN, engine=engine, manifest_digest='fixture')
    with TestClient(app) as client:
        assert client.get('/v1/image-provider').status_code == 401
        client.headers['Authorization'] = 'Bearer ' + TOKEN
        assert client.get('/v1/image-provider', headers={'Origin': 'https://malicious.example'}).status_code == 401
        assert client.post('/v1/image-jobs', content=b'x' * 17000).status_code == 413
        data = {'id': str(uuid4()), 'model': 'stabilityai/stable-diffusion-xl-base-1.0', 'prompt': 'A cabin', 'seed': 7}
        assert client.post('/v1/image-jobs', json=data | {'model_path': 'untrusted-file'}).status_code == 422
        try:
            assert client.post('/v1/image-jobs', json=data).status_code == 202
            assert engine.entered.wait(3)
            assert client.post('/v1/image-jobs', json=data).status_code == 202
            assert client.post('/v1/image-jobs', json=data | {'prompt': 'Different'}).status_code == 409
            assert client.post('/v1/image-jobs', json=data | {'id': str(uuid4())}).status_code == 409
            path = '/v1/image-jobs/' + data['id']
            assert client.get(path + '/image').status_code == 409
            assert client.post('/v1/image-jobs/' + str(uuid4()) + '/cancel').status_code == 404
            assert client.get(path).json()['cancel_requested'] is False
            assert client.post(path + '/cancel').json()['cancel_requested'] is True
            assert client.get(path).json()['execution_released'] is False
        finally:
            engine.finish.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = client.get(path).json()
            if result['execution_released']:
                break
            time.sleep(.01)
        assert result['state'] == 'cancelled'
        assert engine.released and engine.calls == 1
        assert client.get(path + '/image').status_code == 409
    # Restart preserves the old cancelled receipt and cannot replay it.
    replacement = Engine()
    with TestClient(create_app(tmp_path, tmp_path, TOKEN, engine=replacement, manifest_digest='fixture')) as client:
        client.headers['Authorization'] = 'Bearer ' + TOKEN
        assert client.post('/v1/image-jobs', json=data).json()['state'] == 'cancelled'
        assert replacement.calls == 0
