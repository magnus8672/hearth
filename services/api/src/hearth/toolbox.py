"""Shared, reviewed MCP catalog with private credentials and durable executions."""
import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool
from sqlalchemy import text

from hearth import mcp_transport
from hearth.chat import member
from hearth.client_keys import audit, key_current, principal_current
from hearth.database import scoped_session
from hearth.identity import authenticate, cipher
from hearth.inference import ProviderError
from hearth.policy import Principal, permissions_for
from hearth.providers import validate_ca
from hearth.routing import TEXT
from hearth.tool_schemas import validate_arguments

router = APIRouter()
CAPABILITIES = {*TEXT, 'vision.describe'}


class RegisterServer(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=2048)
    tls_ca_pem: str = Field(default='', max_length=16384)
    allow_insecure_http: StrictBool = False
    requires_credential: StrictBool = False
    credential: SecretStr = SecretStr('')
    local_only: StrictBool


class Revision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(strict=True, ge=1)


class SetServer(Revision):
    enabled: StrictBool


class EditServer(RegisterServer, Revision):
    clear_credential: StrictBool = False


class ApproveTool(Revision):
    enabled: StrictBool
    access: Literal['owner', 'members']
    effect: Literal['read', 'write']
    capabilities: list[str] = Field(min_length=1, max_length=8)


class SetCredential(BaseModel):
    model_config = ConfigDict(extra='forbid')
    credential: SecretStr


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approve: StrictBool


def admin(request, mutation=False):
    principal = authenticate(request, mutation)
    if request.app.state.settings.audience != 'admin':
        raise HTTPException(403, 'Open Administration to manage shared tools.')
    principal.require('tool.approve')
    return principal


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def public_name(row):
    return 'mcp_'+row['server_id'].hex+'__'+row['name']


def secret(db, server, principal, settings):
    encrypted = db.execute(text('SELECT credential FROM mcp_credentials WHERE server_id=:id AND connection_revision=:revision'), {'id': server['id'], 'revision': server['connection_revision']}).scalar_one_or_none()
    if not encrypted and server['requires_credential']:
        raise HTTPException(409, 'Add your own credential for this tool server in Workspace, Tools.')
    return cipher(settings).decrypt(encrypted.encode()).decode() if encrypted else ''


def save_credential(db, server_id, principal, settings, value):
    if len(value) > 2048 or any(ord(c) < 32 or ord(c) > 126 for c in value):
        raise HTTPException(400, 'Use a Bearer credential with at most 2048 printable characters.')
    if value:
        db.execute(text('INSERT INTO mcp_credentials(server_id,farm_id,owner_id,credential,connection_revision) SELECT :id,:farm,:owner,:secret,connection_revision FROM mcp_servers WHERE id=:id ON CONFLICT(server_id,owner_id) DO UPDATE SET credential=excluded.credential,connection_revision=excluded.connection_revision'), {'id': server_id, 'farm': principal.farm_id, 'owner': principal.id, 'secret': cipher(settings).encrypt(value.encode()).decode()})
    else:
        db.execute(text('DELETE FROM mcp_credentials WHERE server_id=:id'), {'id': server_id})


