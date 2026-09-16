"""Bounded OpenAI-compatible transport. No model lifecycle or tool execution."""
import ipaddress
import json
import socket
import ssl
import time
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit

import httpx


class ProviderError(Exception):
    def __init__(self, message, *, uncertain=False, provider_fault=True):
        self.uncertain = uncertain
        self.provider_fault = provider_fault
        super().__init__(message)


class ContextLimitError(ProviderError):
    def __init__(self, requested=None, available=None):
        counts = f' ({requested:,} tokens requested; {available:,} available)' if requested and available else ''
        super().__init__('The request exceeds the model\'s loaded context window'+counts+
                         '. Increase its context length in the model server, or reduce the client\'s prompt and tools.',
                         provider_fault=False)


def stream_error(event):
    """Translate known rejection metadata without returning provider text."""
    problem = event.get('error')
    # LM Studio wraps an engine JSON error inside its own message string.
    for _ in range(2):
        if isinstance(problem, dict):
            if problem.get('type') in ('exceed_context_size_error', 'context_length_exceeded') or problem.get('code') == 'context_length_exceeded':
                requested, available = problem.get('n_prompt_tokens'), problem.get('n_ctx')
                if not all(type(value) is int and 0 < value <= 1_000_000_000 for value in (requested, available)):
                    requested = available = None
                return ContextLimitError(requested, available)
            message = problem.get('message')
        else:
            message = problem
        if not isinstance(message, str) or '{' not in message:
            break
        try:
            nested = json.loads(message[message.index('{'):])
            problem = nested.get('error', nested) if isinstance(nested, dict) else None
        except (ValueError, RecursionError):
            break
    return ProviderError('The model server reported a generation error. Check its logs.', uncertain=True)


class AnswerPrefix:
    """Narrow GPT-OSS interoperability profile for leaked leading final headers.

    Ordinary answer text is unchanged. Unknown channels, including analysis and
    tool recipients, fail closed rather than becoming a second execution path.
    See the observed LM Studio fixture and OpenAI harmony/docs/format.md.
    """
    def __init__(self, model_id):
        self.pending = ''
        self.decided = model_id not in {'openai/gpt-oss-20b', 'openai/gpt-oss-120b'}

    def feed(self, content, *, final=False):
        if self.decided:
            return content
        self.pending += content
        candidate = self.pending.lstrip()
        prefixes = ('<|channel|>', '<|start|>assistant<|channel|>')
        prefix = next((item for item in prefixes if candidate.startswith(item)), None)
        if prefix:
            if '<|message|>' not in candidate:
                if len(candidate) > 512 or final:
                    raise ProviderError('The model returned an incomplete channel header. Check its server chat template.', uncertain=not final)
                return ''
            header, answer = candidate[len(prefix):].split('<|message|>', 1)
            if ' '.join(header.split()) not in {'final', 'final <|constrain|>response', 'final <|constrain|>JSON', 'final <|constrain|>json', 'commentary to=final <|constrain|>response'}:
                raise ProviderError('The model returned an unsupported channel. Check its server chat template.', uncertain=True)
            self.decided = True
            return answer
        if not final and any(item.startswith(candidate) for item in prefixes):
            return ''
        self.decided = True
        return self.pending


def normalize_url(value):
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path not in {'', '/', '/v1', '/v1/'}
                or any(ord(c) <= 32 for c in value) or '\\' in value):
            raise ValueError()
        host = parsed.hostname.encode('idna').decode('ascii').lower()
        if '%' in host or host.endswith('.'):
            raise ValueError()
        authority = f'[{host}]' if ':' in host else host
        if port is not None and port != (443 if parsed.scheme == 'https' else 80):
            authority += f':{port}'
        return urlunsplit((parsed.scheme, authority, '/v1', '', ''))
    except (ValueError, UnicodeError):
        raise ProviderError('Use a server base address, with no credentials, query string or path other than /v1.') from None


def endpoint(value, settings):
    canonical = normalize_url(value)
    aliases = settings.development_provider_aliases if settings.mode != 'production' else {}
    transport = normalize_url(aliases.get(canonical, canonical))
    parsed = urlsplit(transport)
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)}
    except OSError:
        raise ProviderError('The model server address could not be resolved.') from None
    for address in addresses:
        ip = ipaddress.ip_address(address)
        ip = getattr(ip, 'ipv4_mapped', None) or ip
        networks = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', 'fc00::/7')
        if not ip.is_loopback and not any(ip in ipaddress.ip_network(network) for network in networks):
            raise ProviderError('This address is not an eligible model server.')
        if (parsed.scheme == 'http' and not ip.is_loopback and canonical not in aliases
                and getattr(settings, 'provider_http_approved_url', '') != canonical):
            raise ProviderError('This LAN server uses unencrypted HTTP. An administrator can accept the risks on its provider card, or use HTTPS.')
        if ip.is_loopback and (parsed.port or 80) in {8080, 8085, 8443, 8444, 8445}:
            raise ProviderError('Choose a model server, not a hearth application or identity address.')
    if not addresses:
        raise ProviderError('The model server has no usable address.')
    # Pin the resolved address for this connection. Keep original Host and SNI
    # so TLS still validates the configured server name, never an arbitrary IP.
    address = sorted(addresses)[0]
    return httpx.URL(transport).copy_with(host=address), parsed.netloc, parsed.hostname


