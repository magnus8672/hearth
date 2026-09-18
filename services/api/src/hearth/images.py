"""Private image jobs with shared resource admission and verified PNG artifacts."""
import json
import time
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from hearth import conversation_media, image_transport
from hearth.chat import identity_current, member, session_current
from hearth.contracts import ImageGeneration
from hearth.database import scoped_session
from hearth.inference import ProviderError
from hearth.provider_health import record_failure
from hearth.providers import claim_pool, credential_for, release_pool, target_record, transport_settings

router = APIRouter()


class CreateImage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request: ImageGeneration
    target_id: UUID


def reconcile(db):
    rows = db.execute(text("SELECT j.id,j.batch_run_id,t.resource_pool_id FROM image_jobs j JOIN inference_targets t ON t.id=j.target_id JOIN provider_pools p ON p.id=t.resource_pool_id WHERE j.status IN ('queued','running') AND (p.active_run_id IS DISTINCT FROM COALESCE(j.batch_run_id,j.id) OR p.lease_until<now()) FOR UPDATE OF j")).mappings().all()
    reconciled = set()
    for row in rows:
        execution = row['batch_run_id'] or row['id']
        if execution in reconciled:
            continue
        reconciled.add(execution)
        db.execute(text("UPDATE image_jobs SET status='interrupted',reason='Execution was interrupted. Check the image provider before retrying.',finished_at=now() WHERE id=:id"), {'id': row['id']})
        conversation_media.finish(db, row['id'], 'interrupted', 'Image generation was interrupted. Check the provider before retrying.', None, None)
        if row['batch_run_id']:
            from hearth.image_batches import finish
            plan = db.execute(text('SELECT * FROM image_plans WHERE id=:id'), {'id': row['batch_run_id']}).mappings().one()
            finish(db, plan, 'interrupted', 'The image batch was interrupted. Check the provider before trying again.')
        release_pool(db, row['resource_pool_id'], row['batch_run_id'] or row['id'], uncertain=True)


@router.get('/api/v1/image-targets', tags=['images'])
def targets(request: Request):
    principal = member(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        rows = db.execute(text("SELECT t.id,t.model_id,t.state,t.verified_until,c.name FROM capability_bindings b JOIN inference_targets t ON t.id=b.target_id JOIN provider_connections c ON c.id=t.connection_id WHERE b.capability_id='image.generate' AND t.protocol='hearth.image.v1' ORDER BY b.priority DESC,t.id")).mappings().all()
    return {'items': [dict(row) | {'ready': row['state'] == 'ready', 'verified_until': None} for row in rows]}


@router.get('/api/v1/images', tags=['images'])
def images(request: Request):
    principal = member(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        reconcile(db)
        rows = db.execute(text('SELECT id,target_id,request,status,progress,cancel_requested,reason,metadata,created_at FROM image_jobs WHERE channel_id IS NULL AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 100')).mappings().all()
    return {'items': [dict(row) for row in rows]}


@router.post('/api/v1/images', tags=['images'], status_code=202)
def generate(request: Request, data: CreateImage):
    principal = member(request, mutation=True)
    engine, settings = request.app.state.engine, request.app.state.settings
    payload = data.request.model_dump(mode='json')
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        workspace = db.execute(text('SELECT id FROM workspaces FOR UPDATE')).scalar_one()
        previous = db.execute(text('SELECT target_id,request,status,deleted_at FROM image_jobs WHERE id=:id'), {'id': data.request.id}).mappings().one_or_none()
        if previous:
            if previous['deleted_at'] is not None:
                raise HTTPException(410, 'This image was deleted. Use a new request to generate another image.')
            if previous['target_id'] != data.target_id or previous['request'] != payload:
                raise HTTPException(409, 'This image request identifier was already used.')
            return {'id': data.request.id, 'status': previous['status']}
        row = target_record(db, data.target_id, lock=True)
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner,7))'), {'owner': str(principal.id)})
        if db.execute(text('SELECT count(*) FROM image_jobs WHERE deleted_at IS NULL')).scalar_one() >= 100:
            raise HTTPException(409, 'This workspace supports 100 saved image jobs in this build.')
        if row['protocol'] != 'hearth.image.v1' or row['model_id'] != data.request.model:
            raise HTTPException(409, 'Choose a configured image model.')
        if row['state'] != 'ready':
            raise HTTPException(409, 'This image model needs verification in Providers.')
        if data.request.shape not in row['profile'].get('shapes', []) or data.request.steps not in row['profile'].get('steps', []):
            raise HTTPException(409, 'These image settings have not been verified for this model.')
        claim_pool(db, row, data.request.id, principal.id)
        db.execute(text('INSERT INTO image_jobs(id,farm_id,owner_id,workspace_id,target_id,request,session_hash,authorization_version) VALUES(:id,:farm,:owner,:workspace,:target,CAST(:request AS jsonb),:session,:version)'),
            {'id': data.request.id, 'farm': principal.farm_id, 'owner': principal.id, 'workspace': workspace, 'target': row['id'], 'request': json.dumps(payload), 'session': request.state.identity['token_hash'], 'version': principal.authorization_version})
    request.app.state.inference_executor.submit(execute, engine, settings, principal, row, data.request)
    return {'id': data.request.id, 'status': 'running'}