@router.get('/api/v1/tool-servers', tags=['tools'])
def servers(request: Request):
    principal = admin(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        servers = db.execute(text('SELECT * FROM mcp_servers ORDER BY created_at')).mappings().all()
        tools = db.execute(text('SELECT * FROM mcp_tools ORDER BY name')).mappings().all()
        return {'items': [dict(server) | {'tools': [dict(tool) for tool in tools if tool['server_id'] == server['id']]} for server in servers], 'capabilities': sorted(CAPABILITIES)}


@router.post('/api/v1/tool-servers', tags=['tools'], status_code=201)
def register(request: Request, data: RegisterServer):
    principal = admin(request, True)
    return register_server(request.app.state.engine, request.app.state.settings, principal, data)


def register_server(engine, settings, principal, data):
    principal.require('tool.approve')
    if not data.local_only:
        raise HTTPException(400, 'Register a local tool service. Cloud tool services are not enabled.')
    url = mcp_transport.normalize_mcp_url(data.base_url)
    validate_ca(data.tls_ca_pem)
    if data.allow_insecure_http and not url.startswith('http://') or data.tls_ca_pem and not url.startswith('https://'):
        raise HTTPException(400, 'Match the HTTP approval or CA certificate to the endpoint scheme.')
    server_id = uuid4()
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:farm,22))'), {'farm': str(principal.farm_id)})
        if db.execute(text('SELECT count(*) FROM mcp_servers')).scalar_one() >= 32:
            raise HTTPException(409, 'This build supports up to 32 tool servers.')
        if db.execute(text('SELECT 1 FROM mcp_servers WHERE base_url=:url'), {'url': url}).first():
            raise HTTPException(409, 'That MCP endpoint is already registered.')
        db.execute(text('INSERT INTO mcp_servers(id,farm_id,owner_id,name,base_url,tls_ca_pem,allow_insecure_http,requires_credential) VALUES(:id,:farm,:owner,:name,:url,:ca,:http,:requires)'), {'id': server_id, 'farm': principal.farm_id, 'owner': principal.id, 'name': data.name, 'url': url, 'ca': data.tls_ca_pem, 'http': data.allow_insecure_http, 'requires': data.requires_credential})
        save_credential(db, server_id, principal, settings, data.credential.get_secret_value())
        audit(db, principal, 'tool.server.registered.http_accepted' if data.allow_insecure_http else 'tool.server.registered', server_id)
    return {'id': server_id, 'revision': 1}


@router.post('/api/v1/tool-servers/{server_id}/discover', tags=['tools'])
def discover(request: Request, server_id: UUID, data: Revision):
    principal = admin(request, True)
    return discover_server(request.app.state.engine, request.app.state.settings, principal, server_id, data.revision)


def discover_server(engine, settings, principal, server_id, revision):
    principal.require('tool.approve')
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        row = db.execute(text('SELECT * FROM mcp_servers WHERE id=:id'), {'id': server_id}).mappings().one_or_none()
        if not row or row['revision'] != revision or not row['enabled']:
            raise HTTPException(409, 'The tool server changed or is disabled. Refresh before discovering.')
        server, credential = dict(row), secret(db, row, principal, settings)
    try:
        definitions = asyncio.run(mcp_transport.discover(server, credential, settings))
    except ProviderError as exc:
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            db.execute(text('UPDATE mcp_servers SET reason=:reason WHERE id=:id AND revision=:revision'), {'reason': str(exc), 'id': server_id, 'revision': revision})
        raise
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        current = db.execute(text('SELECT * FROM mcp_servers WHERE id=:id FOR UPDATE'), {'id': server_id}).mappings().one()
        if current['revision'] != revision or not principal_current(db, principal):
            raise HTTPException(409, 'The server or account changed during discovery. Refresh and retry.')
        names = []
        for definition in definitions:
            names.append(definition['name'])
            db.execute(text('INSERT INTO mcp_tools(id,farm_id,server_id,name,definition,schema_hash) VALUES(:id,:farm,:server,:name,CAST(:definition AS jsonb),:hash) ON CONFLICT(server_id,name) DO UPDATE SET definition=excluded.definition,schema_hash=excluded.schema_hash,enabled=CASE WHEN mcp_tools.schema_hash=excluded.schema_hash THEN mcp_tools.enabled ELSE false END,revision=CASE WHEN mcp_tools.schema_hash=excluded.schema_hash THEN mcp_tools.revision ELSE mcp_tools.revision+1 END'), {'id': uuid4(), 'farm': principal.farm_id, 'server': server_id, 'name': definition['name'], 'definition': json.dumps(definition), 'hash': fingerprint(definition)})
        db.execute(text('UPDATE mcp_tools SET enabled=false,revision=revision+1 WHERE server_id=:id AND NOT(name=ANY(:names)) AND enabled'), {'id': server_id, 'names': names})
        db.execute(text('UPDATE mcp_servers SET checked_at=now(),catalog_revision=catalog_revision+1,reason=NULL WHERE id=:id'), {'id': server_id})
        audit(db, principal, 'tool.catalog.discovered', server_id)
    return {'count': len(definitions)}


