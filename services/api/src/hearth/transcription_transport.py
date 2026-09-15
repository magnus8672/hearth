"""Pinned local transcription transport with request binding and confirmed release."""
import base64
import time

from hearth.contracts import TranscriptionProviderInfo, TranscriptionReceipt
from hearth.inference import ProviderError
from hearth.speech_transport import rpc


def information(base_url, credential, settings):
    return rpc(base_url, credential, settings, 'transcription-provider', model=TranscriptionProviderInfo)


def transcribe(base_url, credential, settings, data, audio, on_receipt=lambda receipt: False):
    dispatched, released, cancel_sent = False, False, False
    try:
        receipt = rpc(base_url, credential, settings, 'transcription-jobs', payload=data.model_dump(mode='json') | {'audio_b64': base64.b64encode(audio).decode('ascii')}, model=TranscriptionReceipt)
        dispatched = True
        deadline = time.monotonic() + 900
        while True:
            if (receipt.id, receipt.model, receipt.audio_sha256) != (data.id, data.model, data.audio_sha256):
                raise ProviderError('The transcript receipt belongs to another request.', uncertain=True)
            released = receipt.execution_released
            stop = on_receipt(receipt)
            if receipt.state not in {'queued', 'running'}:
                if not released:
                    raise ProviderError('The transcription provider has not confirmed release.', uncertain=True)
                if stop:
                    return receipt.model_copy(update={'state': 'cancelled', 'text': ''})
                if receipt.state == 'completed' and not receipt.text.strip():
                    raise ProviderError('No speech was recognized in this recording.')
                return receipt
            if released:
                raise ProviderError('The transcription receipt has inconsistent execution state.', uncertain=True)
            if stop and not cancel_sent:
                receipt = rpc(base_url, credential, settings, f'transcription-jobs/{data.id}/cancel', payload={}, model=TranscriptionReceipt)
                cancel_sent = True
                continue
            if time.monotonic() > deadline:
                rpc(base_url, credential, settings, f'transcription-jobs/{data.id}/cancel', payload={}, model=TranscriptionReceipt)
                raise ProviderError('Transcription exceeded its deadline. Check the provider before retrying.', uncertain=True)
            time.sleep(.5)
            receipt = rpc(base_url, credential, settings, f'transcription-jobs/{data.id}', model=TranscriptionReceipt)
    except ProviderError as exc:
        raise ProviderError(str(exc), uncertain=exc.uncertain or dispatched and not released) from None