@router.post('/api/v1/images/{job_id}/cancel', tags=['images'])
def cancel(request: Request, job_id: UUID):
    principal = member(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        row = db.execute(text('SELECT status FROM image_jobs WHERE id=:id FOR UPDATE'), {'id': job_id}).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, 'This image is not available in your workspace.')
        if row in {'queued', 'running'}:
            db.execute(text('UPDATE image_jobs SET cancel_requested=true WHERE id=:id'), {'id': job_id})
    return {'cancel_requested': row in {'queued', 'running'}}


@router.get('/api/v1/images/{job_id}/image', tags=['images'])
def download(request: Request, job_id: UUID):
    principal = member(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        image = db.execute(text("SELECT image FROM image_jobs WHERE id=:id AND status='completed' AND channel_id IS NULL AND deleted_at IS NULL"), {'id': job_id}).scalar_one_or_none()
        if image is None:
            raise HTTPException(404, 'This completed image is not available in your workspace.')
    return Response(bytes(image), media_type='image/png', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Disposition': f'inline; filename="hearth-{job_id}.png"'})


@router.delete('/api/v1/images/{job_id}', tags=['images'])
def delete_image(request: Request, job_id: UUID):
    principal = member(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        # RLS scopes this to the requesting owner, including when they are an admin.
        # Shared-channel moderation is separate from this private gallery action.
        row = db.execute(text('SELECT status,deleted_at FROM image_jobs WHERE id=:id AND channel_id IS NULL FOR UPDATE'), {'id': job_id}).mappings().one_or_none()
        if row is None:
            raise HTTPException(404, 'This image is not available in your workspace.')
        if row['deleted_at'] is not None:
            return {'deleted': True}
        if row['status'] in {'queued', 'running'}:
            raise HTTPException(409, 'Stop this image and wait for generation to end before deleting it.')
        # Keep IDs for idempotency, batch bookkeeping and variation references,
        # but atomically erase both copies of the artifact and its byte receipt.
        db.execute(text('UPDATE image_jobs SET image=NULL,metadata=NULL,deleted_at=now() WHERE id=:id'), {'id': job_id})
        db.execute(text("UPDATE conversation_images SET image=NULL,sha256=NULL,status='deleted',reason='Image deleted.' WHERE id=:id AND channel_id IS NULL"), {'id': job_id})
    return {'deleted': True}


@router.get('/api/v1/conversation-images/{job_id}/image', tags=['images'])
def conversation_image(request: Request, job_id: UUID):
    principal = member(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        artifact = db.execute(text("SELECT image FROM conversation_images WHERE id=:id AND status='completed'"), {'id': job_id}).scalar_one_or_none()
        if artifact is None:
            raise HTTPException(404, 'This image is not available in this conversation.')
    return Response(bytes(artifact), media_type='image/png', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Disposition': f'inline; filename="hearth-{job_id}.png"'})


def execute(engine, settings, principal, target, data):
    stopped, problem, result, artifact = False, None, None, None
    last_identity = 0.0
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        run = dict(db.execute(text('SELECT * FROM image_jobs WHERE id=:id'), {'id': data.id}).mappings().one())
    execution_id = run['batch_run_id'] or data.id
    try:
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            current = target_record(db, target['id'])
            if (run['cancel_requested'] or not conversation_media.active(db, data.id) or not session_current(db, principal, run['session_hash']) or current['active_run_id'] != execution_id
                    or current['revision'] != target['revision'] or current['state'] != 'ready'):
                raise ProviderError('The session or model changed before image generation.', provider_fault=False)
        if not identity_current(engine, settings, principal, run['session_hash']):
            raise ProviderError('The sending session ended before image generation.', provider_fault=False)
        last_identity = time.monotonic()

        def observe(receipt):
            nonlocal stopped, last_identity
            if not stopped and (time.monotonic() - last_identity >= 5 or receipt.execution_released):
                stopped = not identity_current(engine, settings, principal, run['session_hash'])
                last_identity = time.monotonic()
            if receipt.manifest_sha256 != target['profile'].get('manifest_sha256'):
                stopped = True
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                job = db.execute(text('SELECT status,cancel_requested FROM image_jobs WHERE id=:id FOR UPDATE'), {'id': data.id}).mappings().one()
                if receipt.manifest_sha256 != target['profile'].get('manifest_sha256'):
                    record_failure(db, target, 'The provider model manifest changed. Verify the provider again.')
                current = target_record(db, target['id'])
                stopped = stopped or job['cancel_requested'] or job['status'] != 'running' or not conversation_media.active(db, data.id) or not session_current(db, principal, run['session_hash']) or current['active_run_id'] != execution_id or current['revision'] != target['revision'] or current['state'] != 'ready'
                db.execute(text("UPDATE image_jobs SET progress=:progress WHERE id=:id AND status='running'"), {'id': data.id, 'progress': receipt.progress})
                conversation_media.progress(db, data.id, receipt.progress)
                db.execute(text("UPDATE provider_pools SET lease_until=now()+interval '240 seconds' WHERE id=:pool AND active_run_id=:run"), {'pool': target['resource_pool_id'], 'run': execution_id})
            return stopped

        result, artifact = image_transport.render(target['base_url'], credential_for(target, settings), transport_settings(target, settings), data, observe)
    except ProviderError as exc:
        problem = exc
    except Exception:
        problem = ProviderError('Image generation was interrupted. Check the provider before retrying.', uncertain=True)
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        job = db.execute(text('SELECT status,cancel_requested FROM image_jobs WHERE id=:id FOR UPDATE'), {'id': data.id}).mappings().one()
        current = target_record(db, target['id'])
        if job['status'] != 'running' or current['active_run_id'] != execution_id:
            return
        stopped = stopped or job['cancel_requested'] or not conversation_media.active(db, data.id) or not session_current(db, principal, run['session_hash']) or current['revision'] != target['revision'] or current['state'] != 'ready'
        state = ('interrupted' if problem.uncertain else 'failed') if problem else ('cancelled' if stopped else result.state)
        if state == 'completed' and artifact is None:
            state = 'failed'
        reason = str(problem) if problem else ('Image generation stopped.' if stopped else result.reason)
        record_failure(db, target, problem or (reason or 'The provider job failed.' if state == 'failed' else None))
        metadata = result.model_dump(mode='json') if result else None
        if metadata:
            metadata['model_revision'] = target['profile'].get('model_revision')
            planned = db.execute(text('SELECT planning_target_id,planning_revision,source_image_id FROM image_plans WHERE id=:id'), {'id': execution_id}).mappings().one_or_none()
            if planned:
                metadata['planning'] = {key: str(value) if key.endswith('_id') and value else value for key, value in planned.items()}
        db.execute(text('UPDATE image_jobs SET status=:status,reason=:reason,metadata=CAST(:metadata AS jsonb),image=:image,finished_at=now() WHERE id=:id'),
            {'id': data.id, 'status': state, 'reason': reason, 'metadata': json.dumps(metadata), 'image': artifact if state == 'completed' and run['channel_id'] is None else None})
        conversation_media.finish(db, data.id, state, reason, metadata, artifact)
        if not run['batch_run_id']:
            release_pool(db, target['resource_pool_id'], execution_id, uncertain=bool(problem and problem.uncertain))
        return state, reason, bool(problem and problem.uncertain)