@router.put('/api/v1/tool-servers/{server_id}', tags=['tools'])
def set_server(request: Request, server_id: UUID, data: SetServer):
    principal = admin(request, True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        if not db.execute(text('UPDATE mcp_servers SET enabled=:enabled,revision=revision+1 WHERE id=:id AND revision=:revision RETURNING id'), {'id': server_id, 'revision': data.revision, 'enabled': data.enabled}).first():
            raise HTTPException(409, 'The tool server changed. Refresh before saving.')
        audit(db, principal, 'tool.server.enabled' if data.enabled else 'tool.server.disabled', server_id)
    return {'saved': True}


@router.put('/api/v1/tool-servers/{server_id}/connection', tags=['tools'])
def edit_server(request: Request, server_id: UUID, data: EditServer):
    principal = admin(request, True)
    url = mcp_transport.normalize_mcp_url(data.base_url)
    validate_ca(data.tls_ca_pem)
    if not data.local_only or (data.allow_insecure_http and not url.startswith('http://')) or (data.tls_ca_pem and not url.startswith('https://')):
        raise HTTPException(400, 'Confirm locality and match trust settings to the endpoint scheme.')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:farm,22))'), {'farm': str(principal.farm_id)})
        server = db.execute(text('SELECT * FROM mcp_servers WHERE id=:id FOR UPDATE'), {'id': server_id}).mappings().one_or_none()
        if not server or server['revision'] != data.revision:
            raise HTTPException(409, 'The tool connection changed. Refresh before editing.')
        if db.execute(text('SELECT 1 FROM mcp_servers WHERE base_url=:url AND id<>:id'), {'url': url, 'id': server_id}).first():
            raise HTTPException(409, 'That endpoint is already registered.')
        db.execute(text("UPDATE mcp_servers SET name=:name,base_url=:url,tls_ca_pem=:ca,allow_insecure_http=:http,requires_credential=:requires,revision=revision+1,connection_revision=connection_revision+1,checked_at=NULL,reason='Connection changed. Discover and review its tools again.' WHERE id=:id"), {'id': server_id, 'name': data.name, 'url': url, 'ca': data.tls_ca_pem, 'http': data.allow_insecure_http, 'requires': data.requires_credential})
        db.execute(text('UPDATE mcp_tools SET enabled=false,revision=revision+1 WHERE server_id=:id'), {'id': server_id})
        if data.credential.get_secret_value() or data.clear_credential:
            save_credential(db, server_id, principal, request.app.state.settings, data.credential.get_secret_value())
        audit(db, principal, 'tool.server.connection_changed', server_id)
    return {'saved': True}


@router.put('/api/v1/tool-catalog/{tool_id}', tags=['tools'])
def approve_tool(request: Request, tool_id: UUID, data: ApproveTool):
    principal = admin(request, True)
    if not set(data.capabilities) <= CAPABILITIES:
        raise HTTPException(400, 'Choose supported model capabilities for this tool.')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        if not db.execute(text('UPDATE mcp_tools SET enabled=:enabled,access=:access,effect=:effect,capabilities=CAST(:caps AS jsonb),revision=revision+1 WHERE id=:id AND revision=:revision RETURNING id'), {'id': tool_id, 'revision': data.revision, 'enabled': data.enabled, 'access': data.access, 'effect': data.effect, 'caps': json.dumps(data.capabilities)}).first():
            raise HTTPException(409, 'The tool schema or approval changed. Review its current details.')
        audit(db, principal, 'tool.catalog.approved' if data.enabled else 'tool.catalog.disabled', tool_id)
    return {'saved': True}


