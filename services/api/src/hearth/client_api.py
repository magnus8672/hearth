"""Capability aliases over an explicitly bounded Chat Completions profile.

Client tools round-trip to the caller. This surface never executes them on the
head, imports private chat memory, or sends the caller's key to an upstream.
"""
import json
import queue
import threading
import time
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy import text

from hearth import routing
from hearth.client_keys import bearer, key_current
from hearth.database import scoped_session
from hearth.inference import ProviderError, chat_stream
from hearth.provider_health import record_failure
from hearth.providers import claim_pool, credential_for, release_pool, target_record, transport_settings
from hearth.tool_schemas import NAME, valid_schema

router = APIRouter(dependencies=[Depends(HTTPBearer(auto_error=False))])


class Completion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: str = Field(min_length=1, max_length=80)
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
    tools: list[dict[str, Any]] = Field(default_factory=list, max_length=64)
    tool_choice: Any = None
    stream: StrictBool = False
    stream_options: dict[str, StrictBool] | None = None
    max_tokens: int | None = Field(default=None, strict=True, ge=1, le=65536)
    max_completion_tokens: int | None = Field(default=None, strict=True, ge=1, le=65536)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    stop: str | list[str] | None = None
    seed: int | None = None
    n: Literal[1] = 1
    parallel_tool_calls: StrictBool | None = None
    response_format: dict | None = None
    user: str | None = Field(default=None, max_length=200)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)

    @model_validator(mode='after')
    def supported(self):
        try:
            return self.validate_profile()
        except (TypeError, KeyError, AttributeError, RecursionError) as exc:
            raise ValueError('Malformed message or tool definition.') from exc

    def validate_profile(self):
        if self.model not in {'auto', *routing.TEXT}:
            raise ValueError('Select a supported text capability, not an upstream model.')
        if self.max_tokens is not None and self.max_completion_tokens is not None:
            raise ValueError('Set only one completion limit.')
        if self.stream_options and set(self.stream_options) - {'include_usage'}:
            raise ValueError('Unsupported streaming option.')
        if self.response_format not in (None, {'type': 'text'}, {'type': 'json_object'}):
            raise ValueError('Only text and json_object response formats are supported.')
        names = set()
        for tool in self.tools:
            if set(tool) != {'type', 'function'} or tool['type'] != 'function' or not isinstance(tool['function'], dict):
                raise ValueError('Use function tools.')
            function = tool['function']
            if set(function) - {'name', 'description', 'parameters', 'strict'} or not NAME.fullmatch(function.get('name', '')):
                raise ValueError('Unsupported function definition.')
            if function['name'] in names or len(function.get('description', '')) > 8000:
                raise ValueError('Duplicate tool or oversized description.')
            names.add(function['name'])
            function['parameters'] = valid_schema(function.get('parameters', {}))
        if self.tool_choice not in (None, 'auto', 'none', 'required'):
            if not isinstance(self.tool_choice, dict) or self.tool_choice.get('type') != 'function' or set(self.tool_choice) != {'type', 'function'} or set(self.tool_choice['function']) != {'name'} or self.tool_choice['function']['name'] not in names:
                raise ValueError('Choose a function declared in this request.')
        if not self.tools and self.tool_choice not in (None, 'none'):
            raise ValueError('Tool choice requires tools.')
        pending, seen = set(), set()
        saw_conversation = False
        for message in self.messages:
            if set(message) - {'role', 'content', 'name', 'tool_calls', 'tool_call_id', 'reasoning_content'}:
                raise ValueError('Unsupported message fields.')
            role = message.get('role')
            if role not in {'system', 'developer', 'user', 'assistant', 'tool'}:
                raise ValueError('Unsupported role.')
            content = message.get('content')
            if content is None and role != 'assistant':
                raise ValueError('This message requires text content.')
            if 'name' in message and not NAME.fullmatch(message['name']):
                raise ValueError('Unsupported message name.')
            if not isinstance(content, str) and content is not None:
                # Text-part arrays are used by some current agent SDKs.
                if not isinstance(content, list) or any(not isinstance(part, dict) or set(part) != {'type', 'text'} or part['type'] != 'text' or not isinstance(part['text'], str) for part in content):
                    raise ValueError('This client profile accepts text messages only.')
                message['content'] = '\n'.join(part['text'] for part in content)
            if role in {'system', 'developer'} and saw_conversation:
                raise ValueError('System messages must precede the conversation.')
            if role not in {'system', 'developer'}:
                saw_conversation = True
            if role == 'tool':
                call_id = message.get('tool_call_id')
                if call_id not in pending:
                    raise ValueError('Tool results must match outstanding assistant calls.')
                pending.remove(call_id)
            elif pending:
                raise ValueError('Provide all pending tool results before continuing.')
            if message.get('tool_calls'):
                if role != 'assistant' or not isinstance(message['tool_calls'], list) or len(message['tool_calls']) > 16:
                    raise ValueError('Invalid assistant tool calls.')
                for call in message['tool_calls']:
                    if not isinstance(call, dict) or set(call) != {'id', 'type', 'function'} or call['type'] != 'function' or not NAME.fullmatch(call.get('id', '')) or call['id'] in seen:
                        raise ValueError('Invalid or duplicate tool call ID.')
                    function = call['function']
                    if not isinstance(function, dict) or set(function) != {'name', 'arguments'} or not NAME.fullmatch(function.get('name', '')) or not isinstance(function.get('arguments'), str) or not isinstance(json.loads(function['arguments']), dict):
                        raise ValueError('Invalid tool call arguments.')
                    seen.add(call['id'])
                    pending.add(call['id'])
            if role != 'tool' and 'tool_call_id' in message:
                raise ValueError('Only tool results carry tool_call_id.')
            # Keep provider reasoning out of future prompts; it is not an answer.
            message.pop('reasoning_content', None)
        if pending or not saw_conversation or not any(item['role'] == 'user' for item in self.messages):
            raise ValueError('Complete the conversation and outstanding tool results.')
        if self.stop is not None:
            stops = [self.stop] if isinstance(self.stop, str) else self.stop
            if not 1 <= len(stops) <= 4 or any(not isinstance(s, str) or not 1 <= len(s) <= 200 for s in stops):
                raise ValueError('Use at most four bounded stop strings.')
        return self


