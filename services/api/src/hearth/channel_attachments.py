"""Bounded channel image drafts, shared only by an explicit message submission."""
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import text

from hearth import vision
from hearth.chat import member
from hearth.database import scoped_session

router = APIRouter()


def metadata(db, channel_id, *, message_id=None, owner_id=None):
    condition = 'message_id=:message' if message_id else 'message_id IS NULL AND owner_id=:owner'
    return [dict(row) for row in db.execute(text(f'SELECT id,width,height,media_type,octet_length(image) AS byte_count FROM channel_attachments WHERE channel_id=:channel AND {condition} ORDER BY position,created_at,id'),
        {'channel': channel_id, 'message': message_id, 'owner': owner_id}).mappings()]


def publish(db, channel_id, owner_id, message_id, ids):
    for position, attachment_id in enumerate(ids):
        result = db.execute(text('UPDATE channel_attachments SET message_id=:message,position=:position WHERE id=:id AND channel_id=:channel AND owner_id=:owner AND message_id IS NULL'),
            {'id': attachment_id, 'channel': channel_id, 'owner': owner_id, 'message': message_id, 'position': position})
        if result.rowcount != 1:
            raise HTTPException(404, 'This image is not an unused attachment in your channel draft.')


@router.post('/api/v1/channels/{channel_id}/attachments', tags=['channels'], status_code=201)
async def upload(request: Request, channel_id: UUID):
    from hearth.channels import room
    principal = member(request, mutation=True, permission='channel.use')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        room(db, channel_id)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > vision.UPLOAD_LIMIT:
            raise HTTPException(413, 'Choose an image smaller than 8 MB.')
    raw, width, height = vision.normalize_image(bytes(body))
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        room(db, channel_id, lock=True)
        if len(metadata(db, channel_id, owner_id=principal.id)) >= 4:
            raise HTTPException(409, 'Send or remove the four attached images before adding more.')
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:owner,10))'), {'owner': str(principal.id)})
        count, size = db.execute(text('SELECT count(*),COALESCE(sum(octet_length(image)),0) FROM channel_attachments WHERE owner_id=:owner'), {'owner': principal.id}).one()
        if count >= 1000 or size + len(raw) > 134_217_728:
            raise HTTPException(409, 'Your channel image storage is full. Remove unused attachments before uploading more.')
        attachment_id = uuid4()
        db.execute(text('INSERT INTO channel_attachments(id,farm_id,channel_id,owner_id,image,width,height) VALUES(:id,:farm,:channel,:owner,:image,:width,:height)'),
            {'id': attachment_id, 'farm': principal.farm_id, 'channel': channel_id, 'owner': principal.id, 'image': raw, 'width': width, 'height': height})
    return {'id': attachment_id, 'width': width, 'height': height, 'media_type': 'image/jpeg', 'byte_count': len(raw)}


@router.get('/api/v1/channels/{channel_id}/attachments/{attachment_id}', tags=['channels'])
def download(request: Request, channel_id: UUID, attachment_id: UUID):
    from hearth.channels import room
    principal = member(request, permission='channel.use')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        room(db, channel_id)
        raw = db.execute(text('SELECT image FROM channel_attachments WHERE id=:id AND channel_id=:channel'), {'id': attachment_id, 'channel': channel_id}).scalar_one_or_none()
        if raw is None:
            raise HTTPException(404, 'This channel image is no longer available to you.')
    return Response(bytes(raw), media_type='image/jpeg', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Disposition': 'inline; filename="hearth-channel-image.jpg"'})


@router.delete('/api/v1/channels/{channel_id}/attachments/{attachment_id}', tags=['channels'])
def discard(request: Request, channel_id: UUID, attachment_id: UUID):
    from hearth.channels import room
    principal = member(request, mutation=True, permission='channel.use')
    with scoped_session(request.app.state.engine, principal.id, principal.farm_id) as db:
        room(db, channel_id, lock=True)
        result = db.execute(text('DELETE FROM channel_attachments WHERE id=:id AND channel_id=:channel AND owner_id=:owner AND message_id IS NULL'), {'id': attachment_id, 'channel': channel_id, 'owner': principal.id})
        if result.rowcount != 1:
            raise HTTPException(404, 'Only your unused channel attachments can be removed.')
    return {'deleted': True}
