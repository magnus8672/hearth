"""A bounded image action and conversation-scoped publication, never model URLs.

Only a new human request may authorize the image action. Local prompt planning
can resolve references within that conversation; model text cannot grant access
to a different provider, conversation, tool or image.
"""
import json
import re
import secrets

from fastapi import HTTPException
from sqlalchemy import text

from hearth.contracts import ConversationImage, ImageGeneration

PREFIX = r"(?:(?:hey|hi|hello)[, !]+)?(?:@?hearth[, :!]+)?(?:please\s+)?(?:(?:(?:can|could|would|will) you|I(?:'d| would) like you to|I want you to)\s+)?(?:please\s+)?"
SUBJECT = r"(?:an?\s+|some\s+)?(?P<style>(?:(?:new|beautiful|photorealistic|realistic|square|landscape|portrait)\s+)*)(?P<medium>image|picture|photo|photograph|illustration|painting|drawing|artwork|logo)\b(?!\s+(?:prompt|generator|generation|tool|server|endpoint|API|tutorial|caption|description|metadata|analysis|classifier|viewer|editor|button|pipeline|workflow|model|request|dataset|recognition)\b)(?:\s+for (?:me|us))?(?:\s+(?:of|showing|depicting))?\s*[:,]?\s*(?P<description>.*)"
CREATE = re.compile(r'^' + PREFIX + r'(?:make|create|generate|render)\s+(?:(?:me|us)\s+)?' + SUBJECT + '$', re.I | re.S)
DRAW = re.compile(r'^' + PREFIX + r'(?P<verb>draw|paint|illustrate)\s+(?:(?:me|us)\s+)?(?P<description>.+)$', re.I | re.S)
WANT = re.compile(r"^(?:I(?:'d| would) (?:like|love)|I want|(?:Could|Can) I have)\s+" + SUBJECT + '$', re.I | re.S)
NEGATED = re.compile(r"\b(?:do not|don't|don’t|without)\s+(?:actually\s+)?(?:generate|create|draw|render|make|paint)\b", re.I)
REFERENCE = re.compile(r'\b(?:it|that|this|above|previous|earlier|same)\b|\b(?:we|you|I) (?:just )?(?:discussed|described|mentioned|talked about)\b', re.I)
VARIATION = re.compile(r'^' + PREFIX + r'(?:make|render|draw|create|generate|paint|turn|change)\s+(?:it|that|this|another(?: one)?|a new (?:one|version)|a variation|the (?:image|picture|photo))\b.+$', re.I | re.S)
COUNT = r'(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a dozen)'
PLURAL = re.compile(r'^' + PREFIX + r'(?:ok(?:ay)?[, ]+)?(?:make|create|generate|render|draw|paint|illustrate)\s+(?:(?:me|us)\s+)?(?:(?:the|some|a few|' + COUNT + r')\s+)?(?:different\s+)?(?:images|pictures|photos|photographs|illustrations|paintings|drawings|renders|variations)\b(?!\s+(?:prompts?|generators?|tools?|descriptions?|captions?)\b).*$', re.I | re.S)
COUNTED = re.compile(r'^' + PREFIX + r'(?:make|create|generate|render|draw|paint|illustrate)\s+(?:(?:me|us)\s+)?(?P<count>' + COUNT + r')\s+(?:different\s+)?(?P<subject>.+)$', re.I | re.S)


def image_limit(content):
    """A human request bounds the planner's batch; never infer authority from JSON."""
    count = COUNTED.fullmatch(content.strip())
    if count:
        words = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'a dozen': 12}
        value = count['count'].lower()
        number = int(value) if value.isdigit() else words[value]
        if not 1 <= number <= 4:
            raise HTTPException(422, 'Ask for between one and four images at a time. Nothing has been started.')
        return number
    return 4 if PLURAL.fullmatch(content.strip()) else 1


