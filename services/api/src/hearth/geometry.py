"""Owner-scoped image-to-3D jobs on the shared capability queue."""
import base64
import hashlib
import json
import time
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from hearth import geometry_transport, image_queue
from hearth.chat import identity_current, member, session_current
from hearth.contracts import GeometryGeneration
from hearth.database import scoped_session
from hearth.geometry_validation import validate_glb
from hearth.inference import ProviderError
from hearth.provider_health import record_failure
from hearth.providers import credential_for, release_pool, target_record, transport_settings
from hearth.vision import normalize_image

router = APIRouter()


class CreateGeometry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request: GeometryGeneration
    target_id: UUID
    image: str = Field(max_length=12_000_000)


@router.get('/api/v1/geometry-targets', tags=['geometry'])
def targets(request: Request):
    principal = member(request, permission='capability.geometry.generate')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        rows = db.execute(text("SELECT t.id,t.model_id,t.state,t.profile,c.name FROM capability_bindings b JOIN inference_targets t ON t.id=b.target_id JOIN provider_connections c ON c.id=t.connection_id WHERE b.capability_id='geometry.generate' AND t.protocol='hearth.geometry.v1' ORDER BY b.priority DESC,t.id")).mappings().all()
    return {'items': [dict(row) for row in rows]}


@router.get('/api/v1/geometry', tags=['geometry'])
def listing(request: Request):
    principal = member(request, permission='capability.geometry.generate')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        rows = db.execute(text("SELECT j.id,t.resource_pool_id FROM geometry_jobs j JOIN inference_targets t ON t.id=j.target_id JOIN provider_pools p ON p.id=t.resource_pool_id WHERE j.status IN ('queued','running') AND NOT EXISTS(SELECT 1 FROM capability_queue q WHERE q.id=j.id AND q.state='queued') AND (p.active_run_id IS DISTINCT FROM j.id OR p.lease_until<now()) FOR UPDATE OF j")).mappings().all()
        for row in rows:
            db.execute(text("UPDATE geometry_jobs SET status='interrupted',reason='The worker connection was interrupted. Check Workers before retrying.',finished_at=now() WHERE id=:id"), {'id': row['id']})
            release_pool(db, row['resource_pool_id'], row['id'], uncertain=True)
        rows = db.execute(text('SELECT id,target_id,request,status,progress,cancel_requested,reason,metadata,created_at FROM geometry_jobs WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 50')).mappings().all()
    return {'items': [dict(row) for row in rows]}


@router.post('/api/v1/geometry', tags=['geometry'], status_code=202)
def generate(request: Request, data: CreateGeometry):
    principal = member(request, mutation=True, permission='capability.geometry.generate')
    try:
        raw = base64.b64decode(data.image, validate=True)
    except ValueError:
        raise HTTPException(422, 'Choose a valid image.') from None
    if hashlib.sha256(raw).hexdigest() != data.request.image_sha256:
        raise HTTPException(422, 'The image digest did not match.')
    raw, _, _ = normalize_image(raw)
    payload = data.request.model_copy(update={'image_sha256': hashlib.sha256(raw).hexdigest()}).model_dump(mode='json')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        workspace = db.execute(text('SELECT id FROM workspaces FOR UPDATE')).scalar_one()
        previous = db.execute(text('SELECT target_id,request,status,deleted_at FROM geometry_jobs WHERE id=:id'), {'id': data.request.id}).mappings().one_or_none()
        if previous:
            if previous['deleted_at']:
                raise HTTPException(410, 'This model was deleted. Start a new request.')
            if previous['target_id'] != data.target_id or previous['request'] != payload:
                raise HTTPException(409, 'This request identifier was already used.')
            return {'id': data.request.id, 'status': previous['status']}
        target = target_record(db, data.target_id, lock=True)
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner,7))'), {'owner': str(principal.id)})
        if db.execute(text('SELECT count(*) FROM geometry_jobs WHERE deleted_at IS NULL')).scalar_one() >= 50:
            raise HTTPException(409, 'Delete a saved model before adding more. This build supports 50 per workspace.')
        if target['protocol'] != 'hearth.geometry.v1' or target['model_id'] != data.request.model or target['state'] != 'ready' or data.request.resolution not in target['profile'].get('resolutions', []):
            raise HTTPException(409, 'Choose a verified geometry model and supported resolution.')
        if not db.execute(text("SELECT 1 FROM capability_bindings WHERE capability_id='geometry.generate' AND target_id=:id"), {'id': target['id']}).first():
            raise HTTPException(409, 'Assign this model to the geometry capability first.')
        db.execute(text("INSERT INTO geometry_jobs(id,farm_id,owner_id,workspace_id,target_id,request,source_image,session_hash,authorization_version) VALUES(:id,:farm,:owner,:workspace,:target,CAST(:request AS jsonb),:source,:session,:version)"),
                   {'id': data.request.id, 'farm': principal.farm_id, 'owner': principal.id, 'workspace': workspace, 'target': target['id'], 'request': json.dumps(payload), 'source': raw, 'session': request.state.identity['token_hash'], 'version': principal.authorization_version})
        image_queue.enqueue(db, principal, target, data.request.id, 'geometry')
    return {'id': data.request.id, 'status': 'queued'}


