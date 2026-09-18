"""Actual MCP protocol over HTTP; schema drift, scoped credentials and at-most-once execution."""
import json
import socket
import threading
import time
from uuid import uuid4

import pytest
import uvicorn
from hearth import chat, identity, mcp_transport
from hearth.database import scoped_session
from hearth.inference import ProviderError
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from sqlalchemy import text

from tests.integration.test_chat import csrf, promote, setup, wait_finished
from tests.integration.test_client_api import key, prepared
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


@pytest.fixture
def upstream():
    server = MCPServer('Fixture tools', log_level='ERROR')
    executions = []
    @server.tool(structured_output=True)
    def add(a: int, b: int, ctx: Context) -> dict[str, object]:
        """Add two integers without changing anything."""
        executions.append((a, b, ctx.request_context.request.headers.get('authorization')))
        return {'sum': a+b}
    @server.tool(structured_output=True)
    def change_note(text: str) -> dict[str, object]:
        """Change the synthetic note. Explicit approval required."""
        executions.append(('write', text))
        return {'saved': text}
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    app = server.streamable_http_app(stateless_http=True, json_response=True)
    running = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
    thread = threading.Thread(target=running.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if running.started:
            break
        time.sleep(.02)
    assert running.started
    yield {'url': f'http://127.0.0.1:{port}/mcp', 'server': server, 'executions': executions}
    running.should_exit = True
    thread.join(5)
    sock.close()


def register(admin, settings, upstream):
    h = csrf(admin, settings.admin_origin)
    response = admin.post('/api/v1/tool-servers', headers=h, json={'name': 'Fixture workshop', 'base_url': upstream['url'], 'local_only': True, 'requires_credential': True, 'credential': 'fixture-owner-token'})
    assert response.status_code == 201, response.text
    saved = response.json()
    result = admin.post(f"/api/v1/tool-servers/{saved['id']}/discover", headers=h, json={'revision': 1})
    assert result.status_code == 200, result.text
    return admin.get('/api/v1/tool-servers').json()['items'][0]


def approve(admin, settings, tool, effect='read', access='owner'):
    result = admin.put('/api/v1/tool-catalog/'+tool['id'], headers=csrf(admin, settings.admin_origin), json={'revision': tool['revision'], 'enabled': True, 'access': access, 'effect': effect, 'capabilities': ['chat.general', 'code.implement']})
    assert result.status_code == 200, result.text


def rpc(user, auth, method, params=None, request_id=1):
    result = user.post('/mcp', headers=auth | {'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': '2025-11-25'}, json={'jsonrpc': '2.0', 'id': request_id, 'method': method, **({'params': params} if params is not None else {})})
    assert result.status_code == 200, result.text
    return result.json()


def call(user, auth, name, args):
    result = rpc(user, auth, 'tools/call', {'name': name, 'arguments': args})
    assert 'result' in result, result
    response = result['result']
    assert not response.get('isError'), response
    return response['structuredContent']


def test_exact_three_tool_manifest_discovery_execution_dedup_and_schema_change(bff, monkeypatch, upstream):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        signin(user)
        server = register(admin, settings, upstream)
        saved = key(user, settings)
        auth = {'Authorization': 'Bearer '+saved['key']}
        tools = rpc(user, auth, 'tools/list')['result']['tools']
        assert {item['name'] for item in tools} == {'list_tools', 'describe_tool', 'run_tool'}
        assert call(user, auth, 'list_tools', {})['tools'] == []
        add = next(tool for tool in server['tools'] if tool['name'] == 'add')
        approve(admin, settings, add)
        listed = call(user, auth, 'list_tools', {'query': 'add'})['tools']
        assert len(listed) == 1 and 'inputSchema' not in listed[0]
        described = call(user, auth, 'describe_tool', {'name': listed[0]['name']})
        arguments = {'name': described['name'], 'invocation_id': described['invocation_id'], 'arguments': {'a': 20, 'b': 22}}
        result = call(user, auth, 'run_tool', arguments)
        assert result['state'] == 'completed', result
        assert result['result']['structuredContent'] == {'sum': 42}
        assert upstream['executions'] == [(20, 22, 'Bearer fixture-owner-token')]
        assert call(user, auth, 'run_tool', arguments) == result
        assert len(upstream['executions']) == 1
        changed = rpc(user, auth, 'tools/call', {'name': 'run_tool', 'arguments': arguments | {'arguments': {'a': 2, 'b': 3}}})
        assert changed['result']['isError']
        # Replace the tool on the actual SDK server
        # Previously approved schema
        # must be rejected before the next upstream call can execute it.
        upstream['server'].remove_tool('add')
        @upstream['server'].tool(name='add')
        def replacement(a: int, b: int, extra: str = 'changed') -> int:
            """A changed operation which must not execute under the old approval."""
            upstream['executions'].append('unexpected replacement')
            return a+b
        arguments['invocation_id'] = str(uuid4())
        rejected = call(user, auth, 'run_tool', arguments)
        assert rejected['state'] == 'failed' and 'schema changed' in rejected['result']['message']
        assert len(upstream['executions']) == 1
        assert call(user, auth, 'list_tools', {})['tools'] == []


def test_write_requires_real_browser_approval_and_uncertain_receipts_do_not_replay(bff, monkeypatch, upstream):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        signin(user)
        server = register(admin, settings, upstream)
        change = next(tool for tool in server['tools'] if tool['name'] == 'change_note')
        approve(admin, settings, change, 'write')
        saved = key(user, settings)
        auth = {'Authorization': 'Bearer '+saved['key']}
        name = call(user, auth, 'list_tools', {})['tools'][0]['name']
        described = call(user, auth, 'describe_tool', {'name': name})
        args = {'name': name, 'arguments': {'text': 'review this exact fixture'}, 'invocation_id': described['invocation_id']}
        assert call(user, auth, 'run_tool', args)['state'] == 'awaiting_approval'
        assert not upstream['executions']
        path = '/api/v1/tool-invocations/'+args['invocation_id']+'/decision'
        assert user.post(path, headers=auth, json={'approve': True}).status_code == 403
        assert user.post(path, headers=csrf(user, settings.user_origin), json={'approve': True}).status_code == 200
        assert call(user, auth, 'run_tool', args)['state'] == 'completed'
        assert upstream['executions'] == [('write', 'review this exact fixture')]
        async def uncertain(*args):
            raise ProviderError('Outcome unknown.', uncertain=True)
        monkeypatch.setattr(mcp_transport, 'execute', uncertain)
        args['invocation_id'] = str(uuid4())
        call(user, auth, 'run_tool', args)
        user.post('/api/v1/tool-invocations/'+args['invocation_id']+'/decision', headers=csrf(user, settings.user_origin), json={'approve': True})
        assert call(user, auth, 'run_tool', args)['state'] == 'uncertain'
        assert call(user, auth, 'run_tool', args)['state'] == 'uncertain'


def test_mcp_credentials_and_approval_receipts_are_private_even_between_members(bff, monkeypatch, upstream):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    with factory('admin') as admin, factory() as user, factory() as other:
        signin(admin)
        promote(admin, migration, settings)
        signin(user)
        server = register(admin, settings, upstream)
        add = next(tool for tool in server['tools'] if tool['name'] == 'add')
        approve(admin, settings, add, access='members')
        first = key(user, settings)
        auth = {'Authorization': 'Bearer '+first['key']}
        name = call(user, auth, 'list_tools', {})['tools'][0]['name']
        described = call(user, auth, 'describe_tool', {'name': name})
        call(user, auth, 'run_tool', {'name': name, 'invocation_id': described['invocation_id'], 'arguments': {'a': 1, 'b': 2}})
        second_subject = str(uuid4())
        owner_token_request = identity.token_request
        monkeypatch.setattr(identity, 'verify_id_token', lambda *args: {'sub': second_subject, 'name': 'Other member'})
        monkeypatch.setattr(identity, 'token_request', lambda config, endpoint, data: {'active': True, 'sub': second_subject, 'iss': config.issuer} if endpoint == 'token/introspect' else {'id_token': 'fixture', 'access_token': 'fixture', 'refresh_token': 'fixture', 'expires_in': 300})
        member_token_request = identity.token_request
        signin(other)
        from tests.integration.test_identity import approve_fixture_member
        approve_fixture_member(other, migration, settings)
        other_key = key(other, settings)
        other_auth = {'Authorization': 'Bearer '+other_key['key']}
        mine = other.get('/api/v1/my-tools').json()
        assert mine['invocations'] == [] and not mine['servers'][0]['credential_configured']
        args = {'name': name, 'invocation_id': str(uuid4()), 'arguments': {'a': 4, 'b': 5}}
        assert rpc(other, other_auth, 'tools/call', {'name': 'run_tool', 'arguments': args})['result']['isError']
        assert other.put('/api/v1/my-tools/'+server['id']+'/credential', headers=csrf(other, settings.user_origin), json={'credential': 'fixture-second-token'}).status_code == 200
        assert call(other, other_auth, 'run_tool', args)['state'] == 'completed'
        assert upstream['executions'][-1] == (4, 5, 'Bearer fixture-second-token')
        assert other.post('/api/v1/tool-invocations/'+described['invocation_id']+'/decision', headers=csrf(other, settings.user_origin), json={'approve': True}).status_code == 409
        assert other.get('/api/v1/tool-servers').status_code == 403
        # Changing the registered connection invalidates each member's binding,
        # even if the URL remains the same. Never forward an old user's secret.
        monkeypatch.setattr(identity, 'token_request', owner_token_request)
        edited = admin.put('/api/v1/tool-servers/'+server['id']+'/connection', headers=csrf(admin, settings.admin_origin), json={'revision': server['revision'], 'name': 'Changed workshop', 'base_url': upstream['url'], 'local_only': True, 'requires_credential': True, 'credential': 'new-owner-token'})
        assert edited.status_code == 200, edited.text
        admin.post('/api/v1/tool-servers/'+server['id']+'/discover', headers=csrf(admin, settings.admin_origin), json={'revision': 2})
        current = admin.get('/api/v1/tool-servers').json()['items'][0]
        approve(admin, settings, next(t for t in current['tools'] if t['name'] == 'add'), access='members')
        monkeypatch.setattr(identity, 'token_request', member_token_request)
        assert not other.get('/api/v1/my-tools').json()['servers'][0]['credential_configured']
        before = len(upstream['executions'])
        args['invocation_id'] = str(uuid4())
        assert rpc(other, other_auth, 'tools/call', {'name': 'run_tool', 'arguments': args})['result']['isError']
        assert len(upstream['executions']) == before


@pytest.mark.parametrize('ending', ['approve', 'stop'])
def test_private_chat_uses_the_same_three_tools_and_releases_model_for_approval(bff, monkeypatch, upstream, ending):
    factory, settings, app, migration, subject = bff
    with factory('admin') as admin, factory() as user:
        settings, app, target, owner = prepared(bff, monkeypatch, admin, user)
        server = register(admin, settings, upstream)
        change = next(tool for tool in server['tools'] if tool['name'] == 'change_note')
        approve(admin, settings, change, 'write')
        phases = []
        def stream(base, credential, model, messages, config, **kwargs):
            assert {item['function']['name'] for item in kwargs['tools']} == {'list_tools', 'describe_tool', 'run_tool'}
            last = json.loads(messages[-1]['content']) if messages[-1]['role'] == 'tool' else None
            if last is None:
                name, args = 'list_tools', {}
            elif 'tools' in last:
                name, args = 'describe_tool', {'name': last['tools'][0]['name']}
            elif 'inputSchema' in last:
                name, args = 'run_tool', {'name': last['name'], 'invocation_id': last['invocation_id'], 'arguments': {'text': 'approved chat fixture'}}
            else:
                yield 'text', 'The synthetic note was updated.'
                yield 'done', 'stop'
                return
            phases.append(name)
            yield 'tool_calls', [{'id': 'call_'+str(len(phases)), 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]
            yield 'done', 'tool_calls'
        monkeypatch.setattr(chat, 'chat_stream', stream)
        headers = csrf(user, settings.user_origin)
        conversation = user.post('/api/v1/chats', headers=headers, json={}).json()
        path = '/api/v1/chats/'+conversation['id']
        assert user.post(path+'/turns', headers=headers, json={'request_id': str(uuid4()), 'revision': 1, 'content': 'Use the shared tool to change my note.'}).status_code == 202
        pending = None
        for _ in range(100):
            snapshot = user.get(path).json()
            pending = next((item for item in snapshot['runs'][-1]['tool_invocations'] if item['state'] == 'awaiting_approval'), None)
            if pending:
                break
            time.sleep(.05)
        assert pending, snapshot
        assert snapshot['runs'][-1]['status'] == 'running' and snapshot['runs'][-1]['tool_phase']
        with scoped_session(app, owner, settings.farm_id) as db:
            assert db.execute(text('SELECT active_run_id FROM provider_pools')).scalar_one() is None
        if ending == 'stop':
            assert user.post(path+'/stop', headers=headers).status_code == 200
            completed = wait_finished(user, path)
            assert completed['runs'][-1]['status'] == 'cancelled'
            assert completed['runs'][-1]['tool_invocations'][-1]['state'] == 'denied'
            assert not upstream['executions']
            assert user.post('/api/v1/tool-invocations/'+pending['id']+'/decision', headers=headers, json={'approve': True}).status_code == 409
            return
        assert user.post('/api/v1/tool-invocations/'+pending['id']+'/decision', headers=headers, json={'approve': True}).status_code == 200
        completed = wait_finished(user, path)
        assert completed['runs'][-1]['status'] == 'completed', completed['runs'][-1]
        assert phases == ['list_tools', 'describe_tool', 'run_tool']
        assert upstream['executions'] == [('write', 'approved chat fixture')]
        assert 'updated' in completed['messages'][-1]['content']


@pytest.mark.parametrize('when', ['before_dispatch', 'after_result'])
def test_mcp_key_revocation_blocks_dispatch_or_publication_but_keeps_actual_receipt(bff, monkeypatch, upstream, when):
    factory, settings, app, migration, subject = setup(bff, monkeypatch)
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        signin(user)
        owner = user.get('/api/v1/session').json()['id']
        server = register(admin, settings, upstream)
        approve(admin, settings, next(t for t in server['tools'] if t['name'] == 'add'))
        saved = key(user, settings)
        auth = {'Authorization': 'Bearer '+saved['key']}
        name = call(user, auth, 'list_tools', {})['tools'][0]['name']
        invocation = str(uuid4())
        execute = mcp_transport.execute
        def revoke():
            with scoped_session(app, owner, settings.farm_id) as db:
                db.execute(text('UPDATE client_keys SET revoked_at=now() WHERE id=:id'), {'id': saved['id']})
        async def during(*args):
            if when == 'before_dispatch':
                revoke()
            result = await execute(*args)
            if when == 'after_result':
                revoke()
            return result
        monkeypatch.setattr(mcp_transport, 'execute', during)
        response = rpc(user, auth, 'tools/call', {'name': 'run_tool', 'arguments': {'name': name, 'invocation_id': invocation, 'arguments': {'a': 3, 'b': 4}}})
        assert response['result']['isError']
        assert len(upstream['executions']) == (0 if when == 'before_dispatch' else 1)
        with scoped_session(app, owner, settings.farm_id) as db:
            receipt = db.execute(text('SELECT state,result FROM tool_invocations WHERE id=:id'), {'id': invocation}).mappings().one()
            assert receipt['state'] == ('failed' if when == 'before_dispatch' else 'completed')
            if when == 'after_result':
                assert receipt['result']['structuredContent'] == {'sum': 7}
