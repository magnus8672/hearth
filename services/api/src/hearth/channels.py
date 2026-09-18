"""Joined farm rooms. Only an explicit mention in a new human post dispatches AI."""
import json
import re
import time
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text

from hearth import channel_attachments, conversation_media, image_planning, routing
from hearth.chat import identity_current, member, session_current
from hearth.database import scoped_session
from hearth.inference import ProviderError, chat_stream
from hearth.provider_health import record_failure
from hearth.providers import claim_pool, credential_for, release_pool, target_record, transport_settings

router = APIRouter()
router.include_router(channel_attachments.router)
MENTION = re.compile(r'(?<![\w@])@hearth(?![\w-]|\.[\w])', re.IGNORECASE)


class CreateChannel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80, pattern=r'^[\w -]+$')


class ChannelPost(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: UUID
    content: str = Field(default='', max_length=4000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=4)

    @model_validator(mode='after')
    def valid_message(self):
        if not self.content and not self.attachment_ids:
            raise ValueError('Write a message or attach an image.')
        if len(set(self.attachment_ids)) != len(self.attachment_ids):
            raise ValueError('Attach each image only once per message.')
        return self


def is_joined(db, channel_id):
    return db.execute(text('SELECT EXISTS(SELECT 1 FROM channel_memberships WHERE channel_id=:id)'), {'id': channel_id}).scalar_one()


def room(db, channel_id, *, joined=True, lock=False):
    row = db.execute(text('SELECT id,name,revision FROM channels WHERE id=:id' + (' FOR UPDATE' if lock else '')), {'id': channel_id}).mappings().one_or_none()
    if not row or joined and not is_joined(db, channel_id):
        raise HTTPException(404, 'Join this channel to open its conversation.')
    return dict(row)


@router.get('/api/v1/channels', tags=['channels'])
def list_channels(request: Request):
    principal = member(request, permission='channel.use')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        rows = db.execute(text('SELECT c.id,c.name,EXISTS(SELECT 1 FROM channel_memberships m WHERE m.channel_id=c.id) AS joined FROM channels c ORDER BY c.name')).mappings().all()
    return {'items': [dict(row) for row in rows]}


@router.post('/api/v1/channels', tags=['channels'], status_code=201)
def create_channel(request: Request, data: CreateChannel):
    principal = member(request, mutation=True, permission='channel.use')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:farm,1))'), {'farm': str(principal.farm_id)})
        if db.execute(text('SELECT count(*) FROM channels')).scalar_one() >= 100:
            raise HTTPException(409, 'This farm supports up to 100 shared channels.')
        if db.execute(text('SELECT id FROM channels WHERE name=:name'), {'name': data.name}).first():
            raise HTTPException(409, 'A channel with this name already exists. Join it from the list.')
        channel_id = uuid4()
        values = {'id': channel_id, 'farm': principal.farm_id, 'owner': principal.id, 'name': data.name}
        db.execute(text('INSERT INTO channels(id,farm_id,creator_id,name) VALUES(:id,:farm,:owner,:name)'), values)
        db.execute(text('INSERT INTO channel_memberships(channel_id,farm_id,owner_id) VALUES(:id,:farm,:owner)'), values)
    return {'id': channel_id, 'name': data.name, 'joined': True}


@router.post('/api/v1/channels/{channel_id}/join', tags=['channels'])
def join(request: Request, channel_id: UUID):
    principal = member(request, mutation=True, permission='channel.use')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        room(db, channel_id, joined=False, lock=True)
        db.execute(text('INSERT INTO channel_memberships(channel_id,farm_id,owner_id) VALUES(:id,:farm,:owner) ON CONFLICT DO NOTHING'), {'id': channel_id, 'farm': principal.farm_id, 'owner': principal.id})
    return {'joined': True}


@router.post('/api/v1/channels/{channel_id}/leave', tags=['channels'])
def leave(request: Request, channel_id: UUID):
    principal = member(request, mutation=True, permission='channel.use')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        room(db, channel_id, lock=True)
        # Save the visible cancellation before removing the membership that
        # authorizes channel-message writes. The executor still drains its job.
        db.execute(text("UPDATE channel_messages SET status='cancelled',reason='The person who requested this reply left the channel.' WHERE channel_id=:id AND author_id=:owner AND status='running'"), {'id': channel_id, 'owner': principal.id})
        db.execute(text("UPDATE conversation_images SET status='cancelled',reason='The person who requested this image left the channel.' WHERE channel_id=:id AND owner_id=:owner AND status IN ('queued','running')"), {'id': channel_id, 'owner': principal.id})
        db.execute(text('DELETE FROM channel_attachments WHERE channel_id=:id AND message_id IS NULL'), {'id': channel_id})
        db.execute(text('DELETE FROM channel_memberships WHERE channel_id=:id'), {'id': channel_id})
    return {'joined': False}


