import base64
import hashlib
import io
from uuid import uuid4

from hearth import image_transport
from hearth.database import scoped_session
from PIL import Image
from sqlalchemy import text

from tests.integration.test_chat import csrf, promote, setup
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_images import INFO, image_target, receipt, wait_image
from tests.integration.test_postgres import databases as databases


def test_uploaded_pixels_queue_privacy_replay_and_deletion(bff, monkeypatch):
    factory, settings, engine, migration, subject = setup(bff, monkeypatch)
    monkeypatch.setattr(image_transport, 'information', lambda *args: INFO.model_copy(update={'editing': 'fooocus-vary-v1'}))
    calls = []
    def render(url, key, config, data, observe=lambda value: False, *, source_image=None):
        if data.edit:
            assert hashlib.sha256(source_image).hexdigest() == data.edit.image_sha256
            with Image.open(io.BytesIO(source_image)) as picture:
                assert picture.format == 'JPEG' and max(picture.size) <= 1600
                assert not picture.getexif()
            calls.append(data)
        result = receipt(data).model_copy(update={'edit': data.edit})
        observe(result)
        return result, b'isolated fixture artifact'
    monkeypatch.setattr(image_transport, 'render', render)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        target = image_target(admin, csrf(admin, settings.admin_origin))
        assert len(calls) == 1  # Pixel-edit verification is separate from text generation.
        calls.clear()
        signin(user)
        headers = csrf(user, settings.user_origin)
        raw = io.BytesIO()
        Image.new('RGB', (1800, 1200), 'blue').save(raw, 'PNG')
        raw = raw.getvalue()
        data = {'target_id': target, 'image': base64.b64encode(raw).decode(), 'request': {
            'id': str(uuid4()), 'model': INFO.model, 'prompt': 'A blue ceramic toy', 'seed': 3,
            'edit': {'image_sha256': hashlib.sha256(raw).hexdigest(), 'strength': 0.4}}}
        assert user.post('/api/v1/images', json=data).status_code == 403
        assert user.post('/api/v1/images', json=data | {'image': 'bad'}, headers=headers).status_code == 422
        assert user.post('/api/v1/images', json=data | {'image': None}, headers=headers).status_code == 422
        assert user.post('/api/v1/images', json=data, headers=headers).status_code == 202
        assert wait_image(user)['status'] == 'completed' and len(calls) == 1
        assert user.post('/api/v1/images', json=data, headers=headers).status_code == 202
        assert len(calls) == 1
        assert user.post('/api/v1/images', json=data | {'request': data['request'] | {'edit': data['request']['edit'] | {'strength': 0.8}}}, headers=headers).status_code == 409
        assert 'source_image' not in user.get('/api/v1/images').json()['items'][0]
        owner = user.get('/api/v1/session').json()['id']
        with scoped_session(engine, owner, settings.farm_id) as db:
            assert db.execute(text('SELECT source_image FROM image_jobs WHERE id=:id'), {'id': data['request']['id']}).scalar_one()
        with migration.connect() as db:
            other = db.execute(text('SELECT id FROM users WHERE farm_id=:farm AND subject<>:subject'), {'farm': settings.farm_id, 'subject': subject}).scalar_one()
        with scoped_session(engine, other, settings.farm_id) as db:
            assert db.execute(text('SELECT source_image FROM image_jobs WHERE id=:id'), {'id': data['request']['id']}).first() is None
        assert user.delete('/api/v1/images/' + data['request']['id'], headers=headers).status_code == 200
        with scoped_session(engine, owner, settings.farm_id) as db:
            assert db.execute(text('SELECT source_image FROM image_jobs WHERE id=:id'), {'id': data['request']['id']}).scalar_one() is None
        assert user.post('/api/v1/images', json=data, headers=headers).status_code == 410