@router.post('/api/v1/geometry/{job_id}/cancel', tags=['geometry'])
def cancel(request: Request, job_id: UUID):
    principal = member(request, mutation=True, permission='capability.geometry.generate')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        queued = db.execute(text('SELECT state FROM capability_queue WHERE id=:id AND owner_id=:owner FOR UPDATE'), {'id': job_id, 'owner': principal.id}).scalar_one_or_none()
        state = db.execute(text('SELECT status FROM geometry_jobs WHERE id=:id FOR UPDATE'), {'id': job_id}).scalar_one_or_none()
        if state is None:
            raise HTTPException(404, 'This model is not in your workspace.')
        if state in {'queued', 'running'}:
            db.execute(text('UPDATE geometry_jobs SET cancel_requested=true WHERE id=:id'), {'id': job_id})
            if queued == 'queued':
                image_queue.finish_waiting(db, job_id, 'cancelled', 'Removed from the queue.')
    return {'cancel_requested': state in {'queued', 'running'}}


@router.get('/api/v1/geometry/{job_id}/model', tags=['geometry'])
def download(request: Request, job_id: UUID):
    principal = member(request, permission='capability.geometry.generate')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        artifact = db.execute(text("SELECT artifact FROM geometry_jobs WHERE id=:id AND status='completed' AND deleted_at IS NULL"), {'id': job_id}).scalar_one_or_none()
        if artifact is None:
            raise HTTPException(404, 'This model is not available in your workspace.')
    return Response(bytes(artifact), media_type='model/gltf-binary', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Disposition': f'attachment; filename="hearth-{job_id}.glb"'})


@router.delete('/api/v1/geometry/{job_id}', tags=['geometry'])
def delete(request: Request, job_id: UUID):
    principal = member(request, mutation=True, permission='capability.geometry.generate')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        row = db.execute(text('SELECT status FROM geometry_jobs WHERE id=:id FOR UPDATE'), {'id': job_id}).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, 'This model is not in your workspace.')
        if row in {'queued', 'running'}:
            raise HTTPException(409, 'Stop generation and wait for it to end before deleting this model.')
        db.execute(text('UPDATE geometry_jobs SET artifact=NULL,source_image=NULL,metadata=NULL,deleted_at=now() WHERE id=:id'), {'id': job_id})
    return {'deleted': True}


def execute(engine, settings, principal, target, data):
    stopped, problem, result, artifact, last_identity = False, None, None, None, 0.0
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        run = dict(db.execute(text('SELECT * FROM geometry_jobs WHERE id=:id'), {'id': data.id}).mappings().one())
    try:
        if not identity_current(engine, settings, principal, run['session_hash']):
            raise ProviderError('The sending session ended before generation.', provider_fault=False)
        def observe(receipt):
            nonlocal stopped, last_identity
            if time.monotonic() - last_identity >= 5 or receipt.execution_released:
                stopped = stopped or not identity_current(engine, settings, principal, run['session_hash'])
                last_identity = time.monotonic()
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                row = db.execute(text('SELECT status,cancel_requested FROM geometry_jobs WHERE id=:id FOR UPDATE'), {'id': data.id}).mappings().one()
                current = target_record(db, target['id'])
                mismatch = receipt.manifest_sha256 != target['profile'].get('manifest_sha256')
                stopped = stopped or mismatch or row['cancel_requested'] or row['status'] != 'running' or not session_current(db, principal, run['session_hash']) or current['active_run_id'] != data.id or current['revision'] != target['revision'] or current['state'] != 'ready'
                if mismatch:
                    record_failure(db, target, 'The geometry model inventory changed. Verify again.')
                db.execute(text('UPDATE geometry_jobs SET progress=:progress WHERE id=:id'), {'id': data.id, 'progress': receipt.progress})
                db.execute(text("UPDATE provider_pools SET lease_until=now()+interval '240 seconds' WHERE id=:pool AND active_run_id=:run"), {'pool': target['resource_pool_id'], 'run': data.id})
            return stopped
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            current = target_record(db, target['id'])
            job = db.execute(text('SELECT status,cancel_requested FROM geometry_jobs WHERE id=:id'), {'id': data.id}).mappings().one()
            if job['cancel_requested'] or job['status'] != 'running' or not session_current(db, principal, run['session_hash']) or current['active_run_id'] != data.id or current['revision'] != target['revision'] or current['state'] != 'ready':
                raise ProviderError('The session or provider changed before geometry generation.', provider_fault=False)
        result, artifact = geometry_transport.render(target['base_url'], credential_for(target, settings), transport_settings(target, settings), data, bytes(run['source_image']), observe)
    except ProviderError as exc:
        problem = exc
    except Exception:
        problem = ProviderError('Geometry generation was interrupted. Check the worker before retrying.', uncertain=True)
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        job = db.execute(text('SELECT status,cancel_requested FROM geometry_jobs WHERE id=:id FOR UPDATE'), {'id': data.id}).mappings().one()
        current = target_record(db, target['id'])
        if job['status'] != 'running' or current['active_run_id'] != data.id:
            return
        stopped = stopped or job['cancel_requested'] or not session_current(db, principal, run['session_hash']) or current['revision'] != target['revision'] or current['state'] != 'ready'
        state = ('interrupted' if problem.uncertain else 'failed') if problem else ('cancelled' if stopped else result.state)
        if state == 'completed' and artifact is None:
            state = 'failed'
        reason = str(problem) if problem else ('Geometry generation stopped.' if stopped else result.reason)
        record_failure(db, target, problem or (reason or 'Geometry generation failed.' if state == 'failed' else None))
        metadata = (result.model_dump(mode='json') | validate_glb(artifact) | {'model_revision': target['profile']['model_revision']}) if artifact and state == 'completed' else None
        db.execute(text('UPDATE geometry_jobs SET status=:status,reason=:reason,metadata=CAST(:metadata AS jsonb),artifact=:artifact,source_image=NULL,finished_at=now() WHERE id=:id'), {'id': data.id, 'status': state, 'reason': reason, 'metadata': json.dumps(metadata), 'artifact': artifact if state == 'completed' else None})
        release_pool(db, target['resource_pool_id'], data.id, uncertain=bool(problem and problem.uncertain))
