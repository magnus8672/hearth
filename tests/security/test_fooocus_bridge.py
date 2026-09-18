import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from runtimes.image.fooocus_bridge import Fooocus
from runtimes.image.hearth_image import create_app

TOKEN = 'explicit-image-test-key-with-no-real-authority'


def test_external_profile_preserves_host_peer_and_credential_boundaries(tmp_path):
    engine = SimpleNamespace()
    app = create_app(tmp_path, tmp_path, TOKEN, engine=engine, manifest_digest='a' * 64,
                     model='fooocus/juggernaut-xl-v8', revision='test-profile',
                     allowed_hosts=['media-worker.test'], allowed_controllers=['testclient'])
    with TestClient(app, base_url='http://media-worker.test') as client:
        assert client.get('/v1/image-provider').status_code == 401
        client.headers['Authorization'] = 'Bearer ' + TOKEN
        assert client.get('/v1/image-provider').json()['model'] == 'fooocus/juggernaut-xl-v8'
        assert client.get('/v1/image-provider', headers={'Host': 'untrusted.test'}).status_code == 400
        assert client.get('/v1/image-provider', headers={'Origin': 'http://media-worker.test'}).status_code == 401
    app = create_app(tmp_path, tmp_path, TOKEN, engine=engine, manifest_digest='a' * 64,
                     allowed_controllers=['10.20.30.10'])
    with TestClient(app) as client:
        assert client.get('/v1/image-provider', headers={'Authorization': 'Bearer ' + TOKEN,
                           'X-Forwarded-For': '10.20.30.10'}).status_code == 403


def test_bridge_release_requires_worker_ack_and_cleans_only_its_temp_outputs(tmp_path):
    temp = tmp_path / 'temp'
    temp.mkdir()
    image, unrelated = temp / 'generated.png', tmp_path / 'unrelated.png'
    image.write_bytes(b'fixture')
    unrelated.write_bytes(b'keep')
    bridge = Fooocus(SimpleNamespace(modules=SimpleNamespace(config=SimpleNamespace(temp_path=str(temp)))))
    bridge.task = SimpleNamespace(hearth_released=threading.Event(), results=[str(image), str(unrelated)])
    with pytest.raises(RuntimeError, match='uncertain'):
        bridge.release()
    assert image.exists()
    bridge.task.hearth_released.set()
    bridge.release()
    assert not image.exists() and unrelated.read_bytes() == b'keep'


def test_custom_profile_cannot_fall_back_to_unrelated_sdxl_engine(tmp_path):
    with pytest.raises(RuntimeError, match='explicit engine'):
        create_app(tmp_path, tmp_path, TOKEN, manifest_digest='a' * 64, model='other-model')
