import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from hearth import routing, summary_transport
from hearth.inference import ProviderError, chat_stream

INFO = dict(protocol='hearth.summary.v1', model='hazyresearch/ncm-xsum', revision='c'*40,
            task='xsum', input_tokens=512, output_tokens=48, device='cpu', chat=False, tools=False, streaming=False)


def wire(monkeypatch, change=lambda value: value, status=200):
    calls = []
    def respond(request):
        if request.method == 'GET':
            return httpx.Response(200, json=INFO)
        data = json.loads(request.content)
        calls.append(data)
        result = dict(id=data['id'], model=data['model'], revision=INFO['revision'], text='A library reopened.',
                      input_tokens=20, output_tokens=4, truncated=False, elapsed_seconds=1.0)
        return httpx.Response(status, json=change(result))
    @contextmanager
    def client(*args):
        with httpx.Client(base_url='http://127.0.0.1:1242/v1/', transport=httpx.MockTransport(respond)) as c:
            yield c, {}
    monkeypatch.setattr(summary_transport, 'client_for', client)
    return calls


def test_ncm_routes_only_to_summarization():
    target = dict(protocol='hearth.summary.v1', state='ready', features=['text.summarize', 'summary.single_document'])
    assert routing.readiness('text.summarize', target)[0]
    for cap in ('chat.general', 'reason.plan', 'code.implement', 'vision.describe', 'decision.evaluate'):
        assert not routing.readiness(cap, target)[0]
    assert not routing.readiness('text.summarize', target | {'features': []})[0]


def test_summary_transport_one_final_answer_no_fake_token_stream(monkeypatch):
    calls = wire(monkeypatch)
    result = list(chat_stream('http://127.0.0.1:1242/v1', '', INFO['model'],
                             [{'role': 'system', 'content': 'private memory must not leave'},
                              {'role': 'user', 'content': 'The library reopened.'}],
                             SimpleNamespace(provider_protocol='hearth.summary.v1')))
    assert result == [('text', 'A library reopened.'), ('done', 'stop')]
    assert len(calls) == 1 and calls[0]['text'] == 'The library reopened.'


def test_summary_rejects_smaller_output_budget_before_dispatch(monkeypatch):
    calls = wire(monkeypatch)
    with pytest.raises(ProviderError, match='fixed output budget'):
        list(chat_stream('http://127.0.0.1:1242/v1', '', INFO['model'],
                         [{'role': 'user', 'content': 'Article'}],
                         SimpleNamespace(provider_protocol='hearth.summary.v1'), maximum_tokens=16))
    assert calls == []


@pytest.mark.parametrize('change', [lambda x: x | {'id': 'wrong'}, lambda x: x | {'model': 'chat'},
                                    lambda x: x | {'revision': 'd'*40}, lambda x: x | {'truncated': True},
                                    lambda x: x | {'output_tokens': 49}])
def test_summary_receipt_mismatch_fences_execution(monkeypatch, change):
    calls = wire(monkeypatch, change)
    with pytest.raises(ProviderError) as error:
        summary_transport.summarize('http://127.0.0.1:1242/v1', '', INFO['model'], 'Article', SimpleNamespace())
    assert error.value.uncertain and len(calls) == 1


@pytest.mark.parametrize('status', [400, 413, 422, 503])
def test_known_rejection_does_not_poison_provider(monkeypatch, status):
    wire(monkeypatch, status=status)
    with pytest.raises(ProviderError) as error:
        summary_transport.summarize('http://127.0.0.1:1242/v1', '', INFO['model'], 'Article', SimpleNamespace())
    assert not error.value.uncertain and not error.value.provider_fault


def test_history_tools_images_and_client_system_prompts_are_not_silently_dropped():
    one = {'role': 'user', 'content': 'article'}
    assert summary_transport.source_from_messages([one], caller_owned=True) == 'article'
    for messages in ([one, {'role': 'assistant', 'content': 'old'}, one],
                     [one | {'attachment_ids': ['uploaded-image']}],
                     [{'role': 'user', 'content': [{'type': 'image_url'}]}],
                     [{'role': 'system', 'content': 'Translate instead'}, one]):
        with pytest.raises(ProviderError):
            summary_transport.source_from_messages(messages, caller_owned=True)


def test_runtime_has_no_chat_route_and_bounds_input():
    path = Path(__file__).resolve().parents[2]/'runtimes/ncm/serve.py'
    spec = importlib.util.spec_from_file_location('ncm_runtime_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Network tests use a real loopback server on the authorized runtime host.
    from http.server import ThreadingHTTPServer
    from threading import Thread
    calls = []
    class Model:
        def summarize(self, text):
            calls.append(text)
            if text == 'too long':
                raise ValueError('512-token limit exceeded')
            return dict(text='Summary', input_tokens=2, output_tokens=1, truncated=False)
    server = ThreadingHTTPServer(('127.0.0.1', 0), module.handler(Model(), 'a'*64, 'cpu'))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}', trust_env=False) as c:
            assert c.get('/v1/models').status_code == 401
            c.headers['Authorization'] = 'Bearer '+'a'*64
            assert c.post('/v1/chat/completions', json={}).status_code == 404
            from uuid import uuid4
            body = dict(id=str(uuid4()), model=INFO['model'], text='article')
            assert c.post('/v1/summaries', json=body | {'extra': True}).status_code == 400
            assert c.post('/v1/summaries', json=body | {'text': 'too long'}).status_code == 422
            result = c.post('/v1/summaries', json=body)
            assert result.status_code == 200 and result.json()['id'] == body['id']
            assert calls == ['too long', 'article']
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