@router.get('/v1/models', tags=['clients'])
def models(request: Request):
    client = bearer(request)
    with scoped_session(request.app.state.engine, client.principal.id, client.principal.farm_id) as db:
        available = [cap for cap in routing.TEXT if cap in client.capabilities and routing.candidates(db, cap)]
    return {'object': 'list', 'data': [{'id': cap, 'object': 'model', 'created': 0, 'owned_by': 'hearth'} for cap in (['auto'] if available else [])+available]}


def normalize_messages(capability, data):
    leading, rest = [], []
    for item in data.messages:
        if item['role'] in {'system', 'developer'}:
            leading.append(item.get('content') or '')
        else:
            rest.append(item)
    context = ([{'role': 'system', 'content': '\n\n'.join(leading)}] if leading else [])+rest
    return routing.context_for(capability, context, tools=bool(data.tools))


def admit(engine, settings, client, data):
    principal = client.principal
    if data.tools and not client.allow_tools:
        raise HTTPException(403, 'This key does not allow tool calls. Create a key with tool access enabled.')
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner,21))'), {'owner': str(principal.id)})
        if not key_current(db, principal, client.key_id):
            raise HTTPException(401, 'This client key is no longer active.')
        if db.execute(text("SELECT count(*) FROM client_runs r JOIN provider_pools p ON p.active_run_id=r.id WHERE r.state='running' AND p.lease_until>now()")).scalar_one() >= 4:
            raise HTTPException(429, 'This account already has four active client requests.')
        content = next(item.get('content') or '' for item in reversed(data.messages) if item['role'] == 'user')
        capability = routing.text_capability(db, content, data.model)
        if capability not in client.capabilities:
            raise HTTPException(403, 'This key does not permit the selected capability. Choose an allowed capability explicitly.')
        target = routing.select(db, capability, tools=bool(data.tools))
        if not target:
            raise HTTPException(503, 'No ready, idle target supports this capability'+(' with verified tool calling.' if data.tools else '.'))
        run_id = uuid4()
        claim_pool(db, target, run_id, principal.id)
        receipt = routing.receipt(db, capability, target)
        db.execute(text('INSERT INTO client_runs(id,farm_id,owner_id,key_id,target_id,route_receipt) VALUES(:id,:farm,:owner,:key,:target,CAST(:receipt AS jsonb))'), {'id': run_id, 'farm': principal.farm_id, 'owner': principal.id, 'key': client.key_id, 'target': target['id'], 'receipt': json.dumps(receipt)})
    return run_id, target, receipt, normalize_messages(capability, data)