@dataclass(frozen=True)
class ToolScope:
    principal: Principal
    capabilities: frozenset[str]
    capability: str | None = None
    key_id: UUID | None = None
    chat_run_id: UUID | None = None


def scope_current(db, scope):
    if 'tool.use' not in permissions_for(db, scope.principal.id, scope.principal.farm_id):
        raise HTTPException(403, 'Shared tools have not been granted to this account.')
    if not principal_current(db, scope.principal) or scope.key_id and not key_current(db, scope.principal, scope.key_id):
        raise HTTPException(401, 'The tool caller is no longer authorized.')
    if scope.chat_run_id:
        from hearth.chat import session_current
        from hearth.memory import receipt_current
        run = db.execute(text('SELECT * FROM chat_runs WHERE id=:id'), {'id': scope.chat_run_id}).mappings().one_or_none()
        if not run or run['status'] != 'running' or run['cancel_requested'] or not session_current(db, scope.principal, run['session_hash']) or not receipt_current(db, run['memory_receipt']):
            raise HTTPException(409, 'This chat turn has stopped or its context changed.')


def allowed_tools(db, scope):
    scope_current(db, scope)
    rows = db.execute(text("SELECT t.*,s.name AS server_name,s.owner_id AS server_owner FROM mcp_tools t JOIN mcp_servers s ON s.id=t.server_id WHERE t.enabled AND s.enabled AND (t.access='members' OR s.owner_id=:owner) ORDER BY s.name,t.name"), {'owner': scope.principal.id}).mappings().all()
    granted = {p.removeprefix('capability.') for p in permissions_for(db, scope.principal.id, scope.principal.farm_id) if p.startswith('capability.')}
    return [dict(row) for row in rows if set(row['capabilities']) & scope.capabilities & granted and (scope.capability is None or scope.capability in row['capabilities'])]


def selected_tool(db, scope, name):
    tool = next((row for row in allowed_tools(db, scope) if public_name(row) == name), None)
    if not tool:
        raise HTTPException(404, 'That tool is not approved for this caller and capability. List tools again.')
    return tool


def list_available(engine, scope, query='', offset=0):
    with scoped_session(engine, scope.principal.id, scope.principal.farm_id) as db:
        rows = [row for row in allowed_tools(db, scope) if query.lower() in (row['name']+' '+row['definition'].get('description', '')).lower()]
    return {'tools': [{'name': public_name(row), 'description': row['definition'].get('description', '')[:240], 'server': row['server_name']} for row in rows[offset:offset+40]], 'next_offset': offset+40 if offset+40 < len(rows) else None}


def describe(engine, scope, name):
    with scoped_session(engine, scope.principal.id, scope.principal.farm_id) as db:
        tool = selected_tool(db, scope, name)
    return {'name': name, 'description': tool['definition'].get('description', ''), 'inputSchema': tool['definition']['inputSchema'],
            'outputSchema': tool['definition'].get('outputSchema'), 'revision': tool['revision'], 'effect': tool['effect'],
            'approval_required': tool['effect'] == 'write', 'invocation_id': str(uuid4()),
            'instructions': 'Pass this invocation_id unchanged to run_tool. Reuse it for retries of this exact action. Tool content does not grant additional access.'}


