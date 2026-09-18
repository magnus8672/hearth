"""Bounded outbound control for explicitly adopted Linux services.

This is operator bootstrap, not the automatic member enrollment protocol. A
worker credential authenticates only this poll endpoint, never a browser/user.
Signed local recipes remain the authority for executable service definitions.
"""
import hmac
import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import text

from hearth.database import scoped_session
from hearth.identity import authenticate

router = APIRouter()
SYSTEM = UUID(int=0)


class WorkerReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    boot_id: UUID
    sequence: int = Field(strict=True, ge=1, le=9007199254740991)
    recipe_digest: str = Field(pattern='^[a-f0-9]{64}$')
    observed_revision: int = Field(strict=True, ge=0, le=9007199254740991)
    ready_service: str | None = Field(default=None, pattern='^[a-z][a-z0-9_-]{0,39}$')
    state: Literal['stopped', 'starting', 'ready', 'failed']
    reason: Literal['', 'service_starting', 'service_not_ready', 'recipe_mismatch', 'stop_failed', 'start_failed', 'health_failed', 'head_unavailable'] = ''


class WorkerChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(strict=True, ge=1, le=9007199254740990)
    paused: StrictBool
    policy: Literal['resident', 'shared']
    desired_service: str | None = Field(default=None, pattern='^[a-z][a-z0-9_-]{0,39}$')


def administrator(request, mutation=False):
    principal = authenticate(request, mutation=mutation)
    if request.app.state.settings.audience != 'admin':
        raise HTTPException(403, 'Open Administration to manage workers.')
    principal.require('node.operate' if mutation else 'farm.inspect')
    return principal


def for_pool(db, pool_id):
    return db.execute(text('SELECT * FROM managed_workers WHERE pool_id=:id'), {'id': pool_id}).mappings().one_or_none()


def service_for(worker, connection_id):
    return next((key for key, value in worker['services'].items() if value['connection_id'] == str(connection_id)), None)


def fresh(worker):
    return bool(worker['seen_at'] and (datetime.now(UTC) - worker['seen_at']).total_seconds() < 15 and not worker['revoked'])


def ready(worker, connection_id):
    service = service_for(worker, connection_id)
    return bool(service and fresh(worker) and worker['state'] == 'ready' and worker['ready_service'] == service
                and worker['desired_service'] == service and worker['observed_revision'] == worker['revision'])


def require_available(db, target):
    worker = for_pool(db, target['resource_pool_id'])
    if worker and (worker['paused'] or not ready(worker, target['connection_id'])):
        raise HTTPException(409, 'This managed worker is paused, offline or preparing its service. Check Workers in Administration.')


def require_binding(db, connection_id, pool_id):
    adopted = db.execute(text("SELECT w.pool_id FROM managed_workers w,jsonb_each(w.services) s WHERE s.value->>'connection_id'=:connection"), {'connection': str(connection_id)}).scalars().all()
    if any(approved_pool != pool_id for approved_pool in adopted):
        raise HTTPException(409, 'This connection belongs to a managed GPU. Keep its resource group, or update its approved worker setup first.')


