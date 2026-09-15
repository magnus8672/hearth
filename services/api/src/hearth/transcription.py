"""Owner-scoped transcription drafts. Only an explicit user action puts text into chat."""
import hashlib
import json
import time
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from hearth import routing, transcription_transport
from hearth.chat import conversation, identity_current, member, session_current
from hearth.contracts import TranscriptionRequest
from hearth.database import scoped_session
from hearth.inference import ProviderError
from hearth.provider_health import record_failure
from hearth.providers import claim_pool, credential_for, release_pool, target_record, transport_settings
from hearth.transcription_audio import normalize

router = APIRouter()


def reconcile(db):
    rows = db.execute(text("SELECT j.id,t.resource_pool_id FROM transcription_jobs j JOIN inference_targets t ON t.id=j.target_id JOIN provider_pools p ON p.id=t.resource_pool_id WHERE j.status='running' AND (p.active_run_id IS DISTINCT FROM j.id OR p.lease_until<now()) FOR UPDATE OF j")).mappings().all()
    for row in rows:
        db.execute(text("UPDATE transcription_jobs SET status='interrupted',reason='Transcription was interrupted. Check the provider before retrying.',audio=NULL,finished_at=now() WHERE id=:id"), {'id': row['id']})
        release_pool(db, row['resource_pool_id'], row['id'], uncertain=True)


@router.get('/api/v1/chats/{chat_id}/transcriptions', tags=['transcription'])
def listing(request: Request, chat_id: UUID):
    principal = member(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        conversation(db, chat_id)
        reconcile(db)
        rows = db.execute(text("SELECT id,status,cancel_requested,reason,transcript,route_receipt->>'model_id' AS model_id FROM transcription_jobs WHERE conversation_id=:chat AND NOT dismissed ORDER BY created_at DESC LIMIT 10"), {'chat': chat_id}).mappings().all()
        return {'items': [dict(row) for row in rows]}


@router.post('/api/v1/chats/{chat_id}/transcriptions', tags=['transcription'], status_code=202)
async def submit(request: Request, chat_id: UUID, request_id: UUID):
    principal = member(request, mutation=True)
    engine, settings = request.app.state.engine, request.app.state.settings
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        conversation(db, chat_id)
    raw = await request.body()
    source_digest = hashlib.sha256(raw).hexdigest()
    try:
        audio = normalize(raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        conversation(db, chat_id, lock=True)
        reconcile(db)
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner,11))'), {'owner': str(principal.id)})
        prior = db.execute(text('SELECT id,conversation_id,source_sha256,status FROM transcription_jobs WHERE id=:id'), {'id': request_id}).mappings().one_or_none()
        if prior:
            if prior['conversation_id'] != chat_id or prior['source_sha256'] != source_digest:
                raise HTTPException(409, 'This transcription identifier was already used for another recording.')
            return {'id': prior['id'], 'status': prior['status']}
        if db.execute(text("SELECT 1 FROM transcription_jobs WHERE status='running'")).first():
            raise HTTPException(409, 'Wait for your current transcription to finish, or stop it first.')
        if db.execute(text('SELECT count(*) FROM transcription_jobs WHERE NOT dismissed')).scalar_one() >= 100:
            raise HTTPException(409, 'Dismiss old transcript drafts before creating more.')
        target = routing.select(db, 'audio.transcribe')
        if target is None:
            raise HTTPException(409, 'No verified, idle transcription provider is assigned. Configure Speech input in Administration.')
        data = TranscriptionRequest(id=request_id, model=target['model_id'], audio_sha256=hashlib.sha256(audio).hexdigest())
        claim_pool(db, target, data.id, principal.id)
        db.execute(text('INSERT INTO transcription_jobs(id,farm_id,owner_id,conversation_id,target_id,request,route_receipt,source_sha256,audio,session_hash,authorization_version) VALUES(:id,:farm,:owner,:chat,:target,CAST(:request AS jsonb),CAST(:route AS jsonb),:digest,:audio,:session,:version)'),
                   {'id': data.id, 'farm': principal.farm_id, 'owner': principal.id, 'chat': chat_id, 'target': target['id'], 'request': data.model_dump_json(), 'route': json.dumps(routing.receipt(db, 'audio.transcribe', target)), 'digest': source_digest, 'audio': audio, 'session': request.state.identity['token_hash'], 'version': principal.authorization_version})
    request.app.state.inference_executor.submit(execute, engine, settings, principal, target, data)
    return {'id': data.id, 'status': 'running'}


@router.post('/api/v1/chats/{chat_id}/transcriptions/{job_id}/cancel', tags=['transcription'])
def cancel(request: Request, chat_id: UUID, job_id: UUID):
    principal = member(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        conversation(db, chat_id)
        row = db.execute(text('SELECT status FROM transcription_jobs WHERE id=:id AND conversation_id=:chat FOR UPDATE'), {'id': job_id, 'chat': chat_id}).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, 'This transcription is not available.')
        if row == 'running':
            db.execute(text('UPDATE transcription_jobs SET cancel_requested=true WHERE id=:id'), {'id': job_id})
    return {'cancel_requested': row == 'running'}


