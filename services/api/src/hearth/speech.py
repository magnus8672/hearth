"""Explicit Read aloud jobs bound to an immutable private assistant message."""
import json
import time
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from hearth import routing, speech_transport
from hearth.chat import conversation, identity_current, member, session_current
from hearth.contracts import SpeechGeneration
from hearth.database import scoped_session
from hearth.inference import ProviderError
from hearth.provider_health import record_failure
from hearth.providers import claim_pool, credential_for, release_pool, target_record, transport_settings

router = APIRouter()


class ReadAloud(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID


def reconcile(db):
    rows = db.execute(text("SELECT j.id,t.resource_pool_id FROM speech_jobs j JOIN inference_targets t ON t.id=j.target_id JOIN provider_pools p ON p.id=t.resource_pool_id WHERE j.status='running' AND (p.active_run_id IS DISTINCT FROM j.id OR p.lease_until<now()) FOR UPDATE OF j")).mappings().all()
    for row in rows:
        db.execute(text("UPDATE speech_jobs SET status='interrupted',reason='Speech was interrupted. Check the provider before retrying.',finished_at=now() WHERE id=:id"), {'id': row['id']})
        release_pool(db, row['resource_pool_id'], row['id'], uncertain=True)


def snapshot(db, chat_id):
    reconcile(db)
    rows = db.execute(text("SELECT DISTINCT ON(message_id) id,message_id,status,cancel_requested,reason,metadata,route_receipt->>'model_id' AS model_id,request->>'voice' AS voice FROM speech_jobs WHERE conversation_id=:chat ORDER BY message_id,created_at DESC,id DESC"), {'chat': chat_id}).mappings().all()
    return {row['message_id']: dict(row) for row in rows}


@router.post('/api/v1/chats/{chat_id}/messages/{message_id}/speech', tags=['speech'], status_code=202)
def read_aloud(request: Request, chat_id: UUID, message_id: UUID, data: ReadAloud):
    principal = member(request, mutation=True)
    engine, settings = request.app.state.engine, request.app.state.settings
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        conversation(db, chat_id, lock=True)
        reconcile(db)
        message = db.execute(text('SELECT role,content,status FROM messages WHERE id=:id AND conversation_id=:chat'), {'id': message_id, 'chat': chat_id}).mappings().one_or_none()
        if not message:
            raise HTTPException(404, 'This reply is not available in your conversation.')
        prior = db.execute(text('SELECT id,message_id,status FROM speech_jobs WHERE id=:id'), {'id': data.request_id}).mappings().one_or_none()
        if prior:
            if prior['message_id'] != message_id:
                raise HTTPException(409, 'This speech request identifier was already used.')
            return dict(prior)
        prior = db.execute(text("SELECT id,status FROM speech_jobs WHERE message_id=:id AND status IN ('running','completed')"), {'id': message_id}).mappings().one_or_none()
        if prior:
            return dict(prior)
        if message['role'] != 'assistant' or message['status'] != 'completed' or not message['content'].strip():
            raise HTTPException(409, 'Read aloud is available for completed assistant replies with text.')
        if len(message['content']) > 6000:
            raise HTTPException(409, 'This reply is too long for Read aloud (6,000 characters). Ask for a shorter version first.')
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner,10))'), {'owner': str(principal.id)})
        if db.execute(text("SELECT 1 FROM speech_jobs WHERE status='running'")).first():
            raise HTTPException(409, 'Wait for your current speech generation to finish, or stop it first.')
        count, size = db.execute(text('SELECT count(*),COALESCE(sum(octet_length(audio)),0) FROM speech_jobs')).one()
        if count >= 100 or size + 33554432 > 268435456:
            raise HTTPException(409, 'This workspace has reached its saved speech budget.')
        target = routing.select(db, 'audio.speak')
        if target is None:
            raise HTTPException(409, 'No verified, idle speech provider is assigned. Configure Speech output in Administration.')
        voice = target['profile'].get('default_voice')
        if not voice or voice not in target['profile'].get('voices', []):
            raise HTTPException(409, 'The speech provider needs a verified default voice.')
        generation = SpeechGeneration(id=data.request_id, model=target['model_id'], voice=voice, input=message['content'])
        claim_pool(db, target, data.request_id, principal.id)
        db.execute(text('INSERT INTO speech_jobs(id,farm_id,owner_id,conversation_id,message_id,target_id,request,route_receipt,session_hash,authorization_version) VALUES(:id,:farm,:owner,:chat,:message,:target,CAST(:request AS jsonb),CAST(:route AS jsonb),:session,:version)'),
                   {'id': data.request_id, 'farm': principal.farm_id, 'owner': principal.id, 'chat': chat_id, 'message': message_id, 'target': target['id'],
                    'request': generation.model_dump_json(), 'route': json.dumps(routing.receipt(db, 'audio.speak', target)), 'session': request.state.identity['token_hash'], 'version': principal.authorization_version})
    request.app.state.inference_executor.submit(execute, engine, settings, principal, target, generation)
    return {'id': data.request_id, 'status': 'running'}


