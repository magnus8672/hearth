import hashlib
import io
import math
import struct
import threading
import time
import wave
from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from hearth import speech_transport
from hearth.audio_codec import validate_wav
from hearth.config import Settings
from hearth.contracts import SpeechGeneration, SpeechReceipt
from hearth.inference import ProviderError

from runtimes.speech.hearth_speech import MODEL, VOICE, Cancelled, create_app


def wav_fixture(rate=24000, silent=False):
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b''.join(struct.pack('<h', 0 if silent else int(9000*math.sin(2*math.pi*440*n/rate))) for n in range(rate//4)))
    return output.getvalue()


@pytest.mark.parametrize('fault', ['none', 'wrong_job', 'wrong_input', 'wrong_voice', 'wrong_digest', 'invalid_wav', 'silence', 'lost_receipt', 'unreleased', 'running_released'])
def test_speech_receipt_binding_audio_validation_and_uncertain_execution(monkeypatch, fault):
    data = SpeechGeneration(id=uuid4(), model=MODEL, voice=VOICE, input='Hello from hearth.')
    artifact = b'not a wave' if fault == 'invalid_wav' else wav_fixture(silent=fault == 'silence')
    result = SpeechReceipt(id=data.id, model=MODEL, voice=VOICE, input_sha256=hashlib.sha256(data.input.encode()).hexdigest(), state='completed',
        frames=6000, sha256=hashlib.sha256(artifact).hexdigest(), execution_released=True, manifest_sha256='a'*64, cancel_requested=False)
    if fault == 'wrong_job':
        result.id = uuid4()
    if fault == 'wrong_input':
        result.input_sha256 = '0'*64
    if fault == 'wrong_voice':
        result.voice = 'unrequested'
    if fault == 'wrong_digest':
        result.sha256 = '0'*64
    if fault == 'unreleased':
        result.execution_released = False
    if fault == 'running_released':
        result.state = 'running'
    def handler(request):
        if request.url.path.endswith('/audio'):
            return httpx.Response(200, content=artifact, headers={'content-type': 'audio/wav'})
        if fault == 'lost_receipt':
            if request.method == 'POST':
                return httpx.Response(202, json=result.model_copy(update={'state': 'running', 'execution_released': False}).model_dump(mode='json'))
            raise httpx.ReadError('fixture interrupted stream')
        return httpx.Response(202, json=result.model_dump(mode='json'))
    @contextmanager
    def client(*args):
        with httpx.Client(base_url='http://fixture/v1/', transport=httpx.MockTransport(handler)) as client:
            yield client, {}
    monkeypatch.setattr(speech_transport, 'client_for', client)
    if fault == 'none':
        _, audio = speech_transport.render('http://fixture', '', Settings(mode='test'), data)
        assert audio == artifact
    else:
        with pytest.raises(ProviderError) as exc:
            speech_transport.render('http://fixture', '', Settings(mode='test'), data)
        assert exc.value.uncertain is (fault in {'wrong_job', 'wrong_input', 'wrong_voice', 'lost_receipt', 'unreleased', 'running_released'})


def test_audio_limits_and_truncation():
    raw = wav_fixture()
    assert validate_wav(raw) == 6000
    for invalid in [raw[:-1], raw+b'trailing data', wav_fixture(rate=16000), wav_fixture(silent=True)]:
        with pytest.raises(ValueError):
            validate_wav(invalid)
    with pytest.raises(ValueError):
        validate_wav(raw, frames=6001)


@pytest.mark.parametrize('cancel', [False, True], ids=['complete', 'cancel'])
def test_runtime_authenticated_jobs_cancellation_restart_and_no_replay(tmp_path, cancel):
    class Engine:
        def __init__(self):
            self.calls = 0
            self.entered, self.finish = threading.Event(), threading.Event()
        def generate(self, data, cancelled, output):
            self.calls += 1
            self.entered.set()
            assert self.finish.wait(5)
            if cancelled():
                raise Cancelled()
            output.write_bytes(wav_fixture())
    engine, token = Engine(), 'explicit-speech-runtime-fixture-credential'
    with TestClient(create_app(tmp_path, token, engine=engine, digest='a'*64)) as client:
        assert client.get('/v1/speech-provider').status_code == 401
        client.headers['Authorization'] = 'Bearer '+token
        assert client.get('/v1/speech-provider', headers={'Origin': 'https://malicious.example'}).status_code == 401
        assert client.get('/v1/speech-provider', headers={'Host': 'untrusted.example'}).status_code == 400
        assert client.post('/v1/speech-jobs', content=b'x'*65537).status_code == 413
        data = {'id': str(uuid4()), 'model': MODEL, 'voice': VOICE, 'input': 'Say hello.'}
        assert client.post('/v1/speech-jobs', json=data | {'model_path': 'untrusted'}).status_code == 422
        assert client.post('/v1/speech-jobs', json=data | {'voice': 'unverified'}).status_code == 400
        assert client.post('/v1/speech-jobs', json=data | {'input': 'x'*6001}).status_code == 422
        path = '/v1/speech-jobs/'+data['id']
        try:
            assert client.post('/v1/speech-jobs', json=data).status_code == 202
            assert engine.entered.wait(3)
            assert client.post('/v1/speech-jobs', json=data).status_code == 202
            assert client.post('/v1/speech-jobs', json=data | {'input': 'changed'}).status_code == 409
            assert client.post('/v1/speech-jobs', json=data | {'id': str(uuid4())}).status_code == 409
            assert client.get(path+'/audio').status_code == 409
            assert client.post('/v1/speech-jobs/'+str(uuid4())+'/cancel').status_code == 404
            assert not client.get(path).json()['cancel_requested']
            if cancel:
                assert client.post(path+'/cancel').json()['cancel_requested']
                assert not client.get(path).json()['execution_released']
        finally:
            engine.finish.set()
        for _ in range(200):
            result = client.get(path).json()
            if result['execution_released']:
                break
            time.sleep(.01)
        assert result['state'] == ('cancelled' if cancel else 'completed')
        assert engine.calls == 1
        if not cancel:
            assert validate_wav(client.get(path+'/audio').content) == 6000
    replacement = Engine()
    with TestClient(create_app(tmp_path, token, engine=replacement, digest='a'*64)) as client:
        client.headers['Authorization'] = 'Bearer '+token
        assert client.post('/v1/speech-jobs', json=data).json()['state'] == result['state']
        assert replacement.calls == 0
