"""Opt-in qualification against an exclusively reserved, existing image service."""
import io
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from tests.integration.test_chat import csrf, promote
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


@pytest.mark.skipif(not os.environ.get('HEARTH_LIVE_WORKER_IMAGE'), reason='Requires explicit exclusive access to the existing GPU provider.')
def test_real_gpu_queue_through_private_bff(bff):
    factory, settings, _, migration, _ = bff
    config = json.loads(Path('.hearth/worker-live-provider.json').read_text())
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        response = admin.post('/api/v1/providers', headers=ah, json={'name': 'Explicit worker qualification', 'base_url': config['base_url'], 'model_id': config['model'], 'api_key': config['key'], 'protocol': 'hearth.image.v1', 'local_only': True, 'allow_insecure_http': True})
        assert response.status_code == 201
        target = response.json()['id']
        assert admin.post('/api/v1/providers/' + target + '/probe', headers=ah, json={'revision': 1}).json()['state'] == 'ready'
        signin(user)
        uh = csrf(user, settings.user_origin)
        jobs = []
        for color in ('orange', 'green', 'blue'):
            request = {'id': str(uuid4()), 'model': config['model'], 'prompt': f'A single {color} ceramic cube on a white table, studio photograph', 'seed': len(jobs) + 701, 'options': {'styles': []}}
            result = user.post('/api/v1/images', headers=uh, json={'target_id': target, 'request': request})
            assert result.status_code == 202
            jobs.append(request['id'])
        assert user.post('/api/v1/images/' + jobs[-1] + '/cancel', headers=uh).status_code == 200
        deadline, observed_waiting = time.monotonic() + 180, False
        while time.monotonic() < deadline:
            records = user.get('/api/v1/images').json()['items']
            states = {item['id']: item['status'] for item in records}
            assert list(states.values()).count('running') <= 1
            observed_waiting |= 'queued' in states.values() and 'running' in states.values()
            if all(state not in {'queued', 'running'} for state in states.values()):
                break
            time.sleep(.25)
        assert states == {jobs[0]: 'completed', jobs[1]: 'completed', jobs[2]: 'cancelled'}
        assert observed_waiting
        for job in jobs[:2]:
            image = user.get('/api/v1/images/' + job + '/image')
            assert image.status_code == 200
            with Image.open(io.BytesIO(image.content)) as result:
                assert result.size == (1024, 1024) and result.format == 'PNG'
        print('Real GPU: two queued PNGs completed serially, third cancelled before dispatch; no overlapping running jobs.')