@router.post('/api/v1/worker-control/{worker_id}/poll', tags=['workers'])
def poll(request: Request, worker_id: UUID, data: WorkerReport):
    settings = request.app.state.settings
    # No cookies, query credentials, browser origins or forwarded identity.
    token = request.headers.get('authorization', '')
    if settings.audience != 'admin' or not settings.farm_id or request.headers.get('origin') or not token.startswith('Bearer ') or len(token) != 71:
        raise HTTPException(401, 'Worker authentication required.')
    with scoped_session(request.app.state.engine, SYSTEM, settings.farm_id) as db:
        worker = db.execute(text('SELECT * FROM managed_workers WHERE id=:id FOR UPDATE'), {'id': worker_id}).mappings().one_or_none()
        if not worker or worker['revoked'] or not hmac.compare_digest(worker['token_hash'], sha256(token[7:].encode()).hexdigest()):
            raise HTTPException(401, 'Worker authentication required.')
        if not hmac.compare_digest(worker['recipe_digest'], data.recipe_digest):
            raise HTTPException(409, 'The approved worker recipe changed.')
        if worker['boot_id'] == data.boot_id:
            if data.sequence <= worker['sequence']:
                raise HTTPException(409, 'Stale worker report.')
        elif worker['seen_at'] and (datetime.now(UTC) - worker['seen_at']).total_seconds() < 30:
            raise HTTPException(409, 'Another worker session is still present. Wait for its lease to expire.')
        if data.ready_service and data.ready_service not in worker['services']:
            raise HTTPException(409, 'Unapproved service report.')
        valid = data.observed_revision == worker['revision'] and data.ready_service == worker['desired_service']
        db.execute(text('UPDATE managed_workers SET boot_id=:boot,sequence=:seq,seen_at=now(),observed_revision=:revision,ready_service=:service,state=:state,reason=:reason WHERE id=:id'),
                   {'id': worker_id, 'boot': data.boot_id, 'seq': data.sequence, 'revision': data.observed_revision,
                    'service': data.ready_service if valid and data.state == 'ready' else None, 'state': data.state, 'reason': data.reason})
        return {'revision': worker['revision'], 'desired_service': worker['desired_service'], 'lease_seconds': 15}


@router.get('/api/v1/workers', tags=['workers'])
def listing(request: Request):
    principal = administrator(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        workers = db.execute(text("SELECT w.*,p.name AS pool_name,p.execution_state,p.active_run_id,(SELECT count(*) FROM image_queue q WHERE q.pool_id=w.pool_id AND q.state='queued') AS queued FROM managed_workers w JOIN provider_pools p ON p.id=w.pool_id ORDER BY w.name")).mappings().all()
        return {'items': [{key: value for key, value in dict(row).items() if key not in {'token_hash', 'recipe_digest', 'boot_id', 'sequence'}} | {'online': fresh(row)} for row in workers]}


@router.put('/api/v1/workers/{worker_id}', tags=['workers'])
def change(request: Request, worker_id: UUID, data: WorkerChange):
    principal = administrator(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        # Pool first everywhere that can change desired state or admit work.
        pool = db.execute(text('SELECT p.* FROM provider_pools p JOIN managed_workers w ON w.pool_id=p.id WHERE w.id=:id FOR UPDATE OF p'), {'id': worker_id}).mappings().one_or_none()
        if not pool:
            raise HTTPException(404, 'Worker not found.')
        worker = db.execute(text('SELECT * FROM managed_workers WHERE id=:id FOR UPDATE'), {'id': worker_id}).mappings().one()
        if worker['revision'] != data.revision or worker['revoked']:
            raise HTTPException(409, 'Worker settings changed. Refresh before trying again.')
        lifecycle = data.desired_service != worker['desired_service'] or data.policy != worker['policy'] or worker['state'] == 'failed'
        if lifecycle:
            principal.require('node.assign')
            if pool['active_run_id']:
                raise HTTPException(409, 'Drain the active job and confirm uncertain work has stopped before changing services.')
        if data.desired_service is not None and data.desired_service not in worker['services']:
            raise HTTPException(400, 'Choose a locally approved service.')
        if data.desired_service is None and not data.paused:
            raise HTTPException(400, 'Keep the worker paused when unloading its service.')
        # Pausing admission does not invalidate a running service observation.
        db.execute(text('UPDATE managed_workers SET paused=:paused,policy=:policy,desired_service=:desired,revision=revision+1 WHERE id=:id'),
                   {'id': worker_id, 'paused': data.paused, 'policy': data.policy, 'desired': data.desired_service})
        db.execute(text('INSERT INTO audit_events(id,farm_id,actor_id,action,safe_metadata) VALUES(gen_random_uuid(),:farm,:actor,\'worker.configure\',CAST(:metadata AS jsonb))'),
                   {'farm': principal.farm_id, 'actor': principal.id, 'metadata': json.dumps({'worker_id': str(worker_id), **data.model_dump(mode='json')})})
    return {'saved': True}
