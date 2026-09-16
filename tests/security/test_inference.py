import json
from contextlib import contextmanager

import httpx
import pytest
from hearth import inference
from hearth.config import Settings
from hearth.inference import (
    ContextLimitError,
    ProviderError,
    chat_stream,
    endpoint,
    list_models,
    normalize_url,
)


@pytest.mark.parametrize('url', ['http://user:secret@localhost:1234', 'file:///tmp/key', 'http://localhost:1234/v1?key=secret', 'https://localhost/other', 'https://localhost/#x', 'http://localhost\\@other', 'http://localhost:99999'])
def test_reject_ambiguous_addresses(url):
    with pytest.raises(ProviderError):
        normalize_url(url)


@pytest.mark.parametrize('url', ['http://169.254.169.254', 'https://8.8.8.8', 'http://192.168.1.5:1234', 'http://127.0.0.1:8445', 'http://[::ffff:169.254.169.254]'])
def test_no_metadata_cloud_lan_plaintext_or_hearth_loop(url):
    with pytest.raises(ProviderError):
        endpoint(url, Settings(mode='test'))


def test_dns_pinning_preserves_host_and_sni_and_rejects_mixed_answers(monkeypatch):
    monkeypatch.setattr(inference.socket, 'getaddrinfo', lambda *a, **kw: [(2, 1, 6, '', ('192.168.1.40', 443))])
    url, authority, sni = endpoint('https://models.home/v1/', Settings(mode='test'))
    assert str(url) == 'https://192.168.1.40/v1'
    assert authority == sni == 'models.home'
    monkeypatch.setattr(inference.socket, 'getaddrinfo', lambda *a, **kw: [(2, 1, 6, '', (host, 443)) for host in ['192.168.1.40', '169.254.169.254']])
    with pytest.raises(ProviderError):
        endpoint('https://models.home', Settings(mode='test'))


def test_development_alias_is_specific_and_ipv6_loopback_supported():
    settings = Settings(mode='test', development_provider_aliases={'http://127.0.0.1:1234/v1': 'http://10.0.2.2:1234/v1'})
    assert str(endpoint('http://127.0.0.1:1234', settings)[0]) == 'http://10.0.2.2:1234/v1'
    assert str(endpoint('http://[::1]:1234', settings)[0]) == 'http://[::1]:1234/v1'
    with pytest.raises(ProviderError):
        endpoint('http://10.0.2.2:1235', settings)


def transport(monkeypatch, content, status=200, content_type='text/event-stream'):
    requests = []

    @contextmanager
    def client_for(*args):
        def handler(request):
            requests.append(request)
            return httpx.Response(status, headers={'content-type': content_type, 'location': 'http://169.254.169.254'}, content=content)
        with httpx.Client(base_url='http://fixture/v1/', transport=httpx.MockTransport(handler), follow_redirects=False) as client:
            yield client, {}
    monkeypatch.setattr(inference, 'client_for', client_for)
    return requests


def event(delta, finish=None, model='fixture'):
    return 'data: ' + json.dumps({'model': model, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}) + '\n\n'


@pytest.mark.parametrize('report,status', [
    ({'models': [{'type': 'llm', 'key': 'fixture', 'loaded_instances': []}]}, 200),
    ({'models': [{'type': 'embedding', 'loaded_instances': [{'id': 'fixture'}]}]}, 200),
    ({'models': [{'type': 'llm', 'loaded_instances': 'invalid'}]}, 200),
    ({'data': [{'id': 'fixture'}]}, 200),
    ({'models': []}, 503),
    ({'models': []}, 302),
])
def test_residency_fails_closed_without_sending_generation(monkeypatch, report, status):
    calls = transport(monkeypatch, json.dumps(report), status=status, content_type='application/json')
    settings = Settings(mode='test').model_copy(update={'provider_residency_policy': 'lmstudio_loaded'})
    with pytest.raises(ProviderError) as error:
        list(chat_stream('unused', '', 'fixture', [], settings))
    assert not error.value.uncertain
    assert len(calls) == 1
    assert calls[0].method == 'GET' and calls[0].url.path == '/api/v1/models'