@router.get('/api/v1/channels/{channel_id}', tags=['channels'])
def read_channel(request: Request, channel_id: UUID):
    principal = member(request, permission='channel.use')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        result = room(db, channel_id)
        # Any current participant may reconcile public output after a lost
        # execution, but cannot replay another user's prompt or clear its pool.
        stale = db.execute(text("SELECT m.id,m.request_id,t.resource_pool_id,m.generation_phase FROM channel_messages m JOIN inference_targets t ON t.id=m.target_id JOIN provider_pools p ON p.id=t.resource_pool_id WHERE m.channel_id=:id AND m.status='running' AND NOT EXISTS(SELECT 1 FROM capability_queue q WHERE q.id=m.request_id AND q.state='queued') AND ((m.generation_phase<>'image_handoff' AND (p.active_run_id IS DISTINCT FROM m.request_id OR p.lease_until<now())) OR (m.generation_phase='image_handoff' AND m.phase_changed_at<now()-interval '60 seconds'))"), {'id': channel_id}).mappings().all()
        for item in stale:
            conversation_media.interrupt(db, item['request_id'], 'Image generation was interrupted. Check the provider before retrying.')
            db.execute(text("UPDATE channel_messages SET status='interrupted',reason='Execution was interrupted. Check the model server before asking again.' WHERE id=:id AND status='running'"), {'id': item['id']})
            if item['generation_phase'] != 'image_handoff':
                release_pool(db, item['resource_pool_id'], item['request_id'], uncertain=True)
        rows = db.execute(text('SELECT id,sequence,role,display_name,content,status,reason,created_at,author_id,request_id,generation_phase,model_id FROM channel_messages WHERE channel_id=:id ORDER BY sequence DESC LIMIT 100'), {'id': channel_id}).mappings().all()
        return result | {'unused_attachments': channel_attachments.metadata(db, channel_id, owner_id=principal.id), 'messages': [dict(row) | conversation_media.published(db, row['id']) | {'attachments': channel_attachments.metadata(db, channel_id, message_id=row['id']), 'can_stop': row['role'] == 'assistant' and row['status'] == 'running' and row['author_id'] == principal.id} for row in reversed(rows)]}


@router.post('/api/v1/channels/{channel_id}/runs/{run_id}/stop', tags=['channels'])
def stop(request: Request, channel_id: UUID, run_id: UUID):
    principal = member(request, mutation=True, permission='channel.use')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        room(db, channel_id, lock=True)
        run = db.execute(text('SELECT assistant_message_id FROM channel_runs WHERE id=:id AND channel_id=:channel'), {'id': run_id, 'channel': channel_id}).scalar_one_or_none()
        if run is None:
            raise HTTPException(404, 'Only the person who requested this response can stop it.')
        db.execute(text("UPDATE channel_messages SET status='cancelled',reason='Response stopped. Waiting for the provider to release its resource group.' WHERE id=:id AND status='running'"), {'id': run})
        db.execute(text("UPDATE conversation_images SET status='cancelled',reason='Image stopped. Waiting for the provider to finish cancelling.' WHERE (id=:id OR batch_run_id=:id) AND status IN ('queued','running')"), {'id': run_id})
    return {'stopping': True}


