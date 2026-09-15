"""Speech jobs over the same pinned local transport used by other providers."""
import hashlib
import time

import httpx
from pydantic import ValidationError

from hearth.audio_codec import MAX_AUDIO_BYTES, validate_wav
from hearth.contracts import SpeechProviderInfo, SpeechReceipt
from hearth.inference import ProviderError, client_for


def rpc(base_url, credential, settings, path, *, payload=None, model):
    method = 'GET' if payload is None else 'POST'
    try:
        with client_for(base_url, credential, settings) as (client, extensions), client.stream(method, path, json=payload, extensions=extensions) as response:
            if not 200 <= response.status_code < 300:
                raise ProviderError(f'The speech provider rejected the request (HTTP {response.status_code}).', uncertain=method == 'POST' and response.status_code >= 500)
            raw, started = bytearray(), time.monotonic()
            for block in response.iter_bytes():
                raw.extend(block)
                if len(raw) > 65536 or time.monotonic() - started > 30:
                    raise ProviderError('The speech receipt exceeded its limits.', uncertain=method == 'POST')
        return model.model_validate_json(raw)
    except (ValidationError, ValueError):
        raise ProviderError('The speech provider returned an invalid receipt.', uncertain=method == 'POST') from None
    except httpx.HTTPError:
        raise ProviderError('The speech provider is unreachable. Check its address, certificate and controller key.', uncertain=method == 'POST') from None


def information(base_url, credential, settings):
    return rpc(base_url, credential, settings, 'speech-provider', model=SpeechProviderInfo)


def collect(base_url, credential, settings, receipt):
    try:
        with client_for(base_url, credential, settings) as (client, extensions), client.stream('GET', f'speech-jobs/{receipt.id}/audio', extensions=extensions) as response:
            if response.status_code != 200 or response.headers.get('content-type', '').split(';')[0] != 'audio/wav':
                raise ProviderError('The completed speech audio could not be collected.')
            raw, started = bytearray(), time.monotonic()
            for block in response.iter_bytes():
                raw.extend(block)
                if len(raw) > MAX_AUDIO_BYTES or time.monotonic() - started > 30:
                    raise ProviderError('The audio exceeded its transfer limits.')
        raw = bytes(raw)
        if hashlib.sha256(raw).hexdigest() != receipt.sha256:
            raise ProviderError('The audio digest does not match its receipt.')
        validate_wav(raw, frames=receipt.frames)
        return raw
    except (httpx.HTTPError, ValueError):
        raise ProviderError('The speech audio could not be validated or collected.') from None


def render(base_url, credential, settings, data, on_receipt=lambda receipt: False):
    dispatched, released, cancel_sent = False, False, False
    try:
        receipt = rpc(base_url, credential, settings, 'speech-jobs', payload=data.model_dump(mode='json'), model=SpeechReceipt)
        dispatched = True
        deadline = time.monotonic() + 900
        expected = hashlib.sha256(data.input.encode()).hexdigest()
        while True:
            if (receipt.id, receipt.model, receipt.voice, receipt.input_sha256) != (data.id, data.model, data.voice, expected):
                raise ProviderError('The speech receipt belongs to a different request.', uncertain=True)
            released = receipt.execution_released
            stop = on_receipt(receipt)
            if receipt.state not in {'queued', 'running'}:
                if not released:
                    raise ProviderError('The speech provider has not confirmed that execution stopped.', uncertain=True)
                if receipt.state != 'completed' or stop:
                    return receipt, None
                if not receipt.sha256:
                    raise ProviderError('Completed speech is missing its digest.')
                return receipt, collect(base_url, credential, settings, receipt)
            if released:
                raise ProviderError('The speech receipt has inconsistent execution state.', uncertain=True)
            if stop and not cancel_sent:
                receipt = rpc(base_url, credential, settings, f'speech-jobs/{data.id}/cancel', payload={}, model=SpeechReceipt)
                cancel_sent = True
                continue
            if time.monotonic() > deadline:
                rpc(base_url, credential, settings, f'speech-jobs/{data.id}/cancel', payload={}, model=SpeechReceipt)
                raise ProviderError('Speech exceeded its deadline. Check the provider before retrying.', uncertain=True)
            time.sleep(.5)
            receipt = rpc(base_url, credential, settings, f'speech-jobs/{data.id}', model=SpeechReceipt)
    except ProviderError as exc:
        raise ProviderError(str(exc), uncertain=exc.uncertain or dispatched and not released) from None
