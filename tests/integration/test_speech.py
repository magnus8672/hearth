import hashlib
import json
import os
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest
from hearth import chat, identity, speech_transport
from hearth.audio_codec import validate_wav
from hearth.contracts import SpeechProviderInfo, SpeechReceipt
from hearth.database import scoped_session
from hearth.inference import ProviderError
from sqlalchemy import text

from tests.integration.test_capability_routes import assign
from tests.integration.test_chat import configure, csrf, promote, setup, wait_finished
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases
from tests.security.test_speech import wav_fixture

MODEL, VOICE = 'kokoro-82m-v1.0-onnx', 'af_heart'


@pytest.fixture(autouse=True)
def fixture_text(monkeypatch):
    monkeypatch.setattr(chat, 'chat_stream', lambda *a, **kw: iter([('text', 'Welcome home. Your hearth brings your models together.'), ('done', 'stop')]))


def configure_speech(admin, headers, key=''):
    target = admin.post('/api/v1/providers', headers=headers, json={'name': 'Speech fixture', 'base_url': 'http://127.0.0.1:1236', 'model_id': MODEL, 'protocol': 'hearth.speech.v1', 'resource_pool': 'Independent speech CPU', 'api_key': key, 'local_only': True})
    assert target.status_code == 201, target.text
    target_id = target.json()['id']
    result = admin.post(f'/api/v1/providers/{target_id}/probe', headers=headers, json={'revision': 1})
    assert result.json()['state'] == 'ready', result.text
    assert result.json()['features'] == ['audio.speak', 'audio.jobs']
    assert assign(admin, headers, 'audio.speak', [target_id]).status_code == 200
    return target_id