def image_prompt(content):
    value = content.strip()
    if NEGATED.search(value):
        return None
    match = CREATE.fullmatch(value) or DRAW.fullmatch(value) or WANT.fullmatch(value)
    if not match:
        return None
    prompt = match.group('description').strip()
    prompt = re.sub(r'[, ]+please[.!?]*$', '', prompt, flags=re.I)
    if DRAW.fullmatch(value) and re.match(r'(?:a conclusion|conclusions|a parallel|parallels|attention|on\b|from\b)', prompt, re.I):
        return None
    if not re.search(r'\w', prompt) or re.fullmatch(r'(?:it|that|this|the above|what we discussed)[.!?]*', prompt, re.I):
        raise HTTPException(422, 'Describe what you want in the picture, for example: “Make an image of a fox beside a fireplace.”')
    if len(prompt) > 1000:
        raise HTTPException(422, 'Please shorten the image description. This image model accepts up to 1,000 characters and about 60 words.')
    if match.re is DRAW:
        medium = {'draw': 'drawing', 'paint': 'painting', 'illustrate': 'illustration'}[match.group('verb').lower()]
        prompt = medium + ' of ' + prompt
    else:
        medium = match.group('medium').lower()
        style = re.sub(r'\b(?:new|square|landscape|portrait)\s*', '', match.group('style'), flags=re.I).strip()
        if medium not in {'image', 'picture'}:
            prompt = medium + ' of ' + prompt
        if style:
            prompt = style + ' ' + prompt
    if len(prompt) > 1000:
        raise HTTPException(422, 'Please shorten the image description to fit this model.')
    return prompt


def intent(content, reference=None, *, awaiting_description=False):
    """Return (direct prompt, needs local planning). No historical auto-trigger."""
    value = content.strip()
    if NEGATED.search(value):
        return None, False
    counted = COUNTED.fullmatch(value)
    if PLURAL.fullmatch(value) or (reference and counted and not re.match(r'(?:prompts?|descriptions?|sentences?|paragraphs?|bullet|lists?|ideas?|suggestions?)\b', counted['subject'], re.I)):
        image_limit(value)
        return None, True
    if awaiting_description and not re.match(r"^(?:never\s*mind|cancel|stop|forget|no\b|thanks?\b|thank you|what\b|why\b|how\b|when\b|where\b|who\b|can\b|could\b|would\b|explain\b|tell\b)", value, re.I):
        return None, True
    if reference and VARIATION.fullmatch(value):
        return None, True
    match = CREATE.fullmatch(value) or DRAW.fullmatch(value) or WANT.fullmatch(value)
    if match and match.re is DRAW and re.match(r'(?:a conclusion|conclusions|a parallel|parallels|attention|on\b|from\b)', match.group('description'), re.I):
        return None, False
    if match and REFERENCE.search(match.group('description')):
        return None, True
    try:
        return image_prompt(content), False
    except HTTPException as exc:
        if match and exc.status_code == 422:
            return None, True
        raise


def recent_image(db, *, chat_id=None, channel_id=None):
    # A short acknowledgement preserves focus. Substantive intervening text
    # does not: "make it shorter" must still revise the latest text response.
    table, field, key, value = ('messages', 'conversation_id', 'message_id', chat_id) if chat_id else ('channel_messages', 'channel_id', 'channel_message_id', channel_id)
    rows = db.execute(text(f'SELECT m.id AS message_id,m.role,m.content,i.id,i.request,i.status,i.batch_count FROM {table} m LEFT JOIN LATERAL (SELECT id,request,status,batch_count FROM conversation_images WHERE {key}=m.id ORDER BY (status=\'completed\') DESC,batch_index DESC LIMIT 1) i ON true WHERE m.{field}=:id ORDER BY m.sequence DESC LIMIT 20'), {'id': value}).mappings().all()
    # A channel's current human message has already been inserted at admission.
    if rows and rows[0]['role'] == 'user':
        rows = rows[1:]
    while rows:
        if rows[0]['role'] != 'assistant':
            return None
        image = rows[0]
        if image['id']:
            if image['status'] == 'deleted':
                return None
            if image['batch_count'] > 1:
                pictures = attachments(db, image['message_id'])
                completed = [p for p in pictures if p['status'] == 'completed']
                if len(completed) > 1:
                    return {'id': None, 'images': [{'position': p['batch_index'], 'prompt': p['request']['prompt'], 'shape': p['request']['shape']} for p in completed]}
            return {'id': str(image['id']), 'prompt': image['request']['prompt'], 'shape': image['request']['shape'], 'status': image['status']}
        if len(rows) < 2 or rows[1]['role'] != 'user' or not re.fullmatch(r'(?:thanks(?: a lot)?|thank you(?: very much)?|great|nice|lovely|perfect|excellent|looks good)[.!\s]*', rows[1]['content'].strip(), re.I):
            return None
        rows = rows[2:]
    return None


