"""Bounded private-chat tool loop sharing the network MCP facade's executor."""
import json
import time

from fastapi import HTTPException
from sqlalchemy import text

from hearth import toolbox
from hearth.database import scoped_session
from hearth.inference import ProviderError
from hearth.mcp_gateway import MANIFEST, dispatch
from hearth.providers import claim_pool, credential_for, release_pool, target_record, transport_settings


def stream(engine, settings, principal, run_id, target, context, transport_stream):
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        capability = db.execute(text('SELECT capability_id FROM chat_runs WHERE id=:id'), {'id': run_id}).scalar_one()
        scope = toolbox.ToolScope(principal, frozenset({capability}), capability, chat_run_id=run_id)
        enabled = 'tool.use' in principal.permissions and 'tools' in target['features'] and bool(toolbox.allowed_tools(db, scope))
    if not enabled:
        yield from transport_stream(target['base_url'], credential_for(target, settings), target['model_id'], context, transport_settings(target, settings), include_reasoning=True)
        return
    context = list(context)
    started, executions = time.monotonic(), 0
    for _ in range(8):
        calls, answer, finish = None, '', None
        for kind, value in transport_stream(target['base_url'], credential_for(target, settings), target['model_id'], context, transport_settings(target, settings), tools=MANIFEST, include_reasoning=True):
            if kind == 'tool_calls':
                calls = value
            elif kind == 'done':
                finish = value
            else:
                if kind == 'text':
                    answer += value
                yield kind, value
        if finish != 'tool_calls':
            yield 'done', finish
            return
        if not calls or len(calls) > 8 or executions+len(calls) > 16 or time.monotonic()-started > 900:
            raise ProviderError('This turn reached its tool-work limit. Ask to continue with a smaller step.', provider_fault=False)
        try:
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                toolbox.scope_current(db, scope)
                current = target_record(db, target['id'], lock=True)
                if current['revision'] != target['revision'] or current['active_run_id'] != run_id:
                    raise HTTPException(409, 'The model target changed.')
                db.execute(text('UPDATE chat_runs SET tool_phase=true,tool_phase_at=now() WHERE id=:id'), {'id': run_id})
                release_pool(db, target['resource_pool_id'], run_id)
            context.append({'role': 'assistant', 'content': answer or None, 'tool_calls': calls})
            yield 'heartbeat', ''
            for call in calls:
                executions += 1
                function = call['function']
                try:
                    arguments = json.loads(function['arguments'])
                    result = dispatch(engine, settings, scope, function['name'], arguments)
                    while result.get('state') == 'awaiting_approval' and time.monotonic()-started < 900:
                        # No model slot is held while a human reviews this action.
                        yield 'heartbeat', ''
                        time.sleep(.3)
                        result = dispatch(engine, settings, scope, function['name'], arguments)
                except (HTTPException, ValueError) as exc:
                    result = {'error': exc.detail if isinstance(exc, HTTPException) else 'The tool arguments were invalid. Describe the tool and correct them.'}
                encoded = json.dumps(result, ensure_ascii=False)
                if len(encoded.encode()) > 32768:
                    encoded = json.dumps({'message': 'Tool output exceeded the model context allowance. A prefix follows; it may be incomplete.', 'prefix': encoded.encode()[:30000].decode(errors='ignore')})
                context.append({'role': 'tool', 'tool_call_id': call['id'], 'content': encoded})
                with scoped_session(engine, principal.id, principal.farm_id) as db:
                    toolbox.scope_current(db, scope)
            waiting = time.monotonic()
            while True:
                with scoped_session(engine, principal.id, principal.farm_id) as db:
                    toolbox.scope_current(db, scope)
                    current = target_record(db, target['id'], lock=True, idle_only=True)
                    if current and (current['revision'] != target['revision'] or current['state'] != 'ready'):
                        raise HTTPException(409, 'The model target changed while waiting for tools.')
                    if current:
                        claim_pool(db, current, run_id, principal.id)
                        db.execute(text('UPDATE chat_runs SET tool_phase=false,tool_phase_at=NULL WHERE id=:id'), {'id': run_id})
                        break
                if time.monotonic()-waiting > 90 or time.monotonic()-started > 900:
                    raise HTTPException(409, 'The model stayed busy after tool work. Start another turn to continue.')
                yield 'heartbeat', ''
                time.sleep(.3)
        except HTTPException as exc:
            raise ProviderError(str(exc.detail), provider_fault=False) from None
    raise ProviderError('This turn reached its tool-work limit. Ask to continue with a smaller step.', provider_fault=False)
