"""Opt-in real GPU qualification with synthetic identities in isolated storage."""
import base64
import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest
from hearth.geometry_probe import reference
from hearth.geometry_validation import validate_glb

from tests.integration.test_chat import csrf, promote
from tests.integration.test_identity import bff as bff, signin
from tests.integration.test_postgres import databases as databases


@pytest.mark.skipif(not os.environ.get('HEARTH_LIVE_GEOMETRY'), reason='Requires exclusive operator reservation of the GPU.')
def test_geometry_real_private_queue_cancel_and_export(bff):
    factory, settings, _, migration, _ = bff
    config = json.loads(Path('.hearth/trellis-live-provider.json').read_text())
    with factory('admin') as admin, factory() as user:
        signin(admin); promote(admin, migration, settings); ah = csrf(admin, settings.admin_origin)
        result = admin.post('/api/v1/providers', headers=ah, json={'name': 'Geometry qualification', 'base_url': config['base_url'], 'model_id': config['model'], 'api_key': config['key'], 'tls_ca_pem': config['ca'], 'protocol': 'hearth.geometry.v1', 'local_only': True})
        assert result.status_code == 201, result.text
        target = result.json()['id']
        probe = admin.post(f'/api/v1/providers/{target}/probe', headers=ah, json={'revision': 1})
        assert probe.json()['state'] == 'ready', probe.text
        signin(user); uh = csrf(user, settings.user_origin); image = reference()
        def submit(seed):
            job = str(uuid4())
            result = user.post('/api/v1/geometry', headers=uh, json={'target_id': target, 'request': {'id': job, 'model': config['model'], 'image_sha256': hashlib.sha256(image).hexdigest(), 'seed': seed}, 'image': base64.b64encode(image).decode()})
            assert result.status_code == 202, result.text
            return job
        def wait(job, wanted, timeout=180):
            until = time.monotonic() + timeout
            while time.monotonic() < until:
                items = user.get('/api/v1/geometry').json()['items']
                assert sum(item['status'] == 'running' for item in items) <= 1
                item = next(item for item in items if item['id'] == job)
                if item['status'] == wanted: return item
                assert item['status'] in {'queued', 'running'}, item
                time.sleep(.25)
            raise AssertionError('Geometry job timed out')
        first, cancelled = submit(401), submit(402)
        assert user.post(f'/api/v1/geometry/{cancelled}/cancel', headers=uh).status_code == 200
        wait(first, 'completed')
        artifact = user.get(f'/api/v1/geometry/{first}/model')
        assert artifact.status_code == 200
        metadata = validate_glb(artifact.content)
        assert metadata['triangles'] > 1000 and metadata['textures'] >= 1
        running = submit(403)
        wait(running, 'running')
        # Allow the CLI to enter generation before requesting cancellation.
        time.sleep(2)
        assert user.post(f'/api/v1/geometry/{running}/cancel', headers=uh).status_code == 200
        wait(running, 'cancelled', 30)
        followup = submit(404)
        wait(followup, 'completed')
        assert user.delete(f'/api/v1/geometry/{first}', headers=uh).status_code == 200
        assert user.get(f'/api/v1/geometry/{first}/model').status_code == 404
        print('Real geometry: two completed GLBs; queued and active cancellation; GPU reused after cancellation; private deletion.', metadata)