def test_only_answer_text_is_forwarded_and_done_requires_finish(monkeypatch):
    requests = transport(monkeypatch, event({'reasoning_content': 'PRIVATE REASONING'}) + event({'content': '<script>plain text</script>'}) + event({}, 'stop') + 'data: [DONE]\n\n')
    events = list(chat_stream('unused', '', 'fixture', [{'role': 'user', 'content': 'hello'}], Settings(mode='test')))
    assert ''.join(value for kind, value in events if kind == 'text') == '<script>plain text</script>'
    assert events[-1] == ('done', 'stop')
    assert 'PRIVATE REASONING' not in str(events)
    payload = json.loads(requests[0].content)
    assert payload['stream'] is True and 'tools' not in payload
    assert payload['max_tokens'] == 16384


def test_explicit_probe_budget_is_not_inflated(monkeypatch):
    requests = transport(monkeypatch, event({'content': 'ready'}, 'stop') + 'data: [DONE]\n\n')
    list(chat_stream('unused', '', 'fixture', [], Settings(mode='test'), maximum_tokens=256))
    assert json.loads(requests[0].content)['max_tokens'] == 256


def test_reasoning_preview_is_opt_in_separate_and_never_a_tool(monkeypatch):
    transport(monkeypatch, event({'reasoning_content': '<script>model text</script>', 'content': 'Answer'}) + event({}, 'stop') + 'data: [DONE]\n\n')
    events = list(chat_stream('unused', '', 'fixture', [], Settings(mode='test'), include_reasoning=True))
    assert events[:2] == [('reasoning', '<script>model text</script>'), ('text', 'Answer')]
    assert events[-1] == ('done', 'stop')
    transport(monkeypatch, event({'reasoning_content': 'Only thinking'}, 'length')+'data: [DONE]\n\n')
    preview = chat_stream('unused', '', 'fixture', [], Settings(mode='test'), include_reasoning=True)
    assert next(preview) == ('reasoning', 'Only thinking')
    with pytest.raises(ProviderError, match='no answer'):
        list(preview)
    transport(monkeypatch, event({'reasoning_content': {'unexpected': 'object'}}))
    with pytest.raises(ProviderError, match='invalid stream'):
        list(chat_stream('unused', '', 'fixture', [], Settings(mode='test'), include_reasoning=True))
    transport(monkeypatch, event({'reasoning_content': 'not a grant', 'tool_calls': [{'function': {'name': 'shell'}}]}))
    with pytest.raises(ProviderError, match='tools are not enabled'):
        list(chat_stream('unused', '', 'fixture', [], Settings(mode='test'), include_reasoning=True))


@pytest.mark.parametrize('elapsed,should_finish', [(240, True), (901, False)])
def test_active_chat_can_outlast_old_three_minute_limit_but_is_bounded(monkeypatch, elapsed, should_finish):
    from types import SimpleNamespace
    requests = transport(monkeypatch, event({'content': 'Complete answer'}, 'stop') + 'data: [DONE]\n\n')
    ticks = iter([0, elapsed])
    monkeypatch.setattr(inference, 'time', SimpleNamespace(monotonic=lambda: next(ticks)))
    stream = chat_stream('unused', '', 'fixture', [], Settings(mode='test', chat_max_output_tokens=8192))
    if should_finish:
        assert list(stream)[-1] == ('done', 'stop')
    else:
        with pytest.raises(ProviderError, match='time limit') as error:
            list(stream)
        assert error.value.uncertain
    assert json.loads(requests[0].content)['max_tokens'] == 8192


def test_length_finish_is_preserved_with_final_answer_chunk(monkeypatch):
    transport(monkeypatch, event({'reasoning_content': 'not answer text'}) + event({'content': 'partial answer'}, 'length') + 'data: [DONE]\n\n')
    events = list(chat_stream('unused', '', 'fixture', [], Settings(mode='test')))
    assert events[-2:] == [('text', 'partial answer'), ('done', 'length')]


@pytest.mark.parametrize('stream', [event({'content': 'partial'}), event({'content': 'partial'}) + 'data: [DONE]\n\n', event({'tool_calls': [{'function': {'name': 'shell'}}]}), event({'content': 'wrong'}, model='other'), 'data: []\n\n', 'data: ' + 'x' * 262145], ids=['early-eof','missing-finish','tools','wrong-model','invalid-json-shape','oversize'])
def test_malformed_tools_mismatch_and_incomplete_streams_are_not_success(monkeypatch, stream):
    transport(monkeypatch, stream)
    with pytest.raises(ProviderError):
        list(chat_stream('unused', '', 'fixture', [], Settings(mode='test')))