@contextmanager
def client_for(base_url, credential, settings):
    url, authority, server_name = endpoint(base_url, settings)
    headers = {'Host': authority, 'Accept': 'application/json'}
    if credential:
        if any(ord(c) < 32 or ord(c) > 126 for c in credential):
            raise ProviderError('The API key contains unsupported characters.')
        headers['Authorization'] = 'Bearer ' + credential
    ca_pem = getattr(settings, 'provider_ca_pem', '')
    trust = ssl.create_default_context(cadata=ca_pem) if ca_pem else True
    with httpx.Client(base_url=str(url) + '/', headers=headers, verify=trust, timeout=httpx.Timeout(30, connect=5),
                      follow_redirects=False, trust_env=False) as client:
        yield client, {'sni_hostname': server_name}


def response_ok(response):
    if not 200 <= response.status_code < 300:
        raise ProviderError(f'The model server rejected the request (HTTP {response.status_code}).',
                            uncertain=response.status_code >= 500)


def list_models(base_url, credential, settings):
    started = time.monotonic()
    try:
        with client_for(base_url, credential, settings) as (client, extensions), client.stream('GET', 'models', extensions=extensions) as response:
            response_ok(response)
            raw = bytearray()
            for block in response.iter_bytes():
                raw.extend(block)
                if len(raw) > 262144 or time.monotonic() - started > 30:
                    raise ProviderError('The model list exceeds the supported size.')
            data = json.loads(raw)
            entries = data.get('data')
            if not isinstance(entries, list) or len(entries) > 1000:
                raise ValueError()
            return [item['id'] for item in entries if isinstance(item, dict) and isinstance(item.get('id'), str) and 0 < len(item['id']) <= 200]
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ProviderError('The model server returned an invalid model list.') from None
    except httpx.HTTPError:
        raise ProviderError('The model server is unreachable. Check its address, certificate and API key.') from None


def require_loaded_model(base_url, credential, model_id, settings):
    """Read-only LM Studio preflight; never call load/download/unload endpoints.

    This is an observation, not a reservation. The operator must disable JIT
    loading on the service to close the gap between this GET and inference.
    """
    if getattr(settings, 'provider_residency_policy', 'unknown') != 'lmstudio_loaded':
        return
    started = time.monotonic()
    try:
        with client_for(base_url, credential, settings) as (client, extensions):
            address = client.base_url.copy_with(path='/api/v1/models')
            with client.stream('GET', address, extensions=extensions) as response:
                if response.status_code != 200:
                    raise ProviderError('Cannot check loaded models. This target requires LM Studio /api/v1/models; check the service and connector version.')
                raw = bytearray()
                for block in response.iter_bytes():
                    raw.extend(block)
                    if len(raw) > 262144 or time.monotonic() - started > 30:
                        raise ProviderError('The loaded-model check exceeded its size or time limit.')
                entries = json.loads(raw)['models']
                if not isinstance(entries, list) or len(entries) > 1000:
                    raise ValueError()
                for entry in entries:
                    if not isinstance(entry, dict) or entry.get('type') != 'llm':
                        continue
                    instances = entry.get('loaded_instances')
                    if not isinstance(instances, list):
                        raise ValueError()
                    if any(isinstance(item, dict) and item.get('id') == model_id for item in instances):
                        return
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ProviderError('The server returned an invalid loaded-model report. No generation was sent.') from None
    except httpx.HTTPError:
        raise ProviderError('Cannot confirm that the model is loaded. No generation was sent.') from None
    raise ProviderError('The selected model instance is not loaded on this server. Load it there, keep automatic loading disabled, and verify again. No generation was sent.')