@router.post('/api/v1/channels/{channel_id}/messages', tags=['channels'], status_code=201)
def post(request: Request, channel_id: UUID, data: ChannelPost):
    principal = member(request, mutation=True, permission='channel.use')
    engine, settings = request.app.state.engine, request.app.state.settings
    target, context, assistant_id = None, [], None
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        room(db, channel_id, lock=True)
        existing = db.execute(text("SELECT id,author_id,content FROM channel_messages WHERE channel_id=:channel AND request_id=:request AND role='user'"), {'channel': channel_id, 'request': data.request_id}).mappings().one_or_none()
        if existing:
            saved_ids = [row['id'] for row in channel_attachments.metadata(db, channel_id, message_id=existing['id'])]
            if existing['author_id'] != principal.id or existing['content'] != data.content or saved_ids != data.attachment_ids:
                raise HTTPException(409, 'This message identifier was already used.')
            return {'id': existing['id'], 'saved': True}
        seq = db.execute(text('SELECT COALESCE(max(sequence),0)+1 FROM channel_messages WHERE channel_id=:id'), {'id': channel_id}).scalar_one()
        if seq > 20000:
            raise HTTPException(409, 'This channel reached this build’s history limit. Create another channel.')
        name = db.execute(text('SELECT display_name FROM users WHERE id=:id'), {'id': principal.id}).scalar_one()
        message_id = uuid4()
        values = {'id': message_id, 'channel': channel_id, 'farm': principal.farm_id, 'owner': principal.id,
                  'name': name[:200], 'sequence': seq, 'content': data.content, 'request': data.request_id}
        db.execute(text("INSERT INTO channel_messages(id,channel_id,farm_id,author_id,display_name,sequence,role,content,status,request_id) VALUES(:id,:channel,:farm,:owner,:name,:sequence,'user',:content,'completed',:request)"), values)
        channel_attachments.publish(db, channel_id, principal.id, message_id, data.attachment_ids)
        if MENTION.search(data.content):
            request_text = MENTION.sub('', data.content).strip(' ,:')
            reference = conversation_media.recent_image(db, channel_id=channel_id)
            prompt, needs_plan = conversation_media.intent(request_text, reference, awaiting_description=conversation_media.awaiting_description(db, channel_id=channel_id))
            planned_image, route_problem = None, None
            if needs_plan:
                try:
                    planned_image = image_planning.candidate(db)
                except HTTPException as exc:
                    route_problem = str(exc.detail)
            rows = db.execute(text("SELECT id,role,display_name,content FROM channel_messages WHERE channel_id=:id AND status='completed' ORDER BY sequence DESC LIMIT 20"), {'id': channel_id}).mappings().all()
            # Each human speaker remains data within a user message. A display
            # name or message can never choose an OIDC identity or tool role.
            budget = 0
            for row in rows:
                content = row['content'] if row['role'] == 'assistant' else json.dumps({'speaker': row['display_name'], 'message': row['content']}, ensure_ascii=False)
                budget += len(content.encode('utf-8'))
                if budget > 16000:
                    break
                has_pictures = db.execute(text('SELECT EXISTS(SELECT 1 FROM channel_attachments WHERE message_id=:id)'), {'id': row['id']}).scalar_one()
                if has_pictures:
                    content += '\n[Shared image attached. Pixels are not included in channel chat; do not claim to see it.]'
                context.insert(0, {'role': row['role'], 'content': content})
            capability = 'image.generate' if prompt and not needs_plan else routing.text_capability(db, MENTION.sub('', data.content).strip(' ,:'), planning=needs_plan)
            target = None if route_problem else routing.select(db, capability, queued=capability == 'image.generate')
            assistant_id = uuid4()
            reason = None if target and context else f'No verified {"image" if prompt else "prompt-planning" if needs_plan else "chat"} model is idle. Your message is saved. Mention @hearth again when a model is available.'
            if route_problem:
                reason = route_problem + ' Your message is saved.'
            if not context:
                target = None
            if target and capability != 'image.generate':
                claim_pool(db, target, data.request_id, principal.id)
            db.execute(text("INSERT INTO channel_messages(id,channel_id,farm_id,author_id,display_name,sequence,role,content,status,request_id,target_id,reason,model_id) VALUES(:id,:channel,:farm,:owner,'hearth',:sequence+1,'assistant','',:status,:request,:target,:reason,:model)"), values | {'id': assistant_id, 'status': 'running' if target else 'failed', 'target': target['id'] if target else None, 'reason': reason, 'model': target['model_id'] if target else None})
            if target:
                db.execute(text('INSERT INTO channel_runs(id,farm_id,owner_id,channel_id,assistant_message_id,target_id,session_hash,authorization_version) VALUES(:request,:farm,:owner,:channel,:assistant,:target,:session,:version)'), values | {'assistant': assistant_id, 'target': target['id'], 'session': request.state.identity['token_hash'], 'version': principal.authorization_version})
                db.execute(text('UPDATE channel_runs SET capability_id=:capability,route_receipt=CAST(:receipt AS jsonb) WHERE id=:id'), {'id': data.request_id, 'capability': capability, 'receipt': json.dumps(routing.receipt(db, capability, target))})
                if needs_plan:
                    image_planning.admit(db, principal, request.state.identity['token_hash'], data.request_id, target, planned_image, context, request_text, reference, message_id=assistant_id, channel_id=channel_id)
                if prompt:
                    conversation_media.admit(db, principal, request.state.identity['token_hash'], target, data.request_id, prompt, shape=conversation_media.image_shape(MENTION.sub('', data.content).strip(' ,:')), channel_message_id=assistant_id, channel_id=channel_id)
                if not prompt and not needs_plan:
                    context = routing.context_for(capability, context)
        db.execute(text('UPDATE channels SET revision=revision+1 WHERE id=:id'), {'id': channel_id})
    if target and target['protocol'] != 'hearth.image.v1':
        request.app.state.inference_executor.submit(execute, engine, settings, principal, data.request_id, target, context)
    return {'id': message_id, 'saved': True, 'assistant_requested': assistant_id is not None}