def test_redirect_does_not_forward_credentials_and_model_list_is_bounded(monkeypatch):
    requests = transport(monkeypatch, '', status=302)
    with pytest.raises(ProviderError):
        list_models('unused', 'secret', Settings(mode='test'))
    assert len(requests) == 1
    transport(monkeypatch, 'x' * 262145, content_type='application/json')
    with pytest.raises(ProviderError):
        list_models('unused', '', Settings(mode='test'))


def test_observed_gpt_oss_final_header_is_removed_across_arbitrary_chunks():
    source = '<|channel|>commentary to=final <|constrain|>response<|message|>Ember.'
    for split in range(1, len(source)):
        decoder = inference.AnswerPrefix('openai/gpt-oss-20b')
        answer = decoder.feed(source[:split]) + decoder.feed(source[split:]) + decoder.feed('', final=True)
        assert answer == 'Ember.'
    decoder = inference.AnswerPrefix('openai/gpt-oss-20b')
    assert decoder.feed('An ordinary <tag> stays literal.') == 'An ordinary <tag> stays literal.'
    for header in ('analysis', 'commentary to=functions.shell'):
        decoder = inference.AnswerPrefix('openai/gpt-oss-20b')
        with pytest.raises(ProviderError):
            decoder.feed(f'<|channel|>{header}<|message|>not an answer')


def test_gpt_oss_final_json_format_is_data_without_tool_or_analysis_authority():
    for prefix in ('<|channel|>', '<|start|>assistant<|channel|>'):
        for label in ('JSON', 'json'):
            source = prefix + 'final <|constrain|>' + label + '<|message|>{"action":"clarify"}'
            for split in range(1, len(source)):
                decoder = inference.AnswerPrefix('openai/gpt-oss-20b')
                assert decoder.feed(source[:split]) + decoder.feed(source[split:]) + decoder.feed('', final=True) == '{"action":"clarify"}'
    for header in ('analysis <|constrain|>JSON', 'commentary to=functions.shell <|constrain|>JSON', 'final to=functions.shell <|constrain|>JSON', 'final <|constrain|>shell'):
        with pytest.raises(ProviderError):
            inference.AnswerPrefix('openai/gpt-oss-20b').feed('<|channel|>' + header + '<|message|>not an answer')
    source = '<|channel|>final <|constrain|>JSON<|message|>{}'
    assert inference.AnswerPrefix('other-model').feed(source) == source


def test_lmstudio_context_rejection_is_actionable_and_preserves_provider_qualification(monkeypatch):
    failure = {'error': 'Engine protocol predict request returned 400: '+json.dumps({'error': {
        'code': 400, 'type': 'exceed_context_size_error', 'message': 'DO NOT ECHO PRIVATE PROVIDER TEXT',
        'n_prompt_tokens': 28074, 'n_ctx': 8192}})}
    wire = 'data: '+json.dumps(failure)+'\n\n'
    transport(monkeypatch, wire)
    with pytest.raises(ContextLimitError) as caught:
        list(chat_stream('unused', '', 'fixture', [], Settings(mode='test')))
    assert '28,074' in str(caught.value) and '8,192' in str(caught.value)
    assert 'PRIVATE' not in str(caught.value)
    assert not caught.value.uncertain and not caught.value.provider_fault
    transport(monkeypatch, event({'content': 'partial'})+wire)
    with pytest.raises(ContextLimitError) as caught:
        list(chat_stream('unused', '', 'fixture', [], Settings(mode='test')))
    assert caught.value.uncertain
    transport(monkeypatch, 'data: '+json.dumps({'error': {'message': 'PRIVATE UNKNOWN ERROR'}})+'\n\n')
    with pytest.raises(ProviderError) as caught:
        list(chat_stream('unused', '', 'fixture', [], Settings(mode='test')))
    assert 'PRIVATE' not in str(caught.value) and caught.value.uncertain
