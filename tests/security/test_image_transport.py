import hashlib
import io
from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest
from hearth import image_transport
from hearth.config import Settings
from hearth.contracts import ImageGeneration, ImageReceipt
from hearth.inference import ProviderError
from PIL import Image


@pytest.mark.parametrize('fault', ['none', 'wrong_job', 'wrong_digest', 'invalid_png', 'lost_receipt', 'unreleased', 'running_released'])
def test_receipt_binding_artifact_verification_and_unknown_execution(monkeypatch, fault):
    data = ImageGeneration(id=uuid4(), model='fixture-image', prompt='A cabin', seed=7)
    output = io.BytesIO()
    Image.new('RGB', (1024, 1024), 'orange').save(output, format='PNG')
    artifact = b'not a PNG' if fault == 'invalid_png' else output.getvalue()
    result = ImageReceipt(id=data.id, model=data.model, state='completed', progress=20, steps=20, seed=7,
        shape='square', width=1024, height=1024, sha256=hashlib.sha256(artifact).hexdigest(), execution_released=True,
        manifest_sha256='a' * 64, cancel_requested=False)
    if fault == 'wrong_job':
        result.id = uuid4()
    if fault == 'wrong_digest':
        result.sha256 = '0' * 64
    if fault == 'unreleased':
        result.execution_released = False
    if fault == 'running_released':
        result.state = 'running'

    def handler(request):
        if request.url.path.endswith('/image'):
            return httpx.Response(200, content=artifact, headers={'content-type': 'image/png'})
        if fault == 'lost_receipt':
            if request.method == 'POST':
                return httpx.Response(202, json=result.model_copy(update={'state': 'running', 'execution_released': False}).model_dump(mode='json'))
            raise httpx.ReadError('explicit lost receipt')
        return httpx.Response(202, json=result.model_dump(mode='json'))

    @contextmanager
    def client(*args):
        with httpx.Client(base_url='http://fixture/v1/', transport=httpx.MockTransport(handler)) as client:
            yield client, {}

    monkeypatch.setattr(image_transport, 'client_for', client)
    if fault == 'none':
        _, collected = image_transport.render('http://fixture', '', Settings(mode='test'), data)
        assert collected == artifact
    else:
        with pytest.raises(ProviderError) as error:
            image_transport.render('http://fixture', '', Settings(mode='test'), data)
        assert error.value.uncertain is (fault in {'wrong_job', 'lost_receipt', 'unreleased', 'running_released'})


@pytest.mark.parametrize('large', [False, True])
def test_resolution_receipt_and_legacy_request_compatibility(monkeypatch, large):
    data = ImageGeneration(id=uuid4(), model='fixture', prompt='A cabin', seed=7, shape='widescreen' if large else 'square',
                           options={'resolution': '4k' if large else 'native'})
    output = io.BytesIO()
    size = (3840, 2160) if large else (1024, 1024)
    Image.new('RGB', size, 'orange').save(output, format='PNG')
    artifact = output.getvalue()
    result = ImageReceipt(id=data.id, model=data.model, state='completed', progress=20, steps=20, seed=7,
        shape=data.shape, width=size[0], height=size[1], sha256=hashlib.sha256(artifact).hexdigest(), execution_released=True,
        manifest_sha256='a' * 64, cancel_requested=False)

    def handler(request):
        if request.method == 'POST':
            import json
            payload = json.loads(request.content)
            assert 'edit' not in payload and 'image' not in payload
            assert ('options' in payload) is large
            if large:
                assert payload['options']['resolution'] == '4k'
        if request.url.path.endswith('/image'):
            return httpx.Response(200, content=artifact, headers={'content-type': 'image/png'})
        return httpx.Response(202, json=result.model_dump(mode='json'))

    @contextmanager
    def client(*args):
        with httpx.Client(base_url='http://fixture/v1/', transport=httpx.MockTransport(handler)) as connection:
            yield connection, {}

    monkeypatch.setattr(image_transport, 'client_for', client)
    assert image_transport.render('http://fixture', '', Settings(mode='test'), data)[1] == artifact
    result.width = 1024 if large else 2048
    with pytest.raises(ProviderError, match='different request'):
        image_transport.render('http://fixture', '', Settings(mode='test'), data)


def test_edit_transport_sends_pixels_and_binds_receipt_to_edit(monkeypatch):
    import base64

    from hearth.contracts import ImageEdit
    raw = b'normalized bytes supplied by the controller'
    edit = ImageEdit(image_sha256=hashlib.sha256(raw).hexdigest(), strength=0.4)
    data = ImageGeneration(id=uuid4(), model='fixture', prompt='A cabin', seed=7, edit=edit)
    receipt = ImageReceipt(id=data.id, model=data.model, state='cancelled', progress=0, steps=20, seed=7,
        shape='square', width=1024, height=1024, execution_released=True, manifest_sha256='a'*64, cancel_requested=True, edit=edit)
    def rpc(*args, **kwargs):
        assert base64.b64decode(kwargs['payload']['image']) == raw
        assert kwargs['payload']['edit']['strength'] == 0.4
        return receipt
    monkeypatch.setattr(image_transport, 'rpc', rpc)
    assert image_transport.render('http://fixture', '', Settings(mode='test'), data, source_image=raw)[1] is None
    with pytest.raises(ProviderError, match='missing or changed') as error:
        image_transport.render('http://fixture', '', Settings(mode='test'), data)
    assert not error.value.uncertain
    receipt.edit = None
    with pytest.raises(ProviderError, match='different request') as error:
        image_transport.render('http://fixture', '', Settings(mode='test'), data, source_image=raw)
    assert error.value.uncertain
