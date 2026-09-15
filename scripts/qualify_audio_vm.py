"""Exercise a newly installed audio VM with synthetic input, over verified TLS.

Use only on an idle qualification VM; --restart tests its two audio services.
Never changes farm routing or accesses a user's conversations.
"""
import argparse
import audioop
import base64
import hashlib
import io
import json
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import wave
from uuid import uuid4

from setup_audio_vm import PRIVATE, RECIPES, STATE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restart', action='store_true')
    args = parser.parse_args()
    address = json.loads((PRIVATE/'installation.json').read_text())['address']
    ca = STATE/'provider-ca.crt'
    trust = ssl.create_default_context(cafile=str(ca))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=trust))
    def request(kind, path, payload=None, *, authorized=True, headers=None):
        key = (STATE/kind/'controller.key').read_text().strip()
        auth = {'Authorization': 'Bearer '+key} if authorized else {}
        url = f"https://{address}:{RECIPES[kind]['port']}"+path
        with opener.open(urllib.request.Request(url, data=json.dumps(payload).encode() if payload else None,
                         headers=auth | {'Content-Type': 'application/json'} | (headers or {})), timeout=30) as response:
            body = response.read()
            return body if path.endswith('/audio') else json.loads(body)
    def completed(kind, path):
        until = time.monotonic()+180
        while time.monotonic() < until:
            result = request(kind, path)
            if result['state'] not in {'queued', 'running'}:
                assert result['state'] == 'completed', result
                assert result['execution_released']
                return result
            time.sleep(.5)
        raise RuntimeError('The synthetic qualification job did not finish.')
    for kind, recipe in RECIPES.items():
        assert request(kind, recipe['path'])['model'] == recipe['model']
        for options, expected in [({'authorized': False}, 401), ({'headers': {'Origin': 'https://untrusted.invalid'}}, 401), ({'headers': {'Host': 'untrusted.invalid'}}, 400)]:
            try:
                request(kind, recipe['path'], **options)
                raise AssertionError('The untrusted request was accepted.')
            except urllib.error.HTTPError as exc:
                assert exc.code == expected
    speech_id, transcription_id = str(uuid4()), str(uuid4())
    reference = 'Welcome home. Your hearth brings your models together.'
    request('speech', '/v1/speech-jobs', {'id': speech_id, 'model': RECIPES['speech']['model'], 'voice': 'af_heart', 'input': reference})
    started = time.monotonic()
    completed('speech', '/v1/speech-jobs/'+speech_id)
    speech_seconds = time.monotonic()-started
    audio = request('speech', '/v1/speech-jobs/'+speech_id+'/audio')
    with wave.open(io.BytesIO(audio), 'rb') as source:
        assert source.getnchannels() == 1 and source.getsampwidth() == 2
        frames, _ = audioop.ratecv(source.readframes(source.getnframes()), 2, 1, source.getframerate(), 16000, None)
    output = io.BytesIO()
    with wave.open(output, 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(frames)
    normalized = output.getvalue()
    request('transcription', '/v1/transcription-jobs', {'id': transcription_id, 'model': RECIPES['transcription']['model'], 'audio_sha256': hashlib.sha256(normalized).hexdigest(), 'audio_b64': base64.b64encode(normalized).decode()})
    started = time.monotonic()
    result = completed('transcription', '/v1/transcription-jobs/'+transcription_id)
    transcription_seconds = time.monotonic()-started
    assert re.findall(r'\w+', result['text'].lower()) == re.findall(r'\w+', reference.lower()), result['text']
    if args.restart:
        subprocess.run(['systemctl', 'restart', 'hearth-speech.service', 'hearth-transcription.service'], check=True)
        for kind, job in [('speech', speech_id), ('transcription', transcription_id)]:
            for _attempt in range(90):
                try:
                    completed(kind, f'/v1/{kind}-jobs/'+job)
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(1)
            else:
                raise RuntimeError('The existing job receipt did not survive service restart.')
    print(json.dumps({'tls_verified': True, 'anonymous_origin_host_rejected': True, 'real_cpu_synthesis': True,
                      'real_cpu_transcription': True, 'reference': reference, 'transcript': result['text'],
                      'speech_seconds': round(speech_seconds, 3), 'transcription_seconds': round(transcription_seconds, 3),
                      'service_restart_and_receipts': args.restart, 'physical_esx_host_tested': False}, indent=2))


if __name__ == '__main__':
    main()