def reply(user, headers):
    path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=headers, json={}).json()['id']
    sent = user.post(path+'/turns', headers=headers, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Hello'})
    assert sent.status_code == 202, sent.text
    result = wait_finished(user, path)
    assert result['runs'][-1]['status'] == 'completed', result['runs']
    return path, result['messages'][-1]


def wait_speech(user, path):
    for _ in range(400):
        messages = user.get(path).json()['messages']
        result = messages[-1].get('speech')
        if result and result['status'] != 'running':
            return result
        time.sleep(.025)
    pytest.fail('Speech did not settle')


def fixture_provider(monkeypatch, render=None):
    info = SpeechProviderInfo(protocol='hearth.speech.v1', model=MODEL, model_revision='fixture', manifest_sha256='a'*64,
        voices=[VOICE], default_voice=VOICE, job_cancellation=True, offline=True)
    monkeypatch.setattr(speech_transport, 'information', lambda *a: info)
    def immediate(url, credential, settings, data, observe=lambda receipt: False):
        raw = wav_fixture()
        result = receipt(data, raw)
        stopped = observe(result)
        return result, None if stopped else raw
    monkeypatch.setattr(speech_transport, 'render', render or immediate)


def receipt(data, raw):
    return SpeechReceipt(id=data.id, model=data.model, voice=data.voice, input_sha256=hashlib.sha256(data.input.encode()).hexdigest(), state='completed',
        sha256=hashlib.sha256(raw).hexdigest(), frames=6000, execution_released=True, manifest_sha256='a'*64, cancel_requested=False)


def test_saved_speech_owner_scope_route_binding_idempotency_and_reload(bff, monkeypatch):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    fixture_provider(monkeypatch)
    with factory('admin') as admin, factory() as user, factory() as other:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        target = configure_speech(admin, ah)
        signin(user)
        uh = csrf(user, settings.user_origin)
        path, message = reply(user, uh)
        endpoint = path+'/messages/'+message['id']+'/speech'
        body = {'request_id': str(uuid4())}
        assert user.post(endpoint, json=body).status_code == 403
        assert user.post(endpoint, headers=uh, json=body | {'input': 'untrusted replacement'}).status_code == 422
        assert user.post(endpoint, headers=uh, json=body).status_code == 202
        result = wait_speech(user, path)
        assert result['status'] == 'completed'
        assert (result['model_id'], result['voice']) == (MODEL, VOICE)
        url = path+'/speech/'+result['id']+'/audio'
        assert validate_wav(user.get(url).content) == 6000
        assert user.get(url).headers['cache-control'] == 'no-store'
        assert user.post(endpoint, headers=uh, json=body).json()['id'] == result['id']
        assert user.post(endpoint, headers=uh, json={'request_id': str(uuid4())}).json()['id'] == result['id']
        other_path, other_message = reply(user, uh)
        assert user.get(other_path+'/speech/'+result['id']+'/audio').status_code == 404
        assert user.post(other_path+'/messages/'+message['id']+'/speech', headers=uh, json={'request_id': str(uuid4())}).status_code == 404
        assert user.post(other_path+'/messages/'+other_message['id']+'/speech', headers=uh, json=body).status_code == 409
        human = user.get(path).json()['messages'][0]['id']
        assert user.post(path+'/messages/'+human+'/speech', headers=uh, json={'request_id': str(uuid4())}).status_code == 409
        with scoped_session(app, admin.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            saved = db.execute(text('SELECT request,route_receipt FROM speech_jobs WHERE id=:id'), {'id': result['id']}).mappings().one()
            assert saved['request']['input'] == message['content']
            assert saved['route_receipt']['target_id'] == target
            db.execute(text("UPDATE inference_targets SET model_id='renamed-target' WHERE id=:id"), {'id': target})
        with factory() as fresh:
            signin(fresh)
            assert fresh.get(path).json()['messages'][-1]['speech'] == result
            assert fresh.get(url).content == user.get(url).content
        other_subject = str(uuid4())
        monkeypatch.setattr(identity, 'verify_id_token', lambda *a: {'sub': other_subject, 'name': 'Other member'})
        monkeypatch.setattr(identity, 'token_request', lambda config, endpoint, data:
            {'active': True, 'sub': other_subject, 'iss': config.issuer} if endpoint == 'token/introspect' else
            {'id_token': 'OTHER FIXTURE', 'access_token': 'OTHER FIXTURE', 'refresh_token': 'OTHER FIXTURE', 'expires_in': 300})
        signin(other)
        from tests.integration.test_identity import approve_fixture_member
        approve_fixture_member(other, migration, settings)
        oh = csrf(other, settings.user_origin)
        assert other.get(url).status_code == 404
        assert other.post(endpoint, headers=oh, json=body).status_code == 404
        with scoped_session(app, other.get('/api/v1/session').json()['id'], settings.farm_id) as db:
            assert db.execute(text('SELECT count(*) FROM speech_jobs')).scalar_one() == 0


@pytest.mark.parametrize('ending', ['cancel', 'revoke', 'disconnect', 'manifest'])
def test_speech_drain_revocation_unknown_and_other_pools_stay_independent(bff, monkeypatch, ending):
    factory, settings, app, migration, _ = setup(bff, monkeypatch)
    fixture_provider(monkeypatch)
    entered, finish = threading.Event(), threading.Event()
    def render(url, key, settings, data, observe):
        entered.set()
        assert finish.wait(10)
        if ending == 'disconnect':
            raise ProviderError('Fixture connection lost after dispatch.', uncertain=True)
        raw = wav_fixture()
        result = receipt(data, raw)
        if ending == 'manifest':
            result.manifest_sha256 = 'b'*64
        stopped = observe(result)
        return result, None if stopped else raw
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        target = configure_speech(admin, ah)
        monkeypatch.setattr(speech_transport, 'render', render)
        signin(user)
        uh = csrf(user, settings.user_origin)
        path, message = reply(user, uh)
        body = {'request_id': str(uuid4())}
        endpoint = path+'/messages/'+message['id']+'/speech'
        try:
            assert user.post(endpoint, headers=uh, json=body).status_code == 202
            assert entered.wait(3)
            # A separate text pool remains usable during CPU speech generation.
            another, another_message = reply(user, uh)
            assert user.post(another+'/messages/'+another_message['id']+'/speech', headers=uh, json={'request_id': str(uuid4())}).status_code == 409
            item = next(row for row in admin.get('/api/v1/providers').json()['items'] if row['id'] == target)
            assert item['active_run_id'] == body['request_id']
            if ending == 'cancel':
                assert user.post(path+'/speech/'+body['request_id']+'/cancel', headers=uh).status_code == 200
                assert user.get(path).json()['messages'][-1]['speech']['status'] == 'running'
            if ending == 'revoke':
                with migration.begin() as db:
                    db.execute(text("DELETE FROM browser_sessions WHERE farm_id=:farm AND audience='user'"), {'farm': settings.farm_id})
        finally:
            finish.set()
        if ending == 'revoke':
            signin(user)
        result = wait_speech(user, path)
        assert result['status'] == ('interrupted' if ending == 'disconnect' else 'cancelled')
        assert user.get(path+'/speech/'+body['request_id']+'/audio').status_code == 404
        item = next(row for row in admin.get('/api/v1/providers').json()['items'] if row['id'] == target)
        assert item['execution_state'] == ('unknown' if ending == 'disconnect' else 'idle')


@pytest.mark.skipif(os.environ.get('HEARTH_LIVE_SPEECH') != '1', reason='Explicit running local speech provider required.')
def test_live_local_speech_from_saved_reply_restores_in_fresh_session(bff, monkeypatch):
    factory, settings, _, migration, _ = setup(bff, monkeypatch)
    # Text/OIDC are explicit fixtures; speech transport, Kokoro and database are real.
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        configure(admin, ah)
        key = Path('.hearth/speech-provider/controller.key').read_text(encoding='utf-8').strip()
        configure_speech(admin, ah, key)
        signin(user)
        uh = csrf(user, settings.user_origin)
        path, message = reply(user, uh)
        start = time.monotonic()
        sent = user.post(path+'/messages/'+message['id']+'/speech', headers=uh, json={'request_id': str(uuid4())})
        assert sent.status_code == 202, sent.text
        for _ in range(600):
            result = user.get(path).json()['messages'][-1]['speech']
            if result['status'] != 'running':
                break
            time.sleep(.1)
        assert result['status'] == 'completed', result
        url = path+'/speech/'+result['id']+'/audio'
        raw = user.get(url).content
        frames = validate_wav(raw)
        with factory() as fresh:
            signin(fresh)
            assert fresh.get(url).content == raw
            assert fresh.get(path).json()['messages'][-1]['speech'] == result
        out = Path('evidence/speech/2026-09-13')
        out.mkdir(parents=True, exist_ok=True)
        (out/'live-read-aloud.wav').write_bytes(raw)
        (out/'live-read-aloud.json').write_text(json.dumps({'scope': 'Real CPU Kokoro, authenticated provider transport and restricted PostgreSQL/BFF APIs, with explicit text/OIDC fixtures in a disposable farm.', 'model': result['model_id'], 'voice': result['voice'], 'text': message['content'], 'audio_seconds': frames/24000, 'elapsed_seconds': round(time.monotonic()-start, 3), 'sha256': hashlib.sha256(raw).hexdigest(), 'restored_audio_and_identity': True, 'perceptual_quality': 'Not established by waveform validation.'}, indent=2), encoding='utf-8')