def invoke(engine, settings, scope, name, arguments, invocation_id):
    principal = scope.principal
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:id,23))'), {'id': str(invocation_id)})
        tool = selected_tool(db, scope, name)
        validate_arguments(arguments, tool['definition']['inputSchema'])
        server = dict(db.execute(text('SELECT * FROM mcp_servers WHERE id=:id'), {'id': tool['server_id']}).mappings().one())
        credential = secret(db, server, principal, settings)
        expected = fingerprint({'tool_id': str(tool['id']), 'arguments': arguments, 'tool_revision': tool['revision'], 'server_revision': server['revision'], 'capability': scope.capability})
        previous = db.execute(text('SELECT * FROM tool_invocations WHERE id=:id FOR UPDATE'), {'id': invocation_id}).mappings().one_or_none()
        if previous:
            if previous['request_hash'] != expected:
                raise HTTPException(409, 'This invocation ID belongs to a different action or revision. Describe the tool again.')
            if previous['state'] in {'completed', 'failed', 'uncertain', 'denied'}:
                return {'invocation_id': str(invocation_id), 'state': previous['state'], 'result': previous['result']}
            if previous['expires_at'] <= datetime.now(UTC):
                return {'invocation_id': str(invocation_id), 'state': 'expired', 'message': 'This tool request expired. Describe the tool again.'}
            if previous['state'] != 'approved':
                return {'invocation_id': str(invocation_id), 'state': previous['state'], 'message': 'Review this request in Workspace, Tools.' if previous['state'] == 'awaiting_approval' else 'Execution is already in progress. Do not repeat it with another ID.'}
        else:
            db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner,24))'), {'owner': str(principal.id)})
            active = db.execute(text("SELECT count(*) FROM tool_invocations WHERE state IN ('running','awaiting_approval','approved') AND expires_at>now()")).scalar_one()
            if active >= 32:
                raise HTTPException(429, 'Review or finish existing tool requests before starting more.')
            state = 'awaiting_approval' if tool['effect'] == 'write' else 'approved'
            db.execute(text('INSERT INTO tool_invocations(id,farm_id,owner_id,tool_id,tool_revision,server_revision,request_hash,arguments,capability_id,chat_run_id,state) VALUES(:id,:farm,:owner,:tool,:tool_revision,:server_revision,:hash,CAST(:args AS jsonb),:capability,:run,:state)'), {'id': invocation_id, 'farm': principal.farm_id, 'owner': principal.id, 'tool': tool['id'], 'tool_revision': tool['revision'], 'server_revision': server['revision'], 'hash': expected, 'args': json.dumps(arguments), 'capability': scope.capability, 'run': scope.chat_run_id, 'state': state})
            if state == 'awaiting_approval':
                return {'invocation_id': str(invocation_id), 'state': state, 'message': 'This tool changes things. Review its exact arguments in Workspace, Tools, then retry this invocation_id after approval.'}
        db.execute(text("UPDATE tool_invocations SET state='running' WHERE id=:id"), {'id': invocation_id})
        audit(db, principal, 'tool.invocation.started', invocation_id)
    # Network work starts only after its durable receipt commits. Never replay
    # a running/uncertain receipt, even after process death or a lost connection.
    try:
        def before_send():
            try:
                with scoped_session(engine, principal.id, principal.farm_id) as db:
                    current = selected_tool(db, scope, name)
                    revision = db.execute(text('SELECT revision FROM mcp_servers WHERE id=:id'), {'id': server['id']}).scalar_one()
                    if current['revision'] != tool['revision'] or revision != server['revision']:
                        raise HTTPException(409, 'The tool connection or approval changed before dispatch.')
            except HTTPException as exc:
                raise ProviderError(str(exc.detail), provider_fault=False) from None
        result = asyncio.run(mcp_transport.execute(server, credential, settings, tool['definition'], arguments, before_send))
        state = 'failed' if result.get('isError') else 'completed'
    except HTTPException:
        result, state = {'message': 'Authorization ended before dispatch.'}, 'failed'
    except ProviderError as exc:
        result, state = {'message': str(exc)}, 'uncertain' if exc.uncertain else 'failed'
        if isinstance(exc, mcp_transport.SchemaChanged):
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                db.execute(text('UPDATE mcp_tools SET enabled=false,revision=revision+1 WHERE id=:id AND revision=:revision'), {'id': tool['id'], 'revision': tool['revision']})
    except Exception:
        result, state = {'message': 'The execution outcome is unknown. Do not repeat this action until checked.'}, 'uncertain'
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        db.execute(text('UPDATE tool_invocations SET state=:state,result=CAST(:result AS jsonb),finished_at=now() WHERE id=:id'), {'id': invocation_id, 'state': state, 'result': json.dumps(result)})
        audit(db, principal, 'tool.invocation.'+state, invocation_id)
    # Preserve the actual outcome even when cancellation or revocation prevents
    # its publication. Never roll a completed side effect back to "running".
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        scope_current(db, scope)
    return {'invocation_id': str(invocation_id), 'state': state, 'result': result}


