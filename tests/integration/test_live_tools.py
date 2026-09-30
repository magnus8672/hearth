"""Opt-in qualification using an explicitly configured resident LAN model and a real MCP server."""
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from tests.integration.test_chat import csrf, promote, wait_finished
from tests.integration.test_client_api import key
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases
from tests.integration.test_toolbox import approve, register
from tests.integration.test_toolbox import upstream as upstream
from tests.live_targets import configured_provider


@pytest.mark.skipif(os.environ.get('HEARTH_LIVE_TOOLS') != '1', reason='Explicit live resident tool qualification required.')
def test_resident_qwen_client_function_roundtrip_and_shared_mcp_chat(bff, upstream):
    factory, settings, app, migration, subject = bff
    url, model = configured_provider()
    def loaded():
        return sorted(item['id'] for row in httpx.get(url+'/api/v1/models', timeout=10, trust_env=False).raise_for_status().json()['models'] for item in row['loaded_instances'])
    before = loaded()
    assert model in before
    with migration.connect() as db:
        assert not db.execute(text('SELECT 1 FROM provider_pools WHERE farm_id<>:farm AND active_run_id IS NOT NULL'), {'farm': settings.farm_id}).first(), 'Wait for user requests to finish before the live model test.'
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        ah = csrf(admin, settings.admin_origin)
        target = admin.post('/api/v1/providers', headers=ah, json={'name': 'Live tools fixture', 'base_url': url, 'model_id': model, 'local_only': True, 'allow_insecure_http': True, 'residency_policy': 'lmstudio_loaded'}).json()
        probe = admin.post('/api/v1/providers/'+target['id']+'/probe', headers=ah, json={'revision': 1, 'tools': True})
        assert probe.status_code == 200 and 'tools' in probe.json()['features'], probe.text
        signin(user)
        saved = key(user, settings)
        auth = {'Authorization': 'Bearer '+saved['key']}
        function = {'type': 'function', 'function': {'name': 'read_project_title', 'description': 'Read the title of the synthetic test project.', 'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}}
        messages = [{'role': 'user', 'content': 'Call read_project_title to find this project title, then tell me that exact title.'}]
        response = user.post('/v1/chat/completions', headers=auth, json={'model': 'chat.general', 'messages': messages, 'tools': [function], 'tool_choice': 'required'})
        assert response.status_code == 200, response.text
        message = response.json()['choices'][0]['message']
        assert response.json()['choices'][0]['finish_reason'] == 'tool_calls'
        calls = message['tool_calls']
        assert len(calls) == 1 and calls[0]['function']['name'] == 'read_project_title'
        messages += [message, {'role': 'tool', 'tool_call_id': calls[0]['id'], 'content': '{"title":"Copper Finch Workshop"}'}]
        response = user.post('/v1/chat/completions', headers=auth, json={'model': 'chat.general', 'messages': messages, 'tools': [function], 'tool_choice': 'none', 'stream': True})
        assert response.status_code == 200 and '[DONE]' in response.text
        pieces = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: {')]
        answer = ''.join(item['choices'][0]['delta'].get('content', '') for item in pieces if item.get('choices'))
        assert 'Copper Finch Workshop' in answer
        server = register(admin, settings, upstream)
        add = next(tool for tool in server['tools'] if tool['name'] == 'add')
        approve(admin, settings, add)
        uh = csrf(user, settings.user_origin)
        path = '/api/v1/chats/'+user.post('/api/v1/chats', headers=uh, json={}).json()['id']
        request = {'request_id': str(uuid4()), 'revision': 1, 'content': 'Use the shared MCP tool to add 17 and 25. First list_tools to find addition, describe_tool to get its schema and invocation_id, then run_tool with those exact fields. Report the returned sum. Do not calculate it yourself.'}
        assert user.post(path+'/turns', headers=uh, json=request).status_code == 202
        result = wait_finished(user, path, timeout=300)
        assert result['runs'][-1]['status'] == 'completed', result['runs'][-1]['reason']
        assert upstream['executions'] == [(17, 25, 'Bearer fixture-owner-token')]
        assert '42' in result['messages'][-1]['content']
        assert loaded() == before
        folder = Path('.hearth/test-results/tools/2026-09-14')
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'live-qwen.json').write_text(json.dumps({'model': model, 'native_tool_probe': probe.json()['features'], 'client_alias': 'chat.general', 'client_owned_function': 'read_project_title', 'client_tool_result_consumed': True, 'shared_mcp_steps': ['list_tools', 'describe_tool', 'run_tool'], 'shared_tool_result': 42, 'loaded_models_unchanged': True, 'synthetic_farm': True, 'real_user_data_accessed': False}, indent=2)+'\n')