@router.delete('/api/v1/chats/{chat_id}/transcriptions/{job_id}', tags=['transcription'])
def dismiss(request: Request, chat_id: UUID, job_id: UUID):
    principal = member(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        conversation(db, chat_id)
        row = db.execute(text('SELECT status FROM transcription_jobs WHERE id=:id AND conversation_id=:chat FOR UPDATE'), {'id': job_id, 'chat': chat_id}).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, 'This transcription is not available.')
        if row == 'running':
            raise HTTPException(409, 'Stop transcription and wait for it to finish first.')
        db.execute(text("UPDATE transcription_jobs SET dismissed=true,transcript='',audio=NULL,metadata=NULL WHERE id=:id"), {'id': job_id})
    return {'dismissed': True}


def active(db, run):
    return db.execute(text('SELECT 1 FROM conversations WHERE id=:id AND deleted_at IS NULL'), {'id': run['conversation_id']}).first() is not None


def execute(engine, settings, principal, target, data):
    stopped, problem, result = False, None, None
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        run = dict(db.execute(text('SELECT * FROM transcription_jobs WHERE id=:id'), {'id': data.id}).mappings().one())
    try:
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            current = target_record(db, target['id'])
            if run['cancel_requested'] or not active(db, run) or not session_current(db, principal, run['session_hash']) or current['active_run_id'] != data.id or current['revision'] != target['revision'] or current['state'] != 'ready':
                raise ProviderError('The session or provider changed before transcription.', provider_fault=False)
        if not identity_current(engine, settings, principal, run['session_hash']):
            raise ProviderError('The sending session ended before transcription.', provider_fault=False)
        last_identity = time.monotonic()
        def observe(receipt):
            nonlocal stopped, last_identity
            if not stopped and (time.monotonic() - last_identity >= 5 or receipt.execution_released):
                stopped = not identity_current(engine, settings, principal, run['session_hash'])
                last_identity = time.monotonic()
            if receipt.manifest_sha256 != target['profile'].get('manifest_sha256'):
                stopped = True
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                job = db.execute(text('SELECT status,cancel_requested FROM transcription_jobs WHERE id=:id FOR UPDATE'), {'id': data.id}).mappings().one()
                if receipt.manifest_sha256 != target['profile'].get('manifest_sha256'):
                    record_failure(db, target, 'The provider model manifest changed. Verify the provider again.')
                current = target_record(db, target['id'])
                stopped = stopped or job['cancel_requested'] or job['status'] != 'running' or not active(db, run) or not session_current(db, principal, run['session_hash']) or current['active_run_id'] != data.id or current['revision'] != target['revision'] or current['state'] != 'ready'
                db.execute(text("UPDATE provider_pools SET lease_until=now()+interval '240 seconds' WHERE id=:pool AND active_run_id=:run"), {'pool': target['resource_pool_id'], 'run': data.id})
            return stopped
        result = transcription_transport.transcribe(target['base_url'], credential_for(target, settings), transport_settings(target, settings), data, bytes(run['audio']), observe)
    except ProviderError as exc:
        problem = exc
    except Exception:
        problem = ProviderError('Transcription generation was interrupted. Check the provider before retrying.', uncertain=True)
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        job = db.execute(text('SELECT status,cancel_requested FROM transcription_jobs WHERE id=:id FOR UPDATE'), {'id': data.id}).mappings().one()
        current = target_record(db, target['id'])
        if job['status'] != 'running' or current['active_run_id'] != data.id:
            return
        stopped = stopped or job['cancel_requested'] or not active(db, run) or not session_current(db, principal, run['session_hash']) or current['revision'] != target['revision'] or current['state'] != 'ready'
        state = ('interrupted' if problem.uncertain else 'failed') if problem else ('cancelled' if stopped else result.state)
        reason = str(problem) if problem else ('Transcription generation stopped.' if stopped else result.reason)
        record_failure(db, target, problem or (reason or 'The provider job failed.' if state == 'failed' else None))
        metadata = result.model_dump(mode='json', exclude={'text'}) if result else None
        db.execute(text('UPDATE transcription_jobs SET status=:state,reason=:reason,metadata=CAST(:metadata AS jsonb),transcript=:transcript,audio=NULL,finished_at=now() WHERE id=:id'),
                   {'id': data.id, 'state': state, 'reason': reason, 'metadata': json.dumps(metadata), 'transcript': result.text if state == 'completed' else ''})
        release_pool(db, target['resource_pool_id'], data.id, uncertain=bool(problem and problem.uncertain))