@router.post('/api/v1/chats/{chat_id}/speech/{job_id}/cancel', tags=['speech'])
def cancel(request: Request, chat_id: UUID, job_id: UUID):
    principal = member(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        conversation(db, chat_id)
        row = db.execute(text('SELECT status FROM speech_jobs WHERE id=:id AND conversation_id=:chat FOR UPDATE'), {'id': job_id, 'chat': chat_id}).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, 'This speech job is not available.')
        if row == 'running':
            db.execute(text('UPDATE speech_jobs SET cancel_requested=true WHERE id=:id'), {'id': job_id})
    return {'cancel_requested': row == 'running'}


@router.get('/api/v1/chats/{chat_id}/speech/{job_id}/audio', tags=['speech'])
def download(request: Request, chat_id: UUID, job_id: UUID):
    principal = member(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        conversation(db, chat_id)
        raw = db.execute(text("SELECT audio FROM speech_jobs WHERE id=:id AND conversation_id=:chat AND status='completed'"), {'id': job_id, 'chat': chat_id}).scalar_one_or_none()
        if raw is None:
            raise HTTPException(404, 'This completed speech is not available.')
    return Response(bytes(raw), media_type='audio/wav', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Disposition': f'inline; filename="hearth-{job_id}.wav"'})


def active(db, run):
    return db.execute(text('SELECT 1 FROM conversations WHERE id=:id AND deleted_at IS NULL'), {'id': run['conversation_id']}).first() is not None


def execute(engine, settings, principal, target, data):
    stopped, problem, result, artifact = False, None, None, None
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        run = dict(db.execute(text('SELECT * FROM speech_jobs WHERE id=:id'), {'id': data.id}).mappings().one())
    try:
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            current = target_record(db, target['id'])
            if run['cancel_requested'] or not active(db, run) or not session_current(db, principal, run['session_hash']) or current['active_run_id'] != data.id or current['revision'] != target['revision'] or current['state'] != 'ready':
                raise ProviderError('The session or provider changed before speech generation.', provider_fault=False)
        if not identity_current(engine, settings, principal, run['session_hash']):
            raise ProviderError('The sending session ended before speech generation.', provider_fault=False)
        last_identity = time.monotonic()
        def observe(receipt):
            nonlocal stopped, last_identity
            if not stopped and (time.monotonic() - last_identity >= 5 or receipt.execution_released):
                stopped = not identity_current(engine, settings, principal, run['session_hash'])
                last_identity = time.monotonic()
            if receipt.manifest_sha256 != target['profile'].get('manifest_sha256'):
                stopped = True
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                job = db.execute(text('SELECT status,cancel_requested FROM speech_jobs WHERE id=:id FOR UPDATE'), {'id': data.id}).mappings().one()
                if receipt.manifest_sha256 != target['profile'].get('manifest_sha256'):
                    record_failure(db, target, 'The provider model manifest changed. Verify the provider again.')
                current = target_record(db, target['id'])
                stopped = stopped or job['cancel_requested'] or job['status'] != 'running' or not active(db, run) or not session_current(db, principal, run['session_hash']) or current['active_run_id'] != data.id or current['revision'] != target['revision'] or current['state'] != 'ready'
                db.execute(text("UPDATE provider_pools SET lease_until=now()+interval '240 seconds' WHERE id=:pool AND active_run_id=:run"), {'pool': target['resource_pool_id'], 'run': data.id})
            return stopped
        result, artifact = speech_transport.render(target['base_url'], credential_for(target, settings), transport_settings(target, settings), data, observe)
    except ProviderError as exc:
        problem = exc
    except Exception:
        problem = ProviderError('Speech generation was interrupted. Check the provider before retrying.', uncertain=True)
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        job = db.execute(text('SELECT status,cancel_requested FROM speech_jobs WHERE id=:id FOR UPDATE'), {'id': data.id}).mappings().one()
        current = target_record(db, target['id'])
        if job['status'] != 'running' or current['active_run_id'] != data.id:
            return
        stopped = stopped or job['cancel_requested'] or not active(db, run) or not session_current(db, principal, run['session_hash']) or current['revision'] != target['revision'] or current['state'] != 'ready'
        state = ('interrupted' if problem.uncertain else 'failed') if problem else ('cancelled' if stopped else result.state)
        if state == 'completed' and artifact is None:
            state = 'failed'
        reason = str(problem) if problem else ('Speech generation stopped.' if stopped else result.reason)
        record_failure(db, target, problem or (reason or 'The provider job failed.' if state == 'failed' else None))
        metadata = result.model_dump(mode='json') if result else None
        db.execute(text('UPDATE speech_jobs SET status=:state,reason=:reason,metadata=CAST(:metadata AS jsonb),audio=:audio,finished_at=now() WHERE id=:id'),
                   {'id': data.id, 'state': state, 'reason': reason, 'metadata': json.dumps(metadata), 'audio': artifact if state == 'completed' else None})
        release_pool(db, target['resource_pool_id'], data.id, uncertain=bool(problem and problem.uncertain))
