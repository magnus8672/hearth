"""Private, durable turns. Upstream streams persist independently of browser tabs.

An interrupted execution is never replayed automatically. Pool receipts fence late
writers, and cancellation drains the backend before releasing shared capacity.
"""
import json
import time
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text

from hearth import conversation_media, identity, image_planning, memory, routing, vision
from hearth.database import scoped_session
from hearth.identity import authenticate
from hearth.inference import ProviderError, chat_stream
from hearth.provider_health import record_failure
from hearth.providers import claim_pool, release_pool, target_record

router = APIRouter()


class NewChat(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(default='New conversation', min_length=1, max_length=200)


class SendTurn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: UUID
    revision: int = Field(strict=True, ge=1)
    content: str = Field(min_length=1, max_length=4000)
    capability: routing.TextCapability = 'auto'
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=4)

    @field_validator('attachment_ids')
    @classmethod
    def distinct_attachments(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('Attach each image only once per message.')
        return value
    interrupt_run_id: UUID | None = None
    note_id: UUID | None = None
    note_revision: int | None = Field(default=None, strict=True, ge=1, le=9007199254740991)


def member(request, mutation=False):
    principal = authenticate(request, mutation=mutation)
    principal.require('conversation.own')
    if request.app.state.settings.audience != 'user':
        raise HTTPException(403, 'Open your personal workspace to chat.')
    return principal


def conversation(db, chat_id, lock=False):
    row = db.execute(text("SELECT id,title,revision FROM conversations WHERE id=:id AND kind='chat' AND deleted_at IS NULL" + (' FOR UPDATE' if lock else '')),
                     {'id': chat_id}).mappings().one_or_none()
    if not row:
        raise HTTPException(404, 'This conversation is not available in your workspace.')
    return dict(row)


def session_current(db, principal, session_hash):
    return db.execute(text("SELECT EXISTS(SELECT 1 FROM browser_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=:hash AND s.user_id=:owner AND s.farm_id=:farm AND s.audience='user' AND s.expires_at>now() AND s.last_seen_at>now()-interval '30 minutes' AND u.state='active' AND u.authorization_version=:version AND s.authorization_version=u.authorization_version AND EXISTS(SELECT 1 FROM role_grants g WHERE g.user_id=u.id AND g.farm_id=u.farm_id AND g.role IN ('Owner','FarmAdmin','Operator','Auditor','Member')))"),
        {'hash': session_hash, 'owner': principal.id, 'farm': principal.farm_id, 'version': principal.authorization_version}).scalar_one()


def identity_current(engine, settings, principal, session_hash):
    """Read the latest rotated credential without refreshing it in a second thread."""
    try:
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            if not session_current(db, principal, session_hash):
                return False
            encrypted = db.execute(text('SELECT credentials FROM browser_sessions WHERE token_hash=:hash AND user_id=:owner AND farm_id=:farm'), {'hash': session_hash, 'owner': principal.id, 'farm': principal.farm_id}).scalar_one()
        tokens = json.loads(identity.cipher(settings).decrypt(encrypted.encode()))
        active = identity.token_request(settings, 'token/introspect', {'token': tokens['access_token']})
        return active.get('active') is True and active.get('sub') == tokens['subject'] and active.get('iss') == settings.issuer
    except Exception:
        return False


def reconcile(db, chat_id):
    # Expiration diagnoses lost execution; it never grants permission to replay.
    rows = db.execute(text("SELECT r.id,r.assistant_message_id,t.resource_pool_id,p.active_run_id,p.lease_until,m.generation_phase FROM chat_runs r JOIN messages m ON m.id=r.assistant_message_id JOIN inference_targets t ON t.id=r.target_id JOIN provider_pools p ON p.id=t.resource_pool_id WHERE r.conversation_id=:chat AND r.status='running' AND ((r.tool_phase AND r.tool_phase_at<now()-interval '16 minutes') OR (NOT r.tool_phase AND (m.generation_phase<>'image_handoff' AND (p.active_run_id IS DISTINCT FROM r.id OR p.lease_until<now()))) OR (m.generation_phase='image_handoff' AND m.phase_changed_at<now()-interval '60 seconds')) FOR UPDATE OF r"), {'chat': chat_id}).mappings().all()
    for row in rows:
        conversation_media.interrupt(db, row['id'], 'Image generation was interrupted. Check the provider before retrying.')
        db.execute(text("UPDATE chat_runs SET status='interrupted',reason='Execution was interrupted. Check the model server before starting a new conversation.',finished_at=now() WHERE id=:id"), {'id': row['id']})
        db.execute(text("UPDATE messages SET status='interrupted' WHERE id=:id"), {'id': row['assistant_message_id']})
        if row['generation_phase'] != 'image_handoff':
            release_pool(db, row['resource_pool_id'], row['id'], uncertain=True)
        db.execute(text("UPDATE chat_requests SET state='blocked',reason='The previous execution was interrupted. Check Providers before sending this message again.' WHERE interrupt_run_id=:id AND state='queued'"), {'id': row['id']})


def execute_turn(engine, settings, principal, run_id, target, context):
    if image_planning.run_if_planned(engine, settings, principal, run_id, target):
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            chat_id = db.execute(text('SELECT conversation_id FROM chat_runs WHERE id=:id'), {'id': run_id}).scalar_one()
        dispatch_pending(engine, settings, principal, chat_id)
        return
    if target['protocol'] == 'hearth.image.v1':
        from hearth import images
        from hearth.contracts import ImageGeneration
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            payload = db.execute(text('SELECT request FROM image_jobs WHERE id=:id'), {'id': run_id}).scalar_one()
            chat_id = db.execute(text('SELECT conversation_id FROM chat_runs WHERE id=:id'), {'id': run_id}).scalar_one()
        images.execute(engine, settings, principal, target, ImageGeneration.model_validate(payload))
        dispatch_pending(engine, settings, principal, chat_id)
        return
    answer, stopped, finished, problem = '', False, None, None
    reasoning, reasoning_bytes, reasoning_truncated, stream_phase = '', 0, False, 'waiting'
    last_write, last_identity_check = 0.0, 0.0
    session_hash = None
    try:
        # Check again at dispatch, after the admission transaction committed.
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            memory.state(db, lock=True)
            run = db.execute(text('SELECT * FROM chat_runs WHERE id=:id'), {'id': run_id}).mappings().one()
            session_hash = run['session_hash']
            current = target_record(db, target['id'])
            if (not session_current(db, principal, run['session_hash']) or run['cancel_requested']
                    or current['revision'] != target['revision'] or current['state'] != 'ready' or not memory.receipt_current(db, run['memory_receipt'])
                    or current['active_run_id'] != run_id):
                raise ProviderError('The session or target changed before generation began.', provider_fault=False)
        if not identity_current(engine, settings, principal, session_hash):
            raise ProviderError('The identity session ended before generation began.', provider_fault=False)
        last_identity_check = time.monotonic()
        from hearth.tool_harness import stream as harness_stream
        for kind, value in harness_stream(engine, settings, principal, run_id, target, context, chat_stream):
            if kind == 'text' and not stopped:
                answer += value
                stream_phase = 'answer'
            if kind == 'reasoning' and not stopped:
                stream_phase = 'reasoning'
                encoded = value.encode('utf-8')
                remaining = 65536-reasoning_bytes
                reasoning_truncated = reasoning_truncated or len(encoded) > remaining
                if not reasoning_truncated:
                    reasoning += value
                    reasoning_bytes += len(encoded)
                elif remaining:
                    fragment = encoded[:remaining].decode('utf-8', errors='ignore')
                    reasoning += fragment
                    # The preview is a contiguous prefix, even across UTF-8 cuts.
                    reasoning_bytes = 65536
            if kind == 'done':
                finished = value
            if time.monotonic() - last_write < 0.15 and kind != 'done':
                continue
            if not stopped and (time.monotonic() - last_identity_check >= 5 or kind == 'done'):
                stopped = not identity_current(engine, settings, principal, session_hash)
                last_identity_check = time.monotonic()
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                memory.state(db, lock=True)
                run = db.execute(text('SELECT * FROM chat_runs WHERE id=:id FOR UPDATE'), {'id': run_id}).mappings().one()
                current = target_record(db, target['id'])
                if (run['status'] != 'running' or (not run['tool_phase'] and current['active_run_id'] != run_id)):
                    # Keep draining, but never write with a stale receipt.
                    stopped = True
                    continue
                stopped = stopped or run['cancel_requested'] or not session_current(db, principal, run['session_hash']) or current['revision'] != target['revision'] or current['state'] != 'ready' or not memory.receipt_current(db, run['memory_receipt'])
                if not stopped:
                    db.execute(text('UPDATE messages SET content=:content WHERE id=:id'), {'content': answer, 'id': run['assistant_message_id']})
                    db.execute(text('UPDATE chat_runs SET reasoning_text=:reasoning,reasoning_truncated=:truncated,stream_phase=:phase WHERE id=:id'),
                        {'reasoning': reasoning, 'truncated': reasoning_truncated, 'phase': stream_phase, 'id': run_id})
                db.execute(text("UPDATE provider_pools SET lease_until=now()+interval '240 seconds' WHERE id=:pool AND active_run_id=:run"), {'pool': target['resource_pool_id'], 'run': run_id})
            last_write = time.monotonic()
        if not finished:
            raise ProviderError('The stream ended without a completion receipt.', uncertain=True)
    except ProviderError as exc:
        problem = exc
    except Exception:
        problem = ProviderError('Generation was interrupted. Check the model server before retrying.', uncertain=True)
    # If this transaction itself fails, the durable running receipt expires into
    # an unknown execution. Startup deliberately does not replay personal prompts.
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        memory.state(db, lock=True)
        run = db.execute(text('SELECT * FROM chat_runs WHERE id=:id FOR UPDATE'), {'id': run_id}).mappings().one()
        current = target_record(db, target['id'])
        if run['status'] != 'running' or (not run['tool_phase'] and current['active_run_id'] != run_id):
            return
        stopped = stopped or run['cancel_requested'] or not session_current(db, principal, run['session_hash']) or current['revision'] != target['revision'] or current['state'] != 'ready' or not memory.receipt_current(db, run['memory_receipt'])
        state = 'cancelled' if stopped and run['tool_phase'] and not (problem and problem.uncertain) else ('interrupted' if problem.uncertain else 'failed') if problem else ('cancelled' if stopped else 'completed')
        reason = str(problem) if problem else ('Response stopped. The model has finished processing.' if stopped else None)
        db.execute(text('UPDATE chat_runs SET status=:status,reason=:reason,finish_reason=:finish,finished_at=now() WHERE id=:id'),
            {'status': state, 'reason': reason, 'finish': finished, 'id': run_id})
        db.execute(text('UPDATE messages SET status=:status WHERE id=:id'), {'status': state, 'id': run['assistant_message_id']})
        db.execute(text("UPDATE tool_invocations SET state='denied',finished_at=now() WHERE chat_run_id=:id AND state IN ('awaiting_approval','approved')"), {'id': run_id})
        db.execute(text("UPDATE outbox SET delivered_at=now() WHERE aggregate_id=:id AND event_type='chat.turn.accepted'"), {'id': run_id})
        record_failure(db, target, problem)
        release_pool(db, target['resource_pool_id'], run_id, uncertain=bool(problem and problem.uncertain))
    dispatch_pending(engine, settings, principal, run['conversation_id'])


@router.get('/api/v1/chats', tags=['chat'])
def chats(request: Request):
    principal = member(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        rows = db.execute(text("SELECT id,title,revision FROM conversations WHERE kind='chat' AND deleted_at IS NULL ORDER BY id DESC")).mappings().all()
        return {'items': [dict(row) for row in rows]}


@router.post('/api/v1/chats', tags=['chat'], status_code=201)
def new_chat(request: Request, data: NewChat):
    principal = member(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        workspace = db.execute(text('SELECT id FROM workspaces FOR UPDATE')).scalar_one()
        if db.execute(text("SELECT count(*) FROM conversations WHERE kind='chat' AND deleted_at IS NULL")).scalar_one() >= 200:
            raise HTTPException(409, 'This workspace supports 200 conversations. Archive one to make room.')
        chat_id = uuid4()
        db.execute(text("INSERT INTO conversations(id,farm_id,owner_id,workspace_id,title,kind) VALUES(:id,:farm,:owner,:workspace,:title,'chat')"),
            {'id': chat_id, 'farm': principal.farm_id, 'owner': principal.id, 'workspace': workspace, 'title': data.title})
    return {'id': chat_id, 'title': data.title, 'revision': 1, 'messages': [], 'runs': []}


@router.get('/api/v1/chats/{chat_id}', tags=['chat'])
def read_chat(request: Request, chat_id: UUID):
    principal = member(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        row = conversation(db, chat_id)
        reconcile(db, chat_id)
        # Read completion receipts before messages. Under READ COMMITTED a
        # completed receipt must never accompany an older, still-running reply.
        runs = db.execute(text("SELECT r.id,r.assistant_message_id,r.status,r.cancel_requested,r.reason,r.finish_reason,r.capability_id,r.memory_receipt,r.tool_phase,r.reasoning_text,r.reasoning_truncated,r.stream_phase,r.route_receipt,r.route_receipt->>'model_id' AS model_id,COALESCE(r.route_receipt->>'protocol',t.protocol) AS protocol FROM chat_runs r JOIN inference_targets t ON t.id=r.target_id WHERE r.conversation_id=:id ORDER BY r.created_at"), {'id': chat_id}).mappings().all()
        messages = db.execute(text('SELECT id,sequence,role,content,status,memory_revision,generation_phase,attachment_ids FROM messages WHERE conversation_id=:id ORDER BY sequence'), {'id': chat_id}).mappings().all()
        pending = db.execute(text("SELECT id,content,state,reason,attachment_ids FROM chat_requests WHERE conversation_id=:id AND state IN ('queued','blocked') ORDER BY created_at"), {'id': chat_id}).mappings().all()
        from hearth.speech import snapshot as speech_snapshot
        spoken = speech_snapshot(db, chat_id)
        result = row | {'messages': [dict(item) | conversation_media.published(db, item['id']) | {'attachments': vision.metadata(db, chat_id, item['attachment_ids']), 'speech': spoken.get(item['id'])} for item in messages], 'runs': [dict(item) | {'tool_invocations': [dict(call) for call in db.execute(text('SELECT i.id,i.state,i.arguments,t.name,s.name AS server_name FROM tool_invocations i JOIN mcp_tools t ON t.id=i.tool_id JOIN mcp_servers s ON s.id=t.server_id WHERE i.chat_run_id=:run ORDER BY i.created_at'), {'run': item['id']}).mappings().all()]} for item in runs], 'unused_attachments': vision.unused(db, chat_id), 'pending': [dict(item) for item in pending]}
    if any(item['state'] == 'queued' for item in pending) and not any(item['status'] == 'running' for item in runs):
        # Resume only a separately accepted, never-dispatched steering message.
        # accept_turn's transaction/idempotency guards duplicate readers.
        request.app.state.inference_executor.submit(dispatch_pending, request.app.state.engine, request.app.state.settings, principal, chat_id)
    return result


@router.post('/api/v1/chats/{chat_id}/turns', tags=['chat'], status_code=202)
def send_turn(request: Request, chat_id: UUID, data: SendTurn):
    principal = member(request, mutation=True)
    engine, settings = request.app.state.engine, request.app.state.settings
    result, execution = accept_turn(engine, settings, principal, request.state.identity['token_hash'], chat_id, data)
    if execution:
        request.app.state.inference_executor.submit(execute_turn, engine, settings, principal, data.request_id, *execution)
    return result


def consume_note(db, data):
    if data.note_id is None and data.note_revision is None:
        return
    note = db.execute(text('SELECT content,revision FROM side_notes WHERE id=:id AND dismissed_at IS NULL FOR UPDATE'), {'id': data.note_id}).mappings().one_or_none()
    if not note or note['revision'] != data.note_revision or note['content'] != data.content:
        raise HTTPException(409, 'This side note changed or was already sent. Refresh your notes.')
    db.execute(text('UPDATE side_notes SET dismissed_at=now(),revision=revision+1 WHERE id=:id'), {'id': data.note_id})


def accept_turn(engine, settings, principal, session_hash, chat_id, data, *, from_queue=False):
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        memory.state(db, lock=True)
        row = conversation(db, chat_id, lock=True)
        previous = db.execute(text('SELECT r.conversation_id,r.status,r.requested_capability,m.content,m.attachment_ids FROM chat_runs r JOIN messages m ON m.id=r.user_message_id WHERE r.id=:id'), {'id': data.request_id}).mappings().one_or_none()
        if previous:
            if previous['conversation_id'] != chat_id or previous['content'] != data.content or previous['requested_capability'] != data.capability or previous['attachment_ids'] != data.attachment_ids:
                raise HTTPException(409, 'This request identifier was already used for a different turn.')
            return {'id': data.request_id, 'status': previous['status']}, None
        queued = db.execute(text('SELECT * FROM chat_requests WHERE id=:id FOR UPDATE'), {'id': data.request_id}).mappings().one_or_none()
        if queued:
            if queued['conversation_id'] != chat_id or queued['content'] != data.content or queued['requested_capability'] != data.capability or queued['attachment_ids'] != data.attachment_ids:
                raise HTTPException(409, 'This request identifier was already used for another message.')
            if not from_queue:
                return {'id': data.request_id, 'status': queued['state']}, None
            if queued['state'] != 'queued':
                return {'id': data.request_id, 'status': queued['state']}, None
        elif from_queue:
            raise HTTPException(409, 'This queued message is no longer available.')
        vision.metadata(db, chat_id, data.attachment_ids)
        if data.attachment_ids and data.capability not in {'auto', 'vision.describe'}:
            raise HTTPException(409, 'Choose Automatic or Vision to send an image to a vision model.')
        reconcile(db, chat_id)
        if row['revision'] != data.revision:
            raise HTTPException(409, 'This conversation changed. Reload it before sending.')
        active = db.execute(text("SELECT id FROM chat_runs WHERE conversation_id=:id AND status='running' FOR UPDATE"), {'id': chat_id}).scalar_one_or_none()
        other_pending = db.execute(text("SELECT id FROM chat_requests WHERE conversation_id=:chat AND state IN ('queued','blocked') AND id<>:id"), {'chat': chat_id, 'id': data.request_id}).first()
        if other_pending:
            raise HTTPException(409, 'A steering message is already waiting. Cancel it before sending another.')
        if active:
            if from_queue or data.interrupt_run_id != active:
                raise HTTPException(409, 'A reply is running. Use Steer to send a correction.')
            consume_note(db, data)
            db.execute(text('INSERT INTO chat_requests(id,farm_id,owner_id,conversation_id,content,interrupt_run_id,authorization_version,session_hash) VALUES(:id,:farm,:owner,:chat,:content,:run,:version,:session)'),
                {'id': data.request_id, 'farm': principal.farm_id, 'owner': principal.id, 'chat': chat_id, 'content': data.content, 'run': active, 'version': principal.authorization_version, 'session': session_hash})
            db.execute(text('UPDATE chat_runs SET cancel_requested=true WHERE id=:id'), {'id': active})
            db.execute(text('UPDATE chat_requests SET requested_capability=:capability,attachment_ids=CAST(:attachments AS uuid[]) WHERE id=:id'), {'id': data.request_id, 'capability': data.capability, 'attachments': data.attachment_ids})
            db.execute(text('UPDATE conversations SET revision=revision+1 WHERE id=:id'), {'id': chat_id})
            return {'id': data.request_id, 'status': 'queued'}, None
        if data.interrupt_run_id and not db.execute(text('SELECT id FROM chat_runs WHERE id=:run AND conversation_id=:chat'), {'run': data.interrupt_run_id, 'chat': chat_id}).first():
            raise HTTPException(409, 'That reply is no longer available for steering.')
        context = [dict(item) for item in db.execute(text("SELECT role,content,attachment_ids FROM (SELECT sequence,role,content,attachment_ids FROM messages WHERE conversation_id=:id AND (role='user' OR status='completed') ORDER BY sequence DESC LIMIT 30) recent ORDER BY sequence"), {'id': chat_id}).mappings().all()]
        history_count = db.execute(text("SELECT count(*) FROM messages WHERE conversation_id=:id AND (role='user' OR status='completed')"), {'id': chat_id}).scalar_one()
        context.append({'role': 'user', 'content': data.content, 'attachment_ids': data.attachment_ids})
        context, _ = memory.recent_window(context)
        omitted = history_count + 1 - len(context) + sum(bool(item.get('context_truncated')) for item in context)
        reference = conversation_media.recent_image(db, chat_id=chat_id)
        prompt, needs_plan = conversation_media.intent(data.content, reference, awaiting_description=conversation_media.awaiting_description(db, chat_id=chat_id))
        if data.capability != 'auto':
            prompt, needs_plan = None, False
        use_vision = data.capability == 'vision.describe' or (data.capability == 'auto' and any(item['attachment_ids'] for item in context))
        if use_vision:
            if not any(item['attachment_ids'] for item in context):
                raise HTTPException(409, 'Attach an image before asking a vision model.')
            prompt, needs_plan = None, False
        planned_image = image_planning.candidate(db) if needs_plan else None
        capability = 'image.generate' if prompt and not needs_plan else routing.text_capability(db, data.content, data.capability, planning=needs_plan)
        if use_vision:
            capability = 'vision.describe'
        context = vision.with_images(db, chat_id, context, use_vision)
        target = routing.select(db, capability)
        if target is None:
            raise HTTPException(409, f'No verified model for {capability} is idle. Check its route in Administration, or wait for the current job.')
        claim_pool(db, target, data.request_id, principal.id)
        if not from_queue:
            consume_note(db, data)
        user_message, assistant_message = uuid4(), uuid4()
        sequence = db.execute(text('SELECT COALESCE(max(sequence),0)+1 FROM messages WHERE conversation_id=:id'), {'id': chat_id}).scalar_one()
        values = {'chat': chat_id, 'farm': principal.farm_id, 'owner': principal.id, 'sequence': sequence, 'content': data.content}
        db.execute(text("INSERT INTO messages(id,conversation_id,farm_id,owner_id,sequence,role,content,status) VALUES(:id,:chat,:farm,:owner,:sequence,'user',:content,'completed')"), values | {'id': user_message})
        db.execute(text('UPDATE messages SET attachment_ids=CAST(:attachments AS uuid[]) WHERE id=:id'), {'attachments': data.attachment_ids, 'id': user_message})
        db.execute(text("INSERT INTO messages(id,conversation_id,farm_id,owner_id,sequence,role,content,status) VALUES(:id,:chat,:farm,:owner,:sequence+1,'assistant','','running')"), values | {'id': assistant_message})
        db.execute(text('INSERT INTO chat_runs(id,farm_id,owner_id,conversation_id,target_id,user_message_id,assistant_message_id,authorization_version,session_hash) VALUES(:id,:farm,:owner,:chat,:target,:user_message,:assistant,:version,:session)'), values | {'id': data.request_id, 'target': target['id'], 'user_message': user_message, 'assistant': assistant_message, 'version': principal.authorization_version, 'session': session_hash})
        db.execute(text('UPDATE chat_runs SET capability_id=:capability,requested_capability=:requested,route_receipt=CAST(:receipt AS jsonb) WHERE id=:id'), {'id': data.request_id, 'capability': capability, 'requested': data.capability, 'receipt': json.dumps(routing.receipt(db, capability, target))})
        if needs_plan:
            image_planning.admit(db, principal, session_hash, data.request_id, target, planned_image, context, data.content, reference, message_id=assistant_message, chat_id=chat_id)
        if prompt:
            conversation_media.admit(db, principal, session_hash, target, data.request_id, prompt, shape=conversation_media.image_shape(data.content), message_id=assistant_message)
        if not prompt and not needs_plan:
            context, memory_receipt = memory.recall_context(db, data.content, chat_id, context, omitted)
            db.execute(text('UPDATE chat_runs SET memory_receipt=CAST(:receipt AS jsonb) WHERE id=:id'), {'id': data.request_id, 'receipt': json.dumps(memory_receipt)})
            context = routing.context_for(capability, context, tools='tools' in target['features'])
        db.execute(text('UPDATE conversations SET revision=revision+1,title=CASE WHEN revision=1 THEN :title ELSE title END WHERE id=:id'), {'id': chat_id, 'title': data.content[:80]})
        db.execute(text("INSERT INTO outbox(id,farm_id,owner_id,aggregate_id,aggregate_version,event_type,payload) VALUES(gen_random_uuid(),:farm,:owner,:id,1,'chat.turn.accepted',CAST(:payload AS jsonb))"), {'farm': principal.farm_id, 'owner': principal.id, 'id': data.request_id, 'payload': json.dumps({'run_id': str(data.request_id), 'target_id': str(target['id'])})})
        if from_queue:
            db.execute(text("UPDATE chat_requests SET state='dispatched',reason=NULL WHERE id=:id"), {'id': data.request_id})
    return {'id': data.request_id, 'status': 'running'}, (target, context)


def dispatch_pending(engine, settings, principal, chat_id):
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        pending = db.execute(text("SELECT * FROM chat_requests WHERE conversation_id=:id AND state='queued'"), {'id': chat_id}).mappings().one_or_none()
        if not pending:
            return
        row = conversation(db, chat_id)
    try:
        if pending['authorization_version'] != principal.authorization_version or not identity_current(engine, settings, principal, pending['session_hash']):
            raise HTTPException(401, 'The sending session ended. Sign in and send this message again.')
        data = SendTurn(request_id=pending['id'], revision=row['revision'], content=pending['content'], capability=pending['requested_capability'], attachment_ids=pending['attachment_ids'])
        _, execution = accept_turn(engine, settings, principal, pending['session_hash'], chat_id, data, from_queue=True)
        if execution:
            execute_turn(engine, settings, principal, pending['id'], *execution)
    except HTTPException as exc:
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            db.execute(text("UPDATE chat_requests SET state='blocked',reason=:reason WHERE id=:id AND state='queued'"), {'id': pending['id'], 'reason': str(exc.detail)[:500]})


@router.post('/api/v1/chats/{chat_id}/pending/{request_id}/cancel', tags=['chat'])
def cancel_pending(request: Request, chat_id: UUID, request_id: UUID):
    principal = member(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        memory.state(db, lock=True)
        conversation(db, chat_id, lock=True)
        row = db.execute(text('SELECT state FROM chat_requests WHERE id=:id AND conversation_id=:chat FOR UPDATE'), {'id': request_id, 'chat': chat_id}).mappings().one_or_none()
        if not row:
            raise HTTPException(404, 'This queued message is not available.')
        if row['state'] == 'dispatched':
            raise HTTPException(409, 'This message has started. Use Stop response instead.')
        db.execute(text("UPDATE chat_requests SET state='cancelled' WHERE id=:id"), {'id': request_id})
        db.execute(text('UPDATE conversations SET revision=revision+1 WHERE id=:id'), {'id': chat_id})
    return {'cancelled': True}


@router.post('/api/v1/chats/{chat_id}/stop', tags=['chat'])
def stop(request: Request, chat_id: UUID):
    principal = member(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        conversation(db, chat_id)
        db.execute(text("UPDATE chat_runs SET cancel_requested=true WHERE conversation_id=:id AND status='running'"), {'id': chat_id})
    return {'state': 'stopping', 'reason': 'The reply will stop updating. Its resource group stays occupied until the model finishes.'}


@router.delete('/api/v1/chats/{chat_id}', tags=['chat'])
def archive_chat(request: Request, chat_id: UUID):
    principal = member(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        memory.state(db, lock=True)
        conversation(db, chat_id, lock=True)
        reconcile(db, chat_id)
        if db.execute(text("SELECT id FROM chat_runs WHERE conversation_id=:id AND status='running'"), {'id': chat_id}).first():
            raise HTTPException(409, 'Stop the reply and wait for the model to finish before archiving.')
        db.execute(text("UPDATE chat_requests SET state='cancelled' WHERE conversation_id=:id AND state IN ('queued','blocked')"), {'id': chat_id})
        db.execute(text('DELETE FROM chat_attachments a WHERE a.conversation_id=:id AND NOT EXISTS(SELECT 1 FROM messages m WHERE a.id=ANY(m.attachment_ids))'), {'id': chat_id})
        db.execute(text('UPDATE conversations SET deleted_at=now(),revision=revision+1 WHERE id=:id'), {'id': chat_id})
    return {'archived': True}
