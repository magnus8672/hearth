import base64
import hashlib
import io
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from hearth.contracts import ImageEdit, ImageGeneration
from hearth.image_settings import validate_settings
from PIL import Image
from pydantic import ValidationError

from runtimes.image.fooocus_bridge import Fooocus
from runtimes.image.hearth_image import create_app
from tests.security.test_image_runtime import TOKEN, Engine


def source():
    output = io.BytesIO()
    Image.new('RGB', (64, 48), 'red').save(output, 'JPEG')
    raw = output.getvalue()
    return raw, ImageEdit(image_sha256=hashlib.sha256(raw).hexdigest(), strength=0.35)


@pytest.mark.parametrize('strength', [0, 1, -0.5, float('nan')])
def test_edit_strength_is_bounded(strength):
    with pytest.raises(ValidationError):
        ImageEdit(image_sha256='a' * 64, strength=strength)


def test_legacy_provider_cannot_silently_ignore_source_pixels():
    _, edit = source()
    data = ImageGeneration(id=uuid4(), model='fixture', prompt='A red toy', seed=4, edit=edit)
    with pytest.raises(ValueError, match='does not support'):
        validate_settings(data, {'shapes': ['square'], 'steps': [20]})


def test_fooocus_receives_pixels_strength_and_variation_controls():
    import numpy as np
    names = ['generate_image_grid', 'prompt', 'negative_prompt', 'performance_selection', 'aspect_ratios_selection',
             'image_number', 'output_format', 'image_seed', 'base_model', 'refiner_model', 'overwrite_step',
             'overwrite_width', 'overwrite_height', 'input_image_checkbox', 'enhance_checkbox', 'disable_preview',
             'disable_intermediate_results', 'save_metadata_to_images', 'current_tab', 'uov_method',
             'uov_input_image', 'overwrite_vary_strength']
    ui = SimpleNamespace(**{name: SimpleNamespace(value=None) for name in names})
    ui.ctrls = [None] + [getattr(ui, name) for name in names]
    ui.worker = SimpleNamespace(AsyncTask=lambda values: SimpleNamespace(values=dict(zip(names, values, strict=True))))
    raw, edit = source()
    data = ImageGeneration(id=uuid4(), model='fixture', prompt='A red toy', seed=4, shape='landscape', edit=edit)
    values = Fooocus(ui).build_task(data, lambda: False, raw).values
    assert values['input_image_checkbox'] is True and values['current_tab'] == 'uov'
    assert values['uov_method'] == 'Vary (Subtle)' and values['overwrite_vary_strength'] == 0.35
    assert values['uov_input_image'].shape == (768, 1024, 3)
    assert np.all(values['uov_input_image'][:, :, 0] > 240)
    assert all(getattr(ui, name).value is None for name in names)


def test_runtime_validates_source_and_keeps_pixels_out_of_saved_request(tmp_path):
    class EditEngine(Engine):
        def generate(self, data, cancelled, progress, output, *, source_image):
            self.source = source_image
            super().generate(data, cancelled, progress, output)
    engine = EditEngine()
    profile = {'shapes': ['square'], 'steps': [20], 'editing': 'fooocus-vary-v1'}
    app = create_app(tmp_path, tmp_path, TOKEN, engine=engine, manifest_digest='a'*64, profile=profile)
    raw, edit = source()
    data = ImageGeneration(id=uuid4(), model='stabilityai/stable-diffusion-xl-base-1.0', prompt='A red toy', seed=4, edit=edit).model_dump(mode='json')
    encoded = base64.b64encode(raw).decode()
    with TestClient(app) as client:
        client.headers['Authorization'] = 'Bearer ' + TOKEN
        assert client.post('/v1/image-jobs', json=data).status_code == 422
        assert client.post('/v1/image-jobs', json=data | {'image': 'not base64'}).status_code == 422
        wrong = data | {'edit': data['edit'] | {'image_sha256': 'b'*64}, 'image': encoded}
        assert client.post('/v1/image-jobs', json=wrong).status_code == 422
        assert client.post('/v1/image-jobs', json=data | {'edit': None, 'image': encoded}).status_code == 422
        try:
            assert client.post('/v1/image-jobs', json=data | {'image': encoded}).status_code == 202
            assert engine.entered.wait(3) and engine.source == raw
            assert client.post('/v1/image-jobs', json=data | {'image': encoded}).status_code == 202
            assert client.post('/v1/image-jobs', json=data | {'image': encoded, 'edit': data['edit'] | {'strength': 0.8}}).status_code == 409
            with app.state.jobs.db() as db:
                saved = db.execute('SELECT request FROM jobs').fetchone()[0]
                assert encoded not in saved
            path = '/v1/image-jobs/' + data['id']
            assert client.get(path).json()['edit'] == data['edit']
            assert client.post(path + '/cancel').json()['execution_released'] is False
        finally:
            engine.finish.set()
        for _ in range(100):
            result = client.get(path).json()
            if result['execution_released']:
                break
            time.sleep(.02)
        assert result['state'] == 'cancelled' and engine.calls == 1 and engine.released
