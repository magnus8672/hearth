"""Bounded geometry receipts and self-contained GLB transfer."""
import base64
import hashlib
import time

import httpx

from hearth.contracts import GeometryProviderInfo, GeometryReceipt
from hearth.geometry_validation import MAX_GLB, validate_glb
from hearth.image_transport import rpc
from hearth.inference import ProviderError, client_for


def information(base_url, credential, settings):
    return rpc(base_url, credential, settings, 'geometry-provider', model=GeometryProviderInfo)


def collect(base_url, credential, settings, receipt):
    try:
        with client_for(base_url, credential, settings) as (client, extensions), client.stream('GET', f'geometry-jobs/{receipt.id}/model', extensions=extensions) as response:
            if response.status_code != 200 or response.headers.get('content-type', '').split(';')[0] != 'model/gltf-binary':
                raise ValueError()
            raw, started = bytearray(), time.monotonic()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_GLB or time.monotonic() - started > 90:
                    raise ValueError()
        if hashlib.sha256(raw).hexdigest() != receipt.sha256:
            raise ValueError()
        validate_glb(raw)
        return bytes(raw)
    except Exception:
        raise ProviderError('The generated model failed artifact validation or transfer.') from None


def render(base_url, credential, settings, data, image, on_receipt=lambda receipt: False):
    dispatched, released, cancel_sent = False, False, False
    try:
        receipt = rpc(base_url, credential, settings, 'geometry-jobs', payload={'request': data.model_dump(mode='json'), 'image': base64.b64encode(image).decode()}, model=GeometryReceipt)
        dispatched = True
        deadline = time.monotonic() + 1260
        while True:
            if any(getattr(receipt, key) != value for key, value in data.model_dump().items()):
                raise ProviderError('The geometry receipt belongs to another request.', uncertain=True)
            released = receipt.execution_released
            stop = on_receipt(receipt)
            if receipt.state not in {'queued', 'running'}:
                if not released:
                    raise ProviderError('The geometry service has not confirmed GPU release.', uncertain=True)
                return receipt, collect(base_url, credential, settings, receipt) if receipt.state == 'completed' and not stop else None
            if released:
                raise ProviderError('The geometry receipt is inconsistent.', uncertain=True)
            if stop and not cancel_sent:
                receipt = rpc(base_url, credential, settings, f'geometry-jobs/{data.id}/cancel', payload={}, model=GeometryReceipt)
                cancel_sent = True
                continue
            if time.monotonic() > deadline:
                rpc(base_url, credential, settings, f'geometry-jobs/{data.id}/cancel', payload={}, model=GeometryReceipt)
                raise ProviderError('Geometry generation exceeded its deadline. Check the worker before retrying.', uncertain=True)
            time.sleep(.5)
            receipt = rpc(base_url, credential, settings, f'geometry-jobs/{data.id}', model=GeometryReceipt)
    except (ProviderError, httpx.HTTPError) as exc:
        raise ProviderError(str(exc), uncertain=getattr(exc, 'uncertain', False) or dispatched and not released) from None