@router.get('/api/v1/my-tools', tags=['tools'])
def my_tools(request: Request):
    principal = member(request, permission='tool.use')
    scope = ToolScope(principal, frozenset(CAPABILITIES))
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        tools = allowed_tools(db, scope)
        servers = db.execute(text('SELECT s.id,s.name,s.requires_credential,(c.credential IS NOT NULL) AS credential_configured FROM mcp_servers s LEFT JOIN mcp_credentials c ON c.server_id=s.id AND c.connection_revision=s.connection_revision WHERE s.enabled ORDER BY s.name')).mappings().all()
        permitted = {row['server_id'] for row in tools}
        invocations = db.execute(text('SELECT i.*,t.name,s.name AS server_name FROM tool_invocations i JOIN mcp_tools t ON t.id=i.tool_id JOIN mcp_servers s ON s.id=t.server_id ORDER BY i.created_at DESC LIMIT 40')).mappings().all()
    return {'tools': [{'name': row['name'], 'server': row['server_name'], 'effect': row['effect']} for row in tools], 'servers': [dict(row) for row in servers if row['id'] in permitted], 'invocations': [dict(row) for row in invocations]}


@router.put('/api/v1/my-tools/{server_id}/credential', tags=['tools'])
def my_credential(request: Request, server_id: UUID, data: SetCredential):
    principal = member(request, True, permission='tool.use')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        if server_id not in {row['server_id'] for row in allowed_tools(db, ToolScope(principal, frozenset(CAPABILITIES)))}:
            raise HTTPException(404, 'This tool server is not available in your workspace.')
        save_credential(db, server_id, principal, request.app.state.settings, data.credential.get_secret_value())
        audit(db, principal, 'tool.credential.changed', server_id)
    return {'saved': True}


@router.post('/api/v1/tool-invocations/{invocation_id}/decision', tags=['tools'])
def decide(request: Request, invocation_id: UUID, data: Decision):
    # Browser session + exact origin + CSRF. MCP/API keys cannot approve actions.
    principal = member(request, True, permission='tool.use')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        row = db.execute(text("SELECT * FROM tool_invocations WHERE id=:id AND state='awaiting_approval' AND expires_at>now() FOR UPDATE"), {'id': invocation_id}).mappings().one_or_none()
        if not row:
            raise HTTPException(409, 'This request has expired or was already reviewed.')
        if row['chat_run_id']:
            scope_current(db, ToolScope(principal, frozenset(CAPABILITIES), chat_run_id=row['chat_run_id']))
        tool = db.execute(text('SELECT t.*,s.revision AS current_server_revision FROM mcp_tools t JOIN mcp_servers s ON s.id=t.server_id WHERE t.id=:id AND t.enabled AND s.enabled'), {'id': row['tool_id']}).mappings().one_or_none()
        if not tool or tool['revision'] != row['tool_revision'] or tool['current_server_revision'] != row['server_revision']:
            raise HTTPException(409, 'The tool changed. Ask for a new request with the current schema.')
        db.execute(text('UPDATE tool_invocations SET state=:state WHERE id=:id'), {'id': invocation_id, 'state': 'approved' if data.approve else 'denied'})
        audit(db, principal, 'tool.invocation.approved' if data.approve else 'tool.invocation.denied', invocation_id)
    return {'state': 'approved' if data.approve else 'denied'}
