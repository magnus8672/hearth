"""Bounded image-job transport independent of any upstream graphical UI."""
import hashlib
import io
import time

import httpx
from PIL import Image
from pydantic import ValidationError

from hearth.contracts import ImageProviderInfo, ImageReceipt
from hearth.inference import ProviderError, client_for


def rpc(base_url, credential, settings, path, *, payload=None, model=None):
    method = 'GET' if payload is None else 'POST'
    try:
        with client_for(base_url, credential, settings) as (client, extensions), client.stream(method, path, json=payload, extensions=extensions) as response:
            if not 200 <= response.status_code < 300:
                raise ProviderError(f'The image provider rejected the request (HTTP {response.status_code}).', uncertain=response.status_code >= 500 and method == 'POST')
            raw = bytearray()
            started = time.monotonic()
            for block in response.iter_bytes():
                raw.extend(block)
                if len(raw) > 65536 or time.monotonic() - started > 30:
                    raise ProviderError('The image provider response exceeded its limits.', uncertain=method == 'POST')
        return model.model_validate_json(raw) if model else None
    except (ValidationError, ValueError):
        raise ProviderError('The image provider returned an invalid receipt.', uncertain=method == 'POST') from None
    except httpx.HTTPError:
        raise ProviderError('The image provider is unreachable. Check its address, certificate and controller key.', uncertain=method == 'POST') from None


def information(base_url, credential, settings):
    return rpc(base_url, credential, settings, 'image-provider', model=ImageProviderInfo)


def collect_png(base_url, credential, settings, receipt):
    try:
        with client_for(base_url, credential, settings) as (client, extensions), client.stream('GET', f'image-jobs/{receipt.id}/image', extensions=extensions) as response:
            if response.status_code != 200 or response.headers.get('content-type', '').split(';')[0] != 'image/png':
                raise ProviderError('The completed image could not be collected.')
            raw = bytearray()
            started = time.monotonic()
            for block in response.iter_bytes():
                raw.extend(block)
                if len(raw) > 16777216 or time.monotonic() - started > 30:
                    raise ProviderError('The image exceeded its supported file size or transfer time.')
        if hashlib.sha256(raw).hexdigest() != receipt.sha256:
            raise ProviderError('The image digest did not match its completion receipt.')
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != 'PNG' or image.size != (receipt.width, receipt.height) or getattr(image, 'n_frames', 1) != 1:
                raise ProviderError('The image dimensions or format did not match its receipt.')
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
        return bytes(raw)
    except (httpx.HTTPError, OSError, ValueError, Image.DecompressionBombError):
        raise ProviderError('The image could not be validated or collected.') from None


def render(base_url, credential, settings, data, on_receipt=lambda receipt: False):
    dispatched, released, cancel_sent = False, False, False
    try:
        receipt = rpc(base_url, credential, settings, 'image-jobs', payload=data.model_dump(mode='json'), model=ImageReceipt)
        dispatched = True
        deadline = time.monotonic() + 900
        while True:
            expected_size = {'square': (1024, 1024), 'landscape': (1024, 768), 'portrait': (768, 1024)}[data.shape]
            if (receipt.id != data.id or receipt.model != data.model or receipt.seed != data.seed
                    or receipt.steps != data.steps or receipt.shape != data.shape or (receipt.width, receipt.height) != expected_size):
                raise ProviderError('The image provider returned a receipt for a different request.', uncertain=True)
            released = receipt.execution_released
            stop = on_receipt(receipt)
            if receipt.state not in {'queued', 'running'}:
                if not released:
                    raise ProviderError('The image provider could not confirm that execution stopped.', uncertain=True)
                if receipt.state != 'completed' or stop:
                    return receipt, None
                if not receipt.sha256:
                    raise ProviderError('The completed image is missing its digest.')
                return receipt, collect_png(base_url, credential, settings, receipt)
            if released:
                raise ProviderError('The image provider returned an inconsistent execution receipt.', uncertain=True)
            if stop and not cancel_sent:
                receipt = rpc(base_url, credential, settings, f'image-jobs/{data.id}/cancel', payload={}, model=ImageReceipt)
                cancel_sent = True
                continue
            if time.monotonic() > deadline:
                # No automatic replay or unsafe pool release after a deadline.
                rpc(base_url, credential, settings, f'image-jobs/{data.id}/cancel', payload={}, model=ImageReceipt)
                raise ProviderError('Image generation exceeded its deadline. Check the provider before retrying.', uncertain=True)
            time.sleep(.5)
            receipt = rpc(base_url, credential, settings, f'image-jobs/{data.id}', model=ImageReceipt)
    except ProviderError as exc:
        raise ProviderError(str(exc), uncertain=exc.uncertain or dispatched and not released) from None