def awaiting_description(db, *, chat_id=None, channel_id=None):
    table, field, value = ('messages', 'conversation_id', chat_id) if chat_id else ('channel_messages', 'channel_id', channel_id)
    row = db.execute(text(f"SELECT generation_phase,status FROM {table} WHERE {field}=:id AND role='assistant' ORDER BY sequence DESC LIMIT 1"), {'id': value}).mappings().one_or_none()
    return bool(row and row['generation_phase'] == 'image_planning' and row['status'] == 'completed')


def image_shape(content):
    match = CREATE.fullmatch(content.strip()) or WANT.fullmatch(content.strip())
    if match:
        orientation = re.search(r'\b(square|landscape|portrait)\b', match.group('style'), re.I)
        if orientation:
            return orientation.group(1).lower()
    return 'square'


def admit(db, principal, session_hash, target, run_id, prompt, *, shape='square', negative_prompt='', planning_model=None, source_image_id=None, message_id=None, channel_message_id=None, channel_id=None, batch_run_id=None, batch_index=1, batch_count=1):
    workspace = db.execute(text('SELECT id FROM workspaces')).scalar_one()
    # Serialize the quota without taking workspace/target locks in opposite order
    # to the standalone image endpoint. The target pool is already locked.
    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner,7))'), {'owner': str(principal.id)})
    if db.execute(text('SELECT count(*) FROM image_jobs WHERE deleted_at IS NULL')).scalar_one() >= 100:
        raise HTTPException(409, 'This workspace supports 100 image jobs in this build.')
    if target['protocol'] != 'hearth.image.v1' or shape not in target['profile'].get('shapes', []) or 20 not in target['profile'].get('steps', []):
        raise HTTPException(409, 'The selected image provider needs verification for chat images.')
    data = ImageGeneration(id=run_id, model=target['model_id'], prompt=prompt, negative_prompt=negative_prompt, shape=shape, seed=secrets.randbits(32))
    values = {'id': run_id, 'farm': principal.farm_id, 'owner': principal.id, 'workspace': workspace,
              'target': target['id'], 'request': json.dumps(data.model_dump(mode='json')), 'channel': channel_id,
              'session': session_hash, 'version': principal.authorization_version, 'message': message_id, 'channel_message': channel_message_id}
    db.execute(text('INSERT INTO image_jobs(id,farm_id,owner_id,workspace_id,target_id,request,session_hash,authorization_version,channel_id) VALUES(:id,:farm,:owner,:workspace,:target,CAST(:request AS jsonb),:session,:version,:channel)'), values)
    db.execute(text('INSERT INTO conversation_images(id,farm_id,owner_id,message_id,channel_message_id,channel_id,request,batch_index,batch_count,batch_run_id) VALUES(:id,:farm,:owner,:message,:channel_message,:channel,CAST(:request AS jsonb),:position,:count,:parent)'), values | {'position': batch_index, 'count': batch_count, 'parent': batch_run_id})
    db.execute(text('UPDATE conversation_images SET planning_model=:model,source_image_id=:source,variation=:variation WHERE id=:id'), {'id': run_id, 'model': planning_model, 'source': source_image_id, 'variation': source_image_id is not None})
    if batch_run_id:
        db.execute(text("UPDATE image_jobs SET batch_run_id=:parent,status='queued' WHERE id=:id"), {'id': run_id, 'parent': batch_run_id})
        db.execute(text("UPDATE conversation_images SET batch_run_id=:parent,batch_index=:position,batch_count=:count,status='queued' WHERE id=:id"), {'id': run_id, 'parent': batch_run_id, 'position': batch_index, 'count': batch_count})
    table = 'channel_messages' if channel_id else 'messages'
    db.execute(text(f"UPDATE {table} SET generation_phase='image_rendering',phase_changed_at=now(),content='' WHERE id=:id"), {'id': channel_message_id or message_id})
    return data


