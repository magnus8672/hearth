"""Non-mutating native function-call and result-consumption qualification."""
import json
import secrets

from hearth.inference import ProviderError, chat_stream


def probe(base_url, credential, model_id, settings):
    nonce = secrets.token_hex(6)
    schema = {'type': 'function', 'function': {'name': 'hearth_probe', 'description': 'Return the verification phrase. Call this once with the supplied nonce.', 'parameters': {'type': 'object', 'properties': {'nonce': {'type': 'string', 'enum': [nonce]}}, 'required': ['nonce'], 'additionalProperties': False}}}
    context = [{'role': 'user', 'content': f'Call hearth_probe with nonce {nonce}. After the result, reply with its verification phrase exactly.'}]
    calls, finished = None, None
    for kind, value in chat_stream(base_url, credential, model_id, context, settings, tools=[schema], tool_choice='required', maximum_tokens=4096):
        if kind == 'tool_calls':
            calls = value
        elif kind == 'done':
            finished = value
    if finished != 'tool_calls' or not calls or len(calls) != 1 or calls[0]['function']['name'] != 'hearth_probe' or json.loads(calls[0]['function']['arguments']) != {'nonce': nonce}:
        raise ProviderError('The model did not complete a native function call with valid arguments.')
    phrase = 'hearth tools '+secrets.token_hex(6)
    context += [{'role': 'assistant', 'content': None, 'tool_calls': calls}, {'role': 'tool', 'tool_call_id': calls[0]['id'], 'content': json.dumps({'verification_phrase': phrase})}]
    answer, finished = '', None
    for kind, value in chat_stream(base_url, credential, model_id, context, settings, tools=[schema], tool_choice='none', maximum_tokens=4096):
        if kind == 'text':
            answer += value
        elif kind == 'done':
            finished = value
    if finished != 'stop' or phrase not in answer:
        raise ProviderError('The model called a function but did not consume its returned result.')
    return {'tool_probe': 'native_call_and_result', 'tool_probe_version': 1}