def chat_stream(base_url, credential, model_id, messages, settings, *, maximum_tokens=None, include_reasoning=False,
                tools=None, tool_choice=None, parameters=None, caller_owned_tools=False):
    """Yield answer text, optional separate reasoning, heartbeats and completion.

    Reasoning fields and tool calls never become executable input or UI HTML.
    A caller may stop displaying output while continuing to drain this iterator.
    """
    require_loaded_model(base_url, credential, model_id, settings)
    started = time.monotonic()
    # Interactive replies need room for reasoning as well as visible output.
    # Explicit probe/planner budgets retain their smaller three-minute bound.
    deadline = settings.chat_timeout_seconds if maximum_tokens is None else 180
    maximum_tokens = settings.chat_max_output_tokens if maximum_tokens is None else maximum_tokens
    payload = {'model': model_id, 'messages': messages, 'stream': True, 'max_tokens': maximum_tokens,
               'temperature': 0.3}
    if parameters:
        payload.update(parameters)
    from hearth.tool_schemas import ToolCalls
    calls = ToolCalls(tools, caller_owned=caller_owned_tools)
    if tools:
        payload.update(tools=tools, tool_choice=tool_choice or 'auto')
    finished = None
    total = 0
    saw_answer = False
    answer_prefix = AnswerPrefix(model_id)
    try:
        with client_for(base_url, credential, settings) as (client, extensions), client.stream('POST', 'chat/completions', json=payload, extensions=extensions) as response:
            response_ok(response)
            if 'text/event-stream' not in response.headers.get('content-type', ''):
                raise ProviderError('This model server did not return a streaming response.', uncertain=True)
            pending = b''
            for block in response.iter_bytes():
                total += len(block)
                if total > 16_000_000 or time.monotonic() - started > deadline:
                    raise ProviderError('The response exceeded its size or time limit.', uncertain=True)
                pending += block
                if len(pending) > 262144:
                    raise ProviderError('A stream event exceeded its size limit.', uncertain=True)
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    line = line.strip()
                    if not line.startswith(b'data:'):
                        continue
                    data = line[5:].strip()
                    if data == b'[DONE]':
                        if not finished:
                            raise ProviderError('The response ended without a completion receipt.')
                        trailing = answer_prefix.feed('', final=True)
                        if trailing:
                            saw_answer = saw_answer or bool(trailing.strip())
                            yield ('text', trailing)
                        if finished == 'tool_calls':
                            if not tools or tool_choice == 'none':
                                raise ValueError()
                            yield ('tool_calls', calls.complete())
                        elif calls.items:
                            raise ProviderError('The model did not finish its tool call. No tool was executed.')
                        if not saw_answer and finished != 'tool_calls':
                            raise ProviderError('The model returned no answer. Check the model and output limit.')
                        yield ('done', finished)
                        return
                    event = json.loads(data)
                    if event.get('error'):
                        problem = stream_error(event)
                        if saw_answer or calls.items or finished:
                            # A late error cannot prove execution never began.
                            problem.uncertain = True
                        raise problem
                    if event.get('model') and event['model'] != model_id:
                        raise ProviderError('The server answered with a different model.', uncertain=True)
                    choices = event.get('choices', [])
                    if not choices:
                        if tools is not None and isinstance(event.get('usage'), dict):
                            yield ('usage', {key: value for key, value in event['usage'].items() if key in {'prompt_tokens', 'completion_tokens', 'total_tokens'} and type(value) is int and value >= 0})
                        continue
                    if len(choices) != 1 or choices[0].get('index', 0) != 0:
                        raise ProviderError('The model returned an unsupported choice sequence.', uncertain=True)
                    choice = choices[0]
                    delta = choice.get('delta', {})
                    if delta.get('tool_calls'):
                        if not tools or tool_choice == 'none':
                            raise ProviderError('This chat target requested a tool, but tools are not enabled.', uncertain=True)
                        calls.feed(delta['tool_calls'])
                    # Opt in only for private chat previews. Probes, planners and
                    # other callers retain their answer-only contract.
                    reasoning = delta.get('reasoning_content')
                    if include_reasoning and reasoning is not None:
                        if not isinstance(reasoning, str):
                            raise ValueError()
                        if reasoning:
                            yield ('reasoning', reasoning)
                    content = delta.get('content')
                    if content is not None and not isinstance(content, str):
                        raise ValueError()
                    if content:
                        content = answer_prefix.feed(content)
                        if content:
                            saw_answer = saw_answer or bool(content.strip())
                            yield ('text', content)
                        else:
                            yield ('heartbeat', '')
                    else:
                        yield ('heartbeat', '')
                    if choice.get('finish_reason') is not None:
                        if choice['finish_reason'] not in ({'stop', 'length', 'tool_calls'} if tools else {'stop', 'length'}):
                            raise ProviderError('The model did not complete a supported text response.', uncertain=True)
                        finished = choice['finish_reason']
            raise ProviderError('The model stream ended unexpectedly. Partial output is preserved.', uncertain=True)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ProviderError('The model server returned an invalid stream event.', uncertain=True) from None
    except httpx.ConnectError:
        raise ProviderError('The model server is unreachable. Start it and check the connection.') from None
    except httpx.HTTPError:
        raise ProviderError('The model connection was interrupted. The server may still be generating.', uncertain=True) from None
