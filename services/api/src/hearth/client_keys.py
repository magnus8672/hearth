"""Revocable personal access keys. Bearer credentials never confer administration."""
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import text

from hearth.database import scoped_session
from hearth.identity import authenticate, check_origin, digest
from hearth.policy import Principal, permissions_for
from hearth.routing import TEXT

router = APIRouter()


class NewKey(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    capabilities: list[str] = Field(min_length=1, max_length=7)
    allow_tools: StrictBool = False
    expires_days: int = Field(default=90, strict=True, ge=1, le=365)


def browser_owner(request, mutation=False):
    principal = authenticate(request, mutation=mutation)
    if request.app.state.settings.audience != 'user':
        raise HTTPException(403, 'Open your workspace to manage your client connections.')
    principal.require('api_key.own')
    return principal


def key_current(db, principal, key_id):
    return 'api_key.own' in permissions_for(db, principal.id, principal.farm_id) and db.execute(text("SELECT EXISTS(SELECT 1 FROM client_keys k JOIN users u ON u.id=k.owner_id AND u.farm_id=k.farm_id WHERE k.id=:id AND k.revoked_at IS NULL AND k.expires_at>now() AND u.state='active' AND u.authorization_version=k.authorization_version AND u.authorization_version=:version)"), {'id': key_id, 'version': principal.authorization_version}).scalar_one()


@dataclass(frozen=True)
class ClientIdentity:
    principal: Principal
    key_id: UUID
    capabilities: frozenset[str]
    allow_tools: bool


def bearer(request):
    settings = request.app.state.settings
    if settings.audience != 'user' or not settings.farm_id:
        raise HTTPException(404, 'Client access is served by the workspace origin.')
    check_origin(request)
    if request.headers.get('origin') not in (None, settings.user_origin):
        raise HTTPException(403, 'This client origin is not authorized.')
    raw = request.headers.get('authorization', '')
    match = re.fullmatch(r'Bearer (hrt_([0-9a-f]{32})_[A-Za-z0-9_-]{43})', raw)
    if not match:
        raise HTTPException(401, 'Supply a hearth client API key as a Bearer token.')
    # The ID is only a lookup partition. The full random key hash must match
    # before the row can establish identity or any permission.
    owner = UUID(hex=match[2])
    with scoped_session(request.app.state.engine, owner, settings.farm_id) as db:
        row = db.execute(text('SELECT k.*,u.authorization_version AS current_version FROM client_keys k JOIN users u ON u.id=k.owner_id AND u.farm_id=k.farm_id WHERE token_hash=:hash'), {'hash': digest(match[1])}).mappings().one_or_none()
        if not row:
            raise HTTPException(401, 'This client key is invalid, expired or revoked.')
        principal = Principal(owner, settings.farm_id, permissions_for(db, owner, settings.farm_id), row['current_version'])
        if not key_current(db, principal, row['id']):
            raise HTTPException(401, 'This client key is invalid, expired or revoked.')
        db.execute(text('UPDATE client_keys SET last_used_at=now() WHERE id=:id'), {'id': row['id']})
        return ClientIdentity(principal, row['id'], frozenset(cap for cap in row['capabilities'] if 'capability.'+cap in principal.permissions), row['allow_tools'] and 'tool.use' in principal.permissions)


def principal_current(db, principal):
    return db.execute(text("SELECT EXISTS(SELECT 1 FROM users WHERE id=:id AND farm_id=:farm AND state='active' AND authorization_version=:version)"), {'id': principal.id, 'farm': principal.farm_id, 'version': principal.authorization_version}).scalar_one()


def issue_key(engine, principal, data):
    principal.require('api_key.own')
    if len(set(data.capabilities)) != len(data.capabilities) or not set(data.capabilities) <= set(TEXT):
        raise HTTPException(400, 'Choose supported text capabilities for this key.')
    for capability in data.capabilities:
        principal.require('capability.'+capability)
    if data.allow_tools:
        principal.require('tool.use')
    key_id = uuid4()
    secret = 'hrt_' + principal.id.hex + '_' + secrets.token_urlsafe(32)
    import json
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner,20))'), {'owner': str(principal.id)})
        if db.execute(text('SELECT count(*) FROM client_keys WHERE revoked_at IS NULL AND expires_at>now()')).scalar_one() >= 20:
            raise HTTPException(409, 'Revoke an unused key before adding another. Up to 20 active keys are supported.')
        db.execute(text('INSERT INTO client_keys(id,farm_id,owner_id,name,token_hash,capabilities,allow_tools,authorization_version,expires_at) VALUES(:id,:farm,:owner,:name,:hash,CAST(:capabilities AS jsonb),:tools,:version,:expires)'),
            {'id': key_id, 'farm': principal.farm_id, 'owner': principal.id, 'name': data.name, 'hash': digest(secret), 'capabilities': json.dumps(data.capabilities), 'tools': data.allow_tools, 'version': principal.authorization_version, 'expires': datetime.now(UTC)+timedelta(days=data.expires_days)})
        audit(db, principal, 'client.key.created', key_id)
    return {'id': key_id, 'key': secret}


def audit(db, principal, action, resource):
    db.execute(text('INSERT INTO audit_events(id,farm_id,actor_id,action,safe_metadata) VALUES(gen_random_uuid(),:farm,:actor,:action,jsonb_build_object(\'resource_id\',CAST(:id AS text)))'), {'farm': principal.farm_id, 'actor': principal.id, 'action': action, 'id': str(resource)})


@router.get('/api/v1/client-keys', tags=['clients'])
def keys(request: Request):
    principal = browser_owner(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        rows = db.execute(text('SELECT id,name,capabilities,allow_tools,created_at,expires_at,revoked_at,last_used_at FROM client_keys ORDER BY created_at DESC LIMIT 100')).mappings().all()
    return {'items': [dict(row) for row in rows], 'capabilities': [cap for cap in TEXT if 'capability.'+cap in principal.permissions], 'base_url': request.app.state.settings.user_origin+'/v1', 'mcp_url': request.app.state.settings.user_origin+'/mcp'}


@router.post('/api/v1/client-keys', tags=['clients'], status_code=201)
def create(request: Request, data: NewKey):
    return issue_key(request.app.state.engine, browser_owner(request, True), data)


@router.delete('/api/v1/client-keys/{key_id}', tags=['clients'])
def revoke(request: Request, key_id: UUID):
    principal = browser_owner(request, True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        if not db.execute(text('UPDATE client_keys SET revoked_at=COALESCE(revoked_at,now()) WHERE id=:id RETURNING id'), {'id': key_id}).first():
            raise HTTPException(404, 'This key is not available in your workspace.')
        audit(db, principal, 'client.key.revoked', key_id)
    return {'revoked': True}