def produce(engine, settings, client, data, run_id, target, context, emit, disconnected):
    principal = client.principal
    problem, finished, revoked = None, False, False
    last_check = 0
    parameters = {key: getattr(data, key) for key in ('temperature', 'top_p', 'stop', 'seed', 'parallel_tool_calls', 'response_format', 'presence_penalty', 'frequency_penalty') if getattr(data, key) is not None}
    parameters['stream_options'] = {'include_usage': True}
    maximum = data.max_completion_tokens or data.max_tokens or settings.chat_max_output_tokens
    transport = transport_settings(target, settings).model_copy(update={'chat_max_output_tokens': min(maximum, settings.chat_max_output_tokens)})
    try:
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            if not key_current(db, principal, client.key_id):
                raise ProviderError('The client key was revoked before dispatch.', provider_fault=False)
        for kind, value in chat_stream(target['base_url'], credential_for(target, settings), target['model_id'], context, transport,
                                       tools=data.tools, tool_choice=data.tool_choice, parameters=parameters, include_reasoning=True):
            if time.monotonic()-last_check >= .5 or kind in {'done', 'tool_calls'}:
                with scoped_session(engine, principal.id, principal.farm_id) as db:
                    current = target_record(db, target['id'])
                    revoked = revoked or not key_current(db, principal, client.key_id) or current['revision'] != target['revision'] or current['active_run_id'] != run_id or current['state'] != 'ready'
                    db.execute(text("UPDATE provider_pools SET lease_until=now()+interval '240 seconds' WHERE id=:pool AND active_run_id=:id"), {'pool': target['resource_pool_id'], 'id': run_id})
                last_check = time.monotonic()
            if kind == 'done':
                finished = True
            if not revoked and not disconnected.is_set():
                emit(kind, value)
        if revoked:
            raise ProviderError('The client key or route was revoked during this response.', provider_fault=False)
        if not finished:
            raise ProviderError('The provider response was interrupted.', uncertain=True)
    except ProviderError as exc:
        problem = exc
    except Exception:
        problem = ProviderError('The provider response was interrupted.', uncertain=True)
    finally:
        try:
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                db.execute(text('UPDATE client_runs SET state=:state,finished_at=now() WHERE id=:id'), {'id': run_id, 'state': 'interrupted' if disconnected.is_set() or (problem and problem.uncertain) else 'failed' if problem else 'completed'})
                record_failure(db, target, problem)
                release_pool(db, target['resource_pool_id'], run_id, uncertain=bool(problem and problem.uncertain))
        except Exception:
            # Do not publish a successful completion without its durable receipt.
            # An unavailable database leaves the existing lease to expire.
            problem = ProviderError('The response receipt could not be saved.', uncertain=True, provider_fault=False)
        if problem:
            emit('error', str(problem))
        emit('end', None)


def error_body(message, code='invalid_request'):
    return {'error': {'message': message, 'type': 'hearth_error', 'param': None, 'code': code}}


