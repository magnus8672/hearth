"""Tools execute only after a complete, valid native provider stream."""
import json

import pytest
from hearth.client_api import Completion
from hearth.config import Settings
from hearth.inference import ProviderError, chat_stream
from hearth.tool_schemas import ToolCalls, valid_schema, validate_arguments
from pydantic import ValidationError

from tests.security.test_inference import event, transport

TOOLS = [{'type': 'function', 'function': {'name': 'add', 'parameters': {'type': 'object', 'properties': {'a': {'type': 'integer'}, 'b': {'type': 'integer'}}, 'required': ['a', 'b'], 'additionalProperties': False}}}]


def test_fragmented_native_tool_calls_require_finish_and_done_and_valid_arguments(monkeypatch):
    content = event({'tool_calls': [{'index': 0, 'id': 'call_1', 'type': 'function', 'function': {'name': 'add', 'arguments': '{"a":'}}]})
    content += event({'tool_calls': [{'index': 0, 'function': {'arguments': '20,"b":22}'}}]})
    transport(monkeypatch, content+event({}, 'tool_calls')+'data: [DONE]\n\n')
    result = list(chat_stream('unused', '', 'fixture', [], Settings(mode='test'), tools=TOOLS))
    assert [kind for kind, value in result if kind == 'tool_calls'] == ['tool_calls']
    calls = next(value for kind, value in result if kind == 'tool_calls')
    assert json.loads(calls[0]['function']['arguments']) == {'a': 20, 'b': 22}
    for suffix in ['', event({}, 'length')+'data: [DONE]\n\n', 'data: [DONE]\n\n']:
        transport(monkeypatch, content+suffix)
        observed = []
        with pytest.raises(ProviderError):
            for item in chat_stream('unused', '', 'fixture', [], Settings(mode='test'), tools=TOOLS):
                observed.append(item)
        assert not any(kind == 'tool_calls' for kind, _ in observed)


@pytest.mark.parametrize('call', [
    {'index': 0, 'id': 'call_1', 'function': {'name': 'hidden_shell', 'arguments': '{}'}},
    {'index': 0, 'id': 'call_1', 'function': {'name': 'add', 'arguments': '{"a":"wrong","b":2}'}},
    {'index': 0, 'id': 'call_1', 'function': {'name': 'add', 'arguments': '{"a":1,"b":2,"authority":"admin"}'}},
    {'index': 1, 'id': 'call_1', 'function': {'name': 'add', 'arguments': '{"a":1,"b":2}'}},
])
def test_invalid_tool_call_never_reaches_executor(monkeypatch, call):
    transport(monkeypatch, event({'tool_calls': [call]}, 'tool_calls')+'data: [DONE]\n\n')
    with pytest.raises(ProviderError):
        list(chat_stream('unused', '', 'fixture', [], Settings(mode='test'), tools=TOOLS))


@pytest.mark.parametrize('patch', [
    {'messages': [{'role': [], 'content': 'hello'}]},
    {'messages': [{'role': 'tool', 'content': 'hello', 'tool_call_id': {}}]},
    {'tools': [{'type': 'function', 'function': {'name': 'broken', 'description': 42, 'parameters': {'type': 'object'}}}]},
    {'tools': [{'type': 'function', 'function': {'name': 'broken', 'parameters': {'type': 'object', 'required': 'invalid'}}}]},
    {'tool_choice': {'type': 'function', 'function': []}},
])
def test_malformed_compatibility_payloads_are_validation_errors(patch):
    with pytest.raises(ValidationError):
        Completion.model_validate({'model': 'auto', 'messages': [{'role': 'user', 'content': 'hello'}]} | patch)


def test_local_schema_references_are_inlined_without_external_or_recursive_resolution():
    schema = {'type': 'object', 'properties': {'location': {'$ref': '#/$defs/Location'}}, 'required': ['location'], '$defs': {'Location': {'type': 'object', 'properties': {'city': {'type': 'string'}}, 'required': ['city']}}}
    flattened = valid_schema(schema)
    assert '$ref' not in json.dumps(flattened) and '$defs' not in flattened
    validate_arguments({'location': {'city': 'Portland'}}, flattened)
    with pytest.raises(ValueError):
        validate_arguments({'location': {'city': 123}}, flattened)
    for pointer in ['https://example.test/schema', '#/$defs/Location']:
        schema['$defs']['Location']['properties']['nested'] = {'$ref': pointer}
        with pytest.raises(ValueError):
            valid_schema(schema)


def test_client_reasoning_and_regex_schemas_do_not_relax_head_execution(monkeypatch):
    schema = {'type': 'object', 'properties': {'value': {'type': 'string', 'pattern': '^(a+)+$'}}}
    tool = {'type': 'function', 'function': {'name': 'client_check', 'parameters': schema}}
    data = Completion.model_validate({'model': 'auto', 'messages': [{'role': 'user', 'content': 'hello'}],
                                      'reasoning_effort': 'medium', 'tools': [tool]})
    assert data.reasoning_effort == 'medium'
    assert data.tools[0]['function']['parameters'] == schema
    with pytest.raises(ValueError, match='regular expressions'):
        valid_schema(schema)
    for effort in ('unlimited', 5, True):
        with pytest.raises(ValidationError):
            Completion.model_validate({'model': 'auto', 'messages': [{'role': 'user', 'content': 'hello'}], 'reasoning_effort': effort})

    def must_not_evaluate(*args, **kwargs):
        raise AssertionError('Caller-owned schemas must not run against returned arguments on the head.')
    monkeypatch.setattr('hearth.tool_schemas.validate_arguments', must_not_evaluate)
    calls = ToolCalls([tool], caller_owned=True)
    calls.feed([{'index': 0, 'id': 'test_call', 'function': {'name': 'client_check', 'arguments': json.dumps({'value': 'a'*10000+'!'})}}])
    assert calls.complete()[0]['function']['name'] == 'client_check'


@pytest.mark.parametrize('name,arguments', [('undeclared', '{}'), ('add', '[]'), ('add', '{'), ('add', '{"a":NaN}')])
def test_caller_owned_tools_still_enforce_wire_shape_and_declared_names(name, arguments):
    calls = ToolCalls(TOOLS, caller_owned=True)
    calls.feed([{'index': 0, 'id': 'test_call', 'function': {'name': name, 'arguments': arguments}}])
    with pytest.raises(ValueError):
        calls.complete()


def test_caller_schema_keeps_external_recursive_size_and_depth_boundaries():
    for schema in ({'type': 'object', '$ref': 'https://example.test/schema'},
                   {'type': 'object', '$dynamicRef': '#'},
                   {'type': 'object', 'description': 'x'*32768}):
        with pytest.raises(ValueError):
            valid_schema(schema, caller_owned=True)