def attachment(db, message_id):
    items = attachments(db, message_id)
    return items[0] if items else None


def attachments(db, message_id):
    rows = db.execute(text('SELECT request,status,progress,reason,sha256,planning_model,source_image_id,variation,batch_index,batch_count FROM conversation_images WHERE message_id=:id OR channel_message_id=:id ORDER BY batch_index'), {'id': message_id}).mappings().all()
    return [ConversationImage.model_validate(dict(row)).model_dump(mode='json') for row in rows]


def published(db, message_id):
    items = attachments(db, message_id)
    return {'image': items[0] if items else None, 'images': items}


def active(db, run_id):
    """Standalone jobs have no conversation gate; linked jobs must remain active."""
    parent = db.execute(text('SELECT batch_run_id FROM image_jobs WHERE id=:id'), {'id': run_id}).scalar_one_or_none()
    run_id = parent or run_id
    private = db.execute(text('SELECT status,cancel_requested FROM chat_runs WHERE id=:id'), {'id': run_id}).mappings().one_or_none()
    if private:
        return private['status'] == 'running' and not private['cancel_requested']
    channel = db.execute(text('SELECT assistant_message_id FROM channel_runs WHERE id=:id'), {'id': run_id}).scalar_one_or_none()
    if channel:
        # RLS removes the message when the requesting member leaves.
        return bool(db.execute(text("SELECT id FROM channel_messages WHERE id=:id AND status='running'"), {'id': channel}).first())
    return True


def progress(db, run_id, value):
    db.execute(text("UPDATE conversation_images SET progress=:value WHERE id=:id AND status='running'"), {'id': run_id, 'value': value})


def finish(db, run_id, state, reason, metadata, artifact):
    """Commit the run, its message, and any published PNG together."""
    values = {'id': run_id, 'status': state, 'reason': reason, 'sha': metadata.get('sha256') if metadata else None,
              'image': artifact if state == 'completed' else None}
    db.execute(text("UPDATE conversation_images SET status=:status,reason=:reason,sha256=:sha,image=:image WHERE id=:id AND status='running'"), values)
    if db.execute(text('SELECT batch_run_id FROM image_jobs WHERE id=:id'), {'id': run_id}).scalar_one_or_none():
        return  # The batch coordinator settles its parent after all children.
    caption = 'Generated image (description only; image pixels are not included in the text model context): ' + (db.execute(text("SELECT request->>'prompt' FROM image_jobs WHERE id=:id"), {'id': run_id}).scalar_one()) if state == 'completed' else ''
    db.execute(text("UPDATE messages SET status=:status,content=:content WHERE id=(SELECT assistant_message_id FROM chat_runs WHERE id=:id) AND status='running'"), values | {'content': caption})
    db.execute(text("UPDATE chat_runs SET status=:status,reason=:reason,finished_at=now() WHERE id=:id AND status='running'"), values)
    db.execute(text("UPDATE outbox SET delivered_at=now() WHERE aggregate_id=:id AND event_type='chat.turn.accepted'"), values)
    db.execute(text("UPDATE channel_messages SET status=:status,content=:content,reason=:reason WHERE id=(SELECT assistant_message_id FROM channel_runs WHERE id=:id) AND status='running'"), values | {'content': caption})
    db.execute(text("UPDATE channel_runs SET status=:status,finished_at=now() WHERE id=:id AND status='running'"), values)
    db.execute(text("UPDATE image_plans SET status=:status,reason=:reason,updated_at=now() WHERE id=:id AND status='rendering'"), values)


def interrupt(db, run_id, reason):
    db.execute(text("UPDATE conversation_images SET status='interrupted',reason=:reason WHERE (id=:id OR batch_run_id=:id) AND status IN ('queued','running')"), {'id': run_id, 'reason': reason})
    db.execute(text("UPDATE image_jobs SET status='interrupted',reason=:reason,finished_at=now() WHERE batch_run_id=:id AND status IN ('queued','running')"), {'id': run_id, 'reason': reason})
    db.execute(text("UPDATE image_plans SET status='interrupted',reason=:reason,updated_at=now() WHERE id=:id AND status IN ('planning','handoff','rendering')"), {'id': run_id, 'reason': reason})