def execute(engine, settings, principal, run_id, target, context):
    if image_planning.run_if_planned(engine, settings, principal, run_id, target):
        return
    if target['protocol'] == 'hearth.image.v1':
        from hearth import images
        from hearth.contracts import ImageGeneration
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            payload = db.execute(text('SELECT request FROM image_jobs WHERE id=:id'), {'id': run_id}).scalar_one()
        images.execute(engine, settings, principal, target, ImageGeneration.model_validate(payload))
        return
    answer, stopped, finished, problem = '', False, None, None
    last_write, last_identity = 0.0, 0.0
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        run = dict(db.execute(text('SELECT * FROM channel_runs WHERE id=:id'), {'id': run_id}).mappings().one())
    try:
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            current = target_record(db, target['id'])
            active_message = db.execute(text("SELECT id FROM channel_messages WHERE id=:id AND status='running'"), {'id': run['assistant_message_id']}).first()
            if (not active_message or not is_joined(db, run['channel_id']) or not session_current(db, principal, run['session_hash'])
                    or current['active_run_id'] != run_id or current['revision'] != target['revision'] or current['state'] != 'ready'):
                raise ProviderError('The session, channel or model changed before generation.', provider_fault=False)
        if not identity_current(engine, settings, principal, run['session_hash']):
            raise ProviderError('The sending session ended before generation.', provider_fault=False)
        last_identity = time.monotonic()
        for kind, value in chat_stream(target['base_url'], credential_for(target, settings), target['model_id'], context, transport_settings(target, settings)):
            if kind == 'text' and not stopped:
                answer += value
            if kind == 'done':
                finished = value
            if time.monotonic() - last_write < .15 and not finished:
                continue
            if not stopped and (time.monotonic() - last_identity > 5 or finished):
                stopped = not identity_current(engine, settings, principal, run['session_hash'])
                last_identity = time.monotonic()
            with scoped_session(engine, principal.id, principal.farm_id) as db:
                current = target_record(db, target['id'])
                joined = is_joined(db, run['channel_id'])
                active_message = db.execute(text("SELECT id FROM channel_messages WHERE id=:id AND status='running'"), {'id': run['assistant_message_id']}).first()
                stopped = stopped or not joined or not active_message or not session_current(db, principal, run['session_hash']) or current['active_run_id'] != run_id or current['revision'] != target['revision'] or current['state'] != 'ready'
                if not stopped:
                    db.execute(text("UPDATE channel_messages SET content=:content WHERE id=:id AND status='running'"), {'id': run['assistant_message_id'], 'content': answer})
                db.execute(text("UPDATE provider_pools SET lease_until=now()+interval '240 seconds' WHERE id=:pool AND active_run_id=:run"), {'pool': target['resource_pool_id'], 'run': run_id})
            last_write = time.monotonic()
        if not finished:
            raise ProviderError('The stream ended without a completion receipt.', uncertain=True)
    except ProviderError as exc:
        problem = exc
    except Exception:
        problem = ProviderError('The channel reply was interrupted. Check the model server.', uncertain=True)
    with scoped_session(engine, principal.id, principal.farm_id) as db:
        current = target_record(db, target['id'])
        if current['active_run_id'] != run_id:
            return
        stopped = stopped or not is_joined(db, run['channel_id']) or not session_current(db, principal, run['session_hash']) or current['revision'] != target['revision'] or current['state'] != 'ready'
        status = ('interrupted' if problem.uncertain else 'failed') if problem else ('cancelled' if stopped else 'completed')
        reason = str(problem) if problem else ('The sending session or channel membership ended.' if stopped else 'This reply reached the model output limit and may be incomplete. Ask @hearth to continue.' if finished == 'length' else None)
        db.execute(text("UPDATE channel_messages SET status=:status,reason=:reason WHERE id=:id AND status='running'"), {'id': run['assistant_message_id'], 'status': status, 'reason': reason})
        db.execute(text('UPDATE channel_runs SET status=:status,finished_at=now() WHERE id=:id'), {'id': run_id, 'status': status})
        record_failure(db, target, problem)
        release_pool(db, target['resource_pool_id'], run_id, uncertain=bool(problem and problem.uncertain))