@router.post('/v1/chat/completions', tags=['clients'])
def completion(request: Request, data: Completion):
    client = bearer(request)
    engine, settings = request.app.state.engine, request.app.state.settings
    run_id, target, receipt, context = admit(engine, settings, client, data)
    events = queue.Queue(maxsize=256)
    disconnected = threading.Event()
    def emit(kind, value):
        if disconnected.is_set():
            return
        try:
            events.put((kind, value), timeout=2)
        except queue.Full:
            disconnected.set()
    future = request.app.state.inference_executor.submit(produce, engine, settings, client, data, run_id, target, context, emit, disconnected)
    def received():
        while True:
            if disconnected.is_set():
                yield 'error', 'The client could not receive the response quickly enough.'
                yield 'end', None
                return
            try:
                item = events.get(timeout=1)
            except queue.Empty:
                if future.done():
                    yield 'error', 'The response worker stopped before confirming completion.'
                    yield 'end', None
                    return
                yield 'heartbeat', None
                continue
            yield item
            if item[0] == 'end':
                return
    response_id = 'chatcmpl-'+run_id.hex
    created = int(time.time())
    from urllib.parse import quote
    headers = {'X-Hearth-Capability': receipt['capability_id'], 'X-Hearth-Model': quote(target['model_id'], safe='/.-_'), 'X-Hearth-Run-ID': str(run_id)}
    def chunks():
        finish, usage = None, None
        def event(delta, reason=None):
            return {'id': response_id, 'object': 'chat.completion.chunk', 'created': created, 'model': data.model,
                    'choices': [{'index': 0, 'delta': delta, 'finish_reason': reason}]}
        try:
            yield 'data: '+json.dumps(event({'role': 'assistant'}))+'\n\n'
            for kind, value in received():
                if kind == 'heartbeat':
                    yield ': waiting\n\n'
                    continue
                if kind == 'end':
                    if finish:
                        yield 'data: '+json.dumps(event({}, finish))+'\n\n'
                        if usage and data.stream_options and data.stream_options.get('include_usage'):
                            yield 'data: '+json.dumps(event({}) | {'choices': [], 'usage': usage})+'\n\n'
                        yield 'data: [DONE]\n\n'
                    return
                if kind == 'error':
                    finish = None
                    yield 'data: '+json.dumps(error_body(value, 'generation_failed'))+'\n\n'
                elif kind == 'done':
                    finish = value
                elif kind == 'usage':
                    usage = value
                elif kind in {'text', 'reasoning', 'tool_calls'}:
                    delta = {('content' if kind == 'text' else 'reasoning_content' if kind == 'reasoning' else 'tool_calls'): ([dict(item, index=index) for index, item in enumerate(value)] if kind == 'tool_calls' else value)}
                    yield 'data: '+json.dumps(event(delta))+'\n\n'
        finally:
            disconnected.set()
    if data.stream:
        return StreamingResponse(chunks(), media_type='text/event-stream', headers=headers | {'X-Accel-Buffering': 'no'})
    answer, reasoning, calls, finish, usage, failure = '', '', None, None, None, None
    for kind, value in received():
        if kind == 'end':
            break
        if kind == 'text':
            answer += value
        elif kind == 'reasoning':
            reasoning += value
        elif kind == 'tool_calls':
            calls = value
        elif kind == 'done':
            finish = value
        elif kind == 'usage':
            usage = value
        elif kind == 'error':
            failure = value
    if failure or not finish:
        return JSONResponse(error_body(failure or 'The response did not complete.', 'generation_failed'), status_code=502, headers=headers)
    message = {'role': 'assistant', 'content': answer or None}
    if calls:
        message['tool_calls'] = calls
    if reasoning:
        message['reasoning_content'] = reasoning
    response = {'id': response_id, 'object': 'chat.completion', 'created': created, 'model': data.model, 'choices': [{'index': 0, 'message': message, 'finish_reason': finish}]}
    if usage:
        response['usage'] = usage
    return JSONResponse(response, headers=headers)
