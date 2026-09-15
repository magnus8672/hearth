from types import SimpleNamespace

import pytest
from hearth import provider_health
from hearth.config import Settings
from hearth.inference import ProviderError


@pytest.mark.parametrize('protocol', ['hearth.image.v1', 'hearth.speech.v1', 'hearth.transcription.v1'])
def test_startup_requires_unchanged_qualified_media_information(monkeypatch, protocol):
    adapter = {'hearth.image.v1': provider_health.image_transport, 'hearth.speech.v1': provider_health.speech_transport,
               'hearth.transcription.v1': provider_health.transcription_transport}[protocol]
    info = {'model': 'fixture', 'manifest_sha256': 'a'*64, 'offline': True, 'job_cancellation': True}
    target = {'protocol': protocol, 'base_url': 'https://192.168.1.10:1236/v1', 'model_id': 'fixture', 'credential': '', 'profile': info | {'probe_word_error_rate': 0}}
    monkeypatch.setattr(adapter, 'information', lambda *a: SimpleNamespace(model_dump=lambda **kw: info.copy()))
    provider_health.check_connection(target, Settings(mode='test'))
    for field, value in [('model', 'different'), ('manifest_sha256', 'b'*64), ('offline', False), ('job_cancellation', False)]:
        old = info[field]
        info[field] = value
        with pytest.raises(ProviderError, match='changed'):
            provider_health.check_connection(target, Settings(mode='test'))
        info[field] = old


def test_startup_keeps_loaded_model_policy_and_scoped_http_consent(monkeypatch):
    seen = []
    def loaded(url, key, model, transport):
        seen.append((model, transport.provider_residency_policy, transport.provider_http_approved_url))
        raise ProviderError('Not resident.')
    monkeypatch.setattr(provider_health, 'list_models', lambda *a: ['fixture'])
    monkeypatch.setattr(provider_health, 'require_loaded_model', loaded)
    target = {'protocol': 'openai.chat.v1', 'base_url': 'http://192.168.1.10:1234/v1', 'model_id': 'fixture', 'credential': '', 'residency_policy': 'lmstudio_loaded', 'allow_insecure_http': True}
    with pytest.raises(ProviderError, match='resident'):
        provider_health.check_connection(target, Settings(mode='test'))
    assert seen == [('fixture', 'lmstudio_loaded', 'http://192.168.1.10:1234/v1')]
