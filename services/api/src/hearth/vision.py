"""Bounded private image inputs and an actual pixel-reading verification probe."""
import base64
import io
import re
import secrets
import warnings
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from sqlalchemy import text

from hearth.database import scoped_session
from hearth.inference import ProviderError, chat_stream

router = APIRouter()
UPLOAD_LIMIT = 8_388_608


def normalize_image(raw):
    if not raw or len(raw) > UPLOAD_LIMIT:
        raise HTTPException(413, 'Choose an image smaller than 8 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in {'PNG', 'JPEG', 'WEBP'} or getattr(source, 'n_frames', 1) != 1:
                    raise ValueError()
                if source.width * source.height > 20_000_000:
                    raise ValueError()
                source.load()
                source = ImageOps.exif_transpose(source).convert('RGBA')
                source.thumbnail((1600, 1600))
                canvas = Image.new('RGB', source.size, 'white')
                canvas.paste(source, mask=source.getchannel('A'))
                output = io.BytesIO()
                canvas.save(output, format='JPEG', quality=92)
                result = output.getvalue()
                if len(result) > 3_145_728:
                    raise ValueError()
                return result, canvas.width, canvas.height
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(400, 'Use a still PNG, JPEG or WebP image up to 20 megapixels. Images are resized to 1600 pixels and metadata is removed.') from None


def image_part(raw):
    return {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(raw).decode()}}


def metadata(db, chat_id, ids):
    result = []
    for attachment_id in ids:
        row = db.execute(text('SELECT id,width,height,media_type,octet_length(image) AS byte_count FROM chat_attachments WHERE id=:id AND conversation_id=:chat'), {'id': attachment_id, 'chat': chat_id}).mappings().one_or_none()
        if row is None:
            raise HTTPException(404, 'This attachment is not available in this conversation.')
        result.append(dict(row))
    return result


def unused(db, chat_id):
    rows = db.execute(text("SELECT a.id FROM chat_attachments a WHERE a.conversation_id=:chat AND NOT EXISTS(SELECT 1 FROM messages m WHERE a.id=ANY(m.attachment_ids)) AND NOT EXISTS(SELECT 1 FROM chat_requests r WHERE a.id=ANY(r.attachment_ids) AND r.state IN ('queued','blocked')) ORDER BY a.created_at"), {'chat': chat_id}).scalars().all()
    return metadata(db, chat_id, rows)


def with_images(db, chat_id, messages, enabled):
    if sum(len(item['attachment_ids']) for item in messages) > 4 and enabled:
        raise HTTPException(409, 'This vision conversation supports four image references. Start a new conversation to use more images.')
    context = []
    for item in messages:
        content = item['content']
        if item['attachment_ids']:
            if enabled:
                content = [{'type': 'text', 'text': content}]
                for attachment in item['attachment_ids']:
                    raw = db.execute(text('SELECT image FROM chat_attachments WHERE id=:id AND conversation_id=:chat'), {'id': attachment, 'chat': chat_id}).scalar_one_or_none()
                    if raw is None:
                        raise HTTPException(404, 'This attachment is not available in this conversation.')
                    content.append(image_part(bytes(raw)))
            else:
                content += '\n[Image attached. Its pixels are not included for this text-only specialist.]'
        context.append({'role': item['role'], 'content': content})
    return context


def probe(base_url, credential, model_id, settings):
    number = ''.join(str(secrets.randbelow(10)) for _ in range(6))
    picture = Image.new('RGB', (640, 180), 'white')
    ImageDraw.Draw(picture).text((70, 45), number, font=ImageFont.load_default(size=80), fill='black')
    data = io.BytesIO()
    picture.save(data, 'JPEG')
    answer, finished = '', None
    # The challenge answer exists only in pixels, never in the text prompt.
    context = [{'role': 'user', 'content': [{'type': 'text', 'text': 'Read the six digits in this image. Reply only with those six digits.'}, image_part(data.getvalue())]}]
    for kind, value in chat_stream(base_url, credential, model_id, context, settings, maximum_tokens=4096):
        if kind == 'text':
            answer += value
        elif kind == 'done':
            finished = value
    if finished != 'stop' or re.sub(r'\s', '', answer) != number:
        raise ProviderError('The model did not pass the image-reading check.')
    return {'vision_probe': 'pixel-digits.v1', 'maximum_images': 4, 'maximum_image_edge': 1600}


@router.post('/api/v1/chats/{chat_id}/attachments', tags=['chat'], status_code=201)
async def upload(request: Request, chat_id: UUID):
    from hearth.chat import conversation, member
    principal = member(request, mutation=True)
    # Authorize the conversation before decoding untrusted image content.
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        conversation(db, chat_id)
    raw, width, height = normalize_image(await request.body())
    attachment_id = uuid4()
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        conversation(db, chat_id, lock=True)
        if len(unused(db, chat_id)) >= 4:
            raise HTTPException(409, 'Send or remove the four attached images before adding more.')
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner,9))'), {'owner': str(principal.id)})
        count, size = db.execute(text('SELECT count(*),COALESCE(sum(octet_length(image)),0) FROM chat_attachments')).one()
        if count >= 100 or size + len(raw) > 134_217_728:
            raise HTTPException(409, 'Your image attachment storage is full. Remove unused attachments before uploading more.')
        db.execute(text("INSERT INTO chat_attachments(id,farm_id,owner_id,conversation_id,image,media_type,width,height) VALUES(:id,:farm,:owner,:chat,:image,'image/jpeg',:width,:height)"),
                   {'id': attachment_id, 'farm': principal.farm_id, 'owner': principal.id, 'chat': chat_id, 'image': raw, 'width': width, 'height': height})
        return metadata(db, chat_id, [attachment_id])[0]


@router.get('/api/v1/chats/{chat_id}/attachments/{attachment_id}', tags=['chat'])
def download(request: Request, chat_id: UUID, attachment_id: UUID):
    from hearth.chat import conversation, member
    principal = member(request)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        conversation(db, chat_id)
        raw = db.execute(text('SELECT image FROM chat_attachments WHERE id=:id AND conversation_id=:chat'), {'id': attachment_id, 'chat': chat_id}).scalar_one_or_none()
        if raw is None:
            raise HTTPException(404, 'This attachment is not available in this conversation.')
    return Response(bytes(raw), media_type='image/jpeg', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Disposition': 'inline; filename="hearth-attachment.jpg"'})


@router.delete('/api/v1/chats/{chat_id}/attachments/{attachment_id}', tags=['chat'])
def discard(request: Request, chat_id: UUID, attachment_id: UUID):
    from hearth.chat import conversation, member
    principal = member(request, mutation=True)
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        conversation(db, chat_id, lock=True)
        metadata(db, chat_id, [attachment_id])
        for table in ['messages', 'chat_requests']:
            condition = " AND state IN ('queued','blocked')" if table == 'chat_requests' else ''
            if db.execute(text(f'SELECT 1 FROM {table} WHERE :id=ANY(attachment_ids){condition} LIMIT 1'), {'id': attachment_id}).first():
                raise HTTPException(409, 'This image is part of a saved message and cannot be removed separately.')
        db.execute(text('DELETE FROM chat_attachments WHERE id=:id'), {'id': attachment_id})
    return {'deleted': True}
